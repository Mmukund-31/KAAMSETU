// Error paths, each against real services. Faults in Gnani are injected by the pass-through proxy in front of the
// second backend (8002); everything else hits the normal stack (8001) with real Prisma and Timbre.
import { PORTS } from "../lib/config.mjs";
import { api, db, newContext, plays, recordings, speak, techSignIn, track, unexpectedConsoleErrors, webSignIn } from "../lib/harness.mjs";

const TECH = `http://localhost:${PORTS.tech}`;
const TECH_FAULTS = `http://localhost:${PORTS.techFaults}`;
const T = {
  busy: "Speech service busy hai. Thodi der mein phir koshish karein.",
  speech: "Speech service abhi uplabdh nahi hai. Aap type kar sakte hain.",
  noSpeech: "Koi awaaz nahi suni. Phone ke paas bolein.",
  voiceUnavailable: "Awaaz mein jawab nahi mil paya. Text dikhaya gaya hai.",
  network: "KAAMSETU server tak nahi pahunch paye. Wi-Fi check karke phir koshish karein.",
  session: "Session khatam ho gaya. Phir se sign in karein.",
  notRegistered: "Yeh code equipment register mein nahi hai.",
};

async function typedReport(page, text) {
  await page.getByTestId("type-instead").click();
  await page.getByTestId("report-text").fill(text);
  await page.getByTestId("send-text").click();
}

export async function errors({ report, browser, silentBrowser, proxy, stopFaultBackend, speechSeconds, shot }) {
  const A = api();
  const F = api(PORTS.faultApi);
  const sup = await A.login("supervisor@kaamsetu.demo");
  const tech1 = await A.login("tech1@kaamsetu.demo");
  const tech2 = await A.login("tech2@kaamsetu.demo");

  // ── E1 unknown equipment ───────────────────────────────────────────────
  report.section("E1 unknown machine code: picker of registered machines, no work order possible");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH, "tech1@kaamsetu.demo");
    const resp = page.waitForResponse((r) => r.url().includes("/voice/process-text"));
    // "M-240" is how "M-204" is easily misheard; it is not in the register
    await typedReport(page, "Machine M-240 mein oil leak hai, production chal raha hai");
    const outcome = await (await resp).json();
    await page.getByText(T.notRegistered).waitFor();
    const register = (await A.ok("GET", "/equipment?page_size=200", sup)).items.map((e) => e.code);
    const offered = outcome.equipment.suggestions.map((s) => s.code);
    report.check("app shows 'not in the register'", true, `heard ${outcome.equipment.heard}`);
    report.check("suggestions are registered machines only, M-204 among them", offered.includes("M-204") && offered.every((c) => register.includes(c)), offered.join(", "));
    await shot(page, "err-01-unknown-machine");
    const attempt = await A.call("POST", "/work-orders", tech1, { evidence_token: outcome.evidence_token, draft: outcome.draft, submission_key: `e2e-unknown-${Date.now()}` });
    report.check("server refuses to create it (422 report_incomplete)", attempt.status === 422 && attempt.data.error.code === "report_incomplete", `${attempt.status} ${attempt.data.error?.code}`);
    await context.close();
  }

  // ── E2 missing production impact ───────────────────────────────────────
  report.section("E2 missing production impact: one follow-up question");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH, "tech1@kaamsetu.demo");
    await typedReport(page, "Machine M-305 se ajeeb awaaz aa rahi hai");
    const question = await page.getByTestId("follow-up-question").innerText({ timeout: 30_000 });
    report.check("follow-up asks about production", /production/i.test(question), question);
    await page.getByTestId("impact-stopped").click();
    await page.getByTestId("preview-machine").waitFor({ timeout: 30_000 });
    report.check("one-tap answer completes the preview", (await page.getByTestId("preview-machine").innerText()).includes("M-305"));
    await context.close();
  }

  // ── E3 silence ─────────────────────────────────────────────────────────
  report.section("E3 silence: real Prisma returns an empty transcript");
  {
    const { page, context } = await newContext(silentBrowser);
    await techSignIn(page, TECH, "tech1@kaamsetu.demo");
    await speak(page, "mic-button", 3);
    await page.getByText(T.noSpeech).waitFor({ timeout: 30_000 });
    report.check("'no speech was heard' in the technician's language", true);
    report.check("mic and typing still offered", (await page.getByTestId("mic-button").isVisible()) && (await page.getByTestId("type-instead").isVisible()));
    await shot(page, "err-03-silence");
    await context.close();
  }

  // ── E4 recording limit ─────────────────────────────────────────────────
  report.section("E4 30 s limit: the recorder stops itself and the file is accepted");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH, "tech1@kaamsetu.demo");
    const resp = page.waitForResponse((r) => r.url().includes("/voice/process-report"), { timeout: 90_000 });
    await page.getByTestId("mic-button").click(); // never pressed again
    const r = await resp;
    const rec = (await recordings(page))[0];
    report.check("stopped by itself under 30 s", rec.seconds > 28 && rec.seconds < 30, `${rec.seconds}s recorded`);
    report.check("backend and Prisma accepted it", r.status() === 200, `HTTP ${r.status()}`);
    await context.close();
  }

  // ── E5 Prisma busy (429) ───────────────────────────────────────────────
  report.section("E5 Prisma busy (429 on every retry), then recovers");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH_FAULTS, "tech1@kaamsetu.demo");
    proxy.set({ stt: "429" });
    const injected = proxy.counts.injected;
    await speak(page, "mic-button", Math.ceil(speechSeconds) + 1);
    await page.getByText(T.busy).waitFor({ timeout: 60_000 });
    report.check("busy message, not a crash", true, `${proxy.counts.injected - injected} upstream attempts (backend retries 429)`);
    await shot(page, "err-05-busy");
    proxy.set({ stt: "pass" });
    await speak(page, "mic-button", Math.ceil(speechSeconds) + 1);
    await page.getByTestId("preview-machine").waitFor({ timeout: 60_000 });
    report.check("same tap works once Prisma is back (real Prisma)", true);
    await context.close();
  }

  // ── E6 Prisma down (500) → typing ──────────────────────────────────────
  report.section("E6 Prisma down (500): type instead");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH_FAULTS, "tech1@kaamsetu.demo");
    proxy.set({ stt: "500" });
    await speak(page, "mic-button", 3);
    await page.getByText(T.speech).waitFor({ timeout: 60_000 });
    report.check("'speech not available, you can type' shown", true);
    proxy.set({ stt: "pass" });
    await typedReport(page, "M-204 mein vibration hai, production chal raha hai");
    await page.getByTestId("preview-machine").waitFor({ timeout: 30_000 });
    report.check("typed report reaches the preview without Prisma", true);
    await context.close();
  }

  // ── E7 Timbre down → text only ─────────────────────────────────────────
  report.section("E7 Timbre down (500): replies as text, the work continues");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH_FAULTS, "tech1@kaamsetu.demo");
    proxy.set({ tts: "500" });
    const p0 = await plays(page);
    await typedReport(page, "M-204 mein vibration hai, production chal raha hai");
    await page.getByTestId("preview-machine").waitFor({ timeout: 30_000 });
    report.check("reply text shown with the 'voice unavailable' note", await page.getByText(T.voiceUnavailable).first().isVisible());
    await shot(page, "err-07-tts-down");
    const create = page.waitForResponse((r) => r.url().endsWith("/api/v1/work-orders") && r.request().method() === "POST");
    await page.getByTestId("send-report").click();
    const created = await (await create).json();
    track("wo", created.work_order?.id);
    await page.getByTestId("submitted-number").waitFor();
    report.check("work order still created", /^WO-\d+$/.test(created.work_order?.display_number), created.work_order?.display_number);
    report.check("acknowledgement is text-only (tts_available=false)", created.response?.tts_available === false, created.response?.tts_error);
    report.check("nothing was played", (await plays(page)) === p0);
    proxy.set({ tts: "pass" });
    await context.close();
  }

  // ── E8 duplicate taps and concurrent submissions ───────────────────────
  report.section("E8 duplicates: double tap, and concurrent submissions of one report");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH, "tech1@kaamsetu.demo");
    await typedReport(page, "M-204 bearing garam hai, production chal raha hai");
    await page.getByTestId("preview-machine").waitFor({ timeout: 30_000 });
    const posts = [];
    page.on("request", (r) => r.url().endsWith("/api/v1/work-orders") && r.method() === "POST" && posts.push(r));
    await page.getByTestId("send-report").dblclick();
    await page.getByTestId("submitted-number").waitFor({ timeout: 30_000 });
    await page.waitForTimeout(1000);
    const number = (await page.getByTestId("submitted-number").innerText()).trim();
    const found = await A.ok("GET", `/work-orders?q=${number}`, sup);
    found.items.forEach((w) => track("wo", w.id));
    report.check("double tap sends one request", posts.length === 1, `${posts.length} POST`);
    report.check("one work order exists for it", found.total === 1, number);
    await context.close();

    // five parallel submissions of the same report with the same key, then with different keys
    const text = "M-204 coupling se awaaz aa rahi hai, production chal raha hai";
    const one = await A.ok("POST", "/voice/process-text", tech1, { text, language: "hinglish", speak: false });
    const key = `e2e-race-${Date.now()}`;
    const same = await Promise.all(Array.from({ length: 5 }, () =>
      A.call("POST", "/work-orders", tech1, { evidence_token: one.evidence_token, draft: one.draft, submission_key: key, speak: false })));
    same.filter((r) => r.status === 201).forEach((r) => track("wo", r.data.work_order.id));
    const codes = same.map((r) => r.status).sort().join(",");
    report.check("same key x5 in parallel: exactly one 201, four 409", codes === "201,409,409,409,409", codes);
    const two = await A.ok("POST", "/voice/process-text", tech1, { text, language: "hinglish", speak: false });
    const diff = await Promise.all(Array.from({ length: 5 }, (_, i) =>
      A.call("POST", "/work-orders", tech1, { evidence_token: two.evidence_token, draft: two.draft, submission_key: `${key}-${i}`, speak: false })));
    diff.filter((r) => r.status === 201).forEach((r) => track("wo", r.data.work_order.id));
    const codes2 = diff.map((r) => r.status).sort().join(",");
    report.check("same report, different keys x5: exactly one 201 (evidence is unique)", codes2 === "201,409,409,409,409", codes2);

    // two supervisors act on one order at the same moment
    const woA = same.find((r) => r.status === 201).data.work_order;
    const mgr = await A.login("manager@kaamsetu.demo");
    const race = await Promise.all([
      A.call("POST", `/work-orders/${woA.id}/approve`, sup, {}),
      A.call("POST", `/work-orders/${woA.id}/approve`, mgr, {}),
    ]);
    const raceCodes = race.map((r) => r.status).sort().join(",");
    report.check("two simultaneous approvals: one 200, one 409 (row lock)", raceCodes === "200,409", `${raceCodes} ${race.find((r) => r.status === 409)?.data?.error?.code ?? ""}`);
    const ev = db("evidence", woA.display_number);
    const approvals = ev.audit.filter((a) => a.to === "approved").length;
    report.check("exactly one approval in the audit log", approvals === 1, `${approvals}`);
  }

  // ── E9 roles and scope ─────────────────────────────────────────────────
  report.section("E9 wrong role or wrong person");
  {
    const any = (await A.ok("GET", "/work-orders?page_size=1&sort=created_desc", sup)).items[0];
    const approve = await A.call("POST", `/work-orders/${any.id}/approve`, tech1, {});
    report.check("technician cannot approve (403)", approve.status === 403, approve.data.error?.code);
    const dash = await A.call("GET", "/dashboard/overview", tech1);
    report.check("technician cannot read the dashboard (403)", dash.status === 403, dash.data.error?.code);
    // tech1's own report from E8, unassigned: tech2 must not even learn it exists
    const mine = (await A.ok("GET", "/work-orders?q=coupling&page_size=5", sup)).items.find((w) => !w.assignee);
    const peek = await A.call("GET", `/work-orders/${mine.id}`, tech2);
    report.check("another technician's report is invisible (404)", peek.status === 404);
    const { page, context } = await newContext(browser);
    await page.goto(TECH);
    await page.getByTestId("email").fill("supervisor@kaamsetu.demo");
    await page.getByTestId("password").fill("Kaamsetu@2026");
    await page.getByTestId("sign-in").click();
    await page.getByText(/web console/).first().waitFor();
    report.check("technician app refuses a supervisor", true);
    const web = await newContext(browser, { width: 1280, height: 800 });
    await web.page.goto(`http://localhost:${PORTS.web}/login`);
    await web.page.getByLabel("Email").fill("tech1@kaamsetu.demo");
    await web.page.getByLabel("Password").fill("Kaamsetu@2026");
    await web.page.getByRole("button", { name: "Sign in" }).click();
    await web.page.getByText(/Technicians report work in the KAAMSETU mobile app/).waitFor();
    report.check("supervisor console refuses a technician", true);
    await context.close();
    await web.context.close();
  }

  // ── E10 checklist gate ─────────────────────────────────────────────────
  report.section("E10 completion blocked until the mandatory checklist steps are done");
  {
    const one = await A.ok("POST", "/voice/process-text", tech1, { text: "M-204 shaft mein vibration hai, production chal raha hai", language: "hinglish", speak: false });
    const created = await A.ok("POST", "/work-orders", tech1, { evidence_token: one.evidence_token, draft: one.draft, submission_key: `e2e-gate-${Date.now()}`, speak: false });
    const wo = created.work_order;
    track("wo", wo.id);
    await A.ok("POST", `/work-orders/${wo.id}/approve`, sup, {});
    const techs = await A.ok("GET", "/users?role=technician", sup);
    await A.ok("POST", `/work-orders/${wo.id}/assign`, sup, { technician_id: techs.find((t) => t.email === "tech2@kaamsetu.demo").id });
    await A.ok("POST", `/work-orders/${wo.id}/status`, tech2, { to: "in_progress" });
    const early = await A.call("POST", `/work-orders/${wo.id}/complete`, tech2, {});
    report.check("complete refused with 409 checklist_incomplete", early.status === 409 && early.data.error.code === "checklist_incomplete");
  }

  // ── E11 session expiry ─────────────────────────────────────────────────
  report.section("E11 token expiry in both apps (real short-lived tokens)");
  {
    const { page, context } = await newContext(browser);
    await page.goto(TECH);
    await page.evaluate((t) => {
      localStorage.setItem("kaamsetu.token", t);
      localStorage.setItem("kaamsetu.language", "hinglish");
    }, db("token", "tech1@kaamsetu.demo", "8"));
    await page.reload();
    await page.getByTestId("mic-button").waitFor();
    report.check("technician app opens with the saved session", true);
    await page.waitForTimeout(9000);
    await page.getByText("Mera kaam").last().click();
    await page.getByText(T.session).waitFor({ timeout: 20_000 });
    report.check("expired mid-session: back to sign-in with the reason", await page.getByTestId("sign-in").isVisible());
    await shot(page, "err-11-session-tech");
    await context.close();

    const web = await newContext(browser, { width: 1280, height: 800 });
    await web.page.goto(`http://localhost:${PORTS.web}/login`);
    await web.page.evaluate((t) => localStorage.setItem("kaamsetu.supervisor.token", t), db("token", "supervisor@kaamsetu.demo", "8"));
    await web.page.goto(`http://localhost:${PORTS.web}/work-orders`);
    await web.page.getByRole("heading", { name: "Work orders" }).waitFor();
    await web.page.waitForTimeout(9000);
    await web.page.getByRole("link", { name: /Approvals/ }).first().click();
    await web.page.getByText("Your session has ended. Please sign in again.").waitFor({ timeout: 20_000 });
    report.check("supervisor console: same, with the reason", true);
    await web.context.close();
  }

  // ── E12 server unreachable ─────────────────────────────────────────────
  report.section("E12 backend unreachable");
  {
    const { page, context } = await newContext(browser);
    await techSignIn(page, TECH_FAULTS, "tech1@kaamsetu.demo");
    await stopFaultBackend();
    await typedReport(page, "M-204 vibration");
    await page.getByText(T.network).waitFor({ timeout: 30_000 });
    report.check("'cannot reach the server' in the technician's language; text kept for retry", await page.getByTestId("report-text").isVisible());
    await shot(page, "err-12-offline");
    const unexpected = unexpectedConsoleErrors(page).filter((e) => !/ERR_CONNECTION_REFUSED|Failed to fetch/.test(e));
    report.check("no unexpected console errors", unexpected.length === 0, unexpected.slice(0, 2).join(" | "));
    await context.close();
  }

  const counts = { stt: proxy.counts.stt, tts: proxy.counts.tts, injected: proxy.counts.injected };
  report.section("Gnani traffic through the fault proxy");
  report.note(`STT calls ${counts.stt}, TTS calls ${counts.tts}, injected failures ${counts.injected}`);
  return { proxy: counts };
}
