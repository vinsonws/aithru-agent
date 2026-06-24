// Platform hosted-app runtime context contract.
// Mirrors aithru-docs 03-frontend-constraints §Hosted Subsystem Page Rules.

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export interface HostRuntimeContext {
  theme: { mode: ThemeMode; resolved: ResolvedTheme };
  locale: { language: string; timeZone?: string };
  org?: { id: string; name?: string };
  user?: { id: string; name?: string; avatarUrl?: string };
  route?: { basePath?: string };
  permissions?: string[];
}

export interface HostInitMessage {
  type: "AITHRU_HOST_INIT";
  runtimeContext: HostRuntimeContext;
  /** Hosted access token held in memory only. */
  token?: string | null;
}

export interface HostContextChangedMessage {
  type: "AITHRU_HOST_CONTEXT_CHANGED";
  changed: Partial<HostRuntimeContext>;
}

export type HostInboundMessage = HostInitMessage | HostContextChangedMessage;

export interface HostOutboundRequest {
  type:
    | "AITHRU_REQUEST_TOKEN"
    | "AITHRU_NAVIGATE"
    | "AITHRU_NOTIFY"
    | "AITHRU_OPEN_ADMIN";
  scopes?: string[];
  path?: string;
  level?: "info" | "success" | "warning" | "error";
  message?: string;
}
