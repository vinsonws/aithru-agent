import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import {
  createAithruPlatform,
  type AithruPlatform,
  type AithruTokenClaims,
  type CurrentActor,
} from "@aithru/subsystem-sdk-node";

const APP_KEY = process.env.AITHRU_APP_KEY?.trim() || "agent";

export const AGENT_SCOPES = {
  appView: `${APP_KEY}.app.view`,
  threadsRead: `${APP_KEY}.app.threads.read`,
  threadsWrite: `${APP_KEY}.app.threads.write`,
  runsRead: `${APP_KEY}.app.runs.read`,
  runsExecute: `${APP_KEY}.app.runs.execute`,
  runsCancel: `${APP_KEY}.app.runs.cancel`,
  approvalsRead: `${APP_KEY}.app.approvals.read`,
  approvalsResolve: `${APP_KEY}.app.approvals.resolve`,
  workspacesRead: `${APP_KEY}.app.workspaces.read`,
  workspacesWrite: `${APP_KEY}.app.workspaces.write`,
  memoryManage: `${APP_KEY}.app.memory.manage`,
  settingsRead: `${APP_KEY}.app.settings.read`,
  settingsManage: `${APP_KEY}.app.settings.manage`,
} as const;

type RequestWithActor = FastifyRequest & { aithruActor?: CurrentActor };

export function platformActorFromRequest(request: FastifyRequest): CurrentActor | null {
  return (request as RequestWithActor).aithruActor ?? null;
}

export function requestOrgId(
  actor: CurrentActor | null,
  body?: Record<string, unknown> | null,
  query?: Record<string, unknown> | null,
): string {
  return String(actor?.orgId ?? body?.org_id ?? query?.org_id ?? "org_1");
}

export function requestActorUserId(
  actor: CurrentActor | null,
  body?: Record<string, unknown> | null,
): string {
  return String(actor?.userId ?? actor?.serviceId ?? body?.actor_user_id ?? body?.owner_user_id ?? "user_1");
}

export function actorCanAccessOwnedResource(
  actor: CurrentActor | null,
  resource: { org_id?: string | null; owner_user_id?: string | null; actor_user_id?: string | null },
): boolean {
  if (!actor) return true;
  if (resource.org_id && actor.orgId !== resource.org_id) return false;
  if (scopeAllowed(actor, "*")) return true;
  const actorId = actor.userId ?? actor.serviceId ?? null;
  const ownerId = resource.owner_user_id ?? resource.actor_user_id ?? null;
  return Boolean(actorId && ownerId && actorId === ownerId);
}

export function bodyWithPlatformActor<T extends Record<string, unknown>>(
  body: T,
  actor: CurrentActor | null,
): T {
  if (!actor) return body;
  const actorId = requestActorUserId(actor, body);
  return {
    ...body,
    org_id: requestOrgId(actor, body),
    actor_user_id: actorId,
    owner_user_id: actorId,
  };
}

export function requiredScopeForRequest(method: string, url: string): string | null {
  const path = pathname(url);
  const verb = method.toUpperCase();
  if (path === "/api/health" || path === "/healthz") return null;
  if (!path.startsWith("/api/")) return null;

  if (path.startsWith("/api/threads")) {
    return verb === "GET" ? AGENT_SCOPES.threadsRead : AGENT_SCOPES.threadsWrite;
  }
  if (path.startsWith("/api/runs")) {
    if (verb === "GET" || verb === "HEAD") return AGENT_SCOPES.runsRead;
    if (path.endsWith("/cancel")) return AGENT_SCOPES.runsCancel;
    return AGENT_SCOPES.runsExecute;
  }
  if (path.startsWith("/api/approvals")) {
    return verb === "GET" ? AGENT_SCOPES.approvalsRead : AGENT_SCOPES.approvalsResolve;
  }
  if (path.startsWith("/api/workspaces")) {
    return verb === "GET" || verb === "HEAD" ? AGENT_SCOPES.workspacesRead : AGENT_SCOPES.workspacesWrite;
  }
  if (path.startsWith("/api/memory") || path.startsWith("/api/long-term-memory")) {
    return AGENT_SCOPES.memoryManage;
  }
  if (isSettingsPath(path)) {
    return verb === "GET" || verb === "HEAD" ? AGENT_SCOPES.settingsRead : AGENT_SCOPES.settingsManage;
  }
  return verb === "GET" || verb === "HEAD" ? AGENT_SCOPES.appView : AGENT_SCOPES.settingsManage;
}

export function shouldEnablePlatformAuth(env: NodeJS.ProcessEnv = process.env): boolean {
  if (env.AITHRU_PLATFORM_AUTH_ENABLED === "true") return true;
  if (env.AITHRU_PLATFORM_AUTH_ENABLED === "false") return false;
  return Boolean(
    env.AITHRU_PLATFORM_URL &&
    env.AITHRU_APP_KEY &&
    env.AITHRU_CLIENT_SECRET &&
    env.AITHRU_PUBLIC_BASE_URL
  );
}

export function createAgentPlatform(): AithruPlatform {
  return createAithruPlatform({
    appName: "Aithru Agent",
    appDescription: "Aithru-native AI harness backend",
    platformAppLocation: process.env.AITHRU_PLATFORM_APP_LOCATION ?? "../aithru-platform-app.yml",
  });
}

export function registerPlatformAuth(app: FastifyInstance, aithru: AithruPlatform): void {
  app.addHook("preHandler", async (request, reply) => {
    const requiredScope = requiredScopeForRequest(request.method, request.url);
    if (!requiredScope) return;

    const token = bearerToken(request);
    if (!token) return authError(reply, 401, "AITHRU_AUTH_MISSING_TOKEN", "Missing Authorization header");

    let actor: CurrentActor;
    try {
      actor = currentActorFromClaims(await aithru.jwtVerifier.verify(token));
    } catch {
      return authError(reply, 401, "AITHRU_AUTH_INVALID_TOKEN", "Invalid token");
    }
    if (!scopeAllowed(actor, requiredScope)) {
      return authError(reply, 403, "AITHRU_AUTHZ_DENIED", `Missing required scope: ${requiredScope}`);
    }

    (request as RequestWithActor).aithruActor = actor;
  });
}

function pathname(url: string): string {
  try {
    return new URL(url, "http://aithru.local").pathname;
  } catch {
    return url.split("?")[0] || "/";
  }
}

function isSettingsPath(path: string): boolean {
  return [
    "/api/model-profiles",
    "/api/skills",
    "/api/skill-registry",
    "/api/subagents",
    "/api/external-tools",
  ].some((prefix) => path.startsWith(prefix));
}

function bearerToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  const value = Array.isArray(header) ? header[0] : header;
  const match = typeof value === "string" ? value.match(/^Bearer\s+(.+)$/i) : null;
  return match?.[1]?.trim() || null;
}

function authError(reply: FastifyReply, status: number, code: string, message: string) {
  reply.code(status);
  return {
    error: {
      code,
      message,
    },
  };
}

function scopeAllowed(actor: CurrentActor, requiredScope: string): boolean {
  return actor.scopes.includes("*") || actor.scopes.includes(requiredScope);
}

function currentActorFromClaims(claims: AithruTokenClaims): CurrentActor {
  const actorType = claims.actor_type === "service" ? "service" : claims.actor_type === "system" ? "system" : "user";
  const scopes = uniqueStrings([...claimToStrings(claims.scopes), ...claimToStrings(claims.scope)]);
  return {
    actorType,
    userId: actorType === "service" ? null : claims.sub ?? null,
    serviceId: claims.service_id ?? claims.client_id ?? null,
    orgId: claims.org_id ?? null,
    sessionId: claims.sid ?? claims.session_id ?? null,
    audience: Array.isArray(claims.aud) ? claims.aud[0] ?? null : claims.aud ?? null,
    scopes,
    roles: claims.roles ?? [],
    authzVersion: claims.authz_version ?? null,
    tokenType: claims.typ,
    delegation: claims.delegation ?? undefined,
    requestId: claims.jti ?? null,
    claims,
  };
}

function claimToStrings(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string" && item.length > 0);
  if (typeof value === "string") return value.split(" ").filter(Boolean);
  return [];
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values)];
}
