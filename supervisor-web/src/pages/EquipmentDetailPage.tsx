import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { CategoryBadge, NeutralBadge } from "../components/badges";
import { WorkOrderTable } from "../components/WorkOrderTable";
import { Card, DefinitionList, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from "../components/ui";
import { OPERATIONAL_LABEL, formatDate } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { equipmentApi } from "../services";

export function EquipmentDetailPage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: queryKeys.equipment(id), queryFn: () => equipmentApi.get(id) });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <Card><ErrorState error={query.error} onRetry={() => void query.refetch()} /></Card>;
  const e = query.data!;
  const maxFault = Math.max(1, ...e.recurring_faults.map((f) => f.count));

  return (
    <>
      <Link to="/equipment" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Equipment
      </Link>
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <span className="font-mono">{e.code}</span>
            <span className="text-ink-muted">{e.name}</span>
          </span>
        }
      />
      <div className="-mt-3 mb-5 flex flex-wrap gap-1.5">
        <CategoryBadge category={e.category} />
        <NeutralBadge>{OPERATIONAL_LABEL[e.operational_status]}</NeutralBadge>
        {e.is_critical && <NeutralBadge>Critical equipment</NeutralBadge>}
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Open work orders" value={e.open_work_orders} tone={e.open_work_orders ? "warning" : "neutral"} />
        <StatCard label="Work orders, 90 days" value={e.work_orders_90d} />
        <StatCard label="Work orders, all time" value={e.work_orders_total} />
        <StatCard label="Recurring faults" value={e.recurring_faults.filter((f) => f.count > 1).length} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Details">
          <DefinitionList
            items={[
              ["Site", e.site_name],
              ["Location", e.location ?? "—"],
              ["Registered", formatDate(e.created_at)],
            ]}
          />
        </Card>
        <Card title="Fault history by symptom" className="lg:col-span-2">
          {e.recurring_faults.length === 0 ? (
            <p className="text-sm text-ink-muted">No symptoms recorded for this machine.</p>
          ) : (
            <ul className="space-y-2.5">
              {e.recurring_faults.map((f) => (
                <li key={f.symptom}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-ink">
                      {f.label}
                      {f.count > 1 && <span className="ml-1.5 text-xs font-medium text-amber-800">Recurring</span>}
                    </span>
                    <span className="tabular-nums text-ink-muted">{f.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-surface-sunken" aria-hidden>
                    <div className="h-full rounded-full bg-[#2a78d6]" style={{ width: `${(f.count / maxFault) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Recent work orders" className="mt-6" bodyClassName="p-0">
        {e.recent_work_orders.length ? (
          <WorkOrderTable items={e.recent_work_orders} />
        ) : (
          <EmptyState title="No work orders for this machine yet" />
        )}
      </Card>
    </>
  );
}
