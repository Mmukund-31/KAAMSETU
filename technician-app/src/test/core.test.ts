import { ApiError, onUnauthorized, request, setAuthToken } from "../lib/api";
import { STRINGS, errorKey, translate } from "../lib/i18n";
import { defaultShift } from "../screens/HandoverScreen";
import { mockApi } from "./harness";

describe("interface strings", () => {
  const languages = Object.keys(STRINGS) as (keyof typeof STRINGS)[];

  it("has the same keys and no empty text in all four languages", () => {
    const keys = Object.keys(STRINGS.en).sort();
    for (const l of languages) {
      expect(Object.keys(STRINGS[l]).sort()).toEqual(keys);
      for (const k of keys) expect(STRINGS[l][k as keyof typeof STRINGS.en].trim()).not.toBe("");
    }
  });

  it("keeps every placeholder in every translation", () => {
    for (const [key, text] of Object.entries(STRINGS.en)) {
      const vars = (text.match(/\{\w+\}/g) ?? []).sort();
      for (const l of languages) {
        expect([key, (STRINGS[l][key as keyof typeof STRINGS.en].match(/\{\w+\}/g) ?? []).sort()]).toEqual([key, vars]);
      }
    }
  });

  it("writes Hindi in Devanagari and Telugu in Telugu script", () => {
    expect(STRINGS.hi.tapToSpeak).toMatch(/[ऀ-ॿ]/);
    expect(STRINGS.te.tapToSpeak).toMatch(/[ఀ-౿]/);
    expect(STRINGS.hinglish.tapToSpeak).toMatch(/^[\x00-\x7F]+$/);
  });

  it("fills placeholders", () => {
    expect(translate("en", "submittedBody", { number: "WO-1010" })).toBe("WO-1010 is waiting for supervisor review.");
    expect(translate("te", "recordingSeconds", { s: 4, max: 30 })).toContain("4 / 30");
  });

  it("maps backend error codes to messages a technician can act on", () => {
    expect(errorKey("speech_rate_limited")).toBe("err_busy");
    expect(errorKey("speech_unavailable")).toBe("err_speech");
    expect(errorKey("no_speech_detected")).toBe("err_no_speech");
    expect(errorKey("network_error")).toBe("err_network");
    expect(errorKey("mic_denied")).toBe("err_mic_denied");
    expect(errorKey("something_new")).toBe("err_generic");
  });
});

describe("api client", () => {
  it("sends the token and returns the error envelope as ApiError", async () => {
    setAuthToken("tok");
    mockApi({
      "POST /work-orders": () => ({ status: 422, body: { error: { code: "report_incomplete", message: "Missing fields", details: { missing: ["production_impact"] } } } }),
    });
    const err = (await request("/work-orders", { method: "POST", body: {} }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 422, code: "report_incomplete", details: { missing: ["production_impact"] } });
    const init = (globalThis.fetch as jest.Mock).mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("calls the session handler on 401", async () => {
    const handler = jest.fn();
    onUnauthorized(handler);
    mockApi({ "GET /auth/me": () => ({ status: 401, body: { error: { code: "token_expired", message: "expired" } } }) });
    await expect(request("/auth/me")).rejects.toMatchObject({ code: "token_expired" });
    expect(handler).toHaveBeenCalledTimes(1);
    onUnauthorized(null);
  });

  it("reports an unreachable server as network_error", async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError("Network request failed")) as unknown as typeof fetch;
    await expect(request("/health")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
});

describe("shift names", () => {
  it("uses A / B / C shifts by the clock", () => {
    expect(defaultShift(new Date(2026, 10, 10, 9, 0))).toBe("2026-11-10 A");
    expect(defaultShift(new Date(2026, 10, 10, 15, 0))).toBe("2026-11-10 B");
    expect(defaultShift(new Date(2026, 10, 10, 23, 0))).toBe("2026-11-10 C");
  });
});
