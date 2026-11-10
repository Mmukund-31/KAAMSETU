// One function per backend endpoint the technician app uses (docs/API_DOCUMENTATION.md).
import { appendRecording, type Recording } from "../audio/recording";
import { request } from "../lib/api";
import type {
  ChecklistResponseValue,
  Handover,
  Language,
  Page,
  ReportDraft,
  ReportOutcome,
  SynthesisOut,
  TokenResponse,
  User,
  WorkOrderActionResult,
  WorkOrderDetail,
  WorkOrderStatus,
  WorkOrderSummary,
  FollowUpField,
} from "../types/api";

export const authApi = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request<User>("/auth/me"),
  /** Saves the technician's language on the server, so spoken task announcements use it too. */
  setLanguage: (preferred_language: Language) =>
    request<User>("/auth/me", { method: "PATCH", body: { preferred_language } }),
};

export const voiceApi = {
  /** Recording -> Prisma -> extraction -> preview. Nothing is saved until the technician confirms. */
  async processReport(recording: Recording, language: Language, speak = true): Promise<ReportOutcome> {
    const form = new FormData();
    await appendRecording(form, "audio", recording);
    form.append("language", language);
    form.append("speak", String(speak));
    return request<ReportOutcome>("/voice/process-report", { method: "POST", form });
  },
  /** Typed report (no evidence token) or a correction of the voice transcript (with token). */
  processText: (text: string, language: Language, evidenceToken?: string, speak = true) =>
    request<ReportOutcome>("/voice/process-text", {
      method: "POST",
      body: { text, language, evidence_token: evidenceToken, speak },
    }),
  async followUp(params: {
    evidenceToken: string;
    draft: ReportDraft;
    field: FollowUpField;
    answerText?: string;
    recording?: Recording;
    speak?: boolean;
  }): Promise<ReportOutcome> {
    const form = new FormData();
    form.append("evidence_token", params.evidenceToken);
    form.append("draft", JSON.stringify(params.draft));
    form.append("field", params.field);
    if (params.recording) await appendRecording(form, "audio", params.recording);
    else form.append("answer_text", params.answerText ?? "");
    form.append("speak", String(params.speak ?? true));
    return request<ReportOutcome>("/voice/follow-up", { method: "POST", form });
  },
  evaluateDraft: (evidenceToken: string, draft: ReportDraft, speak = false) =>
    request<ReportOutcome>("/voice/evaluate-draft", {
      method: "POST",
      body: { evidence_token: evidenceToken, draft, speak },
    }),
  synthesize: (text: string, language: Language) =>
    request<SynthesisOut>("/voice/synthesize", {
      method: "POST",
      body: { text: text.slice(0, 500), language },
      query: { as_base64: true },
    }),
};

export const workOrdersApi = {
  create: (body: { evidence_token: string; draft: ReportDraft; submission_key: string; speak?: boolean }) =>
    request<WorkOrderActionResult>("/work-orders", { method: "POST", body: { speak: true, ...body } }),
  /** Work assigned to me. */
  assigned: () =>
    request<Page<WorkOrderSummary>>("/work-orders", { query: { mine: true, sort: "priority", page_size: 50 } }),
  /** Reports I filed. */
  reported: (userId: string) =>
    request<Page<WorkOrderSummary>>("/work-orders", {
      query: { reported_by: userId, sort: "created_desc", page_size: 30 },
    }),
  get: (id: string) => request<WorkOrderDetail>(`/work-orders/${id}`),
  changeStatus: (id: string, to: WorkOrderStatus, comment?: string) =>
    request<WorkOrderDetail>(`/work-orders/${id}/status`, { method: "POST", body: { to, comment } }),
  complete: (id: string, notes?: string) =>
    request<WorkOrderActionResult>(`/work-orders/${id}/complete`, { method: "POST", body: { notes, speak: true } }),
  recordStep: (checklistId: string, itemId: string, response: ChecklistResponseValue, notes?: string) =>
    request(`/checklists/${checklistId}/items/${itemId}`, { method: "PATCH", body: { response, notes } }),
};

export const handoversApi = {
  createText: (shift: string, notes: string, language: Language) =>
    request<Handover>("/handovers", { method: "POST", body: { shift_identifier: shift, notes, language } }),
  async createVoice(shift: string, recording: Recording, language: Language): Promise<Handover> {
    const form = new FormData();
    form.append("shift_identifier", shift);
    await appendRecording(form, "audio", recording);
    form.append("language", language);
    return request<Handover>("/handovers/voice", { method: "POST", form });
  },
  mine: () => request<Page<Handover>>("/handovers", { query: { page_size: 10 } }),
};
