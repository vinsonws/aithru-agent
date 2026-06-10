import type { ThreadId, OrgId, UserId, WorkspaceId, SkillId } from "./ids.js";

export type AgentThreadStatus = "active" | "archived";

export type AgentThread = {
  id: ThreadId;
  orgId: OrgId;
  ownerUserId: UserId;
  title: string;
  status: AgentThreadStatus;
  workspaceId: WorkspaceId;
  defaultSkillId?: SkillId;
  createdAt: string;
  updatedAt: string;
};
