import type {
  ThreadId, OrgId, UserId, RunId, ApprovalId, MessageId,
  SkillId, WorkspaceId, ToolCallId,
} from "@aithru/agent-core";

// ── Server-level types (projection from AgentStreamEvent) ──────────────────

export type AgentServerRunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentServerApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired";

export type AgentThreadRecord = {
  id: ThreadId;
  orgId: OrgId;
  ownerUserId: UserId;
  title: string;
  status: "active" | "archived";
  createdAt: string;
  updatedAt: string;
};

export type AgentMessageRecord = {
  id: MessageId;
  threadId: ThreadId;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  runId?: RunId;
  createdAt: string;
};

export type AgentRunRecord = {
  id: RunId;
  orgId: OrgId;
  actorUserId: UserId;
  threadId?: ThreadId;
  skillId?: SkillId;
  workspaceId?: WorkspaceId;
  goal: string;
  status: AgentServerRunStatus;
  currentApprovalId?: ApprovalId;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
  updatedAt: string;
  error?: unknown;
};

export type AgentApprovalRecord = {
  id: ApprovalId;
  runId: RunId;
  threadId?: ThreadId;
  toolCallId?: ToolCallId;
  toolName?: string;
  status: AgentServerApprovalStatus;
  reason?: string;
  decision?: "approved" | "rejected";
  comment?: string;
  createdAt: string;
  resolvedAt?: string;
  payload?: unknown;
};

// ── Input types ────────────────────────────────────────────────────────────

export type CreateThreadInput = {
  orgId: OrgId;
  ownerUserId: UserId;
  title?: string;
};

export type AppendMessageInput = {
  threadId: ThreadId;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  runId?: RunId;
};

export type CreateRunInput = {
  orgId: OrgId;
  actorUserId: UserId;
  goal: string;
  threadId?: ThreadId;
  skillId?: SkillId;
  workspaceId?: WorkspaceId;
};

export type UpsertApprovalInput = {
  id: ApprovalId;
  runId: RunId;
  threadId?: ThreadId;
  toolCallId?: ToolCallId;
  toolName?: string;
  status: AgentServerApprovalStatus;
  reason?: string;
  payload?: unknown;
};

// ── Store interface ────────────────────────────────────────────────────────

export interface AgentServerStore {
  // Threads
  createThread(input: CreateThreadInput): Promise<AgentThreadRecord>;
  listThreads(): Promise<AgentThreadRecord[]>;
  getThread(id: ThreadId): Promise<AgentThreadRecord | null>;

  // Messages
  appendMessage(input: AppendMessageInput): Promise<AgentMessageRecord>;
  listMessages(threadId: ThreadId): Promise<AgentMessageRecord[]>;

  // Runs
  createRun(input: CreateRunInput): Promise<AgentRunRecord>;
  getRun(id: RunId): Promise<AgentRunRecord | null>;
  listRuns(): Promise<AgentRunRecord[]>;
  updateRun(id: RunId, patch: Partial<AgentRunRecord>): Promise<AgentRunRecord>;
  /** Directly insert/replace a run record (used by event projection for run.created). */
  setRun(record: AgentRunRecord): void;

  // Approvals
  upsertApproval(input: UpsertApprovalInput): Promise<AgentApprovalRecord>;
  getApproval(id: ApprovalId): Promise<AgentApprovalRecord | null>;
  listApprovals(filter?: { status?: AgentServerApprovalStatus; runId?: RunId }): Promise<AgentApprovalRecord[]>;
  resolveApproval(id: ApprovalId, decision: "approved" | "rejected", comment?: string): Promise<AgentApprovalRecord>;
}
