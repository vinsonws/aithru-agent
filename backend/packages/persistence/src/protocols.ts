import type {
  AgentThread,
  AgentMessage,
  AgentRun,
  AgentStreamEvent,
} from "@aithru-agent/contracts";
import type {
  WorkspaceFile,
  AgentTodo,
  AgentApproval,
  AgentDocument,
  AgentContextSummary,
} from "./store.js";

export interface AgentStore {
  // Threads
  createThread(thread: AgentThread): AgentThread;
  getThread(id: string): AgentThread | undefined;
  listThreads(orgId?: string): AgentThread[];
  updateThread(id: string, patch: Partial<AgentThread>): AgentThread;

  // Messages
  createMessage(msg: AgentMessage): AgentMessage;
  getMessage(id: string): AgentMessage | undefined;
  listMessages(threadId: string, orgId?: string): AgentMessage[];

  // Runs
  createRun(run: AgentRun): AgentRun;
  getRun(id: string): AgentRun | undefined;
  listRuns(filter?: { org_id?: string; thread_id?: string }): AgentRun[];
  updateRun(id: string, patch: Partial<AgentRun>): AgentRun;

  // Events
  appendEvent(runId: string, event: AgentStreamEvent): void;
  nextEventSequence(runId: string): number;
  listEvents(runId: string): AgentStreamEvent[];

  // Workspace
  writeFile(
    workspaceId: string,
    path: string,
    content: string,
    options?: { runId?: string | null },
  ): WorkspaceFile;
  readFile(workspaceId: string, path: string): WorkspaceFile | undefined;
  listWorkspaceFiles(workspaceId: string, filter?: { runId?: string }): WorkspaceFile[];
  deleteFile(workspaceId: string, path: string): boolean;
  getWorkspaceRoot(workspaceId: string): string;

  // Todos
  createTodo(todo: AgentTodo): AgentTodo;
  updateTodo(
    runId: string,
    todoId: string,
    patch: Partial<AgentTodo>,
  ): AgentTodo;
  listTodos(runId: string): AgentTodo[];

  // Approvals
  createApproval(approval: AgentApproval): AgentApproval;
  getApproval(id: string): AgentApproval | undefined;
  listApprovals(filter?: { run_id?: string; status?: string; org_id?: string }): AgentApproval[];
  resolveApproval(
    id: string,
    status: "approved" | "denied",
  ): AgentApproval;

  // Generic documents
  upsertDocument(kind: string, id: string, payload: unknown): AgentDocument;
  insertDocument(kind: string, id: string, payload: unknown): AgentDocument;
  getDocument(kind: string, id: string): AgentDocument | undefined;
  listDocuments(kind: string, orgId: string): AgentDocument[];
  deleteDocument(kind: string, id: string): number;

  // Context summaries
  createContextSummary(summary: AgentContextSummary): AgentContextSummary;
  listContextSummaries(threadId: string, orgId?: string): AgentContextSummary[];
  getLatestContextSummary(threadId: string, orgId?: string): AgentContextSummary | undefined;

  // Secrets
  setSecret(orgId: string, secretRef: string, value: string): void;
  getSecret(orgId: string, secretRef: string): string | undefined;

  // Settings
  setSetting(orgId: string, key: string, value: string): void;
  getSetting(orgId: string, key: string): string | undefined;

  // Claims
  acquireClaim(runId: string, workerId: string, leaseSeconds?: number): boolean;
  releaseClaim(runId: string, workerId: string): void;
  findStaleClaims(): AgentRun[];

  // Lifecycle
  close(): void;
}
