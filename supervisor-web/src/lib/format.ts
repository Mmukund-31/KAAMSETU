import type {
  ChecklistResponseValue,
  EquipmentCategory,
  LanguageCode,
  OperationalStatus,
  Priority,
  ProductionImpact,
  WorkOrderStatus,
} from "../types/api";

export const STATUS_LABEL: Record<WorkOrderStatus, string> = {
  reported: "Reported",
  under_review: "Under review",
  approved: "Approved",
  assigned: "Assigned",
  in_progress: "In progress",
  completion_review: "Completion review",
  closed: "Closed",
  rejected: "Rejected",
  awaiting_parts: "Awaiting parts",
  blocked: "Blocked",
  escalated: "Escalated",
  reopened: "Reopened",
};

/** Lifecycle order used for filters and charts. */
export const STATUS_ORDER: WorkOrderStatus[] = [
  "reported",
  "under_review",
  "escalated",
  "approved",
  "assigned",
  "in_progress",
  "blocked",
  "awaiting_parts",
  "completion_review",
  "reopened",
  "closed",
  "rejected",
];

/** Everything except closed and rejected (backend workflows/escalation.py OPEN_STATUSES). */
export const OPEN_STATUSES: WorkOrderStatus[] = STATUS_ORDER.filter((s) => s !== "closed" && s !== "rejected");

/** Waiting for a supervisor decision; matches the dashboard's "awaiting approval" tile. */
export const APPROVAL_STATUSES: WorkOrderStatus[] = ["reported", "under_review", "escalated"];

export const PRIORITY_LABEL: Record<Priority, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};
export const PRIORITY_ORDER: Priority[] = ["critical", "high", "medium", "low"];

export const CATEGORY_LABEL: Record<EquipmentCategory, string> = {
  mechanical: "Mechanical",
  electrical: "Electrical",
  instrumentation: "Instrumentation",
  hydraulic: "Hydraulic",
  pneumatic: "Pneumatic",
  production: "Production",
  other: "Other",
};
export const CATEGORIES = Object.keys(CATEGORY_LABEL) as EquipmentCategory[];

export const IMPACT_LABEL: Record<ProductionImpact, string> = {
  running: "Production running",
  degraded: "Production degraded",
  stopped: "Production stopped",
  unknown: "Impact unknown",
};

export const OPERATIONAL_LABEL: Record<OperationalStatus, string> = {
  running: "Running",
  stopped: "Stopped",
  degraded: "Degraded",
  maintenance: "Maintenance",
  decommissioned: "Decommissioned",
};

export const LANGUAGE_LABEL: Record<LanguageCode, string> = {
  en: "English",
  hi: "Hindi",
  te: "Telugu",
  hinglish: "Hinglish",
};

export const RESPONSE_LABEL: Record<ChecklistResponseValue, string> = {
  done: "Done",
  not_applicable: "Not applicable",
  failed: "Failed",
};

/** Explanations for guard codes returned in allowed_actions[].blocked_reason. */
export const BLOCKED_REASON_LABEL: Record<string, string> = {
  checklist_incomplete: "Mandatory checklist steps are still open.",
  no_technician_assigned: "Assign a technician first.",
  self_approval_not_allowed: "You reported this order, so another supervisor must approve it.",
};

export function blockedReasonText(code: string): string {
  return BLOCKED_REASON_LABEL[code] ?? code.replace(/_/g, " ");
}

/** Turns a snake_case key into readable text, e.g. bearing_vibration -> Bearing vibration. */
export function humanize(key: string): string {
  const text = key.replace(/[_.]/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const dateTime = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const dateOnly = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const shortDay = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" });

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : "—";
}

export function formatDate(value: string | null | undefined): string {
  return value ? dateOnly.format(new Date(value)) : "—";
}

export function formatShortDay(value: string): string {
  // "2026-11-10" is a calendar date; parse it as local midnight, not UTC.
  const [y, m, d] = value.split("-").map(Number);
  return shortDay.format(new Date(y, m - 1, d));
}

/** "in 3 h", "5 min ago", "2 d ago". */
export function relativeTime(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return "—";
  const diff = new Date(value).getTime() - now;
  const abs = Math.abs(diff);
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  let text: string;
  if (abs < minute) text = "now";
  else if (abs < hour) text = `${Math.round(abs / minute)} min`;
  else if (abs < day) text = `${Math.round(abs / hour)} h`;
  else text = `${Math.round(abs / day)} d`;
  if (text === "now") return "just now";
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-IN").format(value);
}
