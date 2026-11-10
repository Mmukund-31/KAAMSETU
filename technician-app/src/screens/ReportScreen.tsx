import { useCallback, useState } from "react";
import { Text, View } from "react-native";
import type { Recording } from "../audio/recording";
import { useRecorder } from "../audio/useRecorder";
import { useLanguage, useSession } from "../auth/SessionContext";
import { MicButton } from "../components/MicButton";
import {
  Button,
  Card,
  Chip,
  ErrorBanner,
  Field,
  Label,
  Loading,
  Muted,
  PriorityBadge,
  Row,
  Screen,
  SpokenReply,
  Title,
  colors,
} from "../components/ui";
import { impactLabel } from "../lib/i18n";
import { useReportFlow, type ReportFlow } from "../report/useReportFlow";
import type { ProductionImpact } from "../types/api";

const IMPACT_CHOICES: ProductionImpact[] = ["running", "degraded", "stopped"];

export function ReportScreen() {
  const { t } = useSession();
  const language = useLanguage();
  const flow = useReportFlow(language);

  // One recorder serves the first report and spoken follow-up answers.
  const onRecording = useCallback(
    (recording: Recording | null) => {
      if (!recording) return;
      if (flow.phase === "review" && flow.outcome?.next_action === "ask_follow_up") void flow.answerFollowUp({ recording });
      else void flow.submitRecording(recording);
    },
    [flow],
  );
  const recorder = useRecorder(onRecording);

  async function toggleMic() {
    if (recorder.isRecording) onRecording(await recorder.stop());
    else await recorder.start();
  }

  const micError = recorder.error;

  if (flow.phase === "processing") {
    return (
      <Screen>
        <Title>{t("reportTitle")}</Title>
        <Loading />
        <Muted style={{ textAlign: "center" }}>{t("processing")}</Muted>
      </Screen>
    );
  }

  if (flow.phase === "submitted" && flow.submitted) {
    return (
      <Screen>
        <Title>{t("submittedTitle")}</Title>
        <Card>
          <Text style={{ fontSize: 28, fontWeight: "800", color: colors.ink }} testID="submitted-number">
            {flow.submitted.number}
          </Text>
          <Muted>{flow.submitted.duplicate ? t("err_duplicate") : t("submittedBody", { number: flow.submitted.number })}</Muted>
        </Card>
        <SpokenReply response={flow.submitted.response} />
        <Button label={t("newReport")} onPress={flow.reset} />
      </Screen>
    );
  }

  if ((flow.phase === "review" || flow.phase === "submitting") && flow.outcome) {
    return (
      <Screen>
        <ReviewView flow={flow} recorder={{ ...recorder, toggle: toggleMic }} />
      </Screen>
    );
  }

  // idle / typing
  return (
    <Screen>
      <Title>{t("reportTitle")}</Title>
      <Muted>{t("reportHint")}</Muted>
      <ErrorBanner error={flow.error ?? micError} />
      {flow.phase === "typing" ? (
        <TypeReport
          busy={flow.busy}
          onSend={(text) => void flow.submitText(text)}
          onCancel={() => {
            flow.setError(null);
            flow.setPhase("idle");
          }}
        />
      ) : (
        <>
          <MicButton recording={recorder.isRecording} seconds={recorder.seconds} disabled={!recorder.supported} onPress={() => void toggleMic()} />
          {!recorder.isRecording ? (
            <Button label={t("typeInstead")} variant="secondary" onPress={() => flow.setPhase("typing")} testID="type-instead" />
          ) : (
            <Button label={t("cancel")} variant="ghost" onPress={() => void recorder.cancel()} />
          )}
        </>
      )}
    </Screen>
  );
}

function TypeReport({ busy, onSend, onCancel }: { busy: boolean; onSend: (text: string) => void; onCancel: () => void }) {
  const { t } = useSession();
  const [text, setText] = useState("");
  return (
    <Card style={{ marginTop: 12 }}>
      <Field label={t("typeReport")} value={text} onChangeText={setText} multiline maxLength={2000} testID="report-text" />
      <Button label={t("send")} onPress={() => onSend(text)} disabled={!text.trim()} loading={busy} testID="send-text" />
      <Button label={t("cancel")} variant="ghost" onPress={onCancel} style={{ marginTop: 6 }} />
    </Card>
  );
}

type MicControls = ReturnType<typeof useRecorder> & { toggle: () => Promise<void> };

function ReviewView({ flow, recorder }: { flow: ReportFlow; recorder: MicControls }) {
  const { t } = useSession();
  const outcome = flow.outcome!;
  const [correcting, setCorrecting] = useState(false);
  const [correction, setCorrection] = useState(outcome.transcript);

  return (
    <>
      <SpokenReply response={outcome.response} />
      <ErrorBanner error={flow.error ?? recorder.error} />

      <Card>
        <Label>{t("youSaid")}</Label>
        <Text style={{ fontSize: 17, color: colors.ink, lineHeight: 24 }} testID="transcript">
          {outcome.original_transcript}
        </Text>
        {outcome.utterances.slice(1).map((u, i) => (
          <Text key={i} style={{ fontSize: 15, color: colors.muted, marginTop: 6 }}>
            → {u.text}
          </Text>
        ))}
        {correcting ? (
          <View style={{ marginTop: 12 }}>
            <Field label={t("fixTranscript")} value={correction} onChangeText={setCorrection} multiline />
            <Button
              label={t("saveCorrection")}
              onPress={() => {
                setCorrecting(false);
                void flow.correctTranscript(correction);
              }}
              disabled={!correction.trim() || flow.busy}
            />
          </View>
        ) : (
          <Button
            label={t("fixTranscript")}
            variant="ghost"
            onPress={() => {
              setCorrection(outcome.transcript);
              setCorrecting(true);
            }}
            style={{ alignSelf: "flex-start", marginTop: 4, paddingHorizontal: 0 }}
          />
        )}
      </Card>

      {outcome.next_action === "fix_equipment" && <FixEquipment flow={flow} />}
      {outcome.next_action === "ask_follow_up" && <FollowUp flow={flow} recorder={recorder} />}
      {outcome.next_action === "confirm_preview" && <Preview flow={flow} />}

      <Button label={t("startOver")} variant="ghost" onPress={flow.reset} style={{ marginTop: 8 }} />
    </>
  );
}

function FixEquipment({ flow }: { flow: ReportFlow }) {
  const { t } = useSession();
  const outcome = flow.outcome!;
  const [code, setCode] = useState(outcome.equipment.heard ?? "");
  return (
    <Card>
      <Text style={{ fontSize: 20, fontWeight: "700", color: colors.ink }}>{t("whichMachine")}</Text>
      {outcome.equipment.heard ? <Muted>{t("heard", { code: outcome.equipment.heard })}</Muted> : null}
      <Muted style={{ marginBottom: 12 }}>{t("notRegistered")}</Muted>
      <Row>
        {outcome.equipment.suggestions.map((s) => (
          <Chip
            key={s.id}
            label={`${s.code} · ${s.name}`}
            onPress={() => void flow.updateDraft({ equipment_code: s.code }, true)}
            testID={`suggestion-${s.code}`}
          />
        ))}
      </Row>
      <Field label={t("machineCode")} value={code} onChangeText={setCode} autoCapitalize="characters" />
      <Button
        label={t("check")}
        variant="secondary"
        onPress={() => void flow.updateDraft({ equipment_code: code.trim() }, true)}
        disabled={!code.trim()}
        loading={flow.busy}
      />
    </Card>
  );
}

function FollowUp({ flow, recorder }: { flow: ReportFlow; recorder: MicControls }) {
  const { t } = useSession();
  const language = useLanguage();
  const outcome = flow.outcome!;
  const question = outcome.follow_up!;
  const [text, setText] = useState("");
  return (
    <Card>
      <Text style={{ fontSize: 20, fontWeight: "700", color: colors.ink, marginBottom: 12 }} testID="follow-up-question">
        {question.question}
      </Text>
      {question.field === "production_impact" ? (
        <Row>
          {IMPACT_CHOICES.map((impact) => (
            <Chip
              key={impact}
              label={impactLabel(language, impact)}
              onPress={() => void flow.updateDraft({ production_impact: impact }, true)}
              testID={`impact-${impact}`}
            />
          ))}
        </Row>
      ) : null}
      <MicButton
        recording={recorder.isRecording}
        seconds={recorder.seconds}
        disabled={!recorder.supported || flow.busy}
        onPress={() => void recorder.toggle()}
        size={96}
        testID="answer-mic"
      />
      <Field label={t("typeAnswer")} value={text} onChangeText={setText} testID="answer-text" />
      <Button
        label={t("send")}
        variant="secondary"
        onPress={() => {
          void flow.answerFollowUp({ text: text.trim() });
          setText("");
        }}
        disabled={!text.trim()}
        loading={flow.busy}
        testID="send-answer"
      />
    </Card>
  );
}

function Preview({ flow }: { flow: ReportFlow }) {
  const { t } = useSession();
  const language = useLanguage();
  const outcome = flow.outcome!;
  const draft = flow.draft!;
  const equipment = outcome.equipment.equipment;
  return (
    <Card>
      <Text style={{ fontSize: 20, fontWeight: "700", color: colors.ink, marginBottom: 12 }}>{t("previewTitle")}</Text>

      <Label>{t("machine")}</Label>
      <Text style={{ fontSize: 18, fontWeight: "700", color: colors.ink, marginBottom: 12 }} testID="preview-machine">
        {equipment ? `${equipment.code} · ${equipment.name}` : draft.equipment_code}
        {equipment?.location ? `\n${equipment.location}` : ""}
      </Text>

      <Field
        label={t("problem")}
        value={draft.issue_description}
        onChangeText={(v) => flow.editLocal({ issue_description: v })}
        multiline
        maxLength={2000}
      />

      {outcome.symptoms.length > 0 ? (
        <>
          <Label>{t("symptoms")}</Label>
          <Row style={{ marginBottom: 8 }}>
            {outcome.symptoms.map((s) => (
              <Chip
                key={s.key}
                label={`${s.label}  ✕`}
                selected
                onPress={() => void flow.updateDraft({ symptoms: draft.symptoms.filter((k) => k !== s.key) })}
              />
            ))}
          </Row>
        </>
      ) : null}

      <Label>{t("production")}</Label>
      <Row style={{ marginBottom: 8 }}>
        {IMPACT_CHOICES.map((impact) => (
          <Chip
            key={impact}
            label={impactLabel(language, impact)}
            selected={draft.production_impact === impact}
            onPress={() => void flow.updateDraft({ production_impact: impact })}
          />
        ))}
      </Row>

      <Label>{t("safety")}</Label>
      <Row style={{ marginBottom: 8 }}>
        <Chip label={t("yes")} selected={draft.safety_concern} onPress={() => void flow.updateDraft({ safety_concern: true })} />
        <Chip label={t("no")} selected={!draft.safety_concern} onPress={() => void flow.updateDraft({ safety_concern: false })} />
      </Row>

      <Field
        label={t("location")}
        value={draft.location_note ?? ""}
        onChangeText={(v) => flow.editLocal({ location_note: v || null })}
        maxLength={255}
      />

      <Label>{t("priority")}</Label>
      <Row>
        <PriorityBadge priority={outcome.priority.level} language={language} />
      </Row>
      <Muted style={{ marginBottom: 4 }}>{outcome.priority.explanation}</Muted>
      {outcome.priority.provisional ? <Muted>{t("provisional")}</Muted> : null}
      {outcome.requires_approval ? <Muted style={{ marginTop: 8 }}>{t("needsApproval")}</Muted> : null}

      <Button
        label={t("sendReport")}
        onPress={() => void flow.confirm()}
        loading={flow.phase === "submitting"}
        disabled={flow.busy}
        style={{ marginTop: 16 }}
        testID="send-report"
      />
    </Card>
  );
}
