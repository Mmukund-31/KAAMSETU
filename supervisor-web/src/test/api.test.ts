import { describe, expect, it, vi } from "vitest";
import { ApiError, buildQuery, getToken, onUnauthorized, request, setToken } from "../lib/api";
import { mockApi } from "./harness";

describe("buildQuery", () => {
  it("repeats array values and drops empty ones", () => {
    expect(buildQuery({ status: ["under_review", "escalated"], q: "", overdue: false, page: 2, x: undefined })).toBe(
      "?status=under_review&status=escalated&page=2",
    );
  });

  it("returns an empty string when nothing is set", () => {
    expect(buildQuery({})).toBe("");
  });
});

describe("request", () => {
  it("sends the bearer token and parses JSON", async () => {
    setToken("abc");
    const { calls, fetchMock } = mockApi({ "GET /auth/me": { id: "1" } });
    await expect(request("/auth/me")).resolves.toEqual({ id: "1" });
    expect(calls[0].path).toBe("/auth/me");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer abc");
  });

  it("turns the backend error envelope into an ApiError", async () => {
    mockApi({
      "POST /work-orders/x/approve": () => ({
        status: 403,
        body: { error: { code: "self_approval_not_allowed", message: "You cannot approve your own report", details: { a: 1 } } },
      }),
    });
    const err = (await request("/work-orders/x/approve", { method: "POST", body: {} }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 403, code: "self_approval_not_allowed", message: "You cannot approve your own report" });
    expect(err.details).toEqual({ a: 1 });
  });

  it("clears the token and notifies the auth layer on 401", async () => {
    setToken("expired");
    const handler = vi.fn();
    onUnauthorized(handler);
    mockApi({ "GET /auth/me": () => ({ status: 401, body: { error: { code: "token_expired", message: "Token expired" } } }) });
    await expect(request("/auth/me")).rejects.toMatchObject({ code: "token_expired" });
    expect(getToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
    onUnauthorized(null);
  });

  it("reports an unreachable server clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(request("/health")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
});
