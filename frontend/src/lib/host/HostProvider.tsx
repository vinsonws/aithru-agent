import * as React from "react";
import { AithruHostedApp, type HostedAppApi, type HostedAppRuntimeContext } from "@aithru/front-hosted-app-sdk";
import { setHostedApiFetch, setRequestContext } from "@/lib/api/client";
import { isHosted, loadMockContext, saveMockContext } from "./mock-host";
import type { HostOutboundRequest, HostRuntimeContext, ResolvedTheme, ThemeMode } from "./types";

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

const appKey = import.meta.env?.VITE_AITHRU_APP_KEY ?? "agent";

function routeBasePath(): string {
  const base = import.meta.env?.BASE_URL ?? "/";
  return base === "/" ? "" : base.replace(/\/+$/, "");
}

function themeMode(value: unknown): ThemeMode {
  return value === "dark" || value === "light" || value === "system" ? value : "light";
}

function resolvedTheme(value: unknown, mode: ThemeMode): ResolvedTheme {
  return value === "dark" || value === "light" ? value : resolveTheme(mode);
}

function contextFromHostedApi(api: HostedAppApi, runtime?: HostedAppRuntimeContext | null): HostRuntimeContext {
  const hostRuntime = runtime ?? api.host.runtimeContext ?? {};
  const mode = themeMode(hostRuntime.theme?.mode);
  const authContext = api.host.authContext;
  const hostUser = api.host.user;
  const authUser = authContext?.user;
  return {
    theme: {
      mode,
      resolved: resolvedTheme(hostRuntime.theme?.resolved, mode),
    },
    locale: {
      language: hostRuntime.locale?.language ?? "en-US",
      timeZone: hostRuntime.locale?.timeZone,
    },
    org: authContext?.org
      ? { id: authContext.org.id, name: authContext.org.name }
      : api.host.orgId
        ? { id: api.host.orgId }
        : undefined,
    user: hostUser || authUser
      ? {
          id: hostUser?.id ?? authUser?.id ?? "",
          name: hostUser?.displayName ?? hostUser?.name ?? authUser?.name,
        }
      : undefined,
    route: { basePath: routeBasePath() },
    permissions: authContext?.app?.permissions ?? [],
  };
}

export function HostProvider({ children }: { children: React.ReactNode }) {
  const hosted = isHosted();
  const hostedApiRef = React.useRef<HostedAppApi | null>(null);
  const [context, setContext] = React.useState<HostRuntimeContext>(() => {
    const initial = loadMockContext();
    return { ...initial, theme: { ...initial.theme, resolved: resolveTheme(initial.theme.mode) } };
  });
  const [ready, setReady] = React.useState(false);

  // Keep local UI context available; hosted API auth is handled by SDK fetch.
  React.useEffect(() => {
    setRequestContext({
      orgId: context.org?.id ?? null,
      userId: context.user?.id ?? null,
      token: null,
    });
  }, [context.org?.id, context.user?.id]);

  // Apply theme.resolved to <html> and bridge Antd tokens reactively.
  React.useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", context.theme.resolved === "dark");
  }, [context.theme.resolved]);

  // Connect to the platform host in hosted mode; local dev keeps the lightweight mock context.
  React.useEffect(() => {
    if (!hosted) {
      setHostedApiFetch(null);
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

    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    const hostedApp = new AithruHostedApp();
    const platformOrigin = new URLSearchParams(window.location.search).get("aithruHostOrigin") ?? undefined;

    hostedApp.connect({ appKey, platformOrigin })
      .then((api) => {
        if (cancelled) return;
        hostedApiRef.current = api;
        setHostedApiFetch(api.fetch);
        setContext(contextFromHostedApi(api));
        unsubscribe = api.onContextChange((runtimeContext) => {
          setContext(contextFromHostedApi(api, runtimeContext));
        });
        setReady(true);
      })
      .catch((error: unknown) => {
        console.error("Aithru host connection failed", error);
      });

    return () => {
      cancelled = true;
      unsubscribe?.();
      hostedApiRef.current = null;
      setHostedApiFetch(null);
    };
  }, [hosted]);

  const send = React.useCallback(
    (req: HostOutboundRequest) => {
      const api = hostedApiRef.current;
      if (!hosted || !api) return;
      if (req.type === "AITHRU_NAVIGATE" && req.path) {
        api.navigate(req.path);
      }
    },
    [hosted],
  );

  const requestToken = React.useCallback(
    (scopes?: string[]) => {
      void hostedApiRef.current?.auth.getToken(scopes);
    },
    [],
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
