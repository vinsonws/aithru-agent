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
  AgentArtifact,
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
  listMessages(threadId: string): AgentMessage[];

  // Runs
  createRun(run: AgentRun): AgentRun;
  getRun(id: string): AgentRun | undefined;
  listRuns(filter?: { org_id?: string; thread_id?: string }): AgentRun[];
  updateRun(id: string, patch: Partial<AgentRun>): AgentRun;

  // Events
  appendEvent(runId: string, event: AgentStreamEvent): void;
  listEvents(runId: string): AgentStreamEvent[];

  // Workspace
  writeFile(
    workspaceId: string,
    path: string,
    content: string,
  ): WorkspaceFile;
  readFile(workspaceId: string, path: string): WorkspaceFile | undefined;
  listWorkspaceFiles(workspaceId: string): WorkspaceFile[];
  deleteFile(workspaceId: string, path: string): boolean;

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
  resolveApproval(
    id: string,
    status: "approved" | "denied",
  ): AgentApproval;

  // Artifacts
  createArtifact(artifact: AgentArtifact): AgentArtifact;
  getArtifact(id: string): AgentArtifact | undefined;
  listArtifacts(runId: string): AgentArtifact[];
  finalizeArtifact(id: string): AgentArtifact;

  // Claims
  acquireClaim(runId: string, workerId: string, leaseSeconds?: number): boolean;
  releaseClaim(runId: string, workerId: string): void;
  findStaleClaims(): AgentRun[];

  // Lifecycle
  close(): void;
}
