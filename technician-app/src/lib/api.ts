import { API_BASE_URL } from "./config";

/**
 * Fetch wrapper for the KAAMSETU API. Errors are always ApiError carrying the backend envelope
 * {error: {code, message, details}}. A 401 clears the session through the registered handler.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let token: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAuthToken(value: string | null): void {
  token = value;
}

export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

type Query = Record<string, string | number | boolean | undefined | null>;

function url(path: string, query?: Query): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") search.append(k, String(v));
  }
  const qs = search.toString();
  return `${API_BASE_URL}/api/v1${path}${qs ? `?${qs}` : ""}`;
}

interface Options {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  form?: FormData;
  query?: Query;
}

export async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { method = "GET", body, form, query } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // For FormData the runtime sets the multipart boundary itself.

  let response: Response;
  try {
    response = await fetch(url(path, query), {
      method,
      headers,
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the KAAMSETU server.");
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const envelope = (data as { error?: { code: string; message: string; details?: Record<string, unknown> } } | null)
      ?.error;
    if (response.status === 401) {
      token = null;
      unauthorizedHandler?.();
    }
    throw new ApiError(
      response.status,
      envelope?.code ?? `http_${response.status}`,
      envelope?.message ?? `Request failed (${response.status})`,
      envelope?.details ?? {},
    );
  }
  return data as T;
}
