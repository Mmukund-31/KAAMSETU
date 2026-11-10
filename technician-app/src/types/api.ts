// Mirrors the backend schemas the technician app uses (backend/app/schemas). Keep in sync.

export type Language = "en" | "hi" | "te" | "hinglish";
export type UserRole = "technician" | "supervisor" | "manager";
export type Priority = "low" | "medium" | "high" | "critical";
export type ProductionImpact = "running" | "degraded" | "stopped" | "unknown";
export type EquipmentCategory =
  | "mechanical"
  | "electrical"
  | "instrumentation"
  | "hydraulic"
  | "pneumatic"
  | "production"
  | "other";
export type WorkOrderStatus =
  | "reported"
  | "under_review"
  | "approved"
  | "assigned"
  | "in_progress"
  | "completion_review"
  | "closed"
  | "rejected"
  | "awaiting_parts"
  | "blocked"
  | "escalated"
  | "reopened";
export type NextAction = "fix_equipment" | "ask_follow_up" | "confirm_preview";
export type FollowUpField = "equipment_code" | "symptoms" | "production_impact";
export type ChecklistResponseValue = "done" | "not_applicable" | "failed";

export interface Site {
  id: string;
  name: string;
  location: string | null;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  preferred_language: Language;
  site_id: string | null;
  site: Site | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

/** Spoken reply: text always, Timbre audio when it succeeded. */
export interface SpokenResponse {
  text: string;
  tts_available: boolean | null;
  tts_error: string | null;
  audio_base64: string | null;
  content_type: string | null;
  voice: string | null;
  gnani_request_id: string | null;
}

export interface ReportDraft {
  equipment_code: string | null;
  issue_description: string;
  symptoms: string[];
  production_impact: ProductionImpact;
  safety_concern: boolean;
  location_note: string | null;
  category_override: EquipmentCategory | null;
}

export interface EquipmentBrief {
  id: string;
  code: string;
  name: string;
  category: EquipmentCategory;
  location: string | null;
  is_critical: boolean;
}

export interface ReportOutcome {
  report_id: string;
  language: Language;
  next_action: NextAction;
  transcript: string;
  original_transcript: string;
  utterances: { kind: string; text: string; gnani_request_id?: string | null }[];
  draft: ReportDraft;
  equipment: {
    status: "matched" | "unknown" | "missing";
    heard: string | null;
    equipment: EquipmentBrief | null;
    suggestions: EquipmentBrief[];
  };
  symptoms: { key: string; label: string; safety: boolean }[];
  category: { value: EquipmentCategory; label: string; basis: string };
  priority: { level: Priority; rule_id: string; explanation: string; provisional: boolean };
  missing_fields: { field: FollowUpField; reason: string; question: string }[];
  follow_up: { field: FollowUpField; question: string } | null;
  requires_approval: boolean;
  warnings: string[];
  response: SpokenResponse;
  evidence_token: string;
}

export interface PersonRef {
  id: string;
  name: string;
}

export interface WorkOrderSummary {
  id: string;
  number: number;
  display_number: string;
  status: WorkOrderStatus;
  priority: Priority;
  issue_category: EquipmentCategory;
  symptoms: string[];
  issue_description: string;
  production_impact: ProductionImpact;
  safety_concern: boolean;
  equipment: { id: string; code: string; name: string; location: string | null; is_critical: boolean };
  reporter: PersonRef;
  assignee: PersonRef | null;
  created_at: string;
  updated_at: string;
  due_at: string | null;
  is_overdue: boolean;
}

export interface ChecklistItem {
  id: string;
  sequence: number;
  description: string;
  is_mandatory: boolean;
  response: ChecklistResponseValue | null;
  notes: string | null;
  completed_at: string | null;
}

export interface Checklist {
  id: string;
  template_name: string;
  template_version: number;
  items: ChecklistItem[];
  items_total: number;
  items_answered: number;
  mandatory_total: number;
  mandatory_done: number;
  is_complete: boolean;
}

export interface AllowedAction {
  action: "submit" | "approve" | "reject" | "assign" | "complete" | "escalate" | "status";
  to: WorkOrderStatus;
  comment_required: boolean;
  blocked_reason: string | null;
}

export interface WorkOrderDetail extends WorkOrderSummary {
  location_note: string | null;
  checklists: Checklist[];
  allowed_actions: AllowedAction[];
  task_announcement: string | null;
}

export interface WorkOrderActionResult {
  work_order: WorkOrderDetail;
  response: SpokenResponse | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface HandoverOrderBrief {
  id: string;
  number: string;
  equipment_code: string;
  status: WorkOrderStatus;
}

export interface Handover {
  id: string;
  shift_identifier: string;
  status: "draft" | "submitted" | "reviewed";
  created_at: string;
  original_notes: string;
  generated_summary: {
    counts?: { completed: number; pending: number; blocked: number; awaiting_approval: number };
    completed?: HandoverOrderBrief[];
    pending?: HandoverOrderBrief[];
    blocked?: HandoverOrderBrief[];
    next_shift_actions?: string[];
    observations?: string[];
  };
  pending_actions: { text: string; source: string; done: boolean }[];
}

export interface SynthesisOut {
  audio_base64: string;
  content_type: string;
  voice: string;
}
