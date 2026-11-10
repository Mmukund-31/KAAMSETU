// The demo scenario (docs/DEMO_SCRIPT.md), across both apps, against the real backend, Prisma and Timbre:
//   tech1 speaks a Hinglish report -> preview -> send -> supervisor sees it, approves, assigns tech2 (Telugu)
//   -> tech2 hears the task, starts, completes the SOP checklist, completes -> supervisor closes -> dashboard.
// Every claim is checked against the API responses the apps received and against the PostgreSQL rows.
import { PORTS, PATHS } from "../lib/config.mjs";
import { api, db, newContext, plays, recordings, speak, techSignIn, timed, track, unexpectedConsoleErrors, webSignIn } from "../lib/harness.mjs";

const SENTENCE_RE = /M-?204/i;

export async function demo({ report, browser, speechSeconds, shot }) {
  const A = api();
  const sup = await A.login("supervisor@kaamsetu.demo");
  const before = await A.ok("GET", "/dashboard/overview", sup);
  const timings = {};

  // Supervisor console open on the approval queue before the report exists.
  report.section("Demo 1: supervisor console waiting on the approval queue");
  const web = await newContext(browser, { width: 1440, height: 900 });
  await webSignIn(web.page, "supervisor@kaamsetu.demo");
  await web.page.goto(`http://localhost:${PORTS.web}/approvals`);
  await web.page.getByRole("heading", { name: "Approvals" }).waitFor();
  report.check("supervisor signed in, approvals open", true);

  // ── technician 1 reports by voice ──────────────────────────────────────
  report.section("Demo 2: tech1 reports the M-204 fault by voice (Hinglish)");
  const t1 = await newContext(browser);
  await techSignIn(t1.page, `http://localhost:${PORTS.tech}`, "tech1@kaamsetu.demo");
  await shot(t1.page, "demo-01-report-home");
  const outcomeResponse = t1.page.waitForResponse((r) => r.url().includes("/voice/process-report"), { timeout: 90_000 });
  const playsBefore = await plays(t1.page);
  await speak(t1.page, "mic-button", Math.ceil(speechSeconds) + 1);
  const [response, previewSeconds] = await timed(async () => {
    const r = await outcomeResponse;
    await t1.page.getByTestId("preview-machine").waitFor({ timeout: 30_000 });
    return r;
  });
  const outcome = await response.json();
  timings.stop_to_preview_s = previewSeconds;
  const sttId = outcome.utterances?.[0]?.gnani_request_id;
  report.check("Prisma transcript received", response.status() === 200 && outcome.original_transcript, `"${outcome.original_transcript}"`);
  report.check("equipment M-204 matched in the register", outcome.equipment.status === "matched" && outcome.equipment.equipment.code === "M-204");
  report.check("category mechanical", outcome.category.value === "mechanical", outcome.category.basis);
  report.check("symptoms extracted", outcome.symptoms.length >= 2, outcome.symptoms.map((s) => s.key).join(", "));
  report.check("production running", outcome.draft.production_impact === "running");
  report.check("priority from rules", ["high", "critical"].includes(outcome.priority.level), `${outcome.priority.level} (${outcome.priority.rule_id})`);
  report.check("next action is confirm", outcome.next_action === "confirm_preview");
  report.check("Prisma request id recorded", !!sttId, sttId);
  const rec = (await recordings(t1.page))[0];
  report.check("recorded as AAC in MP4 (.m4a)", /^audio\/mp4/.test(rec?.mimeType ?? "") && rec?.head?.startsWith("ftyp"), `${rec?.mimeType} ${rec?.head}`);
  await t1.page.waitForTimeout(500);
  report.check("Timbre reply played", (await plays(t1.page)) > playsBefore && outcome.response.tts_available, outcome.response.text);
  report.note(`stop -> preview on screen: ${previewSeconds}s`);
  await shot(t1.page, "demo-02-preview");

  const createResponse = t1.page.waitForResponse((r) => r.url().endsWith("/api/v1/work-orders") && r.request().method() === "POST");
  await t1.page.getByTestId("send-report").click();
  const [created, submitSeconds] = await timed(async () => (await createResponse).json());
  await t1.page.getByTestId("submitted-number").waitFor();
  const number = created.work_order.display_number;
  const woId = created.work_order.id;
  track("wo", woId);
  timings.send_to_ack_s = submitSeconds;
  report.check("work order created and sent for review", created.work_order.status === "under_review", number);
  report.check("spoken acknowledgement", created.response?.tts_available === true, created.response?.text);
  report.note(`send -> work order + acknowledgement: ${submitSeconds}s`);
  await shot(t1.page, "demo-03-submitted");

  // ── supervisor approves and assigns ────────────────────────────────────
  report.section("Demo 3: supervisor approves and assigns tech2");
  const [, seenSeconds] = await timed(() =>
    web.page.getByRole("link", { name: `Open ${number}` }).waitFor({ timeout: 30_000 }),
  );
  timings.report_visible_on_web_s = seenSeconds;
  report.check("new report appears in the queue (15 s polling)", seenSeconds <= 20, `${seenSeconds}s`);
  await shot(web.page, "demo-04-approvals");
  await web.page.getByRole("link", { name: `Open ${number}` }).click();
  await web.page.getByText("What the technician said").waitFor();
  report.check("detail shows the verbatim transcript", await web.page.getByText(outcome.original_transcript.slice(0, 40), { exact: false }).first().isVisible());
  await shot(web.page, "demo-05-detail");
  await web.page.getByRole("button", { name: "Approve", exact: true }).click();
  await web.page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await web.page.locator('[data-status="approved"]').first().waitFor();
  await web.page.getByRole("button", { name: "Assign technician" }).click();
  const dialog = web.page.getByRole("dialog");
  const select = dialog.getByLabel(/Technician/);
  await select.locator("option", { hasText: "Telugu" }).first().waitFor({ state: "attached" });
  await select.selectOption(await select.locator("option", { hasText: "Telugu" }).first().getAttribute("value"));
  await dialog.getByRole("button", { name: "Assign" }).click();
  await web.page.locator('[data-status="assigned"]').first().waitFor();
  report.check("approved and assigned to tech2 in the console", true);
  await web.page.getByText(/SOP checklist ·/).waitFor();
  report.check("SOP checklist attached on assignment", true);

  // ── technician 2 works the task ────────────────────────────────────────
  report.section("Demo 4: tech2 (Telugu) receives, works and completes the task");
  const t2 = await newContext(browser);
  await techSignIn(t2.page, `http://localhost:${PORTS.tech}`, "tech2@kaamsetu.demo");
  await t2.page.locator("text=నా పని >> visible=true").first().click();
  const [, taskSeconds] = await timed(() => t2.page.getByTestId(`task-${number}`).waitFor({ timeout: 40_000 }));
  report.check("task in tech2's list", true, `${taskSeconds}s`);
  const p2 = await plays(t2.page);
  await t2.page.getByTestId(`task-${number}`).click();
  const announcement = await t2.page.getByTestId("task-announcement").innerText();
  report.check("announcement in Telugu, shown as text", /[ఀ-౿]/.test(announcement) && announcement.includes(number), announcement);
  await t2.page.waitForTimeout(2500);
  report.check("announcement spoken by Timbre", (await plays(t2.page)) > p2);
  await shot(t2.page, "demo-06-task-telugu");
  await t2.page.getByTestId("action-in_progress").click();
  await t2.page.getByTestId("step-1-done").waitFor({ timeout: 20_000 });
  const steps = await t2.page.locator('[data-testid$="-done"]').count();
  for (let i = 1; i <= steps; i += 1) {
    await t2.page.getByTestId(`step-${i}-done`).click();
    await t2.page.locator(`[data-testid="step-${i}"]`).getByText(/✓/).waitFor({ timeout: 15_000 });
  }
  report.check(`${steps} checklist steps recorded`, steps >= 1);
  await shot(t2.page, "demo-07-checklist");
  await t2.page.getByTestId("action-completion_review").click();
  await t2.page.getByTestId("action-comment").fill("Bearing badla, vibration normal");
  const p3 = await plays(t2.page);
  await t2.page.getByTestId("confirm-action").click();
  await t2.page.getByTestId("spoken-reply").waitFor({ timeout: 30_000 });
  await t2.page.waitForTimeout(800);
  report.check("completion acknowledged in Telugu, text and voice", (await plays(t2.page)) > p3, (await t2.page.getByTestId("spoken-reply").innerText()).split("\n")[0]);
  await shot(t2.page, "demo-08-complete");

  // ── supervisor closes ──────────────────────────────────────────────────
  report.section("Demo 5: supervisor closes; dashboard and audit");
  await web.page.goto(`http://localhost:${PORTS.web}/approvals?tab=completion`);
  await web.page.getByRole("link", { name: `Open ${number}` }).click();
  await web.page.getByText("Mandatory steps complete").waitFor();
  await web.page.getByRole("button", { name: "Close work order" }).click();
  await web.page.getByRole("dialog").getByRole("button", { name: "Close work order" }).click();
  await web.page.locator('[data-status="closed"]').first().waitFor();
  report.check("closed in the console", true);
  await shot(web.page, "demo-09-closed");
  const after = await A.ok("GET", "/dashboard/overview", sup);
  report.check("dashboard closed count +1", (after.by_status.closed ?? 0) === (before.by_status.closed ?? 0) + 1);
  await web.page.goto(`http://localhost:${PORTS.web}/`);
  await web.page.getByText("Awaiting approval").waitFor();
  await shot(web.page, "demo-10-overview");

  // ── database evidence ──────────────────────────────────────────────────
  report.section("Demo 6: database evidence");
  const ev = db("evidence", number);
  report.check("work_orders row closed, assigned to tech2", ev.work_order.status === "closed" && ev.work_order.assigned_to === "Lakshmi Reddy", `${ev.work_order.number} ${ev.work_order.equipment} ${ev.work_order.priority}`);
  report.check("evidence keeps the Prisma request id", ev.evidence.prisma_request_id === sttId, ev.evidence.prisma_request_id);
  report.check("evidence keeps the transcript verbatim", ev.evidence.original_transcript === outcome.original_transcript);
  report.check("no audio stored (AUDIO_RETENTION=none)", ev.evidence.audio_retained === false);
  report.check(`${steps} checklist responses by tech2`, ev.checklist_responses.length === steps && ev.checklist_responses.every((r) => r.by === "Lakshmi Reddy"));
  const trail = ev.audit.filter((a) => a.action === "work_order.transition").map((a) => `${a.from}->${a.to}`);
  const expected = ["reported->under_review", "under_review->approved", "approved->assigned", "assigned->in_progress", "in_progress->completion_review", "completion_review->closed"];
  report.check("audit transitions in order", JSON.stringify(trail) === JSON.stringify(expected), trail.join(", "));
  report.check("audit sequence strictly increasing", ev.audit.every((a, i, all) => i === 0 || a.seq > all[i - 1].seq), `${ev.audit.length} rows`);
  report.check("no console errors in either app", [t1, t2, web].every((c) => unexpectedConsoleErrors(c.page).length === 0),
    [t1, t2, web].flatMap((c) => unexpectedConsoleErrors(c.page)).slice(0, 3).join(" | "));

  for (const c of [t1, t2, web]) await c.context.close();
  return { number, woId, timings, evidence: ev, transcript: outcome.original_transcript, sttId, ttsVoice: outcome.response.voice, pathsNote: PATHS.run };
}
