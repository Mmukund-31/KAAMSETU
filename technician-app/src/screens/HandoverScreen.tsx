import { useState } from "react";
import { Text } from "react-native";
import type { Recording } from "../audio/recording";
import { useRecorder } from "../audio/useRecorder";
import { useLanguage, useSession } from "../auth/SessionContext";
import { MicButton } from "../components/MicButton";
import { Button, Card, ErrorBanner, Field, Label, Loading, Muted, Screen, Title, colors } from "../components/ui";
import { handoversApi } from "../services";
import type { Handover } from "../types/api";

export function defaultShift(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const h = now.getHours();
  return `${date} ${h >= 6 && h < 14 ? "A" : h >= 14 && h < 22 ? "B" : "C"}`;
}

/** End-of-shift notes by voice (Prisma transcript stored verbatim) or text. The summary comes from records. */
export function HandoverScreen() {
  const { t } = useSession();
  const language = useLanguage();
  const [shift, setShift] = useState(defaultShift);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<Handover | null>(null);

  async function run(fn: () => Promise<Handover>) {
    setBusy(true);
    setError(null);
    try {
      setResult(await fn());
      setNotes("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const onRecording = (recording: Recording | null) => {
    if (recording) void run(() => handoversApi.createVoice(shift.trim(), recording, language));
  };
  const recorder = useRecorder(onRecording);

  if (result) {
    const s = result.generated_summary;
    return (
      <Screen>
        <Title>{t("handoverSent")}</Title>
        <Card>
          <Label>{t("shift")}</Label>
          <Text style={{ fontSize: 18, fontWeight: "700", color: colors.ink, marginBottom: 8 }}>{result.shift_identifier}</Text>
          <Label>{t("notes")}</Label>
          <Text style={{ fontSize: 16, color: colors.ink, marginBottom: 8 }} testID="handover-notes">
            {result.original_notes}
          </Text>
          {s.counts ? <Muted>{t("counts", s.counts)}</Muted> : null}
        </Card>
        {s.next_shift_actions?.length ? (
          <Card>
            <Label>{t("nextShiftActions")}</Label>
            {s.next_shift_actions.map((a, i) => (
              <Text key={i} style={{ fontSize: 16, color: colors.ink, marginTop: 4 }}>
                • {a}
              </Text>
            ))}
          </Card>
        ) : null}
        {s.observations?.length ? (
          <Card>
            <Label>{t("observations")}</Label>
            {s.observations.map((a, i) => (
              <Text key={i} style={{ fontSize: 16, color: colors.ink, marginTop: 4 }}>
                • {a}
              </Text>
            ))}
          </Card>
        ) : null}
        <Button label={t("continue")} onPress={() => setResult(null)} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Title>{t("handoverTitle")}</Title>
      <Muted>{t("handoverHint")}</Muted>
      <ErrorBanner error={error ?? recorder.error} />
      <Field label={t("shift")} value={shift} onChangeText={setShift} maxLength={64} />
      {busy ? (
        <Loading />
      ) : (
        <MicButton
          recording={recorder.isRecording}
          seconds={recorder.seconds}
          disabled={!recorder.supported || !shift.trim()}
          onPress={() => void (recorder.isRecording ? recorder.stop().then(onRecording) : recorder.start())}
          size={110}
          testID="handover-mic"
        />
      )}
      <Card>
        <Field label={t("notes")} value={notes} onChangeText={setNotes} multiline maxLength={4000} testID="handover-text" />
        <Button
          label={t("submitHandover")}
          onPress={() => void run(() => handoversApi.createText(shift.trim(), notes.trim(), language))}
          disabled={!notes.trim() || !shift.trim() || busy}
          testID="submit-handover"
        />
      </Card>
    </Screen>
  );
}
