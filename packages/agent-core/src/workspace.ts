import type { WorkspaceId, OrgId, ThreadId, RunId } from "./ids.js";

export type AgentWorkspaceStorageBackend =
  | "memory"
  | "local"
  | "server"
  | "object_storage"
  | "sandbox";

export type AgentWorkspace = {
  id: WorkspaceId;
  orgId: OrgId;
  threadId?: ThreadId;
  runId?: RunId;
  storageBackend: AgentWorkspaceStorageBackend;
  rootPath?: string;
  retentionPolicyId?: string;
  createdAt: string;
};

export type AgentWorkspaceFile = {
  workspaceId: WorkspaceId;
  path: string;
  size: number;
  mediaType?: string;
  createdAt: string;
  updatedAt: string;
};
