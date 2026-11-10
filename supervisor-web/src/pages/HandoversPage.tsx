import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { NeutralBadge } from "../components/badges";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineError,
  LoadingState,
  Modal,
  PageHeader,
  Pagination,
  Table,
  Td,
  TextAreaField,
  TextField,
  Th,
  cx,
} from "../components/ui";
import { formatDateTime } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { handoversApi } from "../services";
import type { HandoverStatus } from "../types/api";

const STATUS_STYLE: Record<HandoverStatus, string> = {
  draft: "text-ink-muted",
  submitted: "text-amber-800",
  reviewed: "text-primary-700",
};
const STATUS_TEXT: Record<HandoverStatus, string> = { draft: "Draft", submitted: "Awaiting review", reviewed: "Reviewed" };

export function HandoversPage() {
  const [status, setStatus] = useState<HandoverStatus | "">("submitted");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const params = { status: status || undefined, page, page_size: 20 };
  const query = useQuery({
    queryKey: queryKeys.handovers(params),
    queryFn: () => handoversApi.list(params),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="Shift handovers"
        description="Summaries are built from work-order records plus the author's own notes. Nothing is invented."
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setCreating(true)}>
            Write handover
          </Button>
        }
      />
      <div role="tablist" aria-label="Handover status" className="mb-4 flex gap-1 border-b border-line">
        {(
          [
            ["submitted", "Awaiting review"],
            ["reviewed", "Reviewed"],
            ["", "All"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={label}
            role="tab"
            aria-selected={status === value}
            onClick={() => {
              setStatus(value);
              setPage(1);
            }}
            className={cx(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              status === value ? "border-primary-700 text-primary-800" : "border-transparent text-ink-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <Card bodyClassName="p-0">
        {query.isLoading ? (
          <LoadingState />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !query.data?.items.length ? (
          <EmptyState title="No handovers here" description="Technicians submit handovers from the mobile app at the end of a shift." />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Shift</Th>
                  <Th>Author</Th>
                  <Th>Submitted</Th>
                  <Th>Summary</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((h) => {
                  const c = h.generated_summary.counts;
                  return (
                    <tr key={h.id} className="hover:bg-surface-subtle">
                      <Td>
                        <Link to={`/handovers/${h.id}`} className="font-medium text-primary-700 hover:underline">
                          {h.shift_identifier}
                        </Link>
                      </Td>
                      <Td className="text-sm">{h.created_by.name}</Td>
                      <Td className="whitespace-nowrap text-sm text-ink-muted">{formatDateTime(h.created_at)}</Td>
                      <Td>
                        <div className="flex flex-wrap gap-1">
                          {c && (
                            <>
                              <NeutralBadge>{c.completed} completed</NeutralBadge>
                              <NeutralBadge>{c.pending} pending</NeutralBadge>
                              {c.blocked > 0 && <NeutralBadge>{c.blocked} blocked</NeutralBadge>}
                            </>
                          )}
                          <NeutralBadge>{h.pending_actions.length} actions</NeutralBadge>
                        </div>
                      </Td>
                      <Td className={cx("text-sm font-medium", STATUS_STYLE[h.status])}>{STATUS_TEXT[h.status]}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination page={query.data.page} pageSize={query.data.page_size} total={query.data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {creating && <CreateHandoverDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function defaultShift(): string {
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  return `${date} ${now.getHours() < 14 ? "A" : now.getHours() < 22 ? "B" : "C"}`;
}

function CreateHandoverDialog({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [shift, setShift] = useState(defaultShift);
  const [notes, setNotes] = useState("");
  const mutation = useMutation({
    mutationFn: () => handoversApi.create({ shift_identifier: shift.trim(), notes: notes.trim() }),
    onSuccess: (h) => {
      void client.invalidateQueries({ queryKey: ["handovers"] });
      navigate(`/handovers/${h.id}`);
    },
  });
  return (
    <Modal
      open
      title="Write a shift handover"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={mutation.isPending} disabled={!shift.trim() || !notes.trim()} onClick={() => mutation.mutate()}>
            Submit handover
          </Button>
        </>
      }
    >
      <TextField label="Shift" required value={shift} onChange={(e) => setShift(e.target.value)} maxLength={64} />
      <TextAreaField
        label="Notes for the next shift"
        required
        rows={6}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        maxLength={4000}
        hint="Sentences with words like “check”, “follow up” or “pending” become next-shift actions. The rest are kept as observations."
      />
      <InlineError error={mutation.error} />
    </Modal>
  );
}
