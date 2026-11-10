import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { describeChange, entryTitle } from "../components/Timeline";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader, Pagination, Table, Td, Th, cx, plainInputClass } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { auditApi } from "../services";
import type { AuditEntry } from "../types/api";

const ENTITY_TYPES = [
  ["", "Everything"],
  ["work_order", "Work orders"],
  ["handover", "Handovers"],
  ["equipment", "Equipment"],
  ["checklist_template", "Checklist templates"],
  ["user", "Accounts"],
] as const;

function entityLink(e: AuditEntry): string | null {
  if (e.entity_type === "work_order") return `/work-orders/${e.entity_id}`;
  if (e.entity_type === "handover") return `/handovers/${e.entity_id}`;
  if (e.entity_type === "equipment") return `/equipment/${e.entity_id}`;
  return null;
}

export function AuditPage() {
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const params = { entity_type: entityType || undefined, page, page_size: 50 };
  const query = useQuery({
    queryKey: queryKeys.audit(params),
    queryFn: () => auditApi.list(params),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Append-only record of every change, newest first. Rows cannot be edited or deleted."
        actions={
          <select
            aria-label="Record type"
            className={cx(plainInputClass, "w-auto")}
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value);
              setPage(1);
            }}
          >
            {ENTITY_TYPES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        }
      />
      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <LoadingState />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState title="No audit entries" />
        ) : (
          <>
            <Table minWidth={760}>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Who</Th>
                  <Th>What</Th>
                  <Th>Details</Th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((e) => {
                  const link = entityLink(e);
                  return (
                    <tr key={e.id}>
                      <Td className="whitespace-nowrap text-xs text-ink-muted">{formatDateTime(e.timestamp)}</Td>
                      <Td className="whitespace-nowrap text-sm">{e.actor?.name ?? "System"}</Td>
                      <Td className="text-sm">
                        <p className="font-medium">{entryTitle(e)}</p>
                        {link ? (
                          <Link to={link} className="text-xs text-primary-700 hover:underline">
                            Open {e.entity_type.replace("_", " ")}
                          </Link>
                        ) : (
                          <p className="text-xs text-ink-muted">{e.entity_type.replace("_", " ")}</p>
                        )}
                      </Td>
                      <Td className="text-xs text-ink-muted">
                        {(e.action === "work_order.transition" ? [] : describeChange(e)).map((line) => (
                          <p key={line}>{line}</p>
                        ))}
                        {e.comment && <p className="mt-0.5 text-ink">“{e.comment}”</p>}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={query.data.page} pageSize={query.data.page_size} total={query.data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  );
}
