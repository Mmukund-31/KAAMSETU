// Starts and stops exactly the processes this harness owns (never anything else on the machine).
import { spawn, execFileSync } from "node:child_process";
import { createWriteStream } from "node:fs";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createConnection } from "node:net";
import { extname, join, resolve, sep } from "node:path";

const owned = [];

export function start(name, command, args, { cwd, env = {}, logDir }) {
  const log = createWriteStream(join(logDir, `${name}.log`));
  const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, windowsHide: true });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  owned.push({ name, child });
  return child;
}

/** Kills one owned process and its children (uvicorn and vite spawn helpers on Windows). */
export function stop(name) {
  const index = owned.findIndex((p) => p.name === name);
  if (index < 0) return;
  const [{ child }] = owned.splice(index, 1);
  killTree(child.pid);
}

export function stopAll() {
  while (owned.length) {
    const { child } = owned.pop();
    killTree(child.pid);
  }
}

function killTree(pid) {
  try {
    if (process.platform === "win32") execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    else process.kill(-pid, "SIGTERM");
  } catch {
    // already gone
  }
}

export function portInUse(port) {
  return new Promise((resolvePromise) => {
    const socket = createConnection({ port, host: "127.0.0.1" });
    socket.once("connect", () => {
      socket.destroy();
      resolvePromise(true);
    });
    socket.once("error", () => resolvePromise(false));
  });
}

export async function waitFor(url, { timeoutMs = 60_000, ok = (r) => r.ok } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (ok(response)) return response;
      last = `HTTP ${response.status}`;
    } catch (err) {
      last = err.message;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${url} did not come up (${last})`);
}

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".png": "image/png", ".ttf": "font/ttf", ".ico": "image/x-icon" };

/** Serves an Expo web export with single-page fallback. In-process, closed with the returned function. */
export function serveStatic(dir, port) {
  const root = resolve(dir);
  const server = createServer(async (req, res) => {
    const file = resolve(join(root, decodeURIComponent(new URL(req.url, "http://x").pathname)));
    const inside = file === root || file.startsWith(root + sep);
    try {
      if (!inside) throw new Error("outside root");
      const data = await readFile(file);
      res.writeHead(200, { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream" });
      res.end(data);
    } catch {
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(await readFile(join(root, "index.html")));
    }
  });
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r(() => new Promise((c) => server.close(c)))));
}
