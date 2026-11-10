import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { Platform } from "react-native";
import { appendRecording } from "../audio/recording";
import { webMimeType } from "../audio/useRecorder";
import { KEYS, storage } from "../lib/storage";
import { HandoverScreen } from "../screens/HandoverScreen";
import { audioMock, mockApi, needsImpact, outcome, renderApp, renderWithSession, savedSession, task, technician, unknownMachine } from "./harness";

function onWeb<T>(fn: () => T): T {
  const original = Platform.OS;
  Object.defineProperty(Platform, "OS", { value: "web", configurable: true });
  try {
    return fn();
  } finally {
    Object.defineProperty(Platform, "OS", { value: original, configurable: true });
  }
}

async function onWebAsync(fn: () => Promise<void>) {
  const original = Platform.OS;
  Object.defineProperty(Platform, "OS", { value: "web", configurable: true });
  try {
    await fn();
  } finally {
    Object.defineProperty(Platform, "OS", { value: original, configurable: true });
  }
}

async function signedIn(routes: Parameters<typeof mockApi>[0]) {
  savedSession("hinglish");
  const api = mockApi({ "GET /auth/me": technician(), ...routes });
  await renderApp();
  await screen.findByText("Fault report karein");
  return api;
}

async function typeReport(text: string) {
  await fireEvent.press(screen.getByTestId("type-instead"));
  await fireEvent.changeText(screen.getByTestId("report-text"), text);
  await fireEvent.press(screen.getByTestId("send-text"));
}

beforeEach(() => audioMock().__reset());

describe("web code paths", () => {
  it("uploads the recorder's blob on web and a file part on phones", async () => {
    const native = new FormData();
    await appendRecording(native, "audio", { uri: "file:///r.m4a", mimeType: "audio/m4a", name: "report.m4a", durationSeconds: 3 });
    expect(native.get("audio")).toBeTruthy();

    globalThis.fetch = jest.fn(async () => new Response(new Blob(["abc"], { type: "audio/mp4" }))) as unknown as typeof fetch;
    const web = new FormData();
    const append = jest.spyOn(web, "append");
    await onWebAsync(() => appendRecording(web, "audio", { uri: "blob:x", mimeType: "audio/m4a", name: "report.m4a", durationSeconds: 3 }));
    expect(append).toHaveBeenCalledWith("audio", expect.anything(), "report.m4a");
  });

  it("records on web only when the browser can produce AAC in MP4", () => {
    const g = globalThis as { MediaRecorder?: unknown };
    g.MediaRecorder = { isTypeSupported: (t: string) => t === "audio/mp4" };
    expect(onWeb(webMimeType)).toBe("audio/mp4");
    g.MediaRecorder = { isTypeSupported: (t: string) => t.startsWith("audio/webm") };
    expect(onWeb(webMimeType)).toBeNull(); // WebM only: Prisma and the backend refuse it
    delete g.MediaRecorder;
    expect(webMimeType()).toBeNull(); // not web
  });

  it("keeps the session in localStorage on web and the secure store on phones", async () => {
    const data = new Map<string, string>();
    const g = globalThis as { localStorage?: Storage };
    g.localStorage = {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    } as Storage;
    await onWebAsync(async () => {
      await storage.set(KEYS.token, "web-token");
      expect(globalThis.localStorage.getItem(KEYS.token)).toBe("web-token");
      expect(await storage.get(KEYS.token)).toBe("web-token");
      await storage.set(KEYS.token, null);
      expect(globalThis.localStorage.getItem(KEYS.token)).toBeNull();
    });
    delete g.localStorage;
    await storage.set(KEYS.token, "phone-token");
    expect((jest.requireMock("expo-secure-store") as { __store: Map<string, string> }).__store.get(KEYS.token)).toBe("phone-token");
  });
});

describe("review screen edits", () => {
  it("corrects the transcript with the evidence token", async () => {
    const { calls } = await signedIn({
      "POST /voice/process-text": (c) => ({ body: (c.body as { evidence_token?: string }).evidence_token ? outcome({ transcript: "M-204 corrected" }) : outcome() }),
    });
    await typeReport("M-204 vibration, production chal raha hai");
    await fireEvent.press(await screen.findByText("Text sudharein"));
    await fireEvent.changeText(screen.getByLabelText("Text sudharein"), "M-204 bearing vibration, production chal raha hai");
    await fireEvent.press(screen.getByText("Sudhara hua text use karein"));
    await waitFor(() => expect(calls.filter((c) => c.path === "/voice/process-text")).toHaveLength(2));
    expect(calls[calls.length - 1].body).toMatchObject({ evidence_token: "evidence-token-1", text: "M-204 bearing vibration, production chal raha hai" });
  });

  it("checks a hand-typed machine code against the register", async () => {
    const { calls } = await signedIn({ "POST /voice/process-text": unknownMachine(), "POST /voice/evaluate-draft": outcome() });
    await typeReport("M-240 leak");
    await fireEvent.changeText(await screen.findByLabelText("Machine code"), "M-204");
    await fireEvent.press(screen.getByText("Check karein"));
    await screen.findByTestId("preview-machine");
    expect(calls.find((c) => c.path === "/voice/evaluate-draft")!.body).toMatchObject({ draft: { equipment_code: "M-204" }, speak: true });
  });

  it("answers a follow-up in text", async () => {
    const { calls } = await signedIn({ "POST /voice/process-text": needsImpact(), "POST /voice/follow-up": outcome() });
    await typeReport("M-204 vibration");
    await fireEvent.changeText(await screen.findByTestId("answer-text"), "band hai");
    await fireEvent.press(screen.getByTestId("send-answer"));
    await screen.findByTestId("preview-machine");
    const answer = calls.find((c) => c.path === "/voice/follow-up")!;
    expect(answer.form?.get("answer_text")).toBe("band hai");
    expect(answer.form?.get("field")).toBe("production_impact");
  });

  it("re-checks the draft when symptoms, production or safety change", async () => {
    const { calls } = await signedIn({ "POST /voice/process-text": outcome(), "POST /voice/evaluate-draft": outcome() });
    await typeReport("M-204 vibration, production chal raha hai");
    await fireEvent.press(await screen.findByText("Vibration  ✕"));
    await waitFor(() => expect(calls.filter((c) => c.path === "/voice/evaluate-draft")).toHaveLength(1));
    expect((calls.at(-1)!.body as { draft: { symptoms: string[] } }).draft.symptoms).toEqual(["abnormal_pressure"]);
    await fireEvent.press(screen.getByText("Band hai"));
    await waitFor(() => expect(calls.filter((c) => c.path === "/voice/evaluate-draft")).toHaveLength(2));
    expect(calls.at(-1)!.body).toMatchObject({ draft: { production_impact: "stopped" } });
    await fireEvent.press(screen.getByText("Haan"));
    await waitFor(() => expect(calls.filter((c) => c.path === "/voice/evaluate-draft")).toHaveLength(3));
    expect(calls.at(-1)!.body).toMatchObject({ draft: { safety_concern: true } });
  });
});

describe("navigation, profile and lists", () => {
  it("opens a task from My work, shows my reports, switches language and signs out", async () => {
    const { calls } = await signedIn({
      "GET /work-orders": (c) => ({ body: { items: c.query.get("reported_by") ? [] : [task()], total: 1, page: 1, page_size: 50 } }),
      "GET /work-orders/wo-1": task({ task_announcement: null }),
      "PATCH /auth/me": technician({ preferred_language: "te" }),
    });
    await fireEvent.press(screen.getByText("Mera kaam"));
    await fireEvent.press(await screen.findByTestId("task-WO-1008"));
    expect(await screen.findByText("Kaam shuru karein")).toBeOnTheScreen();

    await fireEvent.press(screen.getAllByText("Mera kaam")[0]);
    await fireEvent.press(await screen.findByTestId("tab-reported"));
    expect(await screen.findByText("Aapne abhi tak kuch report nahi kiya.")).toBeOnTheScreen();
    expect(calls.some((c) => c.query.get("reported_by") === "u-t1")).toBe(true);

    await fireEvent.press(screen.getByText("Profile"));
    await fireEvent.press(await screen.findByTestId("lang-te"));
    expect(await screen.findByText("సైన్ అవుట్")).toBeOnTheScreen();
    // saved on the account too, so the server's spoken task announcements follow the switch
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && c.path === "/auth/me")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ preferred_language: "te" });
    await fireEvent.press(screen.getByTestId("sign-out"));
    expect(await screen.findByTestId("sign-in")).toBeOnTheScreen();
  });
});

describe("handover by voice", () => {
  it("uploads the spoken notes with the shift and language", async () => {
    savedSession("hinglish");
    const { calls } = mockApi({
      "GET /auth/me": technician(),
      "POST /handovers/voice": {
        id: "h2", shift_identifier: "2026-11-10 A", status: "submitted", created_at: "2026-11-10T14:00:00Z",
        original_notes: "M-204 bearing badla, next shift vibration check karna hai.",
        generated_summary: { counts: { completed: 1, pending: 0, blocked: 0, awaiting_approval: 0 }, next_shift_actions: ["next shift vibration check karna hai."], observations: [] },
        pending_actions: [],
      },
    });
    await renderWithSession(<HandoverScreen />);
    await fireEvent.press(await screen.findByTestId("handover-mic"));
    await waitFor(() => expect(audioMock().__recorder.record).toHaveBeenCalled());
    await act(async () => audioMock().__set({ durationMillis: 4000 }));
    await fireEvent.press(screen.getByTestId("handover-mic"));
    expect(await screen.findByTestId("handover-notes")).toHaveTextContent(/M-204 bearing badla/);
    const upload = calls.find((c) => c.path === "/handovers/voice")!;
    expect(upload.form?.get("language")).toBe("hinglish");
    expect(String(upload.form?.get("shift_identifier"))).toMatch(/^\d{4}-\d{2}-\d{2} [ABC]$/);
  });
});
