import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  CATEGORIES,
  CATEGORY_LABEL,
  IMPACT_LABEL,
  LANGUAGE_LABEL,
  PRIORITY_LABEL,
  PRIORITY_ORDER,
  STATUS_LABEL,
  blockedReasonText,
} from "../lib/format";
import { WORK_ORDER_DEPENDENTS, queryKeys } from "../lib/queryKeys";
import { usersApi, workOrdersApi } from "../services";
import type {
  AllowedAction,
  EquipmentCategory,
  Priority,
  ProductionImpact,
  WorkOrderDetail,
  WorkOrderStatus,
} from "../types/api";
import { Button, InlineError, Modal, SelectField, TextAreaField, TextField } from "./ui";

/** Applies a work-order mutation result to the cache and refreshes everything that depends on it. */
export function useWorkOrderMutation<TVars>(id: string, fn: (vars: TVars) => Promise<WorkOrderDetail>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (detail) => {
      client.setQueryData(queryKeys.workOrder(id), detail);
      for (const key of WORK_ORDER_DEPENDENTS) {
        void client.invalidateQueries({ queryKey: [...key] });
      }
    },
  });
}

const STATUS_ACTION_LABEL: Partial<Record<WorkOrderStatus, string>> = {
  in_progress: "Start / resume work",
  blocked: "Mark blocked",
  awaiting_parts: "Awaiting parts",
  closed: "Close work order",
  reopened: "Reopen",
  completion_review: "Mark complete",
};

export function actionLabel(a: AllowedAction): string {
  switch (a.action) {
    case "submit":
      return "Submit for review";
    case "approve":
      return "Approve";
    case "reject":
      return "Reject";
    case "escalate":
      return "Escalate";
    case "complete":
      return "Mark complete";
    case "assign":
      return "Assign";
    default:
      return STATUS_ACTION_LABEL[a.to] ?? `Move to ${STATUS_LABEL[a.to]}`;
  }
}

function actionVariant(a: AllowedAction): "primary" | "danger" | "secondary" {
  if (a.action === "approve" || a.to === "closed") return "primary";
  if (a.action === "reject") return "danger";
  return "secondary";
}

/** Buttons built from the server's allowed_actions; the server stays the authority on what is permitted. */
export function ActionBar({ wo }: { wo: WorkOrderDetail }) {
  const [active, setActive] = useState<AllowedAction | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [editing, setEditing] = useState(false);

  // Assignment has its own control driven by can_assign (it also covers reassignment without a status change).
  const actions = wo.allowed_actions.filter((a) => a.action !== "assign");
  const blocked = actions.filter((a) => a.blocked_reason);
  const editable = wo.status !== "closed" && wo.status !== "rejected";

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Button
            key={`${a.action}-${a.to}`}
            variant={actionVariant(a)}
            disabled={!!a.blocked_reason}
            title={a.blocked_reason ? blockedReasonText(a.blocked_reason) : undefined}
            onClick={() => setActive(a)}
          >
            {actionLabel(a)}
          </Button>
        ))}
        {wo.can_assign && (
          <Button variant={wo.status === "approved" ? "primary" : "secondary"} onClick={() => setAssigning(true)}>
            {wo.assignee ? "Reassign" : "Assign technician"}
          </Button>
        )}
        {editable && (
          <Button variant="ghost" onClick={() => setEditing(true)}>
            Edit details
          </Button>
        )}
      </div>
      {blocked.map((a) => (
        <p key={`${a.action}-${a.to}-why`} className="mt-2 text-xs text-amber-800">
          {actionLabel(a)} is unavailable: {blockedReasonText(a.blocked_reason!)}
        </p>
      ))}
      {actions.length === 0 && !wo.can_assign && (
        <p className="text-sm text-ink-muted">No actions are available to you at this stage.</p>
      )}

      {active && <ActionDialog wo={wo} action={active} onClose={() => setActive(null)} />}
      {assigning && <AssignDialog wo={wo} onClose={() => setAssigning(false)} />}
      {editing && <EditDialog wo={wo} onClose={() => setEditing(false)} />}
    </div>
  );
}

// ── one dialog for approve / reject / escalate / submit / generic status ──
export function ActionDialog({ wo, action, onClose }: { wo: WorkOrderDetail; action: AllowedAction; onClose: () => void }) {
  const [comment, setComment] = useState("");
  const [priority, setPriority] = useState<Priority>(wo.priority);
  const [reason, setReason] = useState("");
  const overriding = action.action === "approve" && priority !== wo.priority;
  // reject and escalate always need a reason (backend CommentRequired, min 3 characters)
  const commentRequired = action.comment_required || action.action === "reject" || action.action === "escalate";

  const mutation = useWorkOrderMutation(wo.id, async () => {
    const text = comment.trim() || undefined;
    switch (action.action) {
      case "approve":
        return workOrdersApi.approve(wo.id, {
          comment: text,
          priority: overriding ? priority : undefined,
          priority_reason: overriding ? reason.trim() : undefined,
        });
      case "reject":
        return workOrdersApi.reject(wo.id, comment.trim());
      case "escalate":
        return workOrdersApi.escalate(wo.id, comment.trim());
      case "submit":
        return workOrdersApi.submit(wo.id);
      default:
        return workOrdersApi.changeStatus(wo.id, action.to, text);
    }
  });

  const commentTooShort = commentRequired && comment.trim().length < 3;
  const reasonMissing = overriding && reason.trim().length < 3;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (commentTooShort || reasonMissing) return;
    mutation.mutate(undefined, { onSuccess: onClose });
  }

  const title = `${actionLabel(action)} · ${wo.display_number}`;
  return (
    <Modal
      open
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            form="wo-action-form"
            variant={actionVariant(action) === "danger" ? "danger" : "primary"}
            loading={mutation.isPending}
            disabled={commentTooShort || reasonMissing}
          >
            {actionLabel(action)}
          </Button>
        </>
      }
    >
      <form id="wo-action-form" onSubmit={onSubmit} className="space-y-4">
        <p className="text-sm text-ink-muted">
          {STATUS_LABEL[wo.status]} → <span className="font-medium text-ink">{STATUS_LABEL[action.to]}</span>
        </p>
        {action.action === "approve" && (
          <>
            <SelectField
              label="Priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as Priority)}
              hint={`Rule-based priority: ${PRIORITY_LABEL[wo.priority]}${wo.priority_rule ? ` (${wo.priority_rule})` : ""}. Change it only with a reason.`}
            >
              {PRIORITY_ORDER.map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABEL[p]}
                </option>
              ))}
            </SelectField>
            {overriding && (
              <TextField
                label="Reason for changing the priority"
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                error={reason && reasonMissing ? "At least 3 characters." : undefined}
              />
            )}
          </>
        )}
        {action.action !== "submit" && (
          <TextAreaField
            label={commentRequired ? "Reason" : "Comment (optional)"}
            required={commentRequired}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={1000}
            hint="Saved in the audit trail."
            error={commentRequired && comment && commentTooShort ? "At least 3 characters." : undefined}
          />
        )}
        <InlineError error={mutation.error} />
      </form>
    </Modal>
  );
}

// ── assignment ───────────────────────────────────────────────────────────
export function AssignDialog({ wo, onClose }: { wo: WorkOrderDetail; onClose: () => void }) {
  const technicians = useQuery({ queryKey: queryKeys.technicians, queryFn: () => usersApi.list({ role: "technician" }) });
  const [technicianId, setTechnicianId] = useState("");
  const [comments, setComments] = useState("");
  const mutation = useWorkOrderMutation(wo.id, () =>
    workOrdersApi.assign(wo.id, technicianId, comments.trim() || undefined),
  );
  const options = (technicians.data ?? []).filter((t) => t.id !== wo.assignee?.id);

  return (
    <Modal
      open
      title={`${wo.assignee ? "Reassign" : "Assign"} · ${wo.display_number}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={mutation.isPending}
            disabled={!technicianId}
            onClick={() => mutation.mutate(undefined, { onSuccess: onClose })}
          >
            Assign
          </Button>
        </>
      }
    >
      {wo.assignee && <p className="text-sm text-ink-muted">Currently assigned to {wo.assignee.name}.</p>}
      <SelectField
        label="Technician"
        required
        value={technicianId}
        onChange={(e) => setTechnicianId(e.target.value)}
        disabled={technicians.isLoading}
        hint="Open work is the number of unfinished orders each technician already has."
      >
        <option value="">{technicians.isLoading ? "Loading technicians…" : "Choose a technician"}</option>
        {options.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name} · {LANGUAGE_LABEL[t.preferred_language]} · {t.open_assigned} open
          </option>
        ))}
      </SelectField>
      {technicians.isSuccess && options.length === 0 && (
        <p className="text-sm text-amber-800">No other active technician at this site.</p>
      )}
      <TextAreaField
        label="Instructions (optional)"
        value={comments}
        onChange={(e) => setComments(e.target.value)}
        maxLength={1000}
      />
      <p className="text-xs text-ink-muted">
        The active SOP checklist for {CATEGORY_LABEL[wo.issue_category].toLowerCase()} work is attached automatically.
        The technician hears the task in their own language.
      </p>
      <InlineError error={technicians.error ?? mutation.error} />
    </Modal>
  );
}

// ── edit details ─────────────────────────────────────────────────────────
const IMPACTS: ProductionImpact[] = ["running", "degraded", "stopped", "unknown"];

export function EditDialog({ wo, onClose }: { wo: WorkOrderDetail; onClose: () => void }) {
  const [description, setDescription] = useState(wo.issue_description);
  const [location, setLocation] = useState(wo.location_note ?? "");
  const [category, setCategory] = useState<EquipmentCategory>(wo.issue_category);
  const [impact, setImpact] = useState<ProductionImpact>(wo.production_impact);
  const [priority, setPriority] = useState<Priority>(wo.priority);
  const [reason, setReason] = useState("");
  const priorityChanged = priority !== wo.priority;

  const mutation = useWorkOrderMutation(wo.id, () =>
    workOrdersApi.update(wo.id, {
      issue_description: description.trim() !== wo.issue_description ? description.trim() : undefined,
      location_note: location.trim() !== (wo.location_note ?? "") ? location.trim() : undefined,
      issue_category: category !== wo.issue_category ? category : undefined,
      production_impact: impact !== wo.production_impact ? impact : undefined,
      priority: priorityChanged ? priority : undefined,
      priority_reason: priorityChanged ? reason.trim() : undefined,
    }),
  );
  const invalid = !description.trim() || (priorityChanged && reason.trim().length < 3);

  return (
    <Modal
      open
      title={`Edit · ${wo.display_number}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={mutation.isPending}
            disabled={invalid}
            onClick={() => mutation.mutate(undefined, { onSuccess: onClose })}
          >
            Save
          </Button>
        </>
      }
    >
      <p className="text-xs text-ink-muted">
        Edits are audited. The original transcript is evidence and is never changed.
      </p>
      <TextAreaField
        label="Issue description"
        required
        rows={4}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        maxLength={2000}
      />
      <TextField label="Location note" value={location} onChange={(e) => setLocation(e.target.value)} maxLength={255} />
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Category" value={category} onChange={(e) => setCategory(e.target.value as EquipmentCategory)}>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABEL[c]}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Production impact"
          value={impact}
          onChange={(e) => setImpact(e.target.value as ProductionImpact)}
        >
          {IMPACTS.map((i) => (
            <option key={i} value={i}>
              {IMPACT_LABEL[i]}
            </option>
          ))}
        </SelectField>
      </div>
      <SelectField label="Priority" value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
        {PRIORITY_ORDER.map((p) => (
          <option key={p} value={p}>
            {PRIORITY_LABEL[p]}
          </option>
        ))}
      </SelectField>
      {priorityChanged && (
        <TextField
          label="Reason for changing the priority"
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={500}
        />
      )}
      <InlineError error={mutation.error} />
    </Modal>
  );
}
