import type { ThreadId, MessageId, OrgId, UserId } from "@aithru/agent-core";

export function defaultOrgId(): OrgId {
  return "org_1" as OrgId;
}

export function defaultUserId(): UserId {
  return "user_1" as UserId;
}
