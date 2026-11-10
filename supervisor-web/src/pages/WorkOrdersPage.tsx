import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { WorkOrderTable } from "../components/WorkOrderTable";
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, Pagination, cx, plainInputClass } from "../components/ui";
import { OPEN_STATUSES, PRIORITY_LABEL, PRIORITY_ORDER, STATUS_LABEL, STATUS_ORDER } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { workOrdersApi, type WorkOrderFilters } from "../services";
import type { Priority, WorkOrderSort, WorkOrderStatus } from "../types/api";

const PAGE_SIZE = 20;

const SORTS: { value: WorkOrderSort; label: string }[] = [
  { value: "created_desc", label: "Newest first" },
  { value: "priority", label: "Priority" },
  { value: "due_asc", label: "Due soonest" },
  { value: "updated_desc", label: "Recently updated" },
  { value: "created_asc", label: "Oldest first" },
];

/** Filters live in the URL so a filtered list can be bookmarked, shared and reached from dashboard tiles. */
export function filtersFromParams(params: URLSearchParams): WorkOrderFilters {
  const statuses = params.getAll("status").filter((s): s is WorkOrderStatus => s in STATUS_LABEL);
  const open = params.get("open") === "1";
  return {
    status: statuses.length ? statuses : open ? OPEN_STATUSES : undefined,
    priority: params.getAll("priority").filter((p): p is Priority => p in PRIORITY_LABEL),
    assigned_to: params.get("assigned_to") ?? undefined,
    equipment_id: params.get("equipment_id") ?? undefined,
    overdue: params.get("overdue") === "1" || undefined,
    safety_only: params.get("safety") === "1" || undefined,
    q: params.get("q") ?? undefined,
    sort: (params.get("sort") as WorkOrderSort | null) ?? "created_desc",
    page: Number(params.get("page") ?? "1") || 1,
    page_size: PAGE_SIZE,
  };
}

export function WorkOrdersPage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => filtersFromParams(params), [params]);
  const [search, setSearch] = useState(filters.q ?? "");

  const query = useQuery({
    queryKey: queryKeys.workOrders(filters),
    queryFn: () => workOrdersApi.list(filters),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  function update(mutator: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(params);
    mutator(next);
    next.delete("page");
    setParams(next, { replace: true });
  }

  // Debounce the search box into the URL.
  useEffect(() => {
    const handle = setTimeout(() => {
      if ((params.get("q") ?? "") !== search.trim())
        update((next) => (search.trim() ? next.set("q", search.trim()) : next.delete("q")));
    }, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function toggle(key: string, value: string) {
    update((next) => {
      const values = next.getAll(key);
      next.delete(key);
      if (key === "status") next.delete("open");
      (values.includes(value) ? values.filter((v) => v !== value) : [...values, value]).forEach((v) =>
        next.append(key, v),
      );
    });
  }

  function flag(key: string) {
    update((next) => (next.get(key) === "1" ? next.delete(key) : next.set(key, "1")));
  }

  const activeStatuses = params.getAll("status");
  const activePriorities = params.getAll("priority");
  const hasFilters = [...params.keys()].some((k) => k !== "sort" && k !== "page");

  return (
    <>
      <PageHeader title="Work orders" description="Every reported fault at your site, from report to close." />

      {(params.get("assigned_to") || params.get("equipment_id")) && (
        <p className="mb-3 text-sm text-ink-muted">
          Showing orders for one {params.get("assigned_to") ? "technician" : "machine"}. Clear filters to see all.
        </p>
      )}
      <Card className="mb-4" bodyClassName="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-faint" aria-hidden />
            <input
              type="search"
              aria-label="Search work orders"
              placeholder="Search description, equipment code or WO-1001"
              className={cx(plainInputClass, "pl-8")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label="Sort"
            className={cx(plainInputClass, "w-auto")}
            value={filters.sort}
            onChange={(e) => update((next) => next.set("sort", e.target.value))}
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          {hasFilters && (
            <Button
              size="sm"
              variant="ghost"
              icon={<X className="h-4 w-4" />}
              onClick={() => {
                setSearch("");
                setParams(new URLSearchParams(), { replace: true });
              }}
            >
              Clear filters
            </Button>
          )}
        </div>

        <FilterRow label="Status">
          <Chip active={params.get("open") === "1"} onClick={() => update((next) => {
            next.delete("status");
            if (next.get("open") === "1") next.delete("open");
            else next.set("open", "1");
          })}>
            All open
          </Chip>
          {STATUS_ORDER.map((s) => (
            <Chip key={s} active={activeStatuses.includes(s)} onClick={() => toggle("status", s)}>
              {STATUS_LABEL[s]}
            </Chip>
          ))}
        </FilterRow>
        <FilterRow label="Priority">
          {PRIORITY_ORDER.map((p) => (
            <Chip key={p} active={activePriorities.includes(p)} onClick={() => toggle("priority", p)}>
              {PRIORITY_LABEL[p]}
            </Chip>
          ))}
          <span className="mx-1 h-5 w-px bg-line" aria-hidden />
          <Chip active={params.get("overdue") === "1"} onClick={() => flag("overdue")}>
            Overdue
          </Chip>
          <Chip active={params.get("safety") === "1"} onClick={() => flag("safety")}>
            Safety concern
          </Chip>
        </FilterRow>
      </Card>

      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <LoadingState />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState
            title="No work orders match"
            description={hasFilters ? "Try removing a filter." : "Reports from technicians will appear here."}
          />
        ) : (
          <>
            <WorkOrderTable items={query.data.items} />
            <Pagination
              page={query.data.page}
              pageSize={query.data.page_size}
              total={query.data.total}
              onPage={(page) => {
                const next = new URLSearchParams(params);
                next.set("page", String(page));
                setParams(next);
              }}
            />
          </>
        )}
      </Card>
    </>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      <span className="w-16 shrink-0 text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</span>
      {children}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "border-primary-700 bg-primary-700 text-white"
          : "border-line-strong bg-white text-ink-muted hover:border-ink-faint hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}
