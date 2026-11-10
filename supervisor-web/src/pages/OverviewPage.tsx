import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { WorkOrderTable } from "../components/WorkOrderTable";
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, Skeleton, StatCard } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { dashboardApi, workOrdersApi, type WorkOrderFilters } from "../services";
import type { Page, WorkOrderSummary } from "../types/api";

const POLL = 15_000; // the dashboard polls; there are no websockets in the MVP

const ATTENTION: WorkOrderFilters = {
  status: ["reported", "under_review", "escalated", "blocked", "awaiting_parts", "completion_review"],
  sort: "priority",
  page_size: 8,
};
const OVERDUE: WorkOrderFilters = { overdue: true, sort: "due_asc", page_size: 8 };

export function OverviewPage() {
  const overview = useQuery({ queryKey: queryKeys.overview, queryFn: dashboardApi.overview, refetchInterval: POLL });
  const attention = useQuery({
    queryKey: queryKeys.workOrders(ATTENTION),
    queryFn: () => workOrdersApi.list(ATTENTION),
    refetchInterval: POLL,
  });
  const overdue = useQuery({
    queryKey: queryKeys.workOrders(OVERDUE),
    queryFn: () => workOrdersApi.list(OVERDUE),
    refetchInterval: POLL,
  });

  const o = overview.data;
  return (
    <>
      <PageHeader
        title="Overview"
        description={o ? `Live from the work-order database · updated ${formatDateTime(o.generated_at)}` : undefined}
        actions={
          <Button
            size="sm"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={() => {
              void overview.refetch();
              void attention.refetch();
              void overdue.refetch();
            }}
            loading={overview.isFetching && !overview.isLoading}
          >
            Refresh
          </Button>
        }
      />

      {overview.isError ? (
        <Card>
          <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {o ? (
            <>
              <StatCard label="Awaiting approval" value={o.pending_approval} tone={o.pending_approval ? "warning" : "neutral"} to="/approvals" />
              <StatCard label="Critical / high open" value={o.critical_high_open} tone={o.critical_high_open ? "danger" : "neutral"} to="/work-orders?priority=critical&priority=high&open=1" />
              <StatCard label="Overdue" value={o.overdue} tone={o.overdue ? "danger" : "neutral"} to="/work-orders?overdue=1" />
              <StatCard label="Safety concerns open" value={o.safety_open} tone={o.safety_open ? "danger" : "neutral"} to="/work-orders?safety=1&open=1" />
              <StatCard label="Open work orders" value={o.open} tone="primary" hint={`${o.total} in total`} to="/work-orders?open=1" />
              <StatCard label="In progress" value={o.in_progress} to="/work-orders?status=in_progress" />
              <StatCard label="Blocked / awaiting parts" value={o.blocked} tone={o.blocked ? "warning" : "neutral"} to="/work-orders?status=blocked&status=awaiting_parts" />
              <StatCard label="Completion review" value={o.completion_review} tone={o.completion_review ? "warning" : "neutral"} to="/approvals?tab=completion" />
              <StatCard label="Completed, last 7 days" value={o.completed_7d} />
              <StatCard label="Closed (all time)" value={o.by_status.closed ?? 0} />
            </>
          ) : (
            Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-[84px]" />)
          )}
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card
          title="Needs a decision"
          actions={<Link to="/approvals" className="text-sm font-medium text-primary-700 hover:underline">Approvals</Link>}
          bodyClassName="p-0"
        >
          <ListBody query={attention} empty="Nothing is waiting on a supervisor." />
        </Card>
        <Card
          title="Overdue"
          actions={<Link to="/work-orders?overdue=1" className="text-sm font-medium text-primary-700 hover:underline">All overdue</Link>}
          bodyClassName="p-0"
        >
          <ListBody query={overdue} empty="No open work order is past its due time." />
        </Card>
      </div>
    </>
  );
}

function ListBody({
  query,
  empty,
}: {
  query: UseQueryResult<Page<WorkOrderSummary>>;
  empty: string;
}) {
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (!query.data?.items.length) return <EmptyState title={empty} />;
  return <WorkOrderTable items={query.data.items} compact showAssignee={false} />;
}
