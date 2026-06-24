import * as React from "react";
import { setRequestContext } from "@/lib/api/client";
import { isHosted, loadMockContext, saveMockContext } from "./mock-host";
import type { HostInboundMessage, HostOutboundRequest, HostRuntimeContext } from "./types";

interface HostState {
  context: HostRuntimeContext;
  hosted: boolean;
  ready: boolean;
  /** Update local (mock-dev only) context; in hosted mode context comes from host. */
  updateLocal: (patch: Partial<HostRuntimeContext>) => void;
  requestToken: (scopes?: string[]) => void;
  send: (req: HostOutboundRequest) => void;
}

const HostContext = React.createContext<HostState | null>(null);

export function useHost(): HostState {
  const ctx = React.useContext(HostContext);
  if (!ctx) throw new Error("useHost must be used within HostProvider");
  return ctx;
}

function resolveTheme(mode: HostRuntimeContext["theme"]["mode"]): "light" | "dark" {
  if (mode === "system") {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return mode;
}

export function HostProvider({ children }: { children: React.ReactNode }) {
  const hosted = isHosted();
  const tokenRef = React.useRef<string | null>(null);
  const [context, setContext] = React.useState<HostRuntimeContext>(() => {
    const initial = loadMockContext();
    return { ...initial, theme: { ...initial.theme, resolved: resolveTheme(initial.theme.mode) } };
  });
  const [ready, setReady] = React.useState(false);

  // Wire the typed API client with identity headers + in-memory token.
  React.useEffect(() => {
    setRequestContext({
      orgId: context.org?.id ?? null,
      userId: context.user?.id ?? null,
      // In hosted mode the token arrives via AITHRU_HOST_INIT. In dev mock we
      // fall back to a configured backend token from env (kept in memory only).
      token: tokenRef.current,
    });
  }, [context.org?.id, context.user?.id]);

  // Apply theme.resolved to <html> and bridge Antd tokens reactively.
  React.useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", context.theme.resolved === "dark");
  }, [context.theme.resolved]);

  // Listen for host postMessage (validated origin) in hosted mode.
  React.useEffect(() => {
    if (!hosted) {
      setReady(true);
      // Dev: keep system theme preference reactive.
      const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
      const handler = () => {
        setContext((c) =>
          c.theme.mode === "system"
            ? { ...c, theme: { ...c.theme, resolved: mq?.matches ? "dark" : "light" } }
            : c,
        );
      };
      mq?.addEventListener("change", handler);
      return () => mq?.removeEventListener("change", handler);
    }

    const allowedOrigin = window.location.ancestorOrigins?.[0] ?? "*";

    const onMessage = (event: MessageEvent) => {
      // Validate origin against registered app origin (constraint §Security).
      if (allowedOrigin !== "*" && event.origin !== allowedOrigin) return;
      const msg = event.data as HostInboundMessage;
      if (!msg || typeof msg.type !== "string") return;
      if (msg.type === "AITHRU_HOST_INIT") {
        tokenRef.current = msg.token ?? null;
        setContext({ ...msg.runtimeContext, theme: { ...msg.runtimeContext.theme } });
        setRequestContext({ token: tokenRef.current });
        setReady(true);
      } else if (msg.type === "AITHRU_HOST_CONTEXT_CHANGED") {
        setContext((c) => {
          const merged = { ...c, ...msg.changed };
          if (msg.changed.theme) {
            merged.theme = {
              mode: msg.changed.theme.mode ?? c.theme.mode,
              resolved: msg.changed.theme.resolved ?? resolveTheme(msg.changed.theme.mode ?? c.theme.mode),
            };
          }
          return merged;
        });
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [hosted]);

  const send = React.useCallback(
    (req: HostOutboundRequest) => {
      if (hosted && window.parent !== window.self) {
        window.parent.postMessage(req, "*");
      }
    },
    [hosted],
  );

  const requestToken = React.useCallback(
    (scopes?: string[]) => send({ type: "AITHRU_REQUEST_TOKEN", scopes }),
    [send],
  );

  const updateLocal = React.useCallback(
    (patch: Partial<HostRuntimeContext>) => {
      if (hosted) return; // production: never override host authority
      setContext((c) => {
        const next = { ...c, ...patch };
        if (patch.theme?.mode) {
          next.theme = { mode: patch.theme.mode, resolved: resolveTheme(patch.theme.mode) };
        }
        saveMockContext(patch);
        return next;
      });
    },
    [hosted],
  );

  const value = React.useMemo(
    () => ({ context, hosted, ready, updateLocal, requestToken, send }),
    [context, hosted, ready, updateLocal, requestToken, send],
  );

  return <HostContext.Provider value={value}>{children}</HostContext.Provider>;
}
