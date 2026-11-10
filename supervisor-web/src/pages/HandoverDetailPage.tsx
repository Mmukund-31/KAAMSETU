import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useCurrentUser } from "../auth/AuthContext";
import { PriorityBadge, StatusBadge } from "../components/badges";
import { Timeline } from "../components/Timeline";
import { Button, Card, ErrorState, InlineError, LoadingState, PageHeader, TextAreaField, cx, plainInputClass } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { queryKeys } from "../lib/queryKeys";
import { handoversApi } from "../services";
import type { HandoverDetail, HandoverOrderBrief, PendingAction } from "../types/api";

export function HandoverDetailPage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: queryKeys.handover(id), queryFn: () => handoversApi.get(id) });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <Card><ErrorState error={query.error} onRetry={() => void query.refetch()} /></Card>;
  const h = query.data!;
  const s = h.generated_summary;

  return (
    <>
      <Link to="/handovers" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Handovers
      </Link>
      <PageHeader
        title={`Handover · ${h.shift_identifier}`}
        description={`${h.created_by.name} · ${formatDateTime(h.created_at)}${s.window_hours ? ` · covers the last ${s.window_hours} h` : ""}`}
      />

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Original notes">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{h.original_notes}</p>
              <p className="mt-2 text-xs text-ink-muted">Kept exactly as written or transcribed.</p>
            </Card>
            <Card title="From the notes">
              <NoteList title="Next-shift actions" items={s.next_shift_actions} empty="No action sentences found." />
              <div className="mt-4">
                <NoteList title="Observations" items={s.observations} empty="None." />
              </div>
            </Card>
          </div>

          <Card title="From the work-order records">
            <div className="grid gap-5 md:grid-cols-2">
              <OrderGroup title="Completed this shift" items={s.completed} />
              <OrderGroup title="Still open" items={s.pending} />
              <OrderGroup title="Blocked or awaiting parts" items={s.blocked} />
              <OrderGroup title="Awaiting approval" items={s.awaiting_approval} />
            </div>
            {!!s.equipment_attention?.length && (
              <div className="mt-5 border-t border-line pt-4">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">Equipment needing attention</p>
                <ul className="space-y-1 text-sm">
                  {s.equipment_attention.map((e) => (
                    <li key={e.code}>
                      <span className="font-mono font-semibold">{e.code}</span> {e.name}
                      <span className="text-ink-muted"> · {e.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <ReviewCard h={h} />
          <Card title="History">
            <Timeline entries={h.history} />
          </Card>
        </div>
      </div>
    </>
  );
}

function NoteList({ title, items, empty }: { title: string; items?: string[]; empty: string }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">{title}</p>
      {items?.length ? (
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
          {items.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-muted">{empty}</p>
      )}
    </div>
  );
}

function OrderGroup({ title, items }: { title: string; items?: HandoverOrderBrief[] }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">
        {title} <span className="tabular-nums">({items?.length ?? 0})</span>
      </p>
      {items?.length ? (
        <ul className="space-y-1.5">
          {items.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-1.5 text-sm">
              <Link to={`/work-orders/${w.id}`} className="font-medium text-primary-700 hover:underline">
                {w.number}
              </Link>
              <span className="font-mono text-xs">{w.equipment_code}</span>
              <StatusBadge status={w.status} />
              <PriorityBadge priority={w.priority} />
              {w.assignee && <span className="text-xs text-ink-muted">{w.assignee}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-muted">None.</p>
      )}
    </div>
  );
}

function ReviewCard({ h }: { h: HandoverDetail }) {
  const user = useCurrentUser();
  const client = useQueryClient();
  const [actions, setActions] = useState<PendingAction[]>(h.pending_actions);
  const [draft, setDraft] = useState("");
  const [comment, setComment] = useState("");
  const isAuthor = h.created_by.id === user.id;
  const reviewed = h.status === "reviewed";

  const mutation = useMutation({
    mutationFn: () => handoversApi.review(h.id, { comment: comment.trim() || undefined, pending_actions: actions }),
    onSuccess: (detail) => {
      client.setQueryData(queryKeys.handover(h.id), detail);
      void client.invalidateQueries({ queryKey: ["handovers", "list"] });
    },
  });

  const editable = !reviewed && !isAuthor;

  return (
    <Card title="Pending actions and review">
      {actions.length === 0 && <p className="text-sm text-ink-muted">No pending actions.</p>}
      <ul className="space-y-2">
        {actions.map((a, i) => (
          <li key={i} className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-line-strong"
              checked={a.done}
              disabled={!editable}
              aria-label={`Mark "${a.text}" done`}
              onChange={(e) => setActions((list) => list.map((x, j) => (j === i ? { ...x, done: e.target.checked } : x)))}
            />
            <div className="min-w-0 flex-1">
              <p className={cx("text-sm", a.done ? "text-ink-muted line-through" : "text-ink")}>{a.text}</p>
              <p className="text-xs text-ink-faint">
                {a.source === "notes" ? "From the notes" : a.source === "system" ? "From records" : "Added by supervisor"}
              </p>
            </div>
            {editable && a.source === "supervisor" && (
              <button
                className="rounded p-1 text-ink-faint hover:text-red-700"
                aria-label="Remove action"
                onClick={() => setActions((list) => list.filter((_, j) => j !== i))}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </li>
        ))}
      </ul>

      {editable && (
        <>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!draft.trim()) return;
              setActions((list) => [...list, { text: draft.trim(), source: "supervisor", work_order_id: null, done: false }]);
              setDraft("");
            }}
          >
            <input
              className={plainInputClass}
              placeholder="Add an action for the next shift"
              aria-label="New action"
              value={draft}
              maxLength={500}
              onChange={(e) => setDraft(e.target.value)}
            />
            <Button type="submit" size="md" icon={<Plus className="h-4 w-4" />} aria-label="Add action" />
          </form>
          <div className="mt-4">
            <TextAreaField label="Review comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} />
          </div>
          <Button className="mt-3 w-full" variant="primary" loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Mark reviewed
          </Button>
          <div className="mt-3">
            <InlineError error={mutation.error} />
          </div>
        </>
      )}

      {reviewed && (
        <p className="mt-4 rounded-md bg-primary-50 px-3 py-2 text-sm text-primary-800">
          Reviewed by {h.reviewed_by?.name} · {formatDateTime(h.reviewed_at)}
          {h.review_comment && <span className="mt-1 block text-ink">“{h.review_comment}”</span>}
        </p>
      )}
      {!reviewed && isAuthor && (
        <p className="mt-4 text-sm text-ink-muted">You wrote this handover, so another supervisor reviews it.</p>
      )}
    </Card>
  );
}
