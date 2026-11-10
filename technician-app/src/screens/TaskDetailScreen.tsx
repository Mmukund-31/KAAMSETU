import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { playAudio } from "../audio/player";
import { useLanguage, useSession } from "../auth/SessionContext";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Field,
  Label,
  Loading,
  Muted,
  PriorityBadge,
  Row,
  Screen,
  SpokenReply,
  StatusBadge,
  colors,
} from "../components/ui";
import { impactLabel, type StringKey } from "../lib/i18n";
import { voiceApi, workOrdersApi } from "../services";
import type {
  AllowedAction,
  Checklist,
  ChecklistItem,
  ChecklistResponseValue,
  SpokenResponse,
  WorkOrderDetail,
  WorkOrderStatus,
} from "../types/api";

// Announcements play once per task per app session when the technician first opens it.
const announced = new Set<string>();

const STATUS_ACTION: Partial<Record<WorkOrderStatus, StringKey>> = {
  in_progress: "startWork",
  blocked: "markBlocked",
  awaiting_parts: "awaitingParts",
};

export function TaskDetailScreen({ id }: { id: string }) {
  const { t } = useSession();
  const language = useLanguage();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["work-orders", "detail", id], queryFn: () => workOrdersApi.get(id) });
  const [reply, setReply] = useState<SpokenResponse | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [speechError, setSpeechError] = useState<unknown>(null);

  const refresh = (detail?: WorkOrderDetail) => {
    if (detail) client.setQueryData(["work-orders", "detail", id], detail);
    void client.invalidateQueries({ queryKey: ["work-orders"] });
  };

  async function listen(text: string) {
    setSpeaking(true);
    setSpeechError(null);
    try {
      const audio = await voiceApi.synthesize(text, language);
      await playAudio(audio.audio_base64, audio.content_type);
    } catch (err) {
      setSpeechError(err); // the text stays on screen
    } finally {
      setSpeaking(false);
    }
  }

  const announcement = query.data?.task_announcement;
  useEffect(() => {
    if (announcement && !announced.has(id)) {
      announced.add(id);
      void listen(announcement);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcement, id]);

  if (query.isLoading) return <Screen><Loading /></Screen>;
  if (query.isError || !query.data) {
    return (
      <Screen>
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
      </Screen>
    );
  }
  const wo = query.data;

  return (
    <Screen>
      <Card>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={{ fontSize: 24, fontWeight: "800", color: colors.ink }}>{wo.equipment.code}</Text>
          <Text style={{ fontSize: 16, color: colors.muted }}>{wo.display_number}</Text>
        </View>
        <Muted>{wo.equipment.name}{wo.location_note || wo.equipment.location ? ` · ${wo.location_note ?? wo.equipment.location}` : ""}</Muted>
        <Row style={{ marginTop: 10 }}>
          <PriorityBadge priority={wo.priority} language={language} />
          <StatusBadge status={wo.status} language={language} />
          {wo.safety_concern ? <Badge text={`⚠ ${t("safety")}`} tone="danger" /> : null}
          {wo.is_overdue ? <Badge text={t("overdue")} tone="danger" /> : null}
        </Row>
        <Text style={{ fontSize: 17, color: colors.ink, marginTop: 10, lineHeight: 24 }}>{wo.issue_description}</Text>
        <Muted style={{ marginTop: 6 }}>
          {t("production")}: {impactLabel(language, wo.production_impact)}
        </Muted>
        {wo.task_announcement ? (
          <Text style={{ fontSize: 16, color: colors.primaryDark, marginTop: 10, lineHeight: 22 }} testID="task-announcement">
            {wo.task_announcement}
          </Text>
        ) : null}
        {wo.task_announcement ? (
          <Button
            label={`▶ ${t("listenTask")}`}
            variant="secondary"
            onPress={() => void listen(wo.task_announcement!)}
            loading={speaking}
            style={{ marginTop: 12 }}
            testID="listen-task"
          />
        ) : null}
      </Card>

      <ErrorBanner error={speechError} />
      <SpokenReply response={reply} />

      <Actions wo={wo} onDone={refresh} onReply={setReply} />

      {wo.checklists.map((c) => (
        <ChecklistCard key={c.id} checklist={c} editable={wo.status === "in_progress"} onChanged={() => void query.refetch()} />
      ))}
    </Screen>
  );
}

function Actions({
  wo,
  onDone,
  onReply,
}: {
  wo: WorkOrderDetail;
  onDone: (detail?: WorkOrderDetail) => void;
  onReply: (r: SpokenResponse | null) => void;
}) {
  const { t } = useSession();
  const [pending, setPending] = useState<AllowedAction | null>(null);
  const [comment, setComment] = useState("");

  const mutation = useMutation({
    mutationFn: async (action: AllowedAction) => {
      if (action.action === "complete") {
        const result = await workOrdersApi.complete(wo.id, comment.trim() || undefined);
        onReply(result.response);
        return result.work_order;
      }
      return workOrdersApi.changeStatus(wo.id, action.to, comment.trim() || undefined);
    },
    onSuccess: (detail) => {
      setPending(null);
      setComment("");
      onDone(detail);
    },
  });

  const actions = wo.allowed_actions.filter((a) => a.action === "complete" || (a.action === "status" && STATUS_ACTION[a.to]));
  if (actions.length === 0) return null;
  const label = (a: AllowedAction) => (a.action === "complete" ? t("markComplete") : t(STATUS_ACTION[a.to]!));

  if (pending) {
    const needsReason = pending.comment_required;
    return (
      <Card>
        <Text style={{ fontSize: 18, fontWeight: "700", color: colors.ink, marginBottom: 10 }}>{label(pending)}</Text>
        <Field
          label={needsReason ? t("reason") : t("notesOptional")}
          value={comment}
          onChangeText={setComment}
          multiline
          maxLength={1000}
          testID="action-comment"
        />
        <ErrorBanner error={mutation.error} />
        <Button
          label={t("confirm")}
          onPress={() => mutation.mutate(pending)}
          disabled={needsReason && comment.trim().length < 3}
          loading={mutation.isPending}
          testID="confirm-action"
        />
        <Button label={t("cancel")} variant="ghost" onPress={() => setPending(null)} style={{ marginTop: 6 }} />
      </Card>
    );
  }

  return (
    <Card>
      <ErrorBanner error={mutation.error} />
      {actions.map((a) => (
        <View key={`${a.action}-${a.to}`} style={{ marginBottom: 10 }}>
          <Button
            label={label(a)}
            variant={a.to === "in_progress" || a.action === "complete" ? "primary" : "secondary"}
            disabled={!!a.blocked_reason}
            loading={mutation.isPending && mutation.variables === a}
            testID={`action-${a.to}`}
            onPress={() => {
              // starting work needs no text; everything else opens the reason / notes step
              if (a.to === "in_progress" && !a.comment_required) mutation.mutate(a);
              else setPending(a);
            }}
          />
          {a.blocked_reason === "checklist_incomplete" ? <Muted style={{ marginTop: 4 }}>{t("completeBlocked")}</Muted> : null}
        </View>
      ))}
    </Card>
  );
}

function ChecklistCard({ checklist, editable, onChanged }: { checklist: Checklist; editable: boolean; onChanged: () => void }) {
  const { t } = useSession();
  return (
    <Card>
      <Text style={{ fontSize: 18, fontWeight: "700", color: colors.ink }}>{t("checklist")}</Text>
      <Muted>{checklist.template_name}</Muted>
      <Text style={{ fontSize: 16, fontWeight: "600", color: checklist.is_complete ? colors.primaryDark : colors.warning, marginVertical: 8 }} testID="checklist-progress">
        {t("checklistProgress", { done: checklist.mandatory_done, total: checklist.mandatory_total })}
      </Text>
      {!editable ? <Muted style={{ marginBottom: 8 }}>{t("checklistLocked")}</Muted> : null}
      {checklist.items.map((item) => (
        <ChecklistRow key={item.id} checklistId={checklist.id} item={item} editable={editable} onChanged={onChanged} />
      ))}
    </Card>
  );
}

function ChecklistRow({
  checklistId,
  item,
  editable,
  onChanged,
}: {
  checklistId: string;
  item: ChecklistItem;
  editable: boolean;
  onChanged: () => void;
}) {
  const { t } = useSession();
  const [choice, setChoice] = useState<ChecklistResponseValue | null>(null);
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: (vars: { response: ChecklistResponseValue; notes?: string }) =>
      workOrdersApi.recordStep(checklistId, item.id, vars.response, vars.notes),
    onSuccess: () => {
      setChoice(null);
      setNote("");
      onChanged();
    },
  });

  const answered = item.response
    ? { done: t("stepDone"), not_applicable: t("stepNA"), failed: t("stepFailed") }[item.response]
    : null;

  return (
    <View style={{ borderTopWidth: 1, borderTopColor: colors.line, paddingVertical: 12 }} testID={`step-${item.sequence}`}>
      <Text style={{ fontSize: 16, color: colors.ink, lineHeight: 22 }}>
        {item.sequence}. {item.description}
      </Text>
      {item.is_mandatory ? <Text style={{ color: colors.danger, fontSize: 13, fontWeight: "700", marginTop: 2 }}>{t("mandatory")}</Text> : null}
      {answered ? (
        <Text style={{ marginTop: 6, fontSize: 15, fontWeight: "700", color: item.response === "failed" ? colors.danger : colors.primaryDark }}>
          ✓ {answered}
          {item.notes ? ` · ${item.notes}` : ""}
        </Text>
      ) : null}
      {editable && !choice ? (
        <View style={{ flexDirection: "row", marginTop: 8, gap: 8 }}>
          <Button
            label={t("stepDone")}
            onPress={() => mutation.mutate({ response: "done" })}
            loading={mutation.isPending}
            style={{ flex: 1, minHeight: 48 }}
            testID={`step-${item.sequence}-done`}
          />
          <Button label={t("stepNA")} variant="secondary" onPress={() => setChoice("not_applicable")} style={{ flex: 1, minHeight: 48 }} />
          <Button label={t("stepFailed")} variant="secondary" onPress={() => setChoice("failed")} style={{ flex: 1, minHeight: 48 }} />
        </View>
      ) : null}
      {editable && choice ? (
        <View style={{ marginTop: 8 }}>
          <Label>{t("noteNeeded")}</Label>
          <Field label={t("notes")} value={note} onChangeText={setNote} />
          <Button
            label={t("confirm")}
            onPress={() => mutation.mutate({ response: choice, notes: note.trim() })}
            disabled={!note.trim()}
            loading={mutation.isPending}
          />
          <Button label={t("cancel")} variant="ghost" onPress={() => setChoice(null)} />
        </View>
      ) : null}
      <ErrorBanner error={mutation.error} />
    </View>
  );
}
