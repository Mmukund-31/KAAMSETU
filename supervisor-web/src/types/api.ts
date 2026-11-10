// Mirrors backend/app/schemas (Pydantic). Keep in sync when the API changes.

export type UserRole = "technician" | "supervisor" | "manager";
export type LanguageCode = "en" | "hi" | "te" | "hinglish";
export type EquipmentCategory =
  | "mechanical"
  | "electrical"
  | "instrumentation"
  | "hydraulic"
  | "pneumatic"
  | "production"
  | "other";
export type OperationalStatus = "running" | "stopped" | "degraded" | "maintenance" | "decommissioned";
export type Priority = "low" | "medium" | "high" | "critical";
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
export type ProductionImpact = "running" | "degraded" | "stopped" | "unknown";
export type ReportChannel = "voice" | "text" | "seed";
export type ChecklistStatus = "pending" | "in_progress" | "completed";
export type ChecklistResponseValue = "done" | "not_applicable" | "failed";
export type HandoverStatus = "draft" | "submitted" | "reviewed";
export type WorkOrderSort = "created_desc" | "created_asc" | "due_asc" | "priority" | "updated_desc";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

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
  preferred_language: LanguageCode;
  site_id: string | null;
  site: Site | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

export interface PersonRef {
  id: string;
  name: string;
}

export interface EquipmentRef {
  id: string;
  code: string;
  name: string;
  category: EquipmentCategory;
  location: string | null;
  is_critical: boolean;
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
  report_channel: ReportChannel;
  equipment: EquipmentRef;
  reporter: PersonRef;
  assignee: PersonRef | null;
  created_at: string;
  updated_at: string;
  due_at: string | null;
  closed_at: string | null;
  is_overdue: boolean;
}

/** One spoken or typed input carried in the signed evidence (backend workflows/evidence.py). */
export interface Utterance {
  kind: string;
  text: string;
  field?: string | null;
  gnani_request_id?: string | null;
  model?: string | null;
  language_requested?: string | null;
  detected_language?: string | null;
  at: string;
}

export interface Evidence {
  original_transcript: string;
  detected_language: string | null;
  selected_language: string | null;
  prisma_request_id: string | null;
  prisma_model: string | null;
  utterances: Utterance[];
  validated: Record<string, unknown>;
  audio_retained: boolean;
  created_at: string;
}

export interface Assignment {
  technician: PersonRef;
  assigned_by: PersonRef;
  assigned_at: string;
  comments: string | null;
}

export interface ChecklistItem {
  id: string;
  sequence: number;
  description: string;
  is_mandatory: boolean;
  response: ChecklistResponseValue | null;
  notes: string | null;
  completed_by: PersonRef | null;
  completed_at: string | null;
}

export interface Checklist {
  id: string;
  work_order_id: string;
  template_id: string;
  template_name: string;
  template_version: number;
  status: ChecklistStatus;
  created_at: string;
  completed_at: string | null;
  items: ChecklistItem[];
  items_total: number;
  items_answered: number;
  mandatory_total: number;
  mandatory_done: number;
  is_complete: boolean;
}

export interface HistoryEntry {
  id: string;
  action: string;
  actor: PersonRef | null;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  comment: string | null;
  timestamp: string;
}

export type ActionKind = "submit" | "approve" | "reject" | "assign" | "complete" | "escalate" | "status";

export interface AllowedAction {
  action: ActionKind;
  to: WorkOrderStatus;
  comment_required: boolean;
  blocked_reason: string | null;
}

export interface WorkOrderDetail extends WorkOrderSummary {
  priority_rule: string | null;
  requires_approval: boolean;
  location_note: string | null;
  evidence: Evidence | null;
  assignments: Assignment[];
  checklists: Checklist[];
  history: HistoryEntry[];
  allowed_actions: AllowedAction[];
  can_assign: boolean;
  task_announcement: string | null;
}

export interface WorkOrderUpdate {
  issue_description?: string;
  location_note?: string;
  issue_category?: EquipmentCategory;
  production_impact?: ProductionImpact;
  priority?: Priority;
  priority_reason?: string;
}

export interface Equipment {
  id: string;
  code: string;
  name: string;
  category: EquipmentCategory;
  site_id: string;
  site_name: string;
  location: string | null;
  operational_status: OperationalStatus;
  is_critical: boolean;
  open_work_orders: number;
  created_at: string;
}

export interface FaultCount {
  symptom: string;
  label: string;
  count: number;
}

export interface EquipmentDetail extends Equipment {
  work_orders_total: number;
  work_orders_90d: number;
  recurring_faults: FaultCount[];
  recent_work_orders: WorkOrderSummary[];
}

export interface EquipmentCreate {
  equipment_code: string;
  name: string;
  category: EquipmentCategory;
  location?: string | null;
  is_critical: boolean;
}

export interface UserListItem {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  preferred_language: LanguageCode;
  site_id: string | null;
  is_active: boolean;
  open_assigned: number;
}

export interface UserCreate {
  name: string;
  email: string;
  password: string;
  role: UserRole;
  preferred_language: LanguageCode;
}

export interface TemplateItem {
  id: string;
  sequence: number;
  description: string;
  is_mandatory: boolean;
}

export interface ChecklistTemplate {
  id: string;
  name: string;
  equipment_category: EquipmentCategory;
  work_order_type: string;
  version: number;
  is_active: boolean;
  created_at: string;
  items: TemplateItem[];
}

export interface TemplateCreate {
  name: string;
  equipment_category: EquipmentCategory;
  work_order_type: string;
  items: { description: string; is_mandatory: boolean }[];
}

export interface HandoverOrderBrief {
  id: string;
  number: string;
  equipment_code: string;
  status: WorkOrderStatus;
  priority: Priority;
  assignee: string | null;
}

/** Built by backend services/handovers.py from records; never generated text. */
export interface HandoverSummary {
  generated_at?: string;
  window_hours?: number;
  counts?: { completed: number; pending: number; blocked: number; awaiting_approval: number };
  completed?: HandoverOrderBrief[];
  pending?: HandoverOrderBrief[];
  blocked?: HandoverOrderBrief[];
  awaiting_approval?: HandoverOrderBrief[];
  equipment_attention?: { code: string; name: string; reason: string }[];
  next_shift_actions?: string[];
  observations?: string[];
}

export interface PendingAction {
  text: string;
  source: string;
  work_order_id: string | null;
  done: boolean;
}

export interface Handover {
  id: string;
  site_id: string;
  shift_identifier: string;
  status: HandoverStatus;
  created_by: PersonRef;
  created_at: string;
  original_notes: string;
  detected_language: string | null;
  generated_summary: HandoverSummary;
  pending_actions: PendingAction[];
  reviewed_by: PersonRef | null;
  reviewed_at: string | null;
  review_comment: string | null;
}

export interface HandoverDetail extends Handover {
  history: HistoryEntry[];
}

export interface Overview {
  total: number;
  open: number;
  pending_approval: number;
  in_progress: number;
  blocked: number;
  completion_review: number;
  critical_high_open: number;
  overdue: number;
  safety_open: number;
  completed_7d: number;
  by_status: Partial<Record<WorkOrderStatus, number>>;
  by_priority_open: Partial<Record<Priority, number>>;
  generated_at: string;
}

export interface TrendPoint {
  day: string;
  created: number;
  closed: number;
}

export interface EquipmentIssue {
  equipment_id: string;
  code: string;
  name: string;
  category: EquipmentCategory;
  is_critical: boolean;
  work_orders: number;
  open: number;
  top_symptoms: FaultCount[];
  recurring: boolean;
}

export interface EquipmentIssues {
  days: number;
  equipment: EquipmentIssue[];
  by_category: Partial<Record<EquipmentCategory, number>>;
  by_symptom: FaultCount[];
}

export interface TechnicianWorkload {
  technician: PersonRef;
  preferred_language: LanguageCode;
  assigned: number;
  in_progress: number;
  blocked: number;
  completion_review: number;
  overdue: number;
  closed_30d: number;
  open_total: number;
}

export interface AuditEntry extends HistoryEntry {
  entity_type: string;
  entity_id: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}
