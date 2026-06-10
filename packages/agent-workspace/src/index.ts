import type {
  AgentWorkspace,
  AgentWorkspaceFile,
  WorkspaceId,
  OrgId,
  ThreadId,
  RunId,
} from "@aithru/agent-core";
import { AgentError } from "@aithru/agent-core";

// ── Input types ─────────────────────────────────────────────────────────────

export type CreateWorkspaceInput = {
  orgId: OrgId;
  threadId?: ThreadId;
  runId?: RunId;
};

export type WorkspaceFileContent = {
  content: string | Uint8Array;
  mediaType?: string;
};

export type WriteWorkspaceFileInput = {
  workspaceId: WorkspaceId;
  path: string;
  content: string | Uint8Array;
  mediaType?: string;
};

// ── Provider interface ──────────────────────────────────────────────────────

export interface AgentWorkspaceProvider {
  createWorkspace(input: CreateWorkspaceInput): Promise<AgentWorkspace>;

  listFiles(workspaceId: string, path?: string): Promise<AgentWorkspaceFile[]>;

  readFile(workspaceId: string, path: string): Promise<WorkspaceFileContent>;

  writeFile(input: WriteWorkspaceFileInput): Promise<AgentWorkspaceFile>;

  deleteFile(workspaceId: string, path: string): Promise<void>;

  createSnapshot?(workspaceId: string): Promise<unknown>;
}

// ── Path utilities ──────────────────────────────────────────────────────────

/**
 * Normalize a path: resolve ".." components and reject traversal beyond root.
 */
export function normalizePath(raw: string): string {
  // Replace backslashes, collapse repeated slashes
  const normalized = raw.replace(/\\/g, "/").replace(/\/+/g, "/");

  const parts = normalized.split("/").filter(Boolean);
  const result: string[] = [];

  for (const part of parts) {
    if (part === ".") continue;
    if (part === "..") {
      if (result.length === 0) {
        throw new AgentError("PATH_TRAVERSAL_DENIED", `Path traverses above root: ${raw}`);
      }
      result.pop();
    } else {
      result.push(part);
    }
  }

  return "/" + result.join("/");
}

/**
 * Validate a user-supplied path, then prefix it with the workspace id.
 * The user path is normalized first so that `..` components can't escape
 * the workspace's key prefix.
 */
export function workspaceKey(workspaceId: string, userPath: string): string {
  const safe = normalizePath(userPath);
  return `/${workspaceId}${safe}`;
}

// ── In-memory provider ──────────────────────────────────────────────────────

type FileRecord = {
  content: string | Uint8Array;
  mediaType?: string;
  createdAt: string;
  updatedAt: string;
};

let workspaceCounter = 0;

export class InMemoryWorkspaceProvider implements AgentWorkspaceProvider {
  private workspaces = new Map<WorkspaceId, AgentWorkspace>();
  private files = new Map<string, FileRecord>();

  async createWorkspace(input: CreateWorkspaceInput): Promise<AgentWorkspace> {
    workspaceCounter++;
    const id = `ws_${workspaceCounter}` as WorkspaceId;
    const now = new Date().toISOString();

    const ws: AgentWorkspace = {
      id,
      orgId: input.orgId,
      threadId: input.threadId,
      runId: input.runId,
      storageBackend: "memory",
      createdAt: now,
    };

    this.workspaces.set(id, ws);
    return ws;
  }

  async listFiles(workspaceId: string, path?: string): Promise<AgentWorkspaceFile[]> {
    // Build the key prefix from both workspace id and the optional sub-path.
    // Stored keys are /${workspaceId}/..., so scoping to workspaceId is required.
    const prefix = path
      ? workspaceKey(workspaceId, path)
      : `/${workspaceId}`;
    const result: AgentWorkspaceFile[] = [];

    for (const [key, record] of this.files) {
      if (key !== prefix && !key.startsWith(`${prefix}/`)) continue;
      const filePath = key.slice(prefix.length) || "/";
      result.push({
        workspaceId: workspaceId as WorkspaceId,
        path: filePath,
        size: typeof record.content === "string" ? new TextEncoder().encode(record.content).length : record.content.length,
        mediaType: record.mediaType,
        createdAt: record.createdAt,
        updatedAt: record.updatedAt,
      });
    }

    return result;
  }

  async readFile(workspaceId: string, path: string): Promise<WorkspaceFileContent> {
    const key = workspaceKey(workspaceId, path);
    const record = this.files.get(key);
    if (!record) {
      throw new AgentError("NOT_FOUND", `File not found: ${path}`);
    }
    return { content: record.content, mediaType: record.mediaType };
  }

  async writeFile(input: WriteWorkspaceFileInput): Promise<AgentWorkspaceFile> {
    const normalizedPath = normalizePath(input.path);
    const key = workspaceKey(input.workspaceId, normalizedPath);
    const now = new Date().toISOString();
    const existing = this.files.get(key);

    const record: FileRecord = {
      content: input.content,
      mediaType: input.mediaType,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    };

    this.files.set(key, record);

    return {
      workspaceId: input.workspaceId,
      path: normalizedPath,
      size: typeof input.content === "string" ? new TextEncoder().encode(input.content).length : input.content.length,
      mediaType: input.mediaType,
      createdAt: record.createdAt,
      updatedAt: now,
    };
  }

  async deleteFile(workspaceId: string, path: string): Promise<void> {
    const key = workspaceKey(workspaceId, path);
    if (!this.files.has(key)) {
      throw new AgentError("NOT_FOUND", `File not found: ${path}`);
    }
    this.files.delete(key);
  }
}
