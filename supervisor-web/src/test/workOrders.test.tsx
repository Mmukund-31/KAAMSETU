import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { detail, page, renderApp, signedIn, summary } from "./harness";

describe("work-order list", () => {
  it("renders rows and sends chip filters to the API", async () => {
    const { calls } = signedIn({ "GET /work-orders": page([summary(), summary({ id: "wo-2", display_number: "WO-1009", priority: "low" })]) });
    renderApp("/work-orders");
    expect(await screen.findByRole("link", { name: "Open WO-1008" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open WO-1009" })).toBeInTheDocument();

    await userEvent.click(within(screen.getByRole("group", { name: "Status" })).getByRole("button", { name: "Blocked" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Priority" })).getByRole("button", { name: "Critical" }));
    await waitFor(() => {
      const last = calls.filter((c) => c.path === "/work-orders").at(-1)!;
      expect(last.query.getAll("status")).toEqual(["blocked"]);
      expect(last.query.getAll("priority")).toEqual(["critical"]);
    });
  });

  it("shows an empty state", async () => {
    signedIn({ "GET /work-orders": page([]) });
    renderApp("/work-orders");
    expect(await screen.findByText("No work orders match")).toBeInTheDocument();
  });

  it("shows the server error with a retry", async () => {
    signedIn({ "GET /work-orders": () => ({ status: 503, body: { error: { code: "db", message: "Database unavailable" } } }) });
    renderApp("/work-orders");
    expect(await screen.findByText("Database unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("approvals queue", () => {
  it("asks for reported, under-review and escalated orders by priority", async () => {
    const { calls } = signedIn({ "GET /work-orders": page([summary()]) });
    renderApp("/approvals");
    expect(await screen.findByRole("link", { name: "Open WO-1008" })).toBeInTheDocument();
    const reportQuery = calls.find((c) => c.path === "/work-orders" && c.query.getAll("status").includes("under_review"))!;
    expect(reportQuery.query.getAll("status")).toEqual(["reported", "under_review", "escalated"]);
    expect(reportQuery.query.get("sort")).toBe("priority");
    expect(calls.some((c) => c.path === "/work-orders" && c.query.getAll("status").join() === "completion_review")).toBe(true);
  });
});

describe("work-order detail", () => {
  it("shows the verbatim transcript next to the structured order and the audit trail", async () => {
    signedIn({ "GET /work-orders/wo-1": detail() });
    renderApp("/work-orders/wo-1");
    expect(await screen.findByText(/Production chal raha hai/)).toBeInTheDocument();
    expect(screen.getByText("Structured work order")).toBeInTheDocument();
    expect(screen.getByText("Bearing vibration")).toBeInTheDocument();
    expect(screen.getByText("Reported → Under review")).toBeInTheDocument();
    expect(screen.getByText("req-abc")).toBeInTheDocument();
  });

  it("builds buttons from allowed_actions and explains blocked ones", async () => {
    signedIn({
      "GET /work-orders/wo-1": detail({
        status: "in_progress",
        allowed_actions: [
          { action: "status", to: "blocked", comment_required: true, blocked_reason: null },
          { action: "complete", to: "completion_review", comment_required: false, blocked_reason: "checklist_incomplete" },
        ],
      }),
    });
    renderApp("/work-orders/wo-1");
    expect(await screen.findByRole("button", { name: "Mark blocked" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Mark complete" })).toBeDisabled();
    expect(screen.getByText(/Mandatory checklist steps are still open/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("approves with a priority override only when a reason is given", async () => {
    // stateful like the real server: after approval, GET returns the approved order
    let current = detail();
    const { calls } = signedIn({
      "GET /work-orders/wo-1": () => ({ body: current }),
      "POST /work-orders/wo-1/approve": () => {
        current = detail({ status: "approved", priority: "critical", allowed_actions: [], can_assign: true });
        return { body: current };
      },
    });
    renderApp("/work-orders/wo-1");
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Priority"), "critical");
    const submit = within(dialog).getByRole("button", { name: "Approve" });
    expect(submit).toBeDisabled();

    await userEvent.type(within(dialog).getByLabelText(/Reason for changing/), "Line 2 is the only press line");
    await userEvent.click(submit);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.find((c) => c.path === "/work-orders/wo-1/approve")?.body).toEqual({
      priority: "critical",
      priority_reason: "Line 2 is the only press line",
    });
    // the page now shows the server's new state
    expect(await screen.findByRole("button", { name: "Assign technician" })).toBeInTheDocument();
  });

  it("requires a reason to reject and shows server errors in the dialog", async () => {
    const { calls } = signedIn({
      "GET /work-orders/wo-1": detail(),
      "POST /work-orders/wo-1/reject": () => ({
        status: 409,
        body: { error: { code: "invalid_transition", message: "This work order was already approved" } },
      }),
    });
    renderApp("/work-orders/wo-1");
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Reject" });
    expect(submit).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Duplicate of WO-1007");
    await userEvent.click(submit);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This work order was already approved");
    expect(calls.find((c) => c.path === "/work-orders/wo-1/reject")?.body).toEqual({ comment: "Duplicate of WO-1007" });
  });

  it("assigns a technician from the site list", async () => {
    const { calls } = signedIn({
      "GET /work-orders/wo-1": detail({ status: "approved", allowed_actions: [], can_assign: true }),
      "GET /users": [
        { id: "t2", name: "Lakshmi", email: "tech2@kaamsetu.demo", role: "technician", preferred_language: "te", site_id: "site-1", is_active: true, open_assigned: 1 },
      ],
      "POST /work-orders/wo-1/assign": detail({ status: "assigned", assignee: { id: "t2", name: "Lakshmi" }, allowed_actions: [], can_assign: true }),
    });
    renderApp("/work-orders/wo-1");
    await userEvent.click(await screen.findByRole("button", { name: "Assign technician" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(await within(dialog).findByLabelText(/Technician/), "t2");
    await userEvent.click(within(dialog).getByRole("button", { name: "Assign" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/work-orders/wo-1/assign")).toBe(true));
    expect(calls.find((c) => c.path === "/work-orders/wo-1/assign")?.body).toEqual({ technician_id: "t2" });
    expect(calls.find((c) => c.path === "/users")?.query.get("role")).toBe("technician");
  });

  it("says not found for another site's order", async () => {
    signedIn({ "GET /work-orders/zzz": () => ({ status: 404, body: { error: { code: "not_found", message: "Work order not found" } } }) });
    renderApp("/work-orders/zzz");
    expect(await screen.findByText(/belongs to another site/)).toBeInTheDocument();
  });
});
