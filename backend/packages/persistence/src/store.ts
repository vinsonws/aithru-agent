import type {
  AgentThread,
  AgentMessage,
  AgentRun,
  AgentStreamEvent,
} from "@aithru-agent/contracts";
import { FileWorkspaceStore } from "./workspace-files.js";

export interface WorkspaceFile {
  workspace_id: string;
  org_id?: string | null;
  owner_user_id?: string | null;
  thread_id?: string | null;
  path: string;
  content: string;
  size: number;
  version: number;
  created_by_run_id?: string;
  last_modified_by_run_id?: string;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceBinding {
  workspace_id: string;
  org_id: string;
  owner_user_id?: string | null;
  thread_id?: string | null;
}

export interface WorkspaceAccessGuard {
  orgId?: string | null;
  actorUserId?: string | null;
}

export interface WorkspaceWriteOptions extends WorkspaceAccessGuard {
  runId?: string | null;
  ownerUserId?: string | null;
  threadId?: string | null;
}

export interface WorkspaceListFilter extends WorkspaceAccessGuard {
  runId?: string;
}

export interface AgentTodo {
  id: string;
  org_id?: string | null;
  actor_user_id?: string | null;
  thread_id?: string | null;
  run_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AgentApproval {
  id: string;
  org_id?: string | null;
  actor_user_id?: string | null;
  run_id: string;
  tool_call_id: string;
  tool_name: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
  resolved_at?: string;
}

export interface AgentDocument {
  kind: string;
  id: string;
  payload: unknown;
}

export interface DocumentWriteGuard {
  orgId?: string;
  ownerUserId?: string;
}

export interface AgentContextSummary {
  id: string;
  org_id: string;
  actor_user_id?: string | null;
  thread_id: string;
  run_id: string;
  summary: string;
  source_message_count: number;
  created_at: string;
}

function documentOrgId(payload: unknown): string | null {
  return payload && typeof payload === "object" && typeof (payload as any).org_id === "string"
    ? (payload as any).org_id
    : null;
}

function documentOwnerUserId(payload: unknown): string | null {
  return payload && typeof payload === "object" && typeof (payload as any).owner_user_id === "string"
    ? (payload as any).owner_user_id
    : null;
}

function documentMatchesGuard(payload: unknown, guard?: DocumentWriteGuard): boolean {
  if (!guard) return true;
  if (guard.orgId && documentOrgId(payload) !== guard.orgId) return false;
  if (guard.ownerUserId && documentOwnerUserId(payload) !== guard.ownerUserId) return false;
  return true;
}

export class InMemoryStore {
  private threads = new Map<string, AgentThread>();
  private messages = new Map<string, AgentMessage>();
  private runs = new Map<string, AgentRun>();
  private events = new Map<string, AgentStreamEvent[]>();
  private workspaceFiles = new FileWorkspaceStore();
  private todos = new Map<string, AgentTodo[]>();
  private approvals = new Map<string, AgentApproval[]>();
  private documents = new Map<string, Map<string, unknown>>();
  private secrets = new Map<string, Map<string, string>>();
  private settings = new Map<string, Map<string, string>>();
  private contextSummaries = new Map<string, AgentContextSummary[]>();

  // ── Threads ────────────────────────────────────────────────────────

  createThread(thread: AgentThread): AgentThread {
    this.threads.set(thread.id, thread);
    this.bindWorkspace(workspaceIdForThread(thread.id), {
      org_id: thread.org_id,
      owner_user_id: thread.owner_user_id,
      thread_id: thread.id,
    });
    return thread;
  }

  getThread(id: string): AgentThread | undefined {
    return this.threads.get(id);
  }

  listThreads(orgId?: string): AgentThread[] {
    let threads = [...this.threads.values()];
    if (orgId) threads = threads.filter((t) => t.org_id === orgId);
    return threads;
  }

  updateThread(id: string, patch: Partial<AgentThread>): AgentThread {
    const existing = this.threads.get(id);
    if (!existing) throw new Error(`Thread ${id} not found`);
    const updated = { ...existing, ...patch };
    this.threads.set(id, updated);
    return updated;
  }

  // ── Messages ──────────────────────────────────────────────────────

  createMessage(msg: AgentMessage): AgentMessage {
    const thread = this.getThread(msg.thread_id);
    const run = msg.run_id ? this.getRun(msg.run_id) : undefined;
    const stored = {
      ...msg,
      org_id: thread?.org_id ?? run?.org_id ?? msg.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? thread?.owner_user_id ?? msg.actor_user_id ?? null,
    };
    this.messages.set(msg.id, stored);
    return stored;
  }

  getMessage(id: string): AgentMessage | undefined {
    return this.messages.get(id);
  }

  listMessages(threadId: string, orgId?: string): AgentMessage[] {
    return [...this.messages.values()]
      .filter((m) => m.thread_id === threadId && (!orgId || m.org_id === orgId))
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );
  }

  // ── Runs ──────────────────────────────────────────────────────────

  createRun(run: AgentRun): AgentRun {
    this.runs.set(run.id, run);
    const thread = run.thread_id ? this.getThread(run.thread_id) : undefined;
    this.bindWorkspace(run.workspace_id, {
      org_id: run.org_id,
      owner_user_id: thread?.owner_user_id ?? run.actor_user_id,
      thread_id: run.thread_id,
    });
    return run;
  }

  getRun(id: string): AgentRun | undefined {
    return this.runs.get(id);
  }

  listRuns(
    filter?: { org_id?: string; thread_id?: string },
  ): AgentRun[] {
    let runs = [...this.runs.values()];
    if (filter?.org_id)
      runs = runs.filter((r) => r.org_id === filter.org_id);
    if (filter?.thread_id)
      runs = runs.filter((r) => r.thread_id === filter.thread_id);
    return runs;
  }

  updateRun(id: string, patch: Partial<AgentRun>): AgentRun {
    const existing = this.runs.get(id);
    if (!existing) throw new Error(`Run ${id} not found`);
    const updated = { ...existing, ...patch };
    this.runs.set(id, updated);
    return updated;
  }

  // ── Events ────────────────────────────────────────────────────────

  appendEvent(runId: string, event: AgentStreamEvent): void {
    const run = this.getRun(runId);
    const stored = {
      ...event,
      org_id: run?.org_id ?? event.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? event.actor_user_id ?? null,
    };
    const events = this.events.get(runId) || [];
    events.push(stored);
    this.events.set(runId, events);
  }

  nextEventSequence(runId: string): number {
    return (this.events.get(runId)?.length ?? 0) + 1;
  }

  listEvents(runId: string): AgentStreamEvent[] {
    return this.events.get(runId) || [];
  }

  // ── Workspace Files ────────────────────────────────────────────────

  writeFile(
    workspaceId: string,
    path: string,
    content: string,
    options?: WorkspaceWriteOptions,
  ): WorkspaceFile {
    return this.workspaceFiles.writeFile(workspaceId, path, content, options);
  }

  readFile(workspaceId: string, path: string, guard?: WorkspaceAccessGuard): WorkspaceFile | undefined {
    return this.workspaceFiles.readFile(workspaceId, path, guard);
  }

  listWorkspaceFiles(workspaceId: string, filter?: WorkspaceListFilter): WorkspaceFile[] {
    return this.workspaceFiles.listWorkspaceFiles(workspaceId, filter);
  }

  deleteFile(workspaceId: string, path: string, guard?: WorkspaceAccessGuard): boolean {
    return this.workspaceFiles.deleteFile(workspaceId, path, guard);
  }

  getWorkspaceRoot(workspaceId: string, guard?: WorkspaceAccessGuard): string {
    return this.workspaceFiles.getWorkspaceRoot(workspaceId, guard);
  }

  bindWorkspace(workspaceId: string, binding: Omit<WorkspaceBinding, "workspace_id">): WorkspaceBinding {
    return this.workspaceFiles.bindWorkspace(workspaceId, binding);
  }

  getWorkspaceBinding(workspaceId: string): WorkspaceBinding | undefined {
    return this.workspaceFiles.getWorkspaceBinding(workspaceId);
  }

  canAccessWorkspace(workspaceId: string, guard?: WorkspaceAccessGuard): boolean {
    return this.workspaceFiles.canAccessWorkspace(workspaceId, guard);
  }

  // ── Todos ─────────────────────────────────────────────────────────

  createTodo(todo: AgentTodo): AgentTodo {
    const run = this.getRun(todo.run_id);
    const threadId = todo.thread_id ?? run?.thread_id ?? null;
    const stored = {
      ...todo,
      org_id: run?.org_id ?? todo.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? todo.actor_user_id ?? null,
      thread_id: threadId,
    };
    const key = this.todoScopeKey(todo.run_id);
    const runTodos = this.todos.get(key) || [];
    runTodos.push(stored);
    this.todos.set(key, runTodos);
    return stored;
  }

  updateTodo(runId: string, todoId: string, patch: Partial<AgentTodo>): AgentTodo {
    const orgId = this.getRun(runId)?.org_id;
    const runTodos = this.todos.get(this.todoScopeKey(runId)) || [];
    const todo = runTodos.find((t) => t.id === todoId && (!orgId || t.org_id === orgId));
    if (!todo) throw new Error(`Todo ${todoId} not found`);
    Object.assign(todo, patch, { updated_at: new Date().toISOString().replace(/\.\d{3}/, "") });
    return todo;
  }

  listTodos(runId: string): AgentTodo[] {
    const orgId = this.getRun(runId)?.org_id;
    const todos = this.todos.get(this.todoScopeKey(runId)) || [];
    return orgId ? todos.filter((todo) => todo.org_id === orgId) : todos;
  }

  // ── Approvals ────────────────────────────────────────────────────

  createApproval(approval: AgentApproval): AgentApproval {
    const run = this.getRun(approval.run_id);
    const stored = {
      ...approval,
      org_id: run?.org_id ?? approval.org_id ?? null,
      actor_user_id: run?.actor_user_id ?? approval.actor_user_id ?? null,
    };
    const runApprovals = this.approvals.get(approval.run_id) || [];
    runApprovals.push(stored);
    this.approvals.set(approval.run_id, runApprovals);
    return stored;
  }

  getApproval(id: string): AgentApproval | undefined {
    for (const approvals of this.approvals.values()) {
      const found = approvals.find((a) => a.id === id);
      if (found) return found;
    }
    return undefined;
  }

  listApprovals(filter?: { run_id?: string; status?: string; org_id?: string }): AgentApproval[] {
    let approvals = [...this.approvals.values()].flat();
    const orgId = filter?.org_id ?? (filter?.run_id ? this.getRun(filter.run_id)?.org_id : undefined);
    if (orgId) approvals = approvals.filter((a) => a.org_id === orgId);
    if (filter?.run_id) approvals = approvals.filter((a) => a.run_id === filter.run_id);
    if (filter?.status) approvals = approvals.filter((a) => a.status === filter.status);
    return approvals;
  }

  resolveApproval(
    id: string,
    status: "approved" | "denied",
  ): AgentApproval {
    const approval = this.getApproval(id);
    if (!approval) throw new Error(`Approval ${id} not found`);
    approval.status = status;
    approval.resolved_at = new Date().toISOString().replace(/\.\d{3}/, "");
    return approval;
  }

  // ── Generic Documents ──────────────────────────────────────────────

  upsertDocument(kind: string, id: string, payload: unknown, guard?: DocumentWriteGuard): AgentDocument {
    const docs = this.documents.get(kind) ?? new Map<string, unknown>();
    const existing = docs.get(id);
    if (existing !== undefined && !documentMatchesGuard(existing, guard)) {
      throw new Error(`Document not found: ${kind}/${id}`);
    }
    if (!documentMatchesGuard(payload, guard)) throw new Error(`Document not found: ${kind}/${id}`);
    docs.set(id, payload);
    this.documents.set(kind, docs);
    return { kind, id, payload };
  }

  insertDocument(kind: string, id: string, payload: unknown, guard?: DocumentWriteGuard): AgentDocument {
    const existing = this.getDocument(kind, id);
    if (existing && !documentMatchesGuard(existing.payload, guard)) throw new Error(`Document not found: ${kind}/${id}`);
    if (existing) throw new Error(`Document already exists: ${kind}/${id}`);
    return this.upsertDocument(kind, id, payload, guard);
  }

  getDocument(kind: string, id: string): AgentDocument | undefined {
    const docs = this.documents.get(kind);
    if (!docs?.has(id)) return undefined;
    return { kind, id, payload: docs.get(id) };
  }

  listDocuments(kind: string, orgId: string): AgentDocument[] {
    return [...(this.documents.get(kind) ?? new Map<string, unknown>()).entries()]
      .filter(([, payload]) => documentOrgId(payload) === orgId)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([id, payload]) => ({ kind, id, payload }));
  }

  deleteDocument(kind: string, id: string, guard?: DocumentWriteGuard): number {
    const docs = this.documents.get(kind);
    const existing = docs?.get(id);
    if (existing === undefined || !documentMatchesGuard(existing, guard)) return 0;
    return docs!.delete(id) ? 1 : 0;
  }

  createContextSummary(summary: AgentContextSummary): AgentContextSummary {
    const run = this.getRun(summary.run_id);
    const stored = {
      ...summary,
      org_id: run?.org_id ?? summary.org_id,
      actor_user_id: run?.actor_user_id ?? summary.actor_user_id ?? null,
    };
    const summaries = this.contextSummaries.get(summary.thread_id) ?? [];
    summaries.push(stored);
    summaries.sort((a, b) => a.created_at.localeCompare(b.created_at));
    this.contextSummaries.set(summary.thread_id, summaries);
    return stored;
  }

  listContextSummaries(threadId: string, orgId?: string): AgentContextSummary[] {
    const summaries = this.contextSummaries.get(threadId) ?? [];
    return orgId ? summaries.filter((summary) => summary.org_id === orgId) : summaries;
  }

  getLatestContextSummary(threadId: string, orgId?: string): AgentContextSummary | undefined {
    return this.listContextSummaries(threadId, orgId).at(-1);
  }

  setSecret(orgId: string, secretRef: string, value: string): void {
    const scoped = this.secrets.get(orgId) ?? new Map<string, string>();
    scoped.set(secretRef, value);
    this.secrets.set(orgId, scoped);
  }

  getSecret(orgId: string, secretRef: string): string | undefined {
    return this.secrets.get(orgId)?.get(secretRef);
  }

  setSetting(orgId: string, key: string, value: string): void {
    const scoped = this.settings.get(orgId) ?? new Map<string, string>();
    scoped.set(key, value);
    this.settings.set(orgId, scoped);
  }

  getSetting(orgId: string, key: string): string | undefined {
    return this.settings.get(orgId)?.get(key);
  }

  // ── Claims ───────────────────────────────────────────────────────────

  acquireClaim(
    runId: string,
    workerId: string,
    leaseSeconds: number = 30,
  ): boolean {
    const existing = this.runs.get(runId);
    if (!existing) throw new Error(`Run ${runId} not found`);

    const now = new Date();
    const nowISO = now.toISOString().replace(/\.\d{3}/, "");

    // If there's an existing claim that hasn't expired and belongs to another worker, deny
    if (existing.claim) {
      const expiresAt = new Date(existing.claim.lease_expires_at);
      if (expiresAt > now && existing.claim.worker_id !== workerId) {
        return false;
      }
    }

    // Acquire or renew the claim
    const expiresAt = new Date(now.getTime() + leaseSeconds * 1000);
    const attempt = existing.claim ? existing.claim.attempt + 1 : 1;

    this.runs.set(runId, {
      ...existing,
      claim: {
        worker_id: workerId,
        claimed_at: nowISO,
        last_heartbeat_at: nowISO,
        lease_expires_at: expiresAt.toISOString().replace(/\.\d{3}/, ""),
        attempt,
      },
    });
    return true;
  }

  releaseClaim(runId: string, workerId: string): boolean {
    const existing = this.runs.get(runId);
    if (!existing) throw new Error(`Run ${runId} not found`);
    if (!existing.claim) return false;
    if (existing.claim.worker_id !== workerId) return false;

    const { claim: _removed, ...rest } = existing;
    this.runs.set(runId, rest);
    return true;
  }

  findStaleClaims(maxAgeMs?: number): AgentRun[] {
    const now = new Date();
    const ageThreshold = maxAgeMs ?? 60_000; // default 60s
    const cutoff = new Date(now.getTime() - ageThreshold);

    return [...this.runs.values()].filter((run) => {
      if (!run.claim) return false;
      // Claim is stale if lease_expires_at is in the past
      const expiresAt = new Date(run.claim.lease_expires_at);
      return expiresAt < now || expiresAt < cutoff;
    });
  }

  // ── Lifecycle ───────────────────────────────────────────────────────

  close(): void {
    this.workspaceFiles.close();
  }

  // ── Raw access for testing ────────────────────────────────────────

  _dump() {
    return {
      threads: [...this.threads.values()],
      messages: [...this.messages.values()],
      runs: [...this.runs.values()],
      events: Object.fromEntries(this.events),
      workspaceFiles: [],
      todos: Object.fromEntries(this.todos),
      approvals: Object.fromEntries(this.approvals),
      documents: Object.fromEntries(
        [...this.documents.entries()].map(([kind, docs]) => [kind, Object.fromEntries(docs)]),
      ),
      contextSummaries: Object.fromEntries(this.contextSummaries),
    };
  }

  private todoScopeKey(runId: string): string {
    return this.getRun(runId)?.thread_id ?? runId;
  }
}

function workspaceIdForThread(threadId: string): string {
  return `ws_thread_${threadId}`;
}
