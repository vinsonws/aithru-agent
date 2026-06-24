// Local development mock host.
//
// In production hosted mode the Platform shell posts AITHRU_HOST_INIT /
// AITHRU_HOST_CONTEXT_CHANGED and validates child origins. In local dev there
// is no shell, so we synthesize a runtime context. Debug controls (theme/
// locale switchers) are allowed here per constraints §Theme Rules and
// §Hosted Subsystem I18n, but must be hidden in production hosted mode.

import type { HostRuntimeContext } from "./types";

const MOCK_KEY = "aithru-agent:mock-context";

const DEFAULT: HostRuntimeContext = {
  theme: { mode: "system", resolved: "light" },
  locale: { language: "en-US", timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone },
  org: { id: "org_1", name: "Aithru Org" },
  user: { id: "user_1", name: "Local Developer" },
  route: { basePath: "" },
  permissions: ["*"],
};

export function isHosted(): boolean {
  // Hosted when running inside an iframe with a real parent (not about:blank
  // mock) and the host has sent AITHRU_HOST_INIT.
  try {
    return window.self !== window.top && !!window.location.ancestorOrigins?.length;
  } catch {
    return false;
  }
}

export function loadMockContext(): HostRuntimeContext {
  if (isHosted()) return DEFAULT;
  try {
    const raw = localStorage.getItem(MOCK_KEY);
    if (raw) return { ...DEFAULT, ...JSON.parse(raw) };
  } catch {
    // ignore
  }
  return DEFAULT;
}

export function saveMockContext(ctx: Partial<HostRuntimeContext>): void {
  if (isHosted()) return; // never persist in production hosted mode
  try {
    const merged = { ...loadMockContext(), ...ctx };
    localStorage.setItem(MOCK_KEY, JSON.stringify(merged));
  } catch {
    // ignore
  }
}
