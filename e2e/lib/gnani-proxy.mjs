// A local pass-through proxy in front of the real Gnani API, used only by the error-path stack.
//
// The second backend (port 8002) is started with GNANI_API_BASE_URL pointing here. Every request is forwarded
// unchanged to https://api.vachana.ai and the real response is returned, unless a fault is switched on for that
// service, in which case the proxy answers the way Gnani does when it fails (429 busy, 500 error).
// This lets the harness prove the apps' failure handling with the real API on either side of the fault.
// Nothing is logged: request bodies and the X-API-Key-ID header are passed through, never stored.
import { createServer } from "node:http";

const UPSTREAM = "https://api.vachana.ai";

export function startGnaniProxy(port) {
  const faults = { stt: "pass", tts: "pass" };
  const counts = { stt: 0, tts: 0, injected: 0 };

  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    const service = req.url.startsWith("/stt/") ? "stt" : req.url.includes("/tts/") ? "tts" : "other";
    if (service !== "other") counts[service] += 1;
    const fault = faults[service] ?? "pass";

    if (fault === "429") {
      counts.injected += 1;
      res.writeHead(429, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: { error_code: "RATE_LIMITED", message: "Too many requests", status_code: 429 } }));
      return;
    }
    if (fault === "500") {
      counts.injected += 1;
      res.writeHead(500, { "Content-Type": "application/json" });
      const payload =
        service === "stt"
          ? { success: false, error: { type: "internal_error", message: "Internal server error" } }
          : { success: false, message: "Internal server error", status_code: 500 };
      res.end(JSON.stringify(payload));
      return;
    }

    const headers = {};
    for (const [k, v] of Object.entries(req.headers)) {
      if (!["host", "content-length", "connection", "accept-encoding"].includes(k)) headers[k] = v;
    }
    try {
      const upstream = await fetch(UPSTREAM + req.url, {
        method: req.method,
        headers,
        body: ["GET", "HEAD"].includes(req.method) ? undefined : body,
      });
      const data = Buffer.from(await upstream.arrayBuffer());
      const out = {};
      for (const k of ["content-type", "x-request-id"]) if (upstream.headers.get(k)) out[k] = upstream.headers.get(k);
      res.writeHead(upstream.status, out);
      res.end(data);
    } catch {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: { error_code: "PROXY_UPSTREAM_ERROR", message: "upstream unreachable" } }));
    }
  });

  return new Promise((resolve) =>
    server.listen(port, "127.0.0.1", () =>
      resolve({
        set(next) {
          Object.assign(faults, next);
        },
        counts,
        close: () => new Promise((r) => server.close(r)),
      }),
    ),
  );
}
