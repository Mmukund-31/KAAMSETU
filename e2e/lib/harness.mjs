// Shared helpers: checks with timings, API calls, DB tool, browser with a fake microphone, playback spy.
import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { chromium } from "playwright-core";
import { PATHS, PORTS } from "./config.mjs";

export class Report {
  constructor() {
    this.sections = [];
    this.current = null;
    this.t0 = Date.now();
  }
  section(title) {
    this.current = { title, checks: [], notes: [] };
    this.sections.push(this.current);
    console.log(`\n== ${title}`);
  }
  check(name, ok, detail = "") {
    const entry = { name, ok: !!ok, detail: String(detail ?? ""), atSeconds: +((Date.now() - this.t0) / 1000).toFixed(1) };
    this.current.checks.push(entry);
    console.log(`${entry.ok ? "PASS" : "FAIL"}  ${name}${entry.detail ? `  | ${entry.detail}` : ""}`);
    return entry.ok;
  }
  note(text) {
    this.current.notes.push(text);
    console.log(`      ${text}`);
  }
  get failed() {
    return this.sections.flatMap((s) => s.checks).filter((c) => !c.ok);
  }
  get total() {
    return this.sections.flatMap((s) => s.checks).length;
  }
}

/** Times one step; returns [result, seconds]. */
export async function timed(fn) {
  const start = Date.now();
  const result = await fn();
  return [result, +((Date.now() - start) / 1000).toFixed(2)];
}

export function api(port = PORTS.api) {
  const base = `http://localhost:${port}/api/v1`;
  const call = async (method, path, token, body) => {
    const response = await fetch(base + path, {
      method,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    return { status: response.status, data };
  };
  return {
    call,
    async ok(method, path, token, body) {
      const r = await call(method, path, token, body);
      if (r.status >= 400) throw new Error(`${method} ${path} -> ${r.status} ${JSON.stringify(r.data)}`);
      return r.data;
    },
    async login(email) {
      const r = await call("POST", "/auth/login", null, { email, password: PATHS.password });
      if (r.status !== 200) throw new Error(`login ${email} -> ${r.status}`);
      return r.data.access_token;
    },
  };
}

/** Runs e2e/tools/db.py with the backend virtualenv (DB evidence, counts, tokens, cleanup). */
export function db(...args) {
  const out = execFileSync(PATHS.python, [PATHS.dbTool, ...args], { cwd: PATHS.backend, encoding: "utf8" }).trim();
  return args[0] === "token" ? out : JSON.parse(out);
}

export function track(kind, id) {
  if (id) appendFileSync(PATHS.createdFile, `${kind} ${id}\n`);
}

export async function launchBrowser(micWav) {
  return chromium.launch({
    channel: process.env.E2E_BROWSER_CHANNEL || "msedge",
    headless: process.env.E2E_HEADED !== "1",
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${micWav}`,
      "--autoplay-policy=no-user-gesture-required",
    ],
  });
}

/**
 * A browser context with two spies: every HTMLMediaElement.play() call (Timbre playback) and every MediaRecorder
 * recording (requested and actual mime type, first container bytes). Console errors are collected.
 */
export async function newContext(browser, { width = 390, height = 844 } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, permissions: ["microphone"] });
  await context.addInitScript(() => {
    window.__plays = [];
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...a) {
      window.__plays.push(String(this.currentSrc || this.src).slice(0, 24));
      return play.apply(this, a);
    };
    window.__recordings = [];
    const Native = window.MediaRecorder;
    if (Native) {
      window.MediaRecorder = class extends Native {
        constructor(stream, options) {
          super(stream, options);
          const entry = { requested: options?.mimeType ?? null, mimeType: null, head: "", startedAt: 0, seconds: 0 };
          window.__recordings.push(entry);
          this.addEventListener("start", () => {
            entry.mimeType = this.mimeType;
            entry.startedAt = performance.now();
          });
          this.addEventListener("stop", () => (entry.seconds = +((performance.now() - entry.startedAt) / 1000).toFixed(2)));
          this.addEventListener("dataavailable", async (e) => {
            if (!entry.head && e.data.size > 12) {
              const b = new Uint8Array(await e.data.slice(4, 12).arrayBuffer());
              entry.head = String.fromCharCode(...b);
            }
          });
        }
      };
      window.MediaRecorder.isTypeSupported = Native.isTypeSupported.bind(Native);
    }
  });
  const page = await context.newPage();
  page.consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && page.consoleErrors.push(m.text()));
  page.on("pageerror", (e) => page.consoleErrors.push(e.message));
  return { context, page };
}

export const plays = (page) => page.evaluate(() => window.__plays.length);
export const recordings = (page) => page.evaluate(() => window.__recordings);

/** Console errors that are not the browser logging an HTTP error status the app handled on purpose. */
export function unexpectedConsoleErrors(page) {
  return page.consoleErrors.filter((e) => !/Failed to load resource: the server responded with a status of (4\d\d|5\d\d)/.test(e));
}

// ── technician app actions ───────────────────────────────────────────────
export async function techSignIn(page, appUrl, email, { languageTestId } = {}) {
  await page.goto(appUrl);
  await page.getByTestId("email").fill(email);
  await page.getByTestId("password").fill(PATHS.password);
  await page.getByTestId("sign-in").click();
  if (languageTestId) await page.getByTestId(languageTestId).click();
  await page.getByTestId("language-continue").click();
  await page.getByTestId("mic-button").waitFor();
}

export async function speak(page, micTestId, seconds) {
  await page.getByTestId(micTestId).click();
  await page.waitForTimeout(seconds * 1000);
  await page.getByTestId(micTestId).click();
}

// ── supervisor web actions ───────────────────────────────────────────────
export async function webSignIn(page, email) {
  await page.goto(`http://localhost:${PORTS.web}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PATHS.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Overview" }).waitFor();
}
