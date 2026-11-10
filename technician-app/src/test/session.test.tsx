import { fireEvent, screen } from "@testing-library/react-native";
import { clearSession, mockApi, renderApp, savedSession, technician } from "./harness";

const LOGIN = (user = technician()) => ({ access_token: "tok-1", token_type: "bearer", expires_at: "2026-11-10T10:00:00Z", user });

describe("sign-in and language", () => {
  it("signs a technician in, asks for the language once, then shows the app in that language", async () => {
    clearSession();
    const { calls } = mockApi({ "POST /auth/login": LOGIN(technician({ preferred_language: "te" })) });
    await renderApp();

    await fireEvent.changeText(screen.getByTestId("email"), "tech2@kaamsetu.demo");
    await fireEvent.changeText(screen.getByTestId("password"), "Kaamsetu@2026");
    await fireEvent.press(screen.getByTestId("sign-in"));

    // language step, preselected from the account (Telugu) and shown in it
    expect(await screen.findByText("మీ భాషను ఎంచుకోండి")).toBeOnTheScreen();
    await fireEvent.press(screen.getByTestId("language-continue"));
    expect(await screen.findByText("లోపాన్ని రిపోర్ట్ చేయండి")).toBeOnTheScreen();

    expect(calls[0].body).toEqual({ email: "tech2@kaamsetu.demo", password: "Kaamsetu@2026" });
    const store = (jest.requireMock("expo-secure-store") as { __store: Map<string, string> }).__store;
    expect(store.get("kaamsetu.token")).toBe("tok-1"); // keychain / keystore, not plain storage
    expect(store.get("kaamsetu.language")).toBe("te");
  });

  it("refuses supervisors and keeps no token", async () => {
    clearSession();
    mockApi({ "POST /auth/login": LOGIN(technician({ role: "supervisor" })) });
    await renderApp();
    await fireEvent.changeText(screen.getByTestId("email"), "supervisor@kaamsetu.demo");
    await fireEvent.changeText(screen.getByTestId("password"), "Kaamsetu@2026");
    await fireEvent.press(screen.getByTestId("sign-in"));
    expect(await screen.findByText(/web console/)).toBeOnTheScreen();
    const store = (jest.requireMock("expo-secure-store") as { __store: Map<string, string> }).__store;
    expect(store.has("kaamsetu.token")).toBe(false);
  });

  it("shows the server message for wrong credentials", async () => {
    clearSession();
    mockApi({ "POST /auth/login": () => ({ status: 401, body: { error: { code: "invalid_credentials", message: "Invalid email or password" } } }) });
    await renderApp();
    await fireEvent.changeText(screen.getByTestId("email"), "tech1@kaamsetu.demo");
    await fireEvent.changeText(screen.getByTestId("password"), "nope12345");
    await fireEvent.press(screen.getByTestId("sign-in"));
    expect(await screen.findByText("Invalid email or password")).toBeOnTheScreen();
  });

  it("restores a saved session and returns to sign-in when the token has expired", async () => {
    savedSession("hinglish");
    mockApi({ "GET /auth/me": () => ({ status: 401, body: { error: { code: "token_expired", message: "expired" } } }) });
    await renderApp();
    expect(await screen.findByTestId("sign-in")).toBeOnTheScreen();
  });

  it("restores a saved session straight into the report screen", async () => {
    savedSession("hinglish");
    mockApi({ "GET /auth/me": technician() });
    await renderApp();
    expect(await screen.findByText("Fault report karein")).toBeOnTheScreen();
  });
});
