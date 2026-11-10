import { Link } from "react-router-dom";
import { CATEGORY_LABEL, formatDateTime, relativeTime } from "../lib/format";
import type { WorkOrderSummary } from "../types/api";
import { OverdueBadge, PriorityBadge, SafetyBadge, StatusBadge } from "./badges";
import { Table, Td, Th, cx } from "./ui";

/** Work-order list used on Overview, Work orders, Approvals and Equipment detail. */
export function WorkOrderTable({
  items,
  showAssignee = true,
  compact = false,
}: {
  items: WorkOrderSummary[];
  showAssignee?: boolean;
  compact?: boolean;
}) {
  return (
    <Table minWidth={compact ? 640 : 860}>
      <thead>
        <tr>
          <Th>Order</Th>
          <Th>Equipment</Th>
          <Th>Issue</Th>
          <Th>Priority</Th>
          <Th>Status</Th>
          {showAssignee && <Th>Assignee</Th>}
          <Th>{compact ? "Reported" : "Reported / due"}</Th>
        </tr>
      </thead>
      <tbody>
        {items.map((wo) => (
          <tr key={wo.id} className="hover:bg-surface-subtle">
            <Td className="whitespace-nowrap">
              <Link
                to={`/work-orders/${wo.id}`}
                className="font-medium text-primary-700 hover:underline"
                aria-label={`Open ${wo.display_number}`}
              >
                {wo.display_number}
              </Link>
            </Td>
            <Td>
              <p className="font-mono text-xs font-semibold text-ink">{wo.equipment.code}</p>
              <p className="text-xs text-ink-muted">{wo.equipment.name}</p>
            </Td>
            <Td className="max-w-xs">
              <p className="line-clamp-2 text-sm">{wo.issue_description}</p>
              <p className="mt-0.5 text-xs text-ink-muted">{CATEGORY_LABEL[wo.issue_category]}</p>
            </Td>
            <Td>
              <div className="flex flex-col items-start gap-1">
                <PriorityBadge priority={wo.priority} />
                {wo.safety_concern && <SafetyBadge />}
              </div>
            </Td>
            <Td>
              <div className="flex flex-col items-start gap-1">
                <StatusBadge status={wo.status} />
                {wo.is_overdue && <OverdueBadge />}
              </div>
            </Td>
            {showAssignee && (
              <Td className="whitespace-nowrap text-sm">
                {wo.assignee?.name ?? <span className="text-ink-faint">Unassigned</span>}
              </Td>
            )}
            <Td className="whitespace-nowrap text-xs text-ink-muted">
              <p title={formatDateTime(wo.created_at)}>
                {relativeTime(wo.created_at)} · {wo.reporter.name}
              </p>
              {!compact && wo.due_at && wo.status !== "closed" && wo.status !== "rejected" && (
                <p className={cx("mt-0.5", wo.is_overdue && "font-medium text-red-700")} title={formatDateTime(wo.due_at)}>
                  Due {relativeTime(wo.due_at)}
                </p>
              )}
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
