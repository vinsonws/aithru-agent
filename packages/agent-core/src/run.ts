import type { RunId, ThreadId, SkillId, OrgId, UserId, WorkspaceId } from "./ids.js";

export type AgentRunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentRunSource =
  | "chat"
  | "skill"
  | "api"
  | "workbench_node"
  | "delegated_task";

export type AgentRun = {
  id: RunId;
  orgId: OrgId;
  actorUserId: UserId;
  source: AgentRunSource;
  threadId?: ThreadId;
  skillId?: SkillId;
  workspaceId: WorkspaceId;
  goal: string;
  status: AgentRunStatus;
  startedAt: string;
  completedAt?: string;
};
