export type AgentHttpMode = "standalone" | "platform";

export type AgentHttpActor = {
  actorType: "user" | "service" | "system" | "delegated";
  userId?: string;
  serviceId?: string;
  orgId?: string;
  scopes: string[];
  roles?: string[];
  audience?: string;
  tokenType?: string;
  authzVersion?: number;
};

export type AgentHttpContext = {
  mode: AgentHttpMode;
  actor?: AgentHttpActor;
  apiBasePath?: string;

  requireScope(scope: string): void | Promise<void>;

  auditSuccess?(
    action: string,
    input?: {
      targetType?: string;
      targetId?: string;
      metadata?: Record<string, unknown>;
    },
  ): Promise<void>;

  auditFailure?(
    action: string,
    input?: {
      targetType?: string;
      targetId?: string;
      error?: unknown;
      metadata?: Record<string, unknown>;
    },
  ): Promise<void>;

  registerResource?(input: {
    orgId: string;
    resourceType: string;
    resourceId: string;
    displayName: string;
    ownerUserId?: string;
    metadata?: Record<string, unknown>;
  }): Promise<void>;
};

export function createStandaloneContext(): AgentHttpContext {
  return {
    mode: "standalone",
    actor: undefined,
    requireScope(_scope: string): void {
      // no-op in standalone mode
    },
    auditSuccess: undefined,
    auditFailure: undefined,
    registerResource: undefined,
  };
}
