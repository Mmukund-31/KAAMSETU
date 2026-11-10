import { CATEGORY_LABEL, PRIORITY_LABEL, STATUS_LABEL, formatDateTime, humanize } from "../lib/format";
import type { EquipmentCategory, HistoryEntry, Priority, WorkOrderStatus } from "../types/api";

const ACTION_LABEL: Record<string, string> = {
  "work_order.create": "Reported",
  "work_order.transition": "Status changed",
  "work_order.update": "Details edited",
  "work_order.priority_override": "Priority changed",
  "work_order.reassign": "Reassigned",
  "checklist.attach": "Checklist attached",
  "checklist.item_update": "Checklist step recorded",
  "checklist_template.publish": "Checklist template published",
  "checklist_template.deactivate": "Checklist template deactivated",
  "equipment.create": "Equipment registered",
  "handover.create": "Handover submitted",
  "handover.review": "Handover reviewed",
  "user.create": "Account created",
};

export function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? humanize(action.split(".").slice(-1)[0] ?? action);
}

/** Title for a history row; a status change reads "Under review → Approved". */
export function entryTitle(entry: Pick<HistoryEntry, "action" | "previous_value" | "new_value">): string {
  if (entry.action === "work_order.transition") {
    const from = entry.previous_value?.status as WorkOrderStatus | undefined;
    const to = entry.new_value?.status as WorkOrderStatus | undefined;
    if (from && to) return `${STATUS_LABEL[from] ?? from} → ${STATUS_LABEL[to] ?? to}`;
  }
  if (entry.action === "checklist.item_update" && entry.new_value?.item !== undefined) {
    const response = entry.new_value.response;
    return `Checklist step ${String(entry.new_value.item)}${typeof response === "string" ? `: ${humanize(response)}` : ""}`;
  }
  return actionLabel(entry.action);
}

function changeLines(entry: HistoryEntry): string[] {
  if (entry.action === "work_order.transition") return []; // the title already says what changed
  if (entry.action === "checklist.item_update") {
    const notes = entry.new_value?.notes;
    return typeof notes === "string" && notes ? [`Notes: ${notes}`] : [];
  }
  return describeChange(entry);
}

// Internal identifiers are kept in the audit table but are not useful on screen.
const HIDDEN_KEYS = new Set(["comment", "via", "checklist_id", "technician_id", "assigned_to", "work_order_id", "id"]);

function valueText(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (key.endsWith("_at") && typeof value === "string") return formatDateTime(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (key === "category" && typeof value === "string") return CATEGORY_LABEL[value as EquipmentCategory] ?? value;
  if (key === "response" && typeof value === "string") return humanize(value);
  if (key === "channel" && typeof value === "string") return humanize(value);
  if (key === "status" && typeof value === "string") return STATUS_LABEL[value as WorkOrderStatus] ?? value;
  if (key === "priority" && typeof value === "string") return PRIORITY_LABEL[value as Priority] ?? value;
  if (key === "issue_category" && typeof value === "string")
    return CATEGORY_LABEL[value as EquipmentCategory] ?? value;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

/** Readable "field: before → after" lines from an audit row. */
export function describeChange(entry: Pick<HistoryEntry, "previous_value" | "new_value">): string[] {
  const prev = entry.previous_value ?? {};
  const next = entry.new_value ?? {};
  const keys = Array.from(new Set([...Object.keys(prev), ...Object.keys(next)]));
  return keys
    .filter((k) => !HIDDEN_KEYS.has(k))
    // a field that is empty on both sides says nothing
    .filter((k) => !(isEmpty(prev[k]) && isEmpty(next[k])))
    .map((k) => {
      const label = humanize(k);
      if (k in prev && k in next) return `${label}: ${valueText(k, prev[k])} → ${valueText(k, next[k])}`;
      return `${label}: ${valueText(k, k in next ? next[k] : prev[k])}`;
    });
}

export function Timeline({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-ink-muted">No history yet.</p>;
  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {entries.map((entry) => (
        <li key={entry.id} className="relative">
          <span className="absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-primary-600 ring-1 ring-line" />
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <p className="text-sm font-medium text-ink">{entryTitle(entry)}</p>
            <time className="text-xs text-ink-muted" dateTime={entry.timestamp}>
              {formatDateTime(entry.timestamp)}
            </time>
          </div>
          <p className="text-xs text-ink-muted">{entry.actor?.name ?? "System"}</p>
          {changeLines(entry).map((line) => (
            <p key={line} className="mt-0.5 text-sm text-ink-muted">
              {line}
            </p>
          ))}
          {entry.comment && (
            <p className="mt-1 rounded-md bg-surface-subtle px-2.5 py-1.5 text-sm text-ink">“{entry.comment}”</p>
          )}
        </li>
      ))}
    </ol>
  );
}
