// Typed clients per backend domain. Every function maps to exactly one endpoint in docs/API_DOCUMENTATION.md.
import { request } from "../lib/api";
import type {
  AuditEntry,
  Checklist,
  ChecklistTemplate,
  Equipment,
  EquipmentCategory,
  EquipmentCreate,
  EquipmentDetail,
  EquipmentIssues,
  HandoverDetail,
  Handover,
  HandoverStatus,
  Overview,
  Page,
  PendingAction,
  Priority,
  TechnicianWorkload,
  TemplateCreate,
  TokenResponse,
  TrendPoint,
  User,
  UserCreate,
  UserListItem,
  UserRole,
  WorkOrderDetail,
  WorkOrderSort,
  WorkOrderStatus,
  WorkOrderSummary,
  WorkOrderUpdate,
} from "../types/api";

// ── auth ────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request<User>("/auth/me"),
  register: (body: UserCreate) => request<User>("/auth/register", { method: "POST", body }),
};

// ── work orders ─────────────────────────────────────────────────────────
export interface WorkOrderFilters {
  status?: WorkOrderStatus[];
  priority?: Priority[];
  equipment_id?: string;
  assigned_to?: string;
  overdue?: boolean;
  safety_only?: boolean;
  q?: string;
  sort?: WorkOrderSort;
  page?: number;
  page_size?: number;
}

export const workOrdersApi = {
  list: (filters: WorkOrderFilters = {}) =>
    request<Page<WorkOrderSummary>>("/work-orders", { query: { ...filters } }),
  get: (id: string) => request<WorkOrderDetail>(`/work-orders/${id}`),
  update: (id: string, body: WorkOrderUpdate) =>
    request<WorkOrderDetail>(`/work-orders/${id}`, { method: "PATCH", body }),
  submit: (id: string) => request<WorkOrderDetail>(`/work-orders/${id}/submit`, { method: "POST" }),
  approve: (id: string, body: { comment?: string; priority?: Priority; priority_reason?: string }) =>
    request<WorkOrderDetail>(`/work-orders/${id}/approve`, { method: "POST", body }),
  reject: (id: string, comment: string) =>
    request<WorkOrderDetail>(`/work-orders/${id}/reject`, { method: "POST", body: { comment } }),
  escalate: (id: string, comment: string) =>
    request<WorkOrderDetail>(`/work-orders/${id}/escalate`, { method: "POST", body: { comment } }),
  assign: (id: string, technician_id: string, comments?: string) =>
    request<WorkOrderDetail>(`/work-orders/${id}/assign`, { method: "POST", body: { technician_id, comments } }),
  changeStatus: (id: string, to: WorkOrderStatus, comment?: string) =>
    request<WorkOrderDetail>(`/work-orders/${id}/status`, { method: "POST", body: { to, comment } }),
  attachChecklist: (id: string, template_id?: string) =>
    request<Checklist>(`/work-orders/${id}/checklists`, { method: "POST", body: { template_id } }),
};

// ── equipment ───────────────────────────────────────────────────────────
export const equipmentApi = {
  list: (params: { category?: EquipmentCategory; q?: string; page?: number; page_size?: number } = {}) =>
    request<Page<Equipment>>("/equipment", { query: { ...params } }),
  get: (id: string) => request<EquipmentDetail>(`/equipment/${id}`),
  create: (body: EquipmentCreate) => request<Equipment>("/equipment", { method: "POST", body }),
};

// ── users ───────────────────────────────────────────────────────────────
export const usersApi = {
  list: (params: { role?: UserRole; active_only?: boolean } = {}) =>
    request<UserListItem[]>("/users", { query: { ...params, active_only: params.active_only ?? true } }),
};

// ── checklist templates ─────────────────────────────────────────────────
export const templatesApi = {
  list: (params: { category?: EquipmentCategory; active_only?: boolean } = {}) =>
    request<ChecklistTemplate[]>("/checklists/templates", { query: { ...params } }),
  publish: (body: TemplateCreate) =>
    request<ChecklistTemplate>("/checklists/templates", { method: "POST", body }),
  deactivate: (id: string) =>
    request<ChecklistTemplate>(`/checklists/templates/${id}/deactivate`, { method: "POST" }),
};

// ── handovers ───────────────────────────────────────────────────────────
export const handoversApi = {
  list: (params: { status?: HandoverStatus; page?: number; page_size?: number } = {}) =>
    request<Page<Handover>>("/handovers", { query: { ...params } }),
  get: (id: string) => request<HandoverDetail>(`/handovers/${id}`),
  create: (body: { shift_identifier: string; notes: string }) =>
    request<HandoverDetail>("/handovers", { method: "POST", body }),
  review: (id: string, body: { comment?: string; pending_actions?: PendingAction[] }) =>
    request<HandoverDetail>(`/handovers/${id}/review`, { method: "POST", body }),
};

// ── dashboard ───────────────────────────────────────────────────────────
export const dashboardApi = {
  overview: () => request<Overview>("/dashboard/overview"),
  trends: (days = 30) => request<TrendPoint[]>("/dashboard/work-order-trends", { query: { days } }),
  equipmentIssues: (days = 90, limit = 10) =>
    request<EquipmentIssues>("/dashboard/equipment-issues", { query: { days, limit } }),
  workload: () => request<TechnicianWorkload[]>("/dashboard/technician-workload"),
};

// ── audit ───────────────────────────────────────────────────────────────
export const auditApi = {
  list: (params: { entity_type?: string; action?: string; actor_id?: string; page?: number; page_size?: number } = {}) =>
    request<Page<AuditEntry>>("/audit-logs", { query: { ...params } }),
};
