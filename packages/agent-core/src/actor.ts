import type { OrgId, UserId } from "./ids.js";

export type AgentActorType = "user" | "service" | "delegated" | "system";

export type AgentActorContext = {
  actorType: AgentActorType;
  userId?: UserId;
  serviceId?: string;
  orgId: OrgId;
  scopes: string[];
  authzVersion?: number;
  delegation?: unknown;
};
