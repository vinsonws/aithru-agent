import type { AithruPlatform } from "@aithru/subsystem-sdk-node";
import type { AgentHttpContext, AgentHttpActor } from "../server/context.js";

/**
 * Create a platform-mode AgentHttpContext from the SDK's CurrentActor.
 *
 * Actor identity comes from the verified JWT — request body is never trusted.
 */
export function createPlatformAgentHttpContext(
  aithru: AithruPlatform,
): AgentHttpContext {
  const actor = aithru.auth().currentActor();

  const agentActor: AgentHttpActor | undefined = actor
    ? {
        actorType: actor.actorType as AgentHttpActor["actorType"],
        userId: actor.userId ?? undefined,
        serviceId: actor.serviceId ?? undefined,
        orgId: actor.orgId ?? undefined,
        scopes: actor.scopes ?? [],
        roles: actor.roles ?? [],
        audience: actor.audience ?? undefined,
        tokenType: actor.tokenType,
        authzVersion: actor.authzVersion ?? undefined,
      }
    : undefined;

  return {
    mode: "platform",
    actor: agentActor,
    apiBasePath: "/api/agent",

    requireScope(scope: string): void {
      aithru.authz().requireScope(scope);
    },

    async auditSuccess(
      action: string,
      input?: {
        targetType?: string;
        targetId?: string;
        metadata?: Record<string, unknown>;
      },
    ): Promise<void> {
      const builder = aithru.audit().success(action);
      if (input?.targetType && input?.targetId) {
        builder.target(input.targetType, input.targetId);
      }
      for (const [k, v] of Object.entries(input?.metadata ?? {})) {
        builder.metadata(k, v);
      }
      await builder.send();
    },

    async auditFailure(
      action: string,
      input?: {
        targetType?: string;
        targetId?: string;
        error?: unknown;
        metadata?: Record<string, unknown>;
      },
    ): Promise<void> {
      const builder = aithru.audit().failure(action);
      if (input?.targetType && input?.targetId) {
        builder.target(input.targetType, input.targetId);
      }
      for (const [k, v] of Object.entries(input?.metadata ?? {})) {
        builder.metadata(k, v);
      }
      if (input?.error) {
        const errMsg =
          input.error instanceof Error
            ? input.error.message
            : String(input.error);
        builder.metadata("error", errMsg);
      }
      await builder.send();
    },

    async registerResource(resource: {
      orgId: string;
      resourceType: string;
      resourceId: string;
      displayName: string;
      ownerUserId?: string;
      metadata?: Record<string, unknown>;
    }): Promise<void> {
      await aithru.registry().registerResource(resource);
    },
  };
}
