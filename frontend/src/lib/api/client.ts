// Typed HTTP client for the Aithru Agent backend.
//
// Security rules (aithru-docs 03-frontend-constraints):
//   - Access token stays in memory only (held by the host bridge / auth provider).
//   - The browser is never the security authority; the backend enforces identity.
//   - Identity comes from verified Aithru JWTs, never browser-supplied user/org headers.

export interface AgentRequestContext {
  /** Bearer access token held in memory by the host bridge. */
  token: string | null;
  /** Trusted org identity bound by the backend. */
  orgId: string | null;
  /** Trusted user identity bound by the backend. */
  userId: string | null;
}

let currentContext: AgentRequestContext = {
  token: null,
  orgId: null,
  userId: null,
};

const APP_KEY = import.meta.env?.VITE_AITHRU_APP_KEY ?? "agent";

type HostedApiFetch = (input: RequestInfo | URL, init?: RequestInit, scopes?: string[]) => Promise<Response>;

let hostedApiFetch: HostedApiFetch | null = null;

export function setHostedApiFetch(fetcher: HostedApiFetch | null): void {
  hostedApiFetch = fetcher;
}

export function setRequestContext(ctx: Partial<AgentRequestContext>): void {
  currentContext = { ...currentContext, ...ctx };
}

export function getRequestContext(): AgentRequestContext {
  return currentContext;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const { token } = currentContext;
  if (token) headers.set("authorization", `Bearer ${token}`);
  return headers;
}

async function parseError(res: Response): Promise<ApiError> {
  let code: string | undefined;
  let message = res.statusText || `Request failed (${res.status})`;
  try {
    const body = await res.json();
    code = body?.error?.code ?? body?.code ?? body?.error_code;
    message = body?.error?.message ?? body?.detail ?? body?.message ?? message;
  } catch {
    // non-JSON error body
  }
  return new ApiError(res.status, message, code, res.headers.get("x-request-id") ?? undefined);
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  scopes?: string[];
  /** Override Accept/Content-Type when needed. */
  headers?: HeadersInit;
  /** Return raw Response (e.g. for file downloads). */
  raw?: boolean;
}

export interface EventStreamOptions {
  /** Abort the stream if no bytes arrive during this window. Set <= 0 to disable. */
  idleTimeoutMs?: number;
}

const DEFAULT_EVENT_STREAM_IDLE_TIMEOUT_MS = 45_000;

export class EventStreamKeepaliveTimeoutError extends Error {
  constructor(message = "Event stream keepalive timed out") {
    super(message);
    this.name = "EventStreamKeepaliveTimeoutError";
  }
}

function withQuery(path: string, query?: RequestOptions["query"]): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    params.append(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

function pathName(path: string): string {
  try {
    return new URL(path, "http://aithru.local").pathname;
  } catch {
    return path.split("?")[0] || "/";
  }
}

export function scopesForApiRequest(method: string, path: string): string[] {
  const verb = method.toUpperCase();
  const pathname = pathName(path);
  if (pathname.startsWith("/api/threads")) {
    return [verb === "GET" ? `${APP_KEY}.app.threads.read` : `${APP_KEY}.app.threads.write`];
  }
  if (pathname.startsWith("/api/runs")) {
    if (verb === "GET" || verb === "HEAD") return [`${APP_KEY}.app.runs.read`];
    if (pathname.endsWith("/cancel")) return [`${APP_KEY}.app.runs.cancel`];
    return [`${APP_KEY}.app.runs.execute`];
  }
  if (pathname.startsWith("/api/approvals")) {
    return [verb === "GET" ? `${APP_KEY}.app.approvals.read` : `${APP_KEY}.app.approvals.resolve`];
  }
  if (pathname.startsWith("/api/workspaces")) {
    return [verb === "GET" || verb === "HEAD" ? `${APP_KEY}.app.workspaces.read` : `${APP_KEY}.app.workspaces.write`];
  }
  if (pathname.startsWith("/api/memory") || pathname.startsWith("/api/long-term-memory")) {
    return [`${APP_KEY}.app.memory.manage`];
  }
  if (
    [
      "/api/model-profiles",
      "/api/model-providers",
      "/api/model-default",
      "/api/skills",
      "/api/skill-registry",
      "/api/subagents",
      "/api/external-tools",
    ]
      .some((prefix) => pathname.startsWith(prefix))
  ) {
    return [verb === "GET" || verb === "HEAD" ? `${APP_KEY}.app.settings.read` : `${APP_KEY}.app.settings.manage`];
  }
  return verb === "GET" || verb === "HEAD" ? [`${APP_KEY}.app.view`] : [`${APP_KEY}.app.settings.manage`];
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = buildHeaders(opts.headers);
  const method = opts.method ?? "GET";
  const init: RequestInit = { method, signal: opts.signal };
  if (opts.body !== undefined) {
    headers.set("content-type", "application/json");
    init.body = JSON.stringify(opts.body);
  }
  init.headers = headers;

  const requestPath = withQuery(path, opts.query);
  const scopes = opts.scopes ?? scopesForApiRequest(method, requestPath);
  const res = hostedApiFetch
    ? await hostedApiFetch(requestPath, init, scopes)
    : await fetch(requestPath, init);
  if (!res.ok) throw await parseError(res);
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as unknown as T;
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

/**
 * Subscribe to a Server-Sent Events stream from the backend run stream endpoint.
 * Calls `onEvent` for each parsed `AgentStreamEvent`; resolves when the stream
 * closes (terminal run state) or aborts.
 */
export function openEventStream(
  path: string,
  onEvent: (event: unknown) => void,
  signal?: AbortSignal,
  options: EventStreamOptions = {},
): Promise<void> {
  const headers = buildHeaders({ accept: "text/event-stream" });
  const idleTimeoutMs = options.idleTimeoutMs ?? DEFAULT_EVENT_STREAM_IDLE_TIMEOUT_MS;
  const controller = new AbortController();
  let idleTimer: ReturnType<typeof globalThis.setTimeout> | undefined;
  let keepaliveTimedOut = false;

  const clearIdleTimer = () => {
    if (idleTimer !== undefined) {
      globalThis.clearTimeout(idleTimer);
      idleTimer = undefined;
    }
  };
  const resetIdleTimer = () => {
    if (idleTimeoutMs <= 0) return;
    clearIdleTimer();
    idleTimer = globalThis.setTimeout(() => {
      keepaliveTimedOut = true;
      controller.abort();
    }, idleTimeoutMs);
  };
  const abortFromCaller = () => controller.abort();
  if (signal?.aborted) return Promise.resolve();
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  resetIdleTimer();

  // fetch-based SSE: read the streaming body and parse `data:` frames.
  const fetchStream = hostedApiFetch
    ? hostedApiFetch(path, { method: "GET", headers, signal: controller.signal }, scopesForApiRequest("GET", path))
    : fetch(path, { method: "GET", headers, signal: controller.signal });

  return fetchStream
    .then(async (res) => {
      resetIdleTimer();
      if (!res.ok || !res.body) throw await parseError(res);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        resetIdleTimer();
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLines = frame
            .split("\n")
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trimStart());
          if (!dataLines.length) continue;
          const data = dataLines.join("\n");
          if (data === "[DONE]") return;
          try {
            onEvent(JSON.parse(data));
          } catch {
            // skip malformed frame
          }
        }
      }
    })
    .catch((err) => {
      if (signal?.aborted) return;
      if (keepaliveTimedOut) throw new EventStreamKeepaliveTimeoutError();
      throw err;
    })
    .finally(() => {
      clearIdleTimer();
      signal?.removeEventListener("abort", abortFromCaller);
    });
}
