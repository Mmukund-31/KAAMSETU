import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { WorkOrderTable } from "../components/WorkOrderTable";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, cx } from "../components/ui";
import { APPROVAL_STATUSES } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { workOrdersApi, type WorkOrderFilters } from "../services";

const TABS = {
  reports: {
    label: "New reports",
    description: "Reported, under review or escalated. Approve, reject or escalate each one.",
    filters: { status: APPROVAL_STATUSES, sort: "priority", page_size: 100 } satisfies WorkOrderFilters,
    empty: "No reports are waiting for approval.",
  },
  completion: {
    label: "Completion review",
    description: "The technician has finished. Check the checklist, then close or reopen.",
    filters: { status: ["completion_review"], sort: "priority", page_size: 100 } satisfies WorkOrderFilters,
    empty: "No completed work is waiting to be closed.",
  },
} as const;

type TabKey = keyof typeof TABS;

export function ApprovalsPage() {
  const [params, setParams] = useSearchParams();
  const tab: TabKey = params.get("tab") === "completion" ? "completion" : "reports";

  const reports = useQuery({
    queryKey: queryKeys.workOrders(TABS.reports.filters),
    queryFn: () => workOrdersApi.list(TABS.reports.filters),
    refetchInterval: 15_000,
  });
  const completion = useQuery({
    queryKey: queryKeys.workOrders(TABS.completion.filters),
    queryFn: () => workOrdersApi.list(TABS.completion.filters),
    refetchInterval: 15_000,
  });
  const active = tab === "reports" ? reports : completion;

  return (
    <>
      <PageHeader title="Approvals" description="Highest priority first. Open an order to see the original transcript and act on it." />

      <div role="tablist" aria-label="Approval queues" className="mb-4 flex gap-1 border-b border-line">
        {(Object.keys(TABS) as TabKey[]).map((key) => {
          const count = (key === "reports" ? reports : completion).data?.total;
          return (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setParams(key === "reports" ? {} : { tab: key }, { replace: true })}
              className={cx(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
                tab === key ? "border-primary-700 text-primary-800" : "border-transparent text-ink-muted hover:text-ink",
              )}
            >
              {TABS[key].label}
              {count !== undefined && (
                <span className="ml-1.5 rounded-full bg-surface-sunken px-1.5 text-xs tabular-nums">{count}</span>
              )}
            </button>
          );
        })}
      </div>

      <p className="mb-3 text-sm text-ink-muted">{TABS[tab].description}</p>
      <Card bodyClassName="p-0">
        {active.isLoading ? (
          <LoadingState />
        ) : active.isError ? (
          <ErrorState error={active.error} onRetry={() => void active.refetch()} />
        ) : !active.data?.items.length ? (
          <EmptyState title={TABS[tab].empty} />
        ) : (
          <WorkOrderTable items={active.data.items} showAssignee={tab === "completion"} />
        )}
      </Card>
    </>
  );
}
