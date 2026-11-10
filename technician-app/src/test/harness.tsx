import { NavigationContainer } from "@react-navigation/native";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react-native";
import type { ReactElement } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { SessionProvider } from "../auth/SessionContext";
import { setAuthToken } from "../lib/api";
import { RootNavigator } from "../navigation/RootNavigator";
import type { ReportOutcome, User, WorkOrderDetail } from "../types/api";

export interface Call {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
  form: FormData | null;
}

type Handler = (call: Call) => { status?: number; body?: unknown } | undefined;

/** Replaces fetch with a route table keyed "METHOD /path" (without /api/v1). Unmatched calls fail loudly. */
export function mockApi(routes: Record<string, Handler | object>) {
  const calls: Call[] = [];
  globalThis.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const method = init?.method ?? "GET";
    const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData;
    const call: Call = {
      method,
      path,
      query: url.searchParams,
      body: !isForm && typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      form: isForm ? (init!.body as FormData) : null,
    };
    calls.push(call);
    const route = routes[`${method} ${path}`];
    if (route === undefined) {
      return new Response(JSON.stringify({ error: { code: "unmocked", message: `Unmocked ${method} ${path}` } }), { status: 599 });
    }
    const result = typeof route === "function" ? (route as Handler)(call) : { body: route };
    return new Response(result?.body === undefined ? "" : JSON.stringify(result.body), { status: result?.status ?? 200 });
  }) as unknown as typeof fetch;
  return { calls };
}

export async function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: false } } });
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <QueryClientProvider client={client}>
        <SessionProvider>
          <NavigationContainer>
            <RootNavigator />
          </NavigationContainer>
        </SessionProvider>
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

export async function renderWithSession(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: false } } });
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <QueryClientProvider client={client}>
        <SessionProvider>{ui}</SessionProvider>
      </QueryClientProvider>
    </SafeAreaProvider>,
  );
}

/** Seeds a saved session (token + chosen language) as if the technician had signed in before. */
export function savedSession(language: string | null = "hinglish") {
  const store = (jest.requireMock("expo-secure-store") as { __store: Map<string, string> }).__store;
  store.clear();
  store.set("kaamsetu.token", "saved-token");
  if (language) store.set("kaamsetu.language", language);
  setAuthToken(null);
}

export function clearSession() {
  (jest.requireMock("expo-secure-store") as { __store: Map<string, string> }).__store.clear();
  setAuthToken(null);
}

export const audioMock = () =>
  jest.requireMock("expo-audio") as {
    __recorder: { uri: string | null; record: jest.Mock; stop: jest.Mock; prepareToRecordAsync: jest.Mock };
    __set: (patch: { durationMillis?: number; isRecording?: boolean }) => void;
    __reset: () => void;
    __played: string[];
    requestRecordingPermissionsAsync: jest.Mock;
    createAudioPlayer: jest.Mock;
  };

// ── fixtures shaped like backend responses ──────────────────────────────
export function technician(overrides: Partial<User> = {}): User {
  return {
    id: "u-t1",
    name: "Ravi Kumar",
    email: "tech1@kaamsetu.demo",
    role: "technician",
    preferred_language: "hinglish",
    site_id: "site-1",
    site: { id: "site-1", name: "Hyderabad Plant 1 (Demo)", location: null },
    is_active: true,
    ...overrides,
  };
}

const SPOKEN = {
  tts_available: true,
  tts_error: null,
  audio_base64: "UklGRgAAAABXQVZF",
  content_type: "audio/wav",
  voice: "Poorvi",
  gnani_request_id: "tts-1",
};

const M204 = {
  id: "eq-204",
  code: "M-204",
  name: "Hydraulic Press Main Motor",
  category: "mechanical" as const,
  location: "Press Shop, Bay 2",
  is_critical: true,
};

export function outcome(overrides: Partial<ReportOutcome> = {}): ReportOutcome {
  return {
    report_id: "r-1",
    language: "hinglish",
    next_action: "confirm_preview",
    transcript: "Machine M-204 mein vibration aa raha hai aur pressure low hai. Production chal raha hai.",
    original_transcript: "Machine M-204 mein vibration aa raha hai aur pressure low hai. Production chal raha hai.",
    utterances: [{ kind: "voice", text: "Machine M-204 mein vibration…", gnani_request_id: "stt-1" }],
    draft: {
      equipment_code: "M-204",
      issue_description: "Machine M-204 mein vibration aa raha hai aur pressure low hai.",
      symptoms: ["vibration", "abnormal_pressure"],
      production_impact: "running",
      safety_concern: false,
      location_note: null,
      category_override: null,
    },
    equipment: { status: "matched", heard: "M-204", equipment: M204, suggestions: [] },
    symptoms: [
      { key: "vibration", label: "Vibration", safety: false },
      { key: "abnormal_pressure", label: "Pressure problem", safety: false },
    ],
    category: { value: "mechanical", label: "Mechanical", basis: "symptoms" },
    priority: { level: "high", rule_id: "critical_equipment_fault", explanation: "Critical equipment has a fault", provisional: false },
    missing_fields: [],
    follow_up: null,
    requires_approval: true,
    warnings: [],
    response: { text: "Report ready. Please check and send.", ...SPOKEN },
    evidence_token: "evidence-token-1",
    ...overrides,
  };
}

export function needsImpact(): ReportOutcome {
  const base = outcome();
  return outcome({
    next_action: "ask_follow_up",
    draft: { ...base.draft, production_impact: "unknown" },
    missing_fields: [{ field: "production_impact", reason: "not mentioned", question: "Production chal raha hai ya band hai?" }],
    follow_up: { field: "production_impact", question: "Production chal raha hai ya band hai?" },
    priority: { ...base.priority, provisional: true },
    response: { text: "Production chal raha hai ya band hai?", ...SPOKEN, gnani_request_id: "tts-2" },
  });
}

export function unknownMachine(): ReportOutcome {
  const base = outcome();
  return outcome({
    next_action: "fix_equipment",
    draft: { ...base.draft, equipment_code: "M-240" },
    equipment: { status: "unknown", heard: "M-240", equipment: null, suggestions: [M204] },
    response: { text: "Machine M-240 register mein nahi mili.", ...SPOKEN, gnani_request_id: "tts-3" },
  });
}

export function task(overrides: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return {
    id: "wo-1",
    number: 1008,
    display_number: "WO-1008",
    status: "assigned",
    priority: "high",
    issue_category: "mechanical",
    symptoms: ["vibration"],
    issue_description: "Machine M-204 mein vibration aa raha hai.",
    production_impact: "running",
    safety_concern: false,
    equipment: { id: "eq-204", code: "M-204", name: "Hydraulic Press Main Motor", location: "Press Shop, Bay 2", is_critical: true },
    reporter: { id: "u-t1", name: "Ravi Kumar" },
    assignee: { id: "u-t2", name: "Lakshmi Reddy" },
    created_at: "2026-11-10T09:00:00Z",
    updated_at: "2026-11-10T09:00:00Z",
    due_at: "2026-11-10T13:00:00Z",
    is_overdue: false,
    location_note: null,
    checklists: [
      {
        id: "cl-1",
        template_name: "[DEMO SOP] Mechanical fault inspection",
        template_version: 1,
        items: [
          { id: "i1", sequence: 1, description: "Inform the area supervisor", is_mandatory: true, response: null, notes: null, completed_at: null },
          { id: "i2", sequence: 2, description: "Record vibration readings", is_mandatory: false, response: null, notes: null, completed_at: null },
        ],
        items_total: 2,
        items_answered: 0,
        mandatory_total: 1,
        mandatory_done: 0,
        is_complete: false,
      },
    ],
    allowed_actions: [{ action: "status", to: "in_progress", comment_required: false, blocked_reason: null }],
    task_announcement: "M-204 par naya kaam WO-1008 aapko diya gaya hai.",
    ...overrides,
  };
}
