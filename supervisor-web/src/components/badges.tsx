import { ShieldAlert } from "lucide-react";
import { CATEGORY_LABEL, PRIORITY_LABEL, STATUS_LABEL } from "../lib/format";
import type { EquipmentCategory, Priority, WorkOrderStatus } from "../types/api";
import { cx } from "./ui";

const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

// Colour carries meaning: red = stopped or needs a decision now, amber = waiting on someone,
// teal = work under way, slate = settled. Text labels are always shown, never colour alone.
const STATUS_STYLE: Record<WorkOrderStatus, string> = {
  reported: "bg-slate-50 text-slate-700 ring-slate-300",
  under_review: "bg-amber-50 text-amber-800 ring-amber-300",
  escalated: "bg-red-50 text-red-800 ring-red-300",
  approved: "bg-sky-50 text-sky-800 ring-sky-300",
  assigned: "bg-sky-50 text-sky-800 ring-sky-300",
  in_progress: "bg-primary-50 text-primary-800 ring-primary-600/40",
  blocked: "bg-red-50 text-red-800 ring-red-300",
  awaiting_parts: "bg-amber-50 text-amber-800 ring-amber-300",
  completion_review: "bg-amber-50 text-amber-800 ring-amber-300",
  reopened: "bg-amber-50 text-amber-800 ring-amber-300",
  closed: "bg-slate-100 text-slate-600 ring-slate-300",
  rejected: "bg-slate-100 text-slate-600 ring-slate-300",
};

export function StatusBadge({ status }: { status: WorkOrderStatus }) {
  return (
    <span className={cx(pill, STATUS_STYLE[status])} data-status={status}>
      {STATUS_LABEL[status]}
    </span>
  );
}

const PRIORITY_STYLE: Record<Priority, string> = {
  critical: "bg-red-700 text-white ring-red-700",
  high: "bg-red-50 text-red-800 ring-red-300",
  medium: "bg-amber-50 text-amber-800 ring-amber-300",
  low: "bg-slate-50 text-slate-600 ring-slate-300",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={cx(pill, PRIORITY_STYLE[priority])} data-priority={priority}>
      {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function SafetyBadge() {
  return (
    <span className={cx(pill, "bg-red-50 text-red-800 ring-red-300")}>
      <ShieldAlert className="h-3 w-3" aria-hidden />
      Safety
    </span>
  );
}

export function OverdueBadge() {
  return <span className={cx(pill, "bg-red-50 text-red-800 ring-red-300")}>Overdue</span>;
}

export function CategoryBadge({ category }: { category: EquipmentCategory }) {
  return <span className={cx(pill, "bg-white text-ink-muted ring-line-strong")}>{CATEGORY_LABEL[category]}</span>;
}

export function NeutralBadge({ children }: { children: React.ReactNode }) {
  return <span className={cx(pill, "bg-white text-ink-muted ring-line-strong")}>{children}</span>;
}
