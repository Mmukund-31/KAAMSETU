import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriorityBadge, StatusBadge } from "../components/badges";
import { describeChange, entryTitle } from "../components/Timeline";
import { OPEN_STATUSES, STATUS_LABEL, STATUS_ORDER, blockedReasonText, humanize, relativeTime } from "../lib/format";
import { filtersFromParams } from "../pages/WorkOrdersPage";

describe("format helpers", () => {
  it("covers every backend status exactly once in the lifecycle order", () => {
    expect(new Set(STATUS_ORDER).size).toBe(12);
    expect(Object.keys(STATUS_LABEL).sort()).toEqual([...STATUS_ORDER].sort());
    expect(OPEN_STATUSES).not.toContain("closed");
    expect(OPEN_STATUSES).not.toContain("rejected");
    expect(OPEN_STATUSES).toHaveLength(10);
  });

  it("formats relative times in both directions", () => {
    const now = Date.parse("2026-11-10T12:00:00Z");
    expect(relativeTime("2026-11-10T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-11-10T12:20:00Z", now)).toBe("in 20 min");
    expect(relativeTime("2026-11-13T12:00:00Z", now)).toBe("in 3 d");
    expect(relativeTime(null, now)).toBe("—");
  });

  it("explains guard codes and humanizes keys", () => {
    expect(blockedReasonText("checklist_incomplete")).toMatch(/checklist/i);
    expect(blockedReasonText("some_new_guard")).toBe("some new guard");
    expect(humanize("bearing_vibration")).toBe("Bearing vibration");
  });
});

describe("audit rendering", () => {
  it("titles a transition as from -> to", () => {
    expect(
      entryTitle({ action: "work_order.transition", previous_value: { status: "under_review" }, new_value: { status: "approved" } }),
    ).toBe("Under review → Approved");
  });

  it("titles checklist steps and drops fields that are empty on both sides", () => {
    expect(
      entryTitle({ action: "checklist.item_update", previous_value: null, new_value: { item: 3, response: "not_applicable" } }),
    ).toBe("Checklist step 3: Not applicable");
    expect(describeChange({ previous_value: { notes: null }, new_value: { notes: null, safety_concern: false } })).toEqual([
      "Safety concern: No",
    ]);
  });

  it("shows readable changes and hides internal ids", () => {
    const lines = describeChange({
      previous_value: { priority: "medium" },
      new_value: { priority: "critical", checklist_id: "c-1", technician_id: "t-1" },
    });
    expect(lines).toEqual(["Priority: Medium → Critical"]);
  });
});

describe("badges", () => {
  it("always shows a text label, never colour alone", () => {
    render(
      <>
        <StatusBadge status="completion_review" />
        <PriorityBadge priority="critical" />
      </>,
    );
    expect(screen.getByText("Completion review")).toHaveAttribute("data-status", "completion_review");
    expect(screen.getByText("Critical")).toHaveAttribute("data-priority", "critical");
  });
});

describe("work-order URL filters", () => {
  it("reads repeated statuses and flags", () => {
    const f = filtersFromParams(new URLSearchParams("status=blocked&status=awaiting_parts&overdue=1&q=M-204&sort=priority"));
    expect(f).toMatchObject({ status: ["blocked", "awaiting_parts"], overdue: true, q: "M-204", sort: "priority", page: 1 });
  });

  it("expands open=1 to every open status and ignores unknown values", () => {
    const f = filtersFromParams(new URLSearchParams("open=1&priority=critical&priority=bogus"));
    expect(f.status).toEqual(OPEN_STATUSES);
    expect(f.priority).toEqual(["critical"]);
  });
});
