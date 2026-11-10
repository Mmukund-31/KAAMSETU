import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { HandoverDetail } from "../types/api";
import { page, renderApp, signedIn } from "./harness";

function handover(overrides: Partial<HandoverDetail> = {}): HandoverDetail {
  return {
    id: "h-1",
    site_id: "site-1",
    shift_identifier: "2026-11-10 A",
    status: "submitted",
    created_by: { id: "u-t1", name: "Ravi Kumar" },
    created_at: "2026-11-10T14:00:00Z",
    original_notes: "M-204 vibration kam hua. Next shift bearing check karna hai.",
    detected_language: null,
    generated_summary: {
      window_hours: 12,
      counts: { completed: 1, pending: 1, blocked: 0, awaiting_approval: 0 },
      completed: [{ id: "wo-1", number: "WO-1008", equipment_code: "M-204", status: "closed", priority: "high", assignee: "Lakshmi" }],
      pending: [],
      blocked: [],
      awaiting_approval: [],
      equipment_attention: [{ code: "M-204", name: "Hydraulic Press Motor", reason: "mentioned in handover notes" }],
      next_shift_actions: ["Next shift bearing check karna hai."],
      observations: ["M-204 vibration kam hua."],
    },
    pending_actions: [{ text: "Next shift bearing check karna hai.", source: "notes", work_order_id: null, done: false }],
    reviewed_by: null,
    reviewed_at: null,
    review_comment: null,
    history: [],
    ...overrides,
  };
}

describe("handover review", () => {
  it("shows notes and record-based summary, then reviews with edited actions", async () => {
    const { calls } = signedIn({
      "GET /handovers/h-1": handover(),
      "POST /handovers/h-1/review": () => ({
        body: handover({ status: "reviewed", reviewed_by: { id: "u-sup", name: "Supervisor Rao" }, reviewed_at: "2026-11-10T15:00:00Z" }),
      }),
    });
    renderApp("/handovers/h-1");
    expect(await screen.findByText(/M-204 vibration kam hua\. Next shift/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "WO-1008" })).toBeInTheDocument();
    expect(screen.getByText(/mentioned in handover notes/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("checkbox", { name: /Next shift bearing check/ }));
    await userEvent.type(screen.getByLabelText("New action"), "Order spare bearing");
    await userEvent.click(screen.getByRole("button", { name: "Add action" }));
    await userEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));

    await waitFor(() => expect(screen.getByText(/Reviewed by Supervisor Rao/)).toBeInTheDocument());
    expect(calls.find((c) => c.path === "/handovers/h-1/review")?.body).toEqual({
      pending_actions: [
        { text: "Next shift bearing check karna hai.", source: "notes", work_order_id: null, done: true },
        { text: "Order spare bearing", source: "supervisor", work_order_id: null, done: false },
      ],
    });
  });

  it("does not let the author review their own handover", async () => {
    signedIn({ "GET /handovers/h-1": handover({ created_by: { id: "u-sup", name: "Supervisor Rao" } }) });
    renderApp("/handovers/h-1");
    expect(await screen.findByText(/another supervisor reviews it/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
  });
});

describe("checklist templates", () => {
  it("publishes a template with ordered steps", async () => {
    const { calls } = signedIn({
      "GET /checklists/templates": [],
      "POST /checklists/templates": () => ({ status: 201, body: {} }),
    });
    renderApp("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "New template" }));
    const dialog = await screen.findByRole("dialog");
    const publish = within(dialog).getByRole("button", { name: "Publish" });
    expect(publish).toBeDisabled();

    // user-event reads "[" as a key name; "[[" types a literal bracket
    await userEvent.type(within(dialog).getByLabelText(/^Name/), "[[DEMO SOP] Pump inspection");
    await userEvent.selectOptions(within(dialog).getByLabelText("Equipment category"), "hydraulic");
    await userEvent.type(within(dialog).getByLabelText("Step 1"), "Isolate and lock out the pump");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add step" }));
    await userEvent.type(within(dialog).getByLabelText("Step 2"), "Check seal for leaks");
    await userEvent.click(within(dialog).getAllByLabelText("Mandatory")[1]);
    await userEvent.click(publish);

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/checklists/templates")).toBe(true));
    expect(calls.find((c) => c.method === "POST" && c.path === "/checklists/templates")?.body).toEqual({
      name: "[DEMO SOP] Pump inspection",
      equipment_category: "hydraulic",
      work_order_type: "corrective",
      items: [
        { description: "Isolate and lock out the pump", is_mandatory: true },
        { description: "Check seal for leaks", is_mandatory: false },
      ],
    });
  });
});

describe("dashboard pages render with empty data", () => {
  it.each([
    ["/equipment", { "GET /equipment": page([]) }, "No equipment found"],
    ["/technicians", { "GET /dashboard/technician-workload": [] }, "No technicians at this site"],
    ["/handovers", { "GET /handovers": page([]) }, "No handovers here"],
    ["/audit", { "GET /audit-logs": page([]) }, "No audit entries"],
  ])("%s", async (path, routes, text) => {
    signedIn(routes);
    renderApp(path);
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
});
