import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, Table, Td, Th, cx } from "../components/ui";
import {
  CATEGORIES,
  CATEGORY_LABEL,
  PRIORITY_LABEL,
  PRIORITY_ORDER,
  STATUS_LABEL,
  STATUS_ORDER,
  formatShortDay,
} from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { dashboardApi } from "../services";

// Chart tokens (dataviz reference palette, categorical slots 1-4, validated on the light surface).
// Slots 3 and 4 are under 3:1 contrast, so every chart also has a table view.
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
const MAGNITUDE = "#2a78d6"; // single-hue bars: one measure per chart
const GRID = "#e2e8f0";
const AXIS_TEXT = "#475569";
const RANGES = [7, 30, 90] as const;

const axisProps = { tick: { fill: AXIS_TEXT, fontSize: 12 }, tickLine: false, axisLine: { stroke: GRID } };

export function AnalyticsPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const overview = useQuery({ queryKey: queryKeys.overview, queryFn: dashboardApi.overview });
  const trends = useQuery({ queryKey: queryKeys.trends(days), queryFn: () => dashboardApi.trends(days) });
  const issues = useQuery({ queryKey: queryKeys.equipmentIssues(days), queryFn: () => dashboardApi.equipmentIssues(days) });
  const workload = useQuery({ queryKey: queryKeys.workload, queryFn: dashboardApi.workload });

  const trendRows = (trends.data ?? []).map((p) => ({ ...p, label: formatShortDay(p.day) }));
  const priorityRows = PRIORITY_ORDER.map((p) => ({ label: PRIORITY_LABEL[p], value: overview.data?.by_priority_open[p] ?? 0 }));
  const statusRows = STATUS_ORDER.map((s) => ({ label: STATUS_LABEL[s], value: overview.data?.by_status[s] ?? 0 })).filter(
    (r) => r.value > 0,
  );
  const categoryRows = CATEGORIES.map((c) => ({ label: CATEGORY_LABEL[c], value: issues.data?.by_category[c] ?? 0 })).filter(
    (r) => r.value > 0,
  );
  const symptomRows = (issues.data?.by_symptom ?? []).slice(0, 10).map((s) => ({ label: s.label, value: s.count }));
  const workloadRows = (workload.data ?? []).map((w) => ({
    label: w.technician.name,
    Assigned: w.assigned,
    "In progress": w.in_progress,
    "Blocked / parts": w.blocked,
    "Completion review": w.completion_review,
  }));
  const workloadKeys = ["Assigned", "In progress", "Blocked / parts", "Completion review"] as const;

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Every number is a SQL aggregate over your site's work orders."
        actions={
          <div role="group" aria-label="Time range" className="inline-flex rounded-md border border-line-strong bg-white p-0.5">
            {RANGES.map((r) => (
              <button
                key={r}
                aria-pressed={days === r}
                onClick={() => setDays(r)}
                className={cx(
                  "rounded px-3 py-1 text-sm font-medium",
                  days === r ? "bg-primary-700 text-white" : "text-ink-muted hover:text-ink",
                )}
              >
                {r} days
              </button>
            ))}
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title={`Work orders created and closed per day, last ${days} days`}
          className="lg:col-span-2"
          query={trends}
          empty={!trendRows.some((r) => r.created || r.closed)}
          table={
            <SimpleTable
              head={["Day", "Created", "Closed"]}
              rows={[...trendRows].reverse().filter((r) => r.created || r.closed).map((r) => [r.label, r.created, r.closed])}
            />
          }
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trendRows} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="label" {...axisProps} minTickGap={24} />
              <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
              <Tooltip cursor={{ stroke: AXIS_TEXT, strokeDasharray: "3 3" }} />
              <Legend itemSorter={null} iconType="plainline" wrapperStyle={{ fontSize: 12, color: AXIS_TEXT }} />
              <Line type="linear" dataKey="created" name="Created" stroke={SERIES[0]} strokeWidth={2} dot={days <= 30 ? { r: 2 } : false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
              <Line type="linear" dataKey="closed" name="Closed" stroke={SERIES[1]} strokeWidth={2} dot={days <= 30 ? { r: 2 } : false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Open work orders by priority"
          query={overview}
          empty={!priorityRows.some((r) => r.value)}
          emptyText="No open work orders right now"
          table={<SimpleTable head={["Priority", "Open"]} rows={priorityRows.map((r) => [r.label, r.value])} />}
        >
          <HorizontalBars rows={priorityRows} name="Open" />
        </ChartCard>

        <ChartCard
          title="All work orders by status"
          query={overview}
          empty={!statusRows.length}
          table={<SimpleTable head={["Status", "Work orders"]} rows={statusRows.map((r) => [r.label, r.value])} />}
        >
          <HorizontalBars rows={statusRows} name="Work orders" />
        </ChartCard>

        <ChartCard
          title={`Faults by category, last ${days} days`}
          query={issues}
          empty={!categoryRows.length}
          table={<SimpleTable head={["Category", "Work orders"]} rows={categoryRows.map((r) => [r.label, r.value])} />}
        >
          <HorizontalBars rows={categoryRows} name="Work orders" />
        </ChartCard>

        <ChartCard
          title={`Most reported symptoms, last ${days} days`}
          query={issues}
          empty={!symptomRows.length}
          table={<SimpleTable head={["Symptom", "Reports"]} rows={symptomRows.map((r) => [r.label, r.value])} />}
        >
          <HorizontalBars rows={symptomRows} name="Reports" />
        </ChartCard>

        <ChartCard
          title="Technician workload (open work)"
          className="lg:col-span-2"
          query={workload}
          empty={!(workload.data ?? []).some((w) => w.open_total > 0)}
          emptyText="No technician has open work right now"
          table={
            <SimpleTable
              head={["Technician", ...workloadKeys]}
              rows={workloadRows.map((r) => [r.label, ...workloadKeys.map((k) => r[k])])}
            />
          }
        >
          <ResponsiveContainer width="100%" height={Math.max(160, workloadRows.length * 48 + 60)}>
            <BarChart data={workloadRows} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }} barCategoryGap={12}>
              <CartesianGrid stroke={GRID} horizontal={false} />
              <XAxis type="number" allowDecimals={false} {...axisProps} />
              <YAxis type="category" dataKey="label" width={110} {...axisProps} axisLine={false} />
              <Tooltip cursor={{ fill: "#f1f5f9" }} />
              <Legend itemSorter={null} wrapperStyle={{ fontSize: 12, color: AXIS_TEXT }} />
              {workloadKeys.map((key, i) => (
                // white stroke = the 2px surface gap between stacked segments
                <Bar key={key} dataKey={key} stackId="w" fill={SERIES[i]} stroke="#fff" strokeWidth={2} maxBarSize={22} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <Card title={`Recurring equipment issues, last ${days} days`} className="lg:col-span-2" bodyClassName="p-0">
          {issues.isLoading ? (
            <LoadingState />
          ) : issues.isError ? (
            <ErrorState error={issues.error} onRetry={() => void issues.refetch()} />
          ) : !issues.data?.equipment.length ? (
            <EmptyState title="No equipment faults in this period" />
          ) : (
            <Table minWidth={640}>
              <thead>
                <tr>
                  <Th>Equipment</Th>
                  <Th>Category</Th>
                  <Th className="text-right">Work orders</Th>
                  <Th className="text-right">Open</Th>
                  <Th>Top symptoms</Th>
                </tr>
              </thead>
              <tbody>
                {issues.data.equipment.map((e) => (
                  <tr key={e.equipment_id}>
                    <Td>
                      <Link to={`/equipment/${e.equipment_id}`} className="font-mono text-xs font-semibold text-primary-700 hover:underline">
                        {e.code}
                      </Link>
                      <p className="text-xs text-ink-muted">
                        {e.name}
                        {e.recurring && <span className="ml-1.5 font-medium text-amber-800">· Recurring</span>}
                      </p>
                    </Td>
                    <Td className="text-sm">{CATEGORY_LABEL[e.category]}</Td>
                    <Td className="text-right tabular-nums">{e.work_orders}</Td>
                    <Td className="text-right tabular-nums">{e.open}</Td>
                    <Td className="text-sm text-ink-muted">
                      {e.top_symptoms.map((s) => `${s.label} (${s.count})`).join(", ") || "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}

function HorizontalBars({ rows, name }: { rows: { label: string; value: number }[]; name: string }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, rows.length * 34 + 30)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 32, bottom: 0, left: 8 }} barCategoryGap={8}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" allowDecimals={false} {...axisProps} />
        <YAxis type="category" dataKey="label" width={130} {...axisProps} axisLine={false} />
        <Tooltip cursor={{ fill: "#f1f5f9" }} />
        <Bar
          dataKey="value"
          name={name}
          fill={MAGNITUDE}
          radius={[0, 4, 4, 0]}
          maxBarSize={20}
          label={{ position: "right", fill: AXIS_TEXT, fontSize: 12 }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

function ChartCard({
  title,
  query,
  empty,
  emptyText = "No data for this period",
  table,
  children,
  className,
}: {
  title: string;
  query: { isLoading: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  empty: boolean;
  emptyText?: string;
  table: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card
      title={title}
      className={className}
      actions={
        <button
          className="text-xs font-medium text-primary-700 hover:underline"
          onClick={() => setAsTable((v) => !v)}
          aria-pressed={asTable}
        >
          {asTable ? "Show chart" : "Show table"}
        </button>
      }
    >
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : empty ? (
        <EmptyState title={emptyText} />
      ) : asTable ? (
        table
      ) : (
        children
      )}
    </Card>
  );
}

function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <Table minWidth={280}>
      <thead>
        <tr>
          {head.map((h, i) => (
            <Th key={h} className={i > 0 ? "text-right" : undefined}>
              {h}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={r}>
            {row.map((cell, i) => (
              <Td key={i} className={i > 0 ? "text-right tabular-nums" : undefined}>
                {cell}
              </Td>
            ))}
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
