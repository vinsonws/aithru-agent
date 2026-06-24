// Typed HTTP client for the Aithru Agent backend.
//
// Security rules (aithru-docs 03-frontend-constraints):
//   - Access token stays in memory only (held by the host bridge / auth provider).
//   - The browser is never the security authority; the backend enforces identity.
//   - Identity (org/user) is supplied via trusted X-Aithru-* headers bound by the
//     backend to the active hosted token context.

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
  const { token, orgId, userId } = currentContext;
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (orgId) headers.set("x-aithru-org-id", orgId);
  if (userId) headers.set("x-aithru-user-id", userId);
  return headers;
}

async function parseError(res: Response): Promise<ApiError> {
  let code: string | undefined;
  let message = res.statusText || `Request failed (${res.status})`;
  try {
    const body = await res.json();
    code = body?.code ?? body?.error_code;
    message = body?.detail ?? body?.message ?? message;
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
  /** Override Accept/Content-Type when needed. */
  headers?: HeadersInit;
  /** Return raw Response (e.g. for file downloads). */
  raw?: boolean;
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

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = buildHeaders(opts.headers);
  const init: RequestInit = { method: opts.method ?? "GET", signal: opts.signal };
  if (opts.body !== undefined) {
    headers.set("content-type", "application/json");
    init.body = JSON.stringify(opts.body);
  }
  init.headers = headers;

  const res = await fetch(withQuery(path, opts.query), init);
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
): Promise<void> {
  const headers = buildHeaders({ accept: "text/event-stream" });
  // fetch-based SSE: read the streaming body and parse `data:` frames.
  return fetch(path, { method: "GET", headers, signal })
    .then(async (res) => {
      if (!res.ok || !res.body) throw await parseError(res);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
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
      throw err;
    });
}
