import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import { HandoverScreen } from "../screens/HandoverScreen";
import { TaskDetailScreen } from "../screens/TaskDetailScreen";
import { TasksScreen } from "../screens/TasksScreen";
import { audioMock, mockApi, renderWithSession, savedSession, task, technician } from "./harness";

const SYNTH = { audio_base64: "AAAA", content_type: "audio/wav", voice: "Poorvi", language_code: "hi-en", model: "timbre-v2.5", gnani_request_id: "s1" };

beforeEach(() => {
  savedSession("hinglish");
  audioMock().__reset();
});

describe("my work", () => {
  it("lists open assigned work, highest priority first from the server", async () => {
    const onOpen = jest.fn();
    const { calls } = mockApi({
      "GET /auth/me": technician(),
      "GET /work-orders": { items: [task(), task({ id: "wo-2", display_number: "WO-1001", status: "closed" })], total: 2, page: 1, page_size: 50 },
    });
    await renderWithSession(<TasksScreen onOpen={onOpen} />);
    await fireEvent.press(await screen.findByTestId("task-WO-1008"));
    expect(onOpen).toHaveBeenCalledWith("wo-1");
    expect(screen.queryByTestId("task-WO-1001")).toBeNull(); // closed work is hidden from "assigned"
    const list = calls.find((c) => c.path === "/work-orders")!;
    expect(list.query.get("mine")).toBe("true");
    expect(list.query.get("sort")).toBe("priority");
  });
});

describe("task detail", () => {
  it("speaks the task once, starts work, and records checklist steps", async () => {
    let current = task();
    const { calls } = mockApi({
      "GET /auth/me": technician(),
      "GET /work-orders/wo-1": () => ({ body: current }),
      "POST /voice/synthesize": SYNTH,
      "POST /work-orders/wo-1/status": () => {
        current = task({
          status: "in_progress",
          task_announcement: null,
          allowed_actions: [
            { action: "status", to: "blocked", comment_required: true, blocked_reason: null },
            { action: "complete", to: "completion_review", comment_required: false, blocked_reason: "checklist_incomplete" },
          ],
        });
        return { body: current };
      },
      "PATCH /checklists/cl-1/items/i1": () => ({ body: {} }),
      "PATCH /checklists/cl-1/items/i2": () => ({ body: {} }),
    });
    await renderWithSession(<TaskDetailScreen id="wo-1" />);
    expect(await screen.findByText("M-204 par naya kaam WO-1008 aapko diya gaya hai.")).toBeOnTheScreen();
    await waitFor(() => expect(calls.some((c) => c.path === "/voice/synthesize")).toBe(true));
    expect(calls.find((c) => c.path === "/voice/synthesize")!.body).toEqual({
      text: "M-204 par naya kaam WO-1008 aapko diya gaya hai.",
      language: "hinglish",
    });
    expect(screen.getByText("Steps record karne ke liye pehle kaam shuru karein.")).toBeOnTheScreen();

    await fireEvent.press(screen.getByTestId("action-in_progress"));
    expect(await screen.findByTestId("action-completion_review")).toBeDisabled();
    expect(screen.getByText("Pehle saare zaroori checklist steps poore karein.")).toBeOnTheScreen();
    expect(calls.find((c) => c.path === "/work-orders/wo-1/status")!.body).toEqual({ to: "in_progress" });

    await fireEvent.press(screen.getByTestId("step-1-done"));
    await waitFor(() => expect(calls.some((c) => c.path === "/checklists/cl-1/items/i1")).toBe(true));
    expect(calls.find((c) => c.path === "/checklists/cl-1/items/i1")!.body).toEqual({ response: "done" });

    // N/A needs a note before it can be sent
    await fireEvent.press(screen.getAllByText("Lagu nahi")[1]);
    const confirm = screen.getByText("Confirm");
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    await fireEvent.changeText(screen.getByLabelText("Notes"), "No vibration meter on this line");
    await fireEvent.press(confirm);
    await waitFor(() => expect(calls.some((c) => c.path === "/checklists/cl-1/items/i2")).toBe(true));
    expect(calls.find((c) => c.path === "/checklists/cl-1/items/i2")!.body).toEqual({
      response: "not_applicable",
      notes: "No vibration meter on this line",
    });
  });

  it("needs a reason to mark blocked", async () => {
    const { calls } = mockApi({
      "GET /auth/me": technician(),
      "GET /work-orders/wo-1": task({
        status: "in_progress",
        task_announcement: null,
        allowed_actions: [{ action: "status", to: "blocked", comment_required: true, blocked_reason: null }],
      }),
      "POST /work-orders/wo-1/status": task({ status: "blocked", task_announcement: null, allowed_actions: [] }),
    });
    await renderWithSession(<TaskDetailScreen id="wo-1" />);
    await fireEvent.press(await screen.findByTestId("action-blocked"));
    expect(screen.getByTestId("confirm-action")).toBeDisabled();
    await fireEvent.changeText(screen.getByTestId("action-comment"), "Bearing not in store");
    await fireEvent.press(screen.getByTestId("confirm-action"));
    await waitFor(() => expect(calls.some((c) => c.path === "/work-orders/wo-1/status")).toBe(true));
    expect(calls.find((c) => c.path === "/work-orders/wo-1/status")!.body).toEqual({ to: "blocked", comment: "Bearing not in store" });
  });

  it("completes the work and plays the spoken confirmation", async () => {
    const { calls } = mockApi({
      "GET /auth/me": technician(),
      "GET /work-orders/wo-1": task({
        status: "in_progress",
        task_announcement: null,
        allowed_actions: [{ action: "complete", to: "completion_review", comment_required: false, blocked_reason: null }],
      }),
      "POST /work-orders/wo-1/complete": {
        work_order: task({ status: "completion_review", task_announcement: null, allowed_actions: [] }),
        response: { text: "Kaam poora darj ho gaya.", tts_available: true, tts_error: null, audio_base64: "AAAA", content_type: "audio/wav", voice: "Poorvi", gnani_request_id: "t5" },
      },
    });
    await renderWithSession(<TaskDetailScreen id="wo-1" />);
    await fireEvent.press(await screen.findByTestId("action-completion_review"));
    await fireEvent.changeText(screen.getByTestId("action-comment"), "Bearing replaced");
    await fireEvent.press(screen.getByTestId("confirm-action"));
    expect(await screen.findByText("Kaam poora darj ho gaya.")).toBeOnTheScreen();
    expect(calls.find((c) => c.path === "/work-orders/wo-1/complete")!.body).toEqual({ notes: "Bearing replaced", speak: true });
    expect(audioMock().__played).toHaveLength(1);
  });
});

describe("handover", () => {
  it("submits typed notes and shows the record-based summary", async () => {
    const { calls } = mockApi({
      "GET /auth/me": technician(),
      "POST /handovers": {
        id: "h1",
        shift_identifier: "2026-11-10 A",
        status: "submitted",
        created_at: "2026-11-10T14:00:00Z",
        original_notes: "M-204 bearing badla. Next shift vibration check karna hai.",
        generated_summary: {
          counts: { completed: 1, pending: 0, blocked: 0, awaiting_approval: 0 },
          next_shift_actions: ["Next shift vibration check karna hai."],
          observations: ["M-204 bearing badla."],
        },
        pending_actions: [],
      },
    });
    await renderWithSession(<HandoverScreen />);
    await fireEvent.changeText(await screen.findByTestId("handover-text"), "M-204 bearing badla. Next shift vibration check karna hai.");
    await fireEvent.press(screen.getByTestId("submit-handover"));
    expect(await screen.findByText("• Next shift vibration check karna hai.")).toBeOnTheScreen();
    expect(screen.getByText("Poore 1 · Baaki 0 · Ruke 0")).toBeOnTheScreen();
    expect(calls.find((c) => c.path === "/handovers")!.body).toMatchObject({ language: "hinglish" });
  });
});
