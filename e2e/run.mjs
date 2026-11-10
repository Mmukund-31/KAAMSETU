// KAAMSETU end-to-end harness. Usage (from e2e/):  node run.mjs [demo|errors|all] [--keep] [--docs] [--no-build]
//
// Starts its own stack (two backends, a Gnani fault proxy, the supervisor console and two technician web builds),
// runs the scenarios in headless Edge with a fake microphone, deletes the records it created, scans the server logs
// for secrets and writes .run/report.md. Real Prisma and Timbre are called; this spends a few Gnani credits.
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { PATHS, PORTS } from "./lib/config.mjs";
import { startGnaniProxy } from "./lib/gnani-proxy.mjs";
import { Report, db, launchBrowser } from "./lib/harness.mjs";
import { portInUse, serveStatic, start, stop, stopAll, waitFor } from "./lib/servers.mjs";
import { padWithSilence, writeSilence } from "./lib/wav.mjs";
import { demo } from "./scenarios/demo.mjs";
import { errors } from "./scenarios/errors.mjs";

const args = process.argv.slice(2);
const which = args.find((a) => !a.startsWith("--")) ?? "all";
const keep = args.includes("--keep");
const docs = args.includes("--docs");
const build = !args.includes("--no-build");

const report = new Report();
const closers = [];
let exitCode = 1;

async function main() {
  mkdirSync(PATHS.shots, { recursive: true });
  writeFileSync(PATHS.createdFile, "");
  const logDir = join(PATHS.run, "logs");
  mkdirSync(logDir, { recursive: true });

  report.section("Preflight");
  const busy = [];
  for (const [name, port] of Object.entries(PORTS)) if (await portInUse(port)) busy.push(`${name}:${port}`);
  if (!report.check("harness ports are free (nothing already running is touched)", busy.length === 0, busy.join(", "))) return;
  const initial = db("counts");
  report.check("database reachable", typeof initial.work_orders === "number", JSON.stringify(initial));

  // Fake microphone: the Timbre-generated Hinglish M-204 sentence plus silence, and a silent file.
  const raw = join(PATHS.run, "speech-raw.wav");
  execFileSync("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PATHS.makeWav, PATHS.speechSource, raw], { stdio: "ignore" });
  const speech = join(PATHS.run, "mic-speech.wav");
  const silence = join(PATHS.run, "mic-silence.wav");
  const { speechSeconds } = padWithSilence(raw, speech, 6);
  writeSilence(silence, 4);
  report.check("fake microphone files ready", existsSync(speech) && existsSync(silence), `speech ${speechSeconds.toFixed(1)} s + 6 s silence`);

  const techWeb = join(PATHS.run, "tech-web");
  const techFaults = join(PATHS.run, "tech-web-faults");
  if (build || !existsSync(techWeb) || !existsSync(techFaults)) {
    for (const [dir, port] of [[techWeb, PORTS.api], [techFaults, PORTS.faultApi]]) {
      rmSync(dir, { recursive: true, force: true });
      execFileSync(process.execPath, [join(PATHS.technicianApp, "node_modules", "expo", "bin", "cli"), "export", "--platform", "web", "--output-dir", dir, "--clear"], {
        cwd: PATHS.technicianApp,
        env: { ...process.env, CI: "1", EXPO_PUBLIC_API_URL: `http://localhost:${port}` },
        stdio: "ignore",
      });
    }
  }
  report.check("technician web builds (-> 8001 and -> 8002)", existsSync(join(techWeb, "index.html")) && existsSync(join(techFaults, "index.html")));

  // Login and voice rate limits are raised for the harness only: it signs in a dozen times a minute from one IP.
  const backendEnv = { RATE_LIMIT_LOGIN_PER_MINUTE: "200", RATE_LIMIT_VOICE_PER_MINUTE: "200", LOG_LEVEL: "INFO" };
  const uvicorn = ["-m", "uvicorn", "app.main:app", "--port"];
  start("api", PATHS.python, [...uvicorn, String(PORTS.api)], { cwd: PATHS.backend, env: backendEnv, logDir });
  const proxy = await startGnaniProxy(PORTS.gnaniProxy);
  closers.push(proxy.close);
  start("api-faults", PATHS.python, [...uvicorn, String(PORTS.faultApi)], {
    cwd: PATHS.backend,
    env: { ...backendEnv, GNANI_API_BASE_URL: `http://127.0.0.1:${PORTS.gnaniProxy}`, CORS_ORIGINS: `http://localhost:${PORTS.techFaults}` },
    logDir,
  });
  start("supervisor-web", process.execPath, [join(PATHS.supervisorWeb, "node_modules", "vite", "bin", "vite.js"), "--port", String(PORTS.web), "--strictPort"], {
    cwd: PATHS.supervisorWeb,
    logDir,
  });
  closers.push(await serveStatic(techWeb, PORTS.tech));
  closers.push(await serveStatic(techFaults, PORTS.techFaults));
  const health = await (await waitFor(`http://localhost:${PORTS.api}/api/v1/health`)).json();
  await waitFor(`http://localhost:${PORTS.faultApi}/api/v1/health`);
  await waitFor(`http://localhost:${PORTS.web}/`);
  report.check("stack up: backend, fault backend, proxy, console, two app builds", true, `gnani_configured=${health.gnani_configured}`);
  if (!report.check("Gnani key configured", health.gnani_configured === true)) return;

  const browser = await launchBrowser(speech);
  const silentBrowser = await launchBrowser(silence);
  closers.push(() => browser.close(), () => silentBrowser.close());
  const shot = (page, name) => page.screenshot({ path: join(PATHS.shots, `${name}.png`) });
  const context = { report, browser, silentBrowser, proxy, speechSeconds, shot, stopFaultBackend: async () => stop("api-faults") };

  const results = {};
  for (const [name, fn] of [["demo", demo], ["errors", errors]]) {
    if (which !== "all" && which !== name) continue;
    try {
      results[name] = await fn(context);
    } catch (err) {
      report.check(`${name} scenario ran to the end`, false, err.message.split("\n")[0]);
    }
  }
  writeFileSync(join(PATHS.run, "results.json"), JSON.stringify(results, null, 2));

  // Clean up and verify the dev DB is back where it started.
  report.section("Cleanup and log scan");
  stopAll();
  if (!keep) {
    const cleaned = db("cleanup", PATHS.createdFile);
    report.check("created records removed; DB back to its starting counts", JSON.stringify(cleaned.now) === JSON.stringify(initial), `${cleaned.deleted_work_orders.join(" ")} | now ${JSON.stringify(cleaned.now)}`);
  } else {
    report.note("--keep: created records left in the DB (ids in .run/created.txt)");
  }
  const envFile = readFileSync(join(PATHS.backend, ".env"), "utf8");
  const secret = (k) => envFile.match(new RegExp(`^${k}=(.+)$`, "m"))?.[1]?.trim();
  const logs = ["api", "api-faults"].map((n) => readFileSync(join(logDir, `${n}.log`), "utf8")).join("\n");
  const leaks = [
    ["Gnani key", secret("GNANI_API_KEY")],
    ["JWT secret", secret("JWT_SECRET_KEY")],
    ["demo password", PATHS.password],
  ].filter(([, v]) => v && logs.includes(v)).map(([k]) => k);
  if (/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/.test(logs)) leaks.push("bearer token");
  if (results.demo?.transcript && logs.includes(results.demo.transcript.slice(0, 30))) leaks.push("transcript text");
  report.check("server logs contain no secrets, tokens or transcripts", leaks.length === 0, leaks.join(", ") || `${logs.length} bytes scanned`);

  if (docs) {
    const target = join(PATHS.root, "docs", "screenshots");
    mkdirSync(target, { recursive: true });
    for (const name of ["demo-02-preview", "demo-03-submitted", "demo-04-approvals", "demo-05-detail", "demo-06-task-telugu", "demo-07-checklist", "demo-09-closed", "demo-10-overview", "err-07-tts-down", "err-05-busy"]) {
      const file = join(PATHS.shots, `${name}.png`);
      if (existsSync(file)) copyFileSync(file, join(target, `${name}.png`));
    }
    report.note(`screenshots copied to docs/screenshots`);
  }
  exitCode = report.failed.length ? 1 : 0;
}

function writeReport() {
  const lines = [`# KAAMSETU end-to-end run`, ``, `Run at ${new Date().toISOString()} · ${report.total - report.failed.length}/${report.total} checks passed`, ``];
  for (const s of report.sections) {
    lines.push(`## ${s.title}`, "", "| | Check | Detail |", "|---|---|---|");
    for (const c of s.checks) lines.push(`| ${c.ok ? "PASS" : "**FAIL**"} | ${c.name} | ${c.detail.replace(/\|/g, "/")} |`);
    for (const n of s.notes) lines.push(``, `> ${n}`);
    lines.push("");
  }
  writeFileSync(join(PATHS.run, "report.md"), lines.join("\n"));
}

try {
  await main();
} catch (err) {
  report.section("Harness error");
  report.check("harness completed", false, err.stack?.split("\n").slice(0, 3).join(" "));
} finally {
  for (const close of closers.reverse()) await Promise.resolve(close()).catch(() => undefined);
  stopAll();
  writeReport();
  console.log(`\n${report.total - report.failed.length}/${report.total} checks passed. Report: e2e/.run/report.md`);
  process.exit(exitCode);
}
