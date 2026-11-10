import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { audioMock, mockApi, needsImpact, outcome, renderApp, savedSession, technician, unknownMachine } from "./harness";

async function signedInReport(routes: Parameters<typeof mockApi>[0]) {
  savedSession("hinglish");
  const api = mockApi({ "GET /auth/me": technician(), ...routes });
  await renderApp();
  await screen.findByText("Fault report karein");
  return api;
}

async function speak() {
  await fireEvent.press(screen.getByTestId("mic-button"));
  await waitFor(() => expect(audioMock().__recorder.record).toHaveBeenCalled());
  await act(async () => audioMock().__set({ durationMillis: 6400 }));
  await fireEvent.press(screen.getByTestId("mic-button"));
}

beforeEach(() => audioMock().__reset());

describe("voice report", () => {
  it("records, uploads the m4a with the chosen language, and plays the spoken reply", async () => {
    const { calls } = await signedInReport({ "POST /voice/process-report": outcome() });
    await speak();

    expect(await screen.findByTestId("preview-machine")).toHaveTextContent(/M-204 · Hydraulic Press Main Motor/);
    const upload = calls.find((c) => c.path === "/voice/process-report")!;
    expect(upload.form?.get("language")).toBe("hinglish");
    expect(upload.form?.get("audio")).toBeTruthy();
    // microphone permission asked first; recording is mono AAC
    expect(audioMock().requestRecordingPermissionsAsync).toHaveBeenCalled();
    // the Timbre reply was written to the cache and played
    expect(audioMock().__played[0]).toMatch(/^file:\/\/\/cache\/kaamsetu-reply-\d+\.wav$/);
    expect(screen.getByText("Report ready. Please check and send.")).toBeOnTheScreen();
  });

  it("explains a denied microphone and offers typing", async () => {
    await signedInReport({});
    audioMock().requestRecordingPermissionsAsync.mockResolvedValueOnce({ granted: false });
    await fireEvent.press(screen.getByTestId("mic-button"));
    expect(await screen.findByText(/mic ki permission chahiye/)).toBeOnTheScreen();
    expect(screen.getByTestId("type-instead")).toBeOnTheScreen();
  });

  it("stops by itself at 29.5 s, inside Prisma's 30 s limit, and sends the recording", async () => {
    const { calls } = await signedInReport({ "POST /voice/process-report": outcome() });
    await fireEvent.press(screen.getByTestId("mic-button"));
    await waitFor(() => expect(audioMock().__recorder.record).toHaveBeenCalled());
    await act(async () => audioMock().__set({ durationMillis: 29_000 }));
    expect(audioMock().__recorder.stop).not.toHaveBeenCalled();
    await act(async () => audioMock().__set({ durationMillis: 29_500 }));
    await waitFor(() => expect(calls.some((c) => c.path === "/voice/process-report")).toBe(true));
    expect(audioMock().__recorder.stop).toHaveBeenCalled();
  });

  it("shows a busy speech service in the technician's language", async () => {
    await signedInReport({
      "POST /voice/process-report": () => ({ status: 503, body: { error: { code: "speech_rate_limited", message: "busy" } } }),
    });
    await speak();
    expect(await screen.findByText(/Speech service busy hai/)).toBeOnTheScreen();
    expect(screen.getByTestId("mic-button")).toBeOnTheScreen(); // can try again
  });
});

describe("follow-up and corrections", () => {
  it("asks for production impact and answers with one tap", async () => {
    const { calls } = await signedInReport({
      "POST /voice/process-report": needsImpact(),
      "POST /voice/evaluate-draft": outcome(),
    });
    await speak();
    expect(await screen.findByTestId("follow-up-question")).toHaveTextContent("Production chal raha hai ya band hai?");
    await fireEvent.press(screen.getByTestId("impact-stopped"));
    await screen.findByTestId("preview-machine");
    const evaluate = calls.find((c) => c.path === "/voice/evaluate-draft")!;
    expect(evaluate.body).toMatchObject({ evidence_token: "evidence-token-1", draft: { production_impact: "stopped" }, speak: true });
  });

  it("answers a follow-up by voice", async () => {
    const { calls } = await signedInReport({
      "POST /voice/process-report": needsImpact(),
      "POST /voice/follow-up": outcome(),
    });
    await speak();
    await screen.findByTestId("follow-up-question");
    audioMock().__recorder.record.mockClear();
    await fireEvent.press(screen.getByTestId("answer-mic"));
    await waitFor(() => expect(audioMock().__recorder.record).toHaveBeenCalled());
    await act(async () => audioMock().__set({ durationMillis: 2000 }));
    await fireEvent.press(screen.getByTestId("answer-mic"));
    await screen.findByTestId("preview-machine");
    const answer = calls.find((c) => c.path === "/voice/follow-up")!;
    expect(answer.form?.get("field")).toBe("production_impact");
    expect(answer.form?.get("evidence_token")).toBe("evidence-token-1");
    expect(answer.form?.get("audio")).toBeTruthy();
  });

  it("offers only registered machines when the code is unknown", async () => {
    const { calls } = await signedInReport({
      "POST /voice/process-report": unknownMachine(),
      "POST /voice/evaluate-draft": outcome(),
    });
    await speak();
    expect(await screen.findByText("Suna: M-240")).toBeOnTheScreen();
    expect(screen.getByText("Yeh code equipment register mein nahi hai.")).toBeOnTheScreen();
    await fireEvent.press(screen.getByTestId("suggestion-M-204"));
    await screen.findByTestId("preview-machine");
    expect(calls.find((c) => c.path === "/voice/evaluate-draft")!.body).toMatchObject({ draft: { equipment_code: "M-204" } });
  });
});

describe("typed report and submission", () => {
  it("sends a typed report, then submits once with one idempotency key", async () => {
    let creates = 0;
    const { calls } = await signedInReport({
      "POST /voice/process-text": outcome(),
      "POST /work-orders": () => {
        creates += 1;
        return {
          status: 201,
          body: {
            work_order: { id: "wo-9", display_number: "WO-1010" },
            response: { text: "Request supervisor review ke liye submit kar di gayi hai.", tts_available: true, tts_error: null, audio_base64: "AAAA", content_type: "audio/wav", voice: "Poorvi", gnani_request_id: "tts-9" },
          },
        };
      },
    });
    await fireEvent.press(screen.getByTestId("type-instead"));
    await fireEvent.changeText(screen.getByTestId("report-text"), "M-204 vibration, production chal raha hai");
    await fireEvent.press(screen.getByTestId("send-text"));
    await screen.findByTestId("preview-machine");
    expect(calls.find((c) => c.path === "/voice/process-text")!.body).toMatchObject({ language: "hinglish" });

    await fireEvent.press(screen.getByTestId("send-report"));
    expect(await screen.findByTestId("submitted-number")).toHaveTextContent("WO-1010");
    expect(screen.getByText("Request supervisor review ke liye submit kar di gayi hai.")).toBeOnTheScreen();
    expect(creates).toBe(1);
    const body = calls.find((c) => c.path === "/work-orders")!.body as { submission_key: string; evidence_token: string };
    expect(body.evidence_token).toBe("evidence-token-1");
    expect(body.submission_key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("keeps the typed report when sending fails, so it can be sent again", async () => {
    let online = false;
    const { calls } = await signedInReport({
      "POST /voice/process-text": () => (online ? { body: outcome() } : { status: 503, body: { error: { code: "speech_rate_limited", message: "busy" } } }),
    });
    await fireEvent.press(screen.getByTestId("type-instead"));
    await fireEvent.changeText(screen.getByTestId("report-text"), "M-204 vibration, production chal raha hai");
    await fireEvent.press(screen.getByTestId("send-text"));
    expect(await screen.findByText(/Speech service busy hai/)).toBeOnTheScreen();
    expect(screen.getByTestId("report-text")).toHaveDisplayValue("M-204 vibration, production chal raha hai");
    online = true;
    await fireEvent.press(screen.getByTestId("send-text"));
    await screen.findByTestId("preview-machine");
    expect(calls.filter((c) => c.path === "/voice/process-text")).toHaveLength(2);
  });

  it("treats a duplicate submission as already sent", async () => {
    await signedInReport({
      "POST /voice/process-text": outcome(),
      "POST /work-orders": () => ({
        status: 409,
        body: { error: { code: "duplicate_submission", message: "already", details: { work_order_id: "wo-9", number: "WO-1010" } } },
      }),
    });
    await fireEvent.press(screen.getByTestId("type-instead"));
    await fireEvent.changeText(screen.getByTestId("report-text"), "M-204 vibration");
    await fireEvent.press(screen.getByTestId("send-text"));
    await fireEvent.press(await screen.findByTestId("send-report"));
    expect(await screen.findByTestId("submitted-number")).toHaveTextContent("WO-1010");
    expect(screen.getByText("Yeh report pehle hi bhej di gayi hai.")).toBeOnTheScreen();
  });

  it("keeps the preview and shows why when the server says the report is incomplete", async () => {
    await signedInReport({
      "POST /voice/process-text": outcome(),
      "POST /work-orders": () => ({ status: 422, body: { error: { code: "report_incomplete", message: "Production impact is missing" } } }),
    });
    await fireEvent.press(screen.getByTestId("type-instead"));
    await fireEvent.changeText(screen.getByTestId("report-text"), "M-204 vibration");
    await fireEvent.press(screen.getByTestId("send-text"));
    await fireEvent.press(await screen.findByTestId("send-report"));
    expect(await screen.findByText("Production impact is missing")).toBeOnTheScreen();
    expect(screen.getByTestId("send-report")).toBeOnTheScreen();
  });
});
