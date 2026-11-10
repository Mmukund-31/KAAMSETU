import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Circle, CircleSlash, Mic, Type, XCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ActionBar } from "../components/WorkOrderActions";
import { Timeline } from "../components/Timeline";
import { CategoryBadge, NeutralBadge, OverdueBadge, PriorityBadge, SafetyBadge, StatusBadge } from "../components/badges";
import { Button, Card, DefinitionList, ErrorState, InlineError, LoadingState, PageHeader, cx } from "../components/ui";
import { ApiError } from "../lib/api";
import {
  CATEGORY_LABEL,
  IMPACT_LABEL,
  LANGUAGE_LABEL,
  PRIORITY_LABEL,
  RESPONSE_LABEL,
  formatDateTime,
  humanize,
  relativeTime,
} from "../lib/format";
import { WORK_ORDER_DEPENDENTS, queryKeys } from "../lib/queryKeys";
import { workOrdersApi } from "../services";
import type { Checklist, ChecklistItem, Evidence, LanguageCode, WorkOrderDetail } from "../types/api";

export function WorkOrderDetailPage() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: queryKeys.workOrder(id),
    queryFn: () => workOrdersApi.get(id),
    refetchInterval: 15_000,
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Card>
        {notFound ? (
          <div className="py-10 text-center">
            <p className="text-sm font-medium text-ink">Work order not found</p>
            <p className="mt-1 text-sm text-ink-muted">It does not exist or belongs to another site.</p>
            <Link to="/work-orders" className="mt-4 inline-block text-sm font-medium text-primary-700 hover:underline">
              Back to work orders
            </Link>
          </div>
        ) : (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        )}
      </Card>
    );
  }
  const wo = query.data!;

  return (
    <>
      <Link to="/work-orders" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Work orders
      </Link>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {wo.display_number}
            <span className="font-mono text-base font-semibold text-ink-muted">{wo.equipment.code}</span>
          </span>
        }
        description={`${wo.equipment.name}${wo.equipment.location ? ` · ${wo.equipment.location}` : ""}`}
      />
      <div className="-mt-3 mb-5 flex flex-wrap gap-1.5">
        <StatusBadge status={wo.status} />
        <PriorityBadge priority={wo.priority} />
        {wo.safety_concern && <SafetyBadge />}
        {wo.is_overdue && <OverdueBadge />}
        <CategoryBadge category={wo.issue_category} />
        {wo.equipment.is_critical && <NeutralBadge>Critical equipment</NeutralBadge>}
      </div>

      <Card className="mb-6" title="Actions">
        <ActionBar wo={wo} />
      </Card>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <div className="grid gap-6 lg:grid-cols-2">
            <EvidenceCard evidence={wo.evidence} channel={wo.report_channel} />
            <ExtractedCard wo={wo} />
          </div>
          <ChecklistSection wo={wo} />
        </div>
        <div className="space-y-6">
          <AssignmentCard wo={wo} />
          <Card title="History">
            <Timeline entries={wo.history} />
          </Card>
        </div>
      </div>
    </>
  );
}

// ── what the technician said ────────────────────────────────────────────
function languageName(code: string | null | undefined): string {
  if (!code) return "—";
  return LANGUAGE_LABEL[code as LanguageCode] ?? code;
}

const UTTERANCE_KIND: Record<string, string> = {
  voice: "Spoken report",
  text: "Typed report",
  correction: "Transcript correction",
  follow_up_voice: "Spoken answer",
  follow_up_text: "Typed answer",
};

function EvidenceCard({ evidence, channel }: { evidence: Evidence | null; channel: WorkOrderDetail["report_channel"] }) {
  if (!evidence) {
    return (
      <Card title="Original report">
        <p className="text-sm text-ink-muted">
          {channel === "seed" ? "Synthetic historical record from the seed script; no transcript." : "No evidence stored."}
        </p>
      </Card>
    );
  }
  const followUps = evidence.utterances.slice(1);
  return (
    <Card
      title={
        <span className="flex items-center gap-1.5">
          {channel === "voice" ? <Mic className="h-4 w-4" /> : <Type className="h-4 w-4" />}
          What the technician said
        </span>
      }
    >
      <blockquote className="rounded-md border border-line bg-surface-subtle px-3 py-2.5 text-sm leading-relaxed text-ink" lang={evidence.detected_language ?? undefined}>
        {evidence.original_transcript}
      </blockquote>
      <p className="mt-2 text-xs text-ink-muted">
        Verbatim {channel === "voice" ? "Gnani Prisma transcript" : "typed text"}, stored as immutable evidence.
      </p>
      {followUps.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Later inputs</p>
          {followUps.map((u, i) => (
            <div key={i} className="rounded-md border border-line px-3 py-2">
              <p className="text-xs text-ink-muted">
                {UTTERANCE_KIND[u.kind] ?? humanize(u.kind)}
                {u.field ? ` · ${humanize(u.field)}` : ""}
              </p>
              <p className="text-sm text-ink">{u.text}</p>
            </div>
          ))}
        </div>
      )}
      <div className="mt-4">
        <DefinitionList
          items={[
            ["Language chosen", languageName(evidence.selected_language)],
            ...(evidence.prisma_request_id
              ? ([
                  ["Detected", evidence.detected_language ?? "—"],
                  ["Speech model", evidence.prisma_model ?? "—"],
                  ["Prisma request", <span className="break-all font-mono text-xs">{evidence.prisma_request_id}</span>],
                ] as [string, React.ReactNode][])
              : []),
          ]}
        />
      </div>
    </Card>
  );
}

// ── what the system understood ──────────────────────────────────────────
function ExtractedCard({ wo }: { wo: WorkOrderDetail }) {
  const validated = (wo.evidence?.validated ?? {}) as {
    category_basis?: string;
    priority?: { explanation?: string; rule_id?: string };
  };
  return (
    <Card title="Structured work order">
      <p className="text-sm text-ink">{wo.issue_description}</p>
      {wo.symptoms.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {wo.symptoms.map((s) => (
            <NeutralBadge key={s}>{humanize(s)}</NeutralBadge>
          ))}
        </div>
      )}
      <div className="mt-4">
        <DefinitionList
          items={[
            ["Equipment", `${wo.equipment.code} · ${wo.equipment.name}`],
            ["Category", `${CATEGORY_LABEL[wo.issue_category]}${validated.category_basis ? ` (from ${validated.category_basis})` : ""}`],
            ["Production", IMPACT_LABEL[wo.production_impact]],
            ["Safety concern", wo.safety_concern ? "Yes" : "No"],
            ["Priority", PRIORITY_LABEL[wo.priority]],
            ["Priority rule", wo.priority_rule ?? "—"],
            ["Location", wo.location_note ?? wo.equipment.location ?? "—"],
            ["Reported", `${wo.reporter.name} · ${formatDateTime(wo.created_at)}`],
            ["Due", wo.due_at ? `${formatDateTime(wo.due_at)} (${relativeTime(wo.due_at)})` : "—"],
            ["Closed", formatDateTime(wo.closed_at)],
          ]}
        />
      </div>
      {validated.priority?.explanation && (
        <p className="mt-4 rounded-md bg-surface-subtle px-3 py-2 text-xs text-ink-muted">
          Why this priority: {validated.priority.explanation.replace(/\.+$/, "")}. Priority comes from configured site
          rules, not a diagnosis.
        </p>
      )}
    </Card>
  );
}

// ── assignment ──────────────────────────────────────────────────────────
function AssignmentCard({ wo }: { wo: WorkOrderDetail }) {
  return (
    <Card title="Assignment">
      {wo.assignee ? (
        <p className="text-sm text-ink">
          <span className="font-medium">{wo.assignee.name}</span>
        </p>
      ) : (
        <p className="text-sm text-ink-muted">Not assigned yet.</p>
      )}
      {wo.assignments.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-line pt-3">
          {[...wo.assignments].reverse().map((a, i) => (
            <li key={i} className="text-xs text-ink-muted">
              <span className="font-medium text-ink">{a.technician.name}</span> by {a.assigned_by.name} ·{" "}
              {formatDateTime(a.assigned_at)}
              {a.comments && <p className="mt-0.5 text-ink">“{a.comments}”</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ── checklist ───────────────────────────────────────────────────────────
function ChecklistSection({ wo }: { wo: WorkOrderDetail }) {
  const client = useQueryClient();
  const attach = useMutation({
    mutationFn: () => workOrdersApi.attachChecklist(wo.id),
    onSuccess: () => {
      for (const key of WORK_ORDER_DEPENDENTS) void client.invalidateQueries({ queryKey: [...key] });
    },
  });
  // backend services/checklists.py ATTACHABLE
  const canAttach = ["approved", "assigned", "in_progress", "blocked", "awaiting_parts", "reopened"].includes(wo.status);

  if (wo.checklists.length === 0) {
    return (
      <Card title="SOP checklist">
        <p className="text-sm text-ink-muted">
          No checklist yet. The active template for this equipment category is attached when a technician is assigned.
        </p>
        {canAttach && (
          <Button className="mt-3" size="sm" loading={attach.isPending} onClick={() => attach.mutate()}>
            Attach checklist now
          </Button>
        )}
        <div className="mt-3">
          <InlineError error={attach.error} />
        </div>
      </Card>
    );
  }
  return (
    <>
      {wo.checklists.map((c) => (
        <ChecklistCard key={c.id} checklist={c} />
      ))}
    </>
  );
}

function ResponseIcon({ item }: { item: ChecklistItem }) {
  const cls = "h-4 w-4 shrink-0";
  if (item.response === "done") return <CheckCircle2 className={cx(cls, "text-primary-700")} aria-label="Done" />;
  if (item.response === "failed") return <XCircle className={cx(cls, "text-red-700")} aria-label="Failed" />;
  if (item.response === "not_applicable") return <CircleSlash className={cx(cls, "text-ink-muted")} aria-label="Not applicable" />;
  return <Circle className={cx(cls, "text-ink-faint")} aria-label="Not answered" />;
}

function ChecklistCard({ checklist: c }: { checklist: Checklist }) {
  const pct = c.items_total ? Math.round((c.items_answered / c.items_total) * 100) : 0;
  return (
    <Card
      title={`SOP checklist · ${c.template_name} (v${c.template_version})`}
      actions={
        <span className={cx("text-xs font-medium", c.is_complete ? "text-primary-700" : "text-amber-800")}>
          {c.is_complete ? "Mandatory steps complete" : `${c.mandatory_done}/${c.mandatory_total} mandatory done`}
        </span>
      }
    >
      <div className="mb-4">
        <div className="mb-1 flex justify-between text-xs text-ink-muted">
          <span>
            {c.items_answered} of {c.items_total} steps answered
          </span>
          <span>{pct}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface-sunken" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Checklist progress">
          <div className="h-full rounded-full bg-primary-600" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <ol className="divide-y divide-line">
        {c.items.map((item) => (
          <li key={item.id} className="flex gap-3 py-2.5">
            <ResponseIcon item={item} />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-ink">
                {item.sequence}. {item.description}
                {item.is_mandatory && <span className="ml-1.5 text-xs font-medium text-red-700">Mandatory</span>}
              </p>
              {item.response && (
                <p className="mt-0.5 text-xs text-ink-muted">
                  {RESPONSE_LABEL[item.response]}
                  {item.completed_by ? ` · ${item.completed_by.name}` : ""}
                  {item.completed_at ? ` · ${formatDateTime(item.completed_at)}` : ""}
                </p>
              )}
              {item.notes && <p className="mt-0.5 text-sm text-ink">“{item.notes}”</p>}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-ink-muted">
        Steps are recorded by the assigned technician in the mobile app. Template content is company-approved SOP text.
      </p>
    </Card>
  );
}
