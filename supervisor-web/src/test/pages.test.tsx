import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OVERVIEW, detail, page, renderApp, signedIn, summary, user } from "./harness";

const EQUIPMENT = {
  id: "eq-204",
  code: "M-204",
  name: "Hydraulic Press Main Motor",
  category: "mechanical",
  site_id: "site-1",
  site_name: "Hyderabad Plant 1",
  location: "Press Shop, Bay 2",
  operational_status: "running",
  is_critical: true,
  open_work_orders: 2,
  created_at: "2026-10-01T00:00:00Z",
};

const WORKLOAD = [
  { technician: { id: "t1", name: "Ravi Kumar" }, preferred_language: "hinglish", assigned: 1, in_progress: 2, blocked: 1, completion_review: 0, overdue: 1, closed_30d: 4, open_total: 4 },
  { technician: { id: "t2", name: "Lakshmi Reddy" }, preferred_language: "te", assigned: 0, in_progress: 0, blocked: 0, completion_review: 0, overdue: 0, closed_30d: 0, open_total: 0 },
];

describe("overview", () => {
  it("shows the dashboard numbers exactly as the API returns them, with links to the filtered lists", async () => {
    signedIn({
      "GET /dashboard/overview": { ...OVERVIEW, pending_approval: 3, overdue: 2, critical_high_open: 5 },
      "GET /work-orders": page([summary()]),
    });
    renderApp("/");
    const tile = (await screen.findByText("Awaiting approval")).closest("a")!;
    expect(within(tile).getByText("3")).toBeInTheDocument();
    expect(tile).toHaveAttribute("href", "/approvals");
    expect(screen.getByText("Overdue", { selector: "p" }).closest("a")).toHaveAttribute("href", "/work-orders?overdue=1");
    expect(within(screen.getByText("Critical / high open").closest("a")!).getByText("5")).toBeInTheDocument();
  });
});

describe("analytics", () => {
  const routes = {
    "GET /dashboard/work-order-trends": [
      { day: "2026-11-09", created: 2, closed: 1 },
      { day: "2026-11-10", created: 1, closed: 3 },
    ],
    "GET /dashboard/equipment-issues": {
      days: 30,
      equipment: [{ equipment_id: "eq-204", code: "M-204", name: "Hydraulic Press Main Motor", category: "mechanical", is_critical: true, work_orders: 3, open: 1, top_symptoms: [{ symptom: "bearing_vibration", label: "Bearing vibration", count: 2 }], recurring: true }],
      by_category: { mechanical: 3, electrical: 1 },
      by_symptom: [{ symptom: "bearing_vibration", label: "Bearing vibration", count: 2 }],
    },
    "GET /dashboard/technician-workload": WORKLOAD,
  };

  it("renders the charts and an exact table view of each", async () => {
    const { calls } = signedIn({ ...routes, "GET /dashboard/overview": { ...OVERVIEW, by_priority_open: { high: 2, low: 1 } } });
    renderApp("/analytics");
    expect(await screen.findByText("Work orders created and closed per day, last 30 days")).toBeInTheDocument();
    expect(await screen.findByText(/Recurring$/)).toBeInTheDocument(); // equipment issues load separately
    await userEvent.click(screen.getAllByRole("button", { name: "Show table" })[0]);
    const trendCard = screen.getByText("Work orders created and closed per day, last 30 days").closest("section")!;
    const rows = within(trendCard).getAllByRole("row");
    // newest first, exactly the API numbers: day, created, closed
    expect(rows[1]).toHaveTextContent("10 Nov13");
    expect(rows[2]).toHaveTextContent("09 Nov21");
    await userEvent.click(screen.getByRole("button", { name: "90 days" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/dashboard/work-order-trends" && c.query.get("days") === "90")).toBe(true));
  });

  it("explains empty data instead of drawing empty charts", async () => {
    signedIn({
      ...routes,
      "GET /dashboard/overview": { ...OVERVIEW, by_priority_open: {} },
      "GET /dashboard/technician-workload": WORKLOAD.map((w) => ({ ...w, open_total: 0 })),
    });
    renderApp("/analytics");
    expect(await screen.findByText("No open work orders right now")).toBeInTheDocument();
    expect(screen.getByText("No technician has open work right now")).toBeInTheDocument();
  });
});

describe("equipment", () => {
  it("searches the register and registers a machine with a valid code only", async () => {
    const { calls } = signedIn({
      "GET /equipment": page([EQUIPMENT]),
      "POST /equipment": () => ({ status: 201, body: { ...EQUIPMENT, id: "eq-new", code: "M-206" } }),
    });
    renderApp("/equipment");
    expect(await screen.findByRole("link", { name: "M-204" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search equipment"), "press");
    await waitFor(() => expect(calls.some((c) => c.path === "/equipment" && c.query.get("q") === "press")).toBe(true));

    await userEvent.click(screen.getByRole("button", { name: "Register equipment" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Equipment code/), "MOTOR");
    expect(within(dialog).getByText("Use a code like M-205 or CV12.")).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText(/Equipment code/));
    await userEvent.type(within(dialog).getByLabelText(/Equipment code/), "M-206");
    await userEvent.type(within(dialog).getByLabelText(/^Name/), "Spare press motor");
    await userEvent.click(within(dialog).getByRole("checkbox"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Register" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/equipment")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      equipment_code: "M-206",
      name: "Spare press motor",
      category: "mechanical",
      location: null,
      is_critical: true,
    });
  });

  it("shows a machine's history and recurring faults", async () => {
    signedIn({
      "GET /equipment/eq-204": {
        ...EQUIPMENT,
        work_orders_total: 7,
        work_orders_90d: 3,
        recurring_faults: [{ symptom: "bearing_vibration", label: "Bearing vibration", count: 3 }],
        recent_work_orders: [summary()],
      },
    });
    renderApp("/equipment/eq-204");
    expect(await screen.findByText("Fault history by symptom")).toBeInTheDocument();
    expect(screen.getByText("Bearing vibration")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open WO-1008" })).toBeInTheDocument();
    expect(within(screen.getByText("Work orders, all time").closest("div")!).getByText("7")).toBeInTheDocument();
  });
});

describe("technicians", () => {
  it("shows workload and lets a supervisor create technician accounts only", async () => {
    const { calls } = signedIn({
      "GET /dashboard/technician-workload": WORKLOAD,
      "POST /auth/register": () => ({ status: 201, body: user({ id: "new", role: "technician" }) }),
    });
    renderApp("/technicians");
    const row = (await screen.findByRole("link", { name: "Ravi Kumar" })).closest("tr")!;
    expect(row).toHaveTextContent("Hinglish");
    expect(screen.getByRole("link", { name: "Ravi Kumar" })).toHaveAttribute("href", "/work-orders?open=1&assigned_to=t1");

    await userEvent.click(screen.getByRole("button", { name: "Add account" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Role")).toBeDisabled(); // supervisors create technicians only
    await userEvent.type(within(dialog).getByLabelText(/^Name/), "Arjun Yadav");
    await userEvent.type(within(dialog).getByLabelText(/^Email/), "tech4@kaamsetu.demo");
    await userEvent.type(within(dialog).getByLabelText(/Initial password/), "short");
    expect(within(dialog).getByRole("button", { name: "Create account" })).toBeDisabled();
    await userEvent.clear(within(dialog).getByLabelText(/Initial password/));
    await userEvent.type(within(dialog).getByLabelText(/Initial password/), "Welcome2026");
    await userEvent.selectOptions(within(dialog).getByLabelText(/Spoken language/), "te");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/auth/register")).toBe(true));
    expect(calls.find((c) => c.path === "/auth/register")!.body).toEqual({
      name: "Arjun Yadav",
      email: "tech4@kaamsetu.demo",
      password: "Welcome2026",
      role: "technician",
      preferred_language: "te",
    });
  });
});

describe("handovers and audit", () => {
  it("lists handovers awaiting review by default and writes a new one", async () => {
    const { calls } = signedIn({
      "GET /handovers": page([]),
      "POST /handovers": () => ({ status: 201, body: { id: "h9" } }),
      "GET /handovers/h9": () => ({ status: 404, body: { error: { code: "not_found", message: "Handover not found" } } }),
    });
    renderApp("/handovers");
    expect(await screen.findByText("No handovers here")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/handovers")!.query.get("status")).toBe("submitted");
    await userEvent.click(screen.getByRole("button", { name: "Write handover" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Notes for the next shift/), "Check M-204 bearing next shift.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Submit handover" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/handovers")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ notes: "Check M-204 bearing next shift." });
  });

  it("filters the audit log by record type", async () => {
    const { calls } = signedIn({
      "GET /audit-logs": page([
        {
          id: "a1",
          action: "work_order.transition",
          actor: { id: "u-sup", name: "Supervisor Rao" },
          previous_value: { status: "under_review" },
          new_value: { status: "approved", via: "approve" },
          comment: "ok to proceed",
          timestamp: "2026-11-10T10:00:00Z",
          entity_type: "work_order",
          entity_id: "wo-1",
        },
      ]),
    });
    renderApp("/audit");
    expect(await screen.findByText("Under review → Approved")).toBeInTheDocument();
    expect(screen.getByText("“ok to proceed”")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Record type"), "handover");
    await waitFor(() => expect(calls.some((c) => c.path === "/audit-logs" && c.query.get("entity_type") === "handover")).toBe(true));
  });
});

describe("edit details", () => {
  it("sends only changed fields and needs a reason for a priority change", async () => {
    const { calls } = signedIn({
      "GET /work-orders/wo-1": detail(),
      "PATCH /work-orders/wo-1": detail({ location_note: "Bay 2, north side" }),
    });
    renderApp("/work-orders/wo-1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Location note"), "Bay 2, north side");
    await userEvent.selectOptions(within(dialog).getByLabelText("Priority"), "critical");
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason for changing/), "Only press on the line");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({
      location_note: "Bay 2, north side",
      priority: "critical",
      priority_reason: "Only press on the line",
    });
  });

  it("shows a page-not-found screen for unknown routes", async () => {
    signedIn({});
    renderApp("/no-such-page");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
