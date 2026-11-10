import { useQueryClient } from "@tanstack/react-query";
import { randomUUID } from "expo-crypto";
import { useCallback, useRef, useState } from "react";
import { stopPlayback } from "../audio/player";
import type { Recording } from "../audio/recording";
import { ApiError } from "../lib/api";
import { voiceApi, workOrdersApi } from "../services";
import type { Language, ReportDraft, ReportOutcome, SpokenResponse } from "../types/api";

/*
 * The technician's report, from first words to a submitted work order.
 *
 *   idle -> (voice | typing) -> processing -> review -> submitting -> submitted
 *
 * Nothing is stored on the server until "Send report". Every step returns a fresh ReportOutcome whose
 * signed evidence_token carries the original transcript; the client only edits the draft fields.
 */

export type Phase = "idle" | "typing" | "processing" | "review" | "submitting" | "submitted";

export interface Submitted {
  workOrderId: string;
  number: string;
  response: SpokenResponse | null;
  duplicate: boolean;
}

export function useReportFlow(language: Language) {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [outcome, setOutcome] = useState<ReportOutcome | null>(null);
  const [draft, setDraft] = useState<ReportDraft | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState<Submitted | null>(null);
  // One idempotency key per report: a double tap or a retry after a timeout cannot create two orders.
  const submissionKey = useRef<string>(randomUUID());

  const accept = useCallback((next: ReportOutcome) => {
    setOutcome(next);
    setDraft(next.draft);
    setError(null);
    setPhase("review");
  }, []);

  /** Runs a step that returns a new outcome. On failure the previous screen stays, with the error. */
  const step = useCallback(
    async (fn: () => Promise<ReportOutcome>, fallbackPhase: Phase) => {
      setBusy(true);
      setError(null);
      try {
        accept(await fn());
      } catch (err) {
        setError(err);
        setPhase(fallbackPhase);
      } finally {
        setBusy(false);
      }
    },
    [accept],
  );

  const submitRecording = useCallback(
    (recording: Recording) => {
      setPhase("processing");
      return step(() => voiceApi.processReport(recording, language), "idle");
    },
    [language, step],
  );

  const submitText = useCallback(
    (text: string) => {
      setPhase("processing");
      return step(() => voiceApi.processText(text.trim(), language), "typing");
    },
    [language, step],
  );

  const correctTranscript = useCallback(
    (text: string) => {
      if (!outcome) return Promise.resolve();
      return step(() => voiceApi.processText(text.trim(), language, outcome.evidence_token), "review");
    },
    [language, outcome, step],
  );

  const answerFollowUp = useCallback(
    (answer: { text?: string; recording?: Recording }) => {
      if (!outcome?.follow_up || !draft) return Promise.resolve();
      const { field } = outcome.follow_up;
      return step(
        () =>
          voiceApi.followUp({
            evidenceToken: outcome.evidence_token,
            draft,
            field,
            answerText: answer.text,
            recording: answer.recording,
          }),
        "review",
      );
    },
    [draft, outcome, step],
  );

  /** Applies a draft change and lets the server re-check it (equipment, priority, missing fields). */
  const updateDraft = useCallback(
    (patch: Partial<ReportDraft>, speak = false) => {
      if (!outcome || !draft) return Promise.resolve();
      const next = { ...draft, ...patch };
      setDraft(next);
      return step(() => voiceApi.evaluateDraft(outcome.evidence_token, next, speak), "review");
    },
    [draft, outcome, step],
  );

  /** Local-only edits (free text). They are sent with the submission and validated there. */
  const editLocal = useCallback((patch: Partial<ReportDraft>) => {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }, []);

  const confirm = useCallback(async () => {
    if (!outcome || !draft || busy) return;
    setBusy(true);
    setError(null);
    setPhase("submitting");
    try {
      const result = await workOrdersApi.create({
        evidence_token: outcome.evidence_token,
        draft,
        submission_key: submissionKey.current,
      });
      setSubmitted({
        workOrderId: result.work_order.id,
        number: result.work_order.display_number,
        response: result.response,
        duplicate: false,
      });
      setPhase("submitted");
      void queryClient.invalidateQueries({ queryKey: ["work-orders"] });
    } catch (err) {
      if (err instanceof ApiError && err.code === "duplicate_submission") {
        // Already created (e.g. the first tap succeeded but the reply was lost). Show it, do not resend.
        setSubmitted({
          workOrderId: String(err.details.work_order_id ?? ""),
          number: String(err.details.number ?? ""),
          response: null,
          duplicate: true,
        });
        setPhase("submitted");
      } else {
        setError(err);
        setPhase("review");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, draft, outcome, queryClient]);

  const reset = useCallback(() => {
    stopPlayback();
    submissionKey.current = randomUUID();
    setOutcome(null);
    setDraft(null);
    setError(null);
    setSubmitted(null);
    setPhase("idle");
  }, []);

  return {
    phase,
    setPhase,
    outcome,
    draft,
    error,
    setError,
    busy,
    submitted,
    submitRecording,
    submitText,
    correctTranscript,
    answerFollowUp,
    updateDraft,
    editLocal,
    confirm,
    reset,
  };
}

export type ReportFlow = ReturnType<typeof useReportFlow>;
