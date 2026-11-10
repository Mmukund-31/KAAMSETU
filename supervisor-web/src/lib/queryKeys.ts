// One place for React Query cache keys, so mutations can invalidate exactly what they change.
export const queryKeys = {
  overview: ["dashboard", "overview"] as const,
  trends: (days: number) => ["dashboard", "trends", days] as const,
  equipmentIssues: (days: number) => ["dashboard", "equipment-issues", days] as const,
  workload: ["dashboard", "workload"] as const,
  workOrders: (filters: unknown) => ["work-orders", "list", filters] as const,
  workOrder: (id: string) => ["work-orders", "detail", id] as const,
  equipmentList: (params: unknown) => ["equipment", "list", params] as const,
  equipment: (id: string) => ["equipment", "detail", id] as const,
  technicians: ["users", "technicians"] as const,
  users: ["users"] as const,
  templates: (activeOnly: boolean) => ["templates", activeOnly] as const,
  handovers: (params: unknown) => ["handovers", "list", params] as const,
  handover: (id: string) => ["handovers", "detail", id] as const,
  audit: (params: unknown) => ["audit", params] as const,
};

/** Prefixes invalidated after any work-order change (lists, detail, dashboard tiles, workload, equipment counts). */
export const WORK_ORDER_DEPENDENTS = [["work-orders"], ["dashboard"], ["equipment"], ["users"], ["audit"]] as const;
