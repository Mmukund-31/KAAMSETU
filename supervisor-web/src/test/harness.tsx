import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type { User, WorkOrderDetail, WorkOrderSummary } from "../types/api";

export interface Call {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

type Handler = (call: Call) => { status?: number; body?: unknown } | undefined;

/**
 * Replaces fetch with a route table keyed by "METHOD /path" (path without /api/v1).
 * Unmatched requests fail the test loudly instead of hanging.
 */
export function mockApi(routes: Record<string, Handler | object>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = init?.method ?? "GET";
    const call: Call = { method, path, query: url.searchParams, body: init?.body ? JSON.parse(String(init.body)) : undefined };
    calls.push(call);
    const route = routes[`${method} ${path}`];
    if (route === undefined) {
      return new Response(JSON.stringify({ error: { code: "unmocked", message: `Unmocked ${method} ${path}` } }), { status: 599 });
    }
    const result = typeof route === "function" ? (route as Handler)(call) : { body: route };
    return new Response(result?.body === undefined ? null : JSON.stringify(result.body), {
      status: result?.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(path: string) {
  return renderWithProviders(<App />, path);
}

export function renderWithProviders(ui: ReactElement, path = "/", routePath?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          {routePath ? (
            <Routes>
              <Route path={routePath} element={ui} />
            </Routes>
          ) : (
            ui
          )}
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── fixtures shaped exactly like backend responses ──────────────────────
export const SITE = { id: "site-1", name: "Hyderabad Plant 1", location: "Hyderabad" };

export function user(overrides: Partial<User> = {}): User {
  return {
    id: "u-sup",
    name: "Supervisor Rao",
    email: "supervisor@kaamsetu.demo",
    role: "supervisor",
    preferred_language: "en",
    site_id: SITE.id,
    site: SITE,
    is_active: true,
    created_at: "2026-11-01T08:00:00Z",
    ...overrides,
  };
}

export function summary(overrides: Partial<WorkOrderSummary> = {}): WorkOrderSummary {
  return {
    id: "wo-1",
    number: 1008,
    display_number: "WO-1008",
    status: "under_review",
    priority: "high",
    issue_category: "mechanical",
    symptoms: ["bearing_vibration", "abnormal_pressure"],
    issue_description: "Machine M-204 mein vibration aa raha hai aur pressure low hai.",
    production_impact: "running",
    safety_concern: false,
    report_channel: "voice",
    equipment: { id: "eq-204", code: "M-204", name: "Hydraulic Press Motor", category: "mechanical", location: "Line 2", is_critical: true },
    reporter: { id: "u-t1", name: "Ravi Kumar" },
    assignee: null,
    created_at: "2026-11-10T09:00:00Z",
    updated_at: "2026-11-10T09:00:00Z",
    due_at: "2026-11-11T09:00:00Z",
    closed_at: null,
    is_overdue: false,
    ...overrides,
  };
}

export function detail(overrides: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return {
    ...summary(),
    priority_rule: "running_mechanical_fault",
    requires_approval: true,
    location_note: null,
    evidence: {
      original_transcript: "Machine M-204 mein vibration aa raha hai aur pressure low hai. Production chal raha hai.",
      detected_language: "en-IN",
      selected_language: "hinglish",
      prisma_request_id: "req-abc",
      prisma_model: "prisma-v3.0",
      utterances: [{ kind: "voice", text: "Machine M-204 mein vibration…", at: "2026-11-10T09:00:00Z" }],
      validated: { category_basis: "symptoms", priority: { explanation: "Production is running with a mechanical fault" } },
      audio_retained: false,
      created_at: "2026-11-10T09:00:00Z",
    },
    assignments: [],
    checklists: [],
    history: [
      {
        id: "h1",
        action: "work_order.create",
        actor: { id: "u-t1", name: "Ravi Kumar" },
        previous_value: null,
        new_value: { number: 1008, equipment: "M-204", priority: "high" },
        comment: null,
        timestamp: "2026-11-10T09:00:00Z",
      },
      {
        id: "h2",
        action: "work_order.transition",
        actor: { id: "u-t1", name: "Ravi Kumar" },
        previous_value: { status: "reported" },
        new_value: { status: "under_review", via: "submit" },
        comment: null,
        timestamp: "2026-11-10T09:00:01Z",
      },
    ],
    allowed_actions: [
      { action: "approve", to: "approved", comment_required: false, blocked_reason: null },
      { action: "reject", to: "rejected", comment_required: true, blocked_reason: null },
      { action: "escalate", to: "escalated", comment_required: true, blocked_reason: null },
    ],
    can_assign: false,
    task_announcement: null,
    ...overrides,
  };
}

export function page<T>(items: T[], total = items.length) {
  return { items, total, page: 1, page_size: 20 };
}

export const OVERVIEW = {
  total: 8,
  open: 1,
  pending_approval: 1,
  in_progress: 0,
  blocked: 0,
  completion_review: 0,
  critical_high_open: 1,
  overdue: 0,
  safety_open: 0,
  completed_7d: 3,
  by_status: { under_review: 1, closed: 7 },
  by_priority_open: { high: 1 },
  generated_at: "2026-11-10T09:05:00Z",
};

/** Signs in as a supervisor by seeding a token that /auth/me accepts. */
export function signedIn(routes: Record<string, Handler | object> = {}) {
  localStorage.setItem("kaamsetu.supervisor.token", "test-token");
  return mockApi({ "GET /auth/me": user(), "GET /dashboard/overview": OVERVIEW, ...routes });
}
