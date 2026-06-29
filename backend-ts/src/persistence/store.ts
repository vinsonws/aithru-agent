import type {
  AgentThread,
  AgentMessage,
  AgentRun,
  AgentStreamEvent,
} from "../contracts/types.js";

export interface WorkspaceFile {
  workspace_id: string;
  path: string;
  content: string;
  size: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface AgentTodo {
  id: string;
  run_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AgentApproval {
  id: string;
  run_id: string;
  tool_call_id: string;
  tool_name: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
  resolved_at?: string;
}

export class InMemoryStore {
  private threads = new Map<string, AgentThread>();
  private messages = new Map<string, AgentMessage>();
  private runs = new Map<string, AgentRun>();
  private events = new Map<string, AgentStreamEvent[]>();
  private workspaceFiles = new Map<string, WorkspaceFile[]>();
  private todos = new Map<string, AgentTodo[]>();
  private approvals = new Map<string, AgentApproval[]>();

  // ── Threads ────────────────────────────────────────────────────────

  createThread(thread: AgentThread): AgentThread {
    this.threads.set(thread.id, thread);
    return thread;
  }

  getThread(id: string): AgentThread | undefined {
    return this.threads.get(id);
  }

  listThreads(orgId: string): AgentThread[] {
    return [...this.threads.values()].filter((t) => t.org_id === orgId);
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
    this.messages.set(msg.id, msg);
    return msg;
  }

  getMessage(id: string): AgentMessage | undefined {
    return this.messages.get(id);
  }

  listMessages(threadId: string): AgentMessage[] {
    return [...this.messages.values()]
      .filter((m) => m.thread_id === threadId)
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );
  }

  // ── Runs ──────────────────────────────────────────────────────────

  createRun(run: AgentRun): AgentRun {
    this.runs.set(run.id, run);
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
    const events = this.events.get(runId) || [];
    events.push(event);
    this.events.set(runId, events);
  }

  listEvents(runId: string): AgentStreamEvent[] {
    return this.events.get(runId) || [];
  }

  // ── Workspace Files ────────────────────────────────────────────────

  writeFile(
    workspaceId: string,
    path: string,
    content: string,
  ): WorkspaceFile {
    const files = this.workspaceFiles.get(workspaceId) || [];
    const existing = files.find((f) => f.path === path);
    const now = new Date().toISOString().replace(/\.\d{3}/, "");
    if (existing) {
      existing.content = content;
      existing.size = Buffer.byteLength(content, "utf8");
      existing.version += 1;
      existing.updated_at = now;
      return existing;
    }
    const file: WorkspaceFile = {
      workspace_id: workspaceId,
      path,
      content,
      size: Buffer.byteLength(content, "utf8"),
      version: 1,
      created_at: now,
      updated_at: now,
    };
    files.push(file);
    this.workspaceFiles.set(workspaceId, files);
    return file;
  }

  readFile(workspaceId: string, path: string): WorkspaceFile | undefined {
    const files = this.workspaceFiles.get(workspaceId) || [];
    return files.find((f) => f.path === path);
  }

  listWorkspaceFiles(workspaceId: string): WorkspaceFile[] {
    return this.workspaceFiles.get(workspaceId) || [];
  }

  deleteFile(workspaceId: string, path: string): boolean {
    const files = this.workspaceFiles.get(workspaceId) || [];
    const idx = files.findIndex((f) => f.path === path);
    if (idx === -1) return false;
    files.splice(idx, 1);
    this.workspaceFiles.set(workspaceId, files);
    return true;
  }

  // ── Todos ─────────────────────────────────────────────────────────

  createTodo(todo: AgentTodo): AgentTodo {
    const runTodos = this.todos.get(todo.run_id) || [];
    runTodos.push(todo);
    this.todos.set(todo.run_id, runTodos);
    return todo;
  }

  updateTodo(runId: string, todoId: string, patch: Partial<AgentTodo>): AgentTodo {
    const runTodos = this.todos.get(runId) || [];
    const todo = runTodos.find((t) => t.id === todoId);
    if (!todo) throw new Error(`Todo ${todoId} not found`);
    Object.assign(todo, patch, { updated_at: new Date().toISOString().replace(/\.\d{3}/, "") });
    return todo;
  }

  listTodos(runId: string): AgentTodo[] {
    return this.todos.get(runId) || [];
  }

  // ── Approvals ────────────────────────────────────────────────────

  createApproval(approval: AgentApproval): AgentApproval {
    const runApprovals = this.approvals.get(approval.run_id) || [];
    runApprovals.push(approval);
    this.approvals.set(approval.run_id, runApprovals);
    return approval;
  }

  getApproval(id: string): AgentApproval | undefined {
    for (const approvals of this.approvals.values()) {
      const found = approvals.find((a) => a.id === id);
      if (found) return found;
    }
    return undefined;
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

  // ── Raw access for testing ────────────────────────────────────────

  _dump() {
    return {
      threads: [...this.threads.values()],
      messages: [...this.messages.values()],
      runs: [...this.runs.values()],
      events: Object.fromEntries(this.events),
      workspaceFiles: Object.fromEntries(this.workspaceFiles),
      todos: Object.fromEntries(this.todos),
      approvals: Object.fromEntries(this.approvals),
    };
  }
}
