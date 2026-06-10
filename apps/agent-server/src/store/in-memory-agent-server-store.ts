import type {
  ThreadId, OrgId, UserId, RunId, ApprovalId, MessageId,
  SkillId, WorkspaceId, ToolCallId,
} from "@aithru/agent-core";
import type {
  AgentServerStore,
  AgentThreadRecord,
  AgentMessageRecord,
  AgentRunRecord,
  AgentApprovalRecord,
  AgentServerApprovalStatus,
  AgentServerRunStatus,
  CreateThreadInput,
  AppendMessageInput,
  CreateRunInput,
  UpsertApprovalInput,
} from "./types.js";

let threadCounter = 0;
let messageCounter = 0;

function nextThreadId(): ThreadId {
  return `thread_${++threadCounter}` as ThreadId;
}

function nextMessageId(): MessageId {
  return `msg_${++messageCounter}` as MessageId;
}

export class InMemoryAgentServerStore implements AgentServerStore {
  private threads = new Map<ThreadId, AgentThreadRecord>();
  private messages = new Map<ThreadId, AgentMessageRecord[]>();
  private runs = new Map<RunId, AgentRunRecord>();
  private approvals = new Map<ApprovalId, AgentApprovalRecord>();

  // ── Threads ────────────────────────────────────────────────────────────────

  async createThread(input: CreateThreadInput): Promise<AgentThreadRecord> {
    const now = new Date().toISOString();
    const thread: AgentThreadRecord = {
      id: nextThreadId(),
      orgId: input.orgId,
      ownerUserId: input.ownerUserId,
      title: input.title ?? "Untitled thread",
      status: "active",
      createdAt: now,
      updatedAt: now,
    };
    this.threads.set(thread.id, thread);
    this.messages.set(thread.id, []);
    return thread;
  }

  async listThreads(): Promise<AgentThreadRecord[]> {
    return [...this.threads.values()];
  }

  async getThread(id: ThreadId): Promise<AgentThreadRecord | null> {
    return this.threads.get(id) ?? null;
  }

  // ── Messages ───────────────────────────────────────────────────────────────

  async appendMessage(input: AppendMessageInput): Promise<AgentMessageRecord> {
    const msg: AgentMessageRecord = {
      id: nextMessageId(),
      threadId: input.threadId,
      role: input.role,
      content: input.content,
      runId: input.runId,
      createdAt: new Date().toISOString(),
    };
    const list = this.messages.get(input.threadId) ?? [];
    list.push(msg);
    this.messages.set(input.threadId, list);
    return msg;
  }

  async listMessages(threadId: ThreadId): Promise<AgentMessageRecord[]> {
    return this.messages.get(threadId) ?? [];
  }

  // ── Runs ───────────────────────────────────────────────────────────────────

  async createRun(input: CreateRunInput): Promise<AgentRunRecord> {
    const now = new Date().toISOString();
    const run: AgentRunRecord = {
      id: `run_placeholder` as RunId, // overwritten by projectEvent
      orgId: input.orgId,
      actorUserId: input.actorUserId,
      goal: input.goal,
      threadId: input.threadId,
      skillId: input.skillId,
      workspaceId: input.workspaceId,
      status: "queued",
      createdAt: now,
      updatedAt: now,
    };
    return run;
  }

  async getRun(id: RunId): Promise<AgentRunRecord | null> {
    return this.runs.get(id) ?? null;
  }

  async listRuns(): Promise<AgentRunRecord[]> {
    return [...this.runs.values()];
  }

  async updateRun(id: RunId, patch: Partial<AgentRunRecord>): Promise<AgentRunRecord> {
    const existing = this.runs.get(id);
    if (!existing) {
      throw new Error(`Run not found: ${id}`);
    }
    const updated: AgentRunRecord = {
      ...existing,
      ...patch,
      id: existing.id,
      updatedAt: new Date().toISOString(),
    };
    this.runs.set(id, updated);
    return updated;
  }

  setRun(record: AgentRunRecord): void {
    this.runs.set(record.id, record);
  }

  // ── Approvals ──────────────────────────────────────────────────────────────

  async upsertApproval(input: UpsertApprovalInput): Promise<AgentApprovalRecord> {
    const now = new Date().toISOString();
    const existing = this.approvals.get(input.id);
    const record: AgentApprovalRecord = {
      id: input.id,
      runId: input.runId,
      threadId: input.threadId,
      toolCallId: input.toolCallId,
      toolName: input.toolName,
      status: input.status,
      reason: input.reason,
      createdAt: existing?.createdAt ?? now,
      payload: input.payload,
    };
    this.approvals.set(input.id, record);
    return record;
  }

  async getApproval(id: ApprovalId): Promise<AgentApprovalRecord | null> {
    return this.approvals.get(id) ?? null;
  }

  async listApprovals(filter?: { status?: AgentServerApprovalStatus; runId?: RunId }): Promise<AgentApprovalRecord[]> {
    let result = [...this.approvals.values()];
    if (filter?.status) {
      result = result.filter((a) => a.status === filter.status);
    }
    if (filter?.runId) {
      result = result.filter((a) => a.runId === filter.runId);
    }
    return result;
  }

  async resolveApproval(id: ApprovalId, decision: "approved" | "rejected", comment?: string): Promise<AgentApprovalRecord> {
    const existing = this.approvals.get(id);
    if (!existing) {
      throw new Error(`Approval not found: ${id}`);
    }
    const now = new Date().toISOString();
    const record: AgentApprovalRecord = {
      ...existing,
      status: decision === "approved" ? "approved" : "rejected",
      decision,
      comment,
      resolvedAt: now,
    };
    this.approvals.set(id, record);
    return record;
  }
}
