/**
 * Minimal type declarations for @aithru/subsystem-sdk-node.
 *
 * These are stub types used at compile time only. The actual SDK must be
 * installed (via npm link or Nexus) for platform subsystem mode to run.
 *
 * See README.md for setup instructions.
 */

declare module "@aithru/subsystem-sdk-node" {
  export interface CurrentActor {
    actorType: "user" | "service" | "system";
    userId?: string | null;
    serviceId?: string | null;
    orgId?: string | null;
    sessionId?: string | null;
    audience?: string | null;
    scopes: string[];
    roles: string[];
    authzVersion?: number | null;
    tokenType: string;
    delegation?: unknown;
    requestId?: string | null;
    claims: Record<string, unknown>;
  }

  export interface AithruPlatformConfig {
    baseUrl: string;
    issuer: string;
    appKey: string;
    serviceName: string;
    serviceVersion?: string;
    clientId: string;
    clientSecret: string;
    audience?: string;
    manifestLocation?: string;
    registrationEnabled?: boolean;
    failOnRegistrationError?: boolean;
    jwksCacheTtlMs?: number;
    allowedClockSkewMs?: number;
    authzCacheEnabled?: boolean;
    authzCacheTtlMs?: number;
    authzFailClosed?: boolean;
    auditEnabled?: boolean;
    auditBestEffort?: boolean;
    lifecycleEnabled?: boolean;
    heartbeatEnabled?: boolean;
    heartbeatIntervalMs?: number;
    instanceId?: string;
    publicBaseUrl?: string;
    internalBaseUrl?: string;
    healthUrl?: string;
  }

  export interface AithruAuth {
    currentActor(): CurrentActor;
    currentActorOrNull(): CurrentActor | null;
    currentBearerToken(): string;
  }

  export interface AithruPermissionChecker {
    requireScope(permission: string): void;
    requireResourcePermission(action: string, resourceType: string, resourceId: string): Promise<void>;
    check(action: string, resourceType?: string, resourceId?: string): Promise<boolean>;
  }

  export interface AithruRegistry {
    registerManifest(location?: string): Promise<void>;
  }

  export interface AithruAudit {
    success(action: string): AithruAudit;
    failure(action: string): AithruAudit;
    target(resourceType: string, resourceId: string): AithruAudit;
    metadata(key: string, value: unknown): AithruAudit;
    send(): Promise<void>;
  }

  export interface AithruServiceClient {
    targetApp(appKey: string): unknown;
  }

  export interface AithruDelegationClient {}

  export class AithruPlatform {
    readonly config: AithruPlatformConfig;
    auth(): AithruAuth;
    authz(): AithruPermissionChecker;
    registry(): AithruRegistry;
    client(): AithruServiceClient;
    delegation(): AithruDelegationClient;
    audit(): AithruAudit;
    start(): Promise<void>;
    stop(): Promise<void>;
  }

  export function createAithruPlatform(configOverrides?: Partial<AithruPlatformConfig>): AithruPlatform;
}

declare module "@aithru/subsystem-sdk-node/express" {
  import type { RequestHandler } from "express";

  interface AithruJwtVerifierStub {
    verify(token: string): Promise<Record<string, unknown>>;
  }

  export function aithruExpressMiddleware(
    input: AithruPlatform | AithruJwtVerifierStub,
  ): RequestHandler;
}
