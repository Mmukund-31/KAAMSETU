import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OVERVIEW, mockApi, page, renderApp, signedIn, user } from "./harness";

const DASHBOARD_LISTS = { "GET /work-orders": page([]) };

describe("login and route protection", () => {
  it("redirects to the login page without a session", async () => {
    mockApi({});
    renderApp("/work-orders");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("signs a supervisor in and opens the overview", async () => {
    const { calls } = mockApi({
      "POST /auth/login": { access_token: "tok", token_type: "bearer", expires_at: "2026-11-10T10:00:00Z", user: user() },
      "GET /dashboard/overview": OVERVIEW,
      ...DASHBOARD_LISTS,
    });
    renderApp("/");
    await userEvent.type(await screen.findByLabelText(/email/i), "supervisor@kaamsetu.demo");
    await userEvent.type(screen.getByLabelText(/password/i), "Kaamsetu@2026");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(localStorage.getItem("kaamsetu.supervisor.token")).toBe("tok");
    expect(calls.find((c) => c.path === "/auth/login")?.body).toEqual({
      email: "supervisor@kaamsetu.demo",
      password: "Kaamsetu@2026",
    });
    // dashboard tile numbers come straight from /dashboard/overview
    expect(await screen.findByText("Awaiting approval")).toBeInTheDocument();
  });

  it("refuses technicians and stores no token", async () => {
    mockApi({
      "POST /auth/login": { access_token: "tok", token_type: "bearer", expires_at: "x", user: user({ role: "technician" }) },
    });
    renderApp("/");
    await userEvent.type(await screen.findByLabelText(/email/i), "tech1@kaamsetu.demo");
    await userEvent.type(screen.getByLabelText(/password/i), "Kaamsetu@2026");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/mobile app/i);
    expect(localStorage.getItem("kaamsetu.supervisor.token")).toBeNull();
  });

  it("shows the server's message for wrong credentials", async () => {
    mockApi({
      "POST /auth/login": () => ({ status: 401, body: { error: { code: "invalid_credentials", message: "Invalid email or password" } } }),
    });
    renderApp("/");
    await userEvent.type(await screen.findByLabelText(/email/i), "supervisor@kaamsetu.demo");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong-pass1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  });

  it("restores a saved session and signs out when the token is rejected later", async () => {
    let meOk = true;
    signedIn({
      "GET /auth/me": () => (meOk ? { body: user() } : { status: 401, body: { error: { code: "token_expired", message: "expired" } } }),
      ...DASHBOARD_LISTS,
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByText("Supervisor Rao")).toBeInTheDocument();

    meOk = false;
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument());
    expect(localStorage.getItem("kaamsetu.supervisor.token")).toBeNull();
  });
});
