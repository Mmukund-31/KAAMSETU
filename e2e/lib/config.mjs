import { fileURLToPath } from "node:url";
import { join } from "node:path";

const here = fileURLToPath(new URL("..", import.meta.url));
const root = join(here, "..");
const run = join(here, ".run");

/** Ports owned by the harness. Each must be free before a run; nothing already running is touched. */
export const PORTS = {
  api: 8001, // backend with the real Gnani API
  faultApi: 8002, // second backend whose Gnani traffic goes through the fault proxy
  gnaniProxy: 8099,
  web: 5173, // supervisor-web dev server (proxies /api to 8001)
  tech: 8081, // technician web build -> 8001
  techFaults: 8082, // technician web build -> 8002
};

export const PATHS = {
  root,
  run,
  backend: join(root, "backend"),
  supervisorWeb: join(root, "supervisor-web"),
  technicianApp: join(root, "technician-app"),
  python: join(root, "backend", ".venv", process.platform === "win32" ? "Scripts\\python.exe" : "bin/python"),
  dbTool: join(here, "tools", "db.py"),
  makeWav: join(here, "tools", "make-wav.ps1"),
  speechSource: join(root, "backend", "app", "tests", "fixtures", "audio", "hinglish_m204.mp3"),
  createdFile: join(run, "created.txt"),
  shots: join(run, "shots"),
  password: "Kaamsetu@2026", // synthetic seed accounts (README)
};
