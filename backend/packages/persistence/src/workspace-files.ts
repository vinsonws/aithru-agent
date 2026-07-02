import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { tmpdir } from "node:os";
import type {
  WorkspaceAccessGuard,
  WorkspaceBinding,
  WorkspaceFile,
  WorkspaceListFilter,
  WorkspaceWriteOptions,
} from "./store.js";

interface FileMeta {
  created_at: string;
  version: number;
  created_by_run_id?: string;
  last_modified_by_run_id?: string;
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}/, "");
}

function workspaceDirName(workspaceId: string): string {
  return encodeURIComponent(workspaceId);
}

function normalizeWorkspacePath(path: string): { path: string; relativePath: string } {
  const parts = String(path).split(/[\\/]+/).filter(Boolean);
  if (parts.length === 0 || parts.includes("..")) {
    throw new Error(`Invalid workspace path: ${path}`);
  }
  const relativePath = parts.join("/");
  return { path: `/${relativePath}`, relativePath };
}

export class FileWorkspaceStore {
  private root = mkdtempSync(join(tmpdir(), "aithru-workspaces-"));
  private meta = new Map<string, FileMeta>();
  private workspaceMeta = new Map<string, WorkspaceBinding>();

  bindWorkspace(workspaceId: string, binding: Omit<WorkspaceBinding, "workspace_id">): WorkspaceBinding {
    const existing = this.workspaceMeta.get(workspaceId);
    if (existing && existing.org_id !== binding.org_id) {
      throw new Error(`Workspace ${workspaceId} already belongs to org ${existing.org_id}`);
    }
    const merged: WorkspaceBinding = {
      workspace_id: workspaceId,
      org_id: existing?.org_id ?? binding.org_id,
      owner_user_id: existing?.owner_user_id ?? binding.owner_user_id ?? null,
      thread_id: existing?.thread_id ?? binding.thread_id ?? null,
    };
    this.workspaceMeta.set(workspaceId, merged);
    return merged;
  }

  getWorkspaceBinding(workspaceId: string): WorkspaceBinding | undefined {
    return this.workspaceMeta.get(workspaceId);
  }

  canAccessWorkspace(workspaceId: string, guard: WorkspaceAccessGuard = {}): boolean {
    if (!guard.orgId) return true;
    const binding = this.workspaceMeta.get(workspaceId);
    if (!binding) return false;
    if (binding.org_id !== guard.orgId) return false;
    if (guard.actorUserId && binding.owner_user_id && binding.owner_user_id !== guard.actorUserId) return false;
    return true;
  }

  writeFile(
    workspaceId: string,
    path: string,
    content: string,
    options: WorkspaceWriteOptions = {},
  ): WorkspaceFile {
    if (options.orgId) {
      this.bindWorkspace(workspaceId, {
        org_id: options.orgId,
        owner_user_id: options.ownerUserId ?? options.actorUserId ?? null,
        thread_id: options.threadId ?? null,
      });
    }
    this.assertWorkspaceAccess(workspaceId, {
      orgId: options.orgId,
      actorUserId: options.actorUserId ?? options.ownerUserId,
    });
    const target = this.resolvePath(workspaceId, path);
    const existing = this.readFile(workspaceId, target.path);
    mkdirSync(dirname(target.fullPath), { recursive: true });
    writeFileSync(target.fullPath, content, "utf8");
    const timestamp = nowIso();
    const key = this.metaKey(workspaceId, target.path);
    this.meta.set(key, {
      created_at: existing?.created_at ?? timestamp,
      version: (existing?.version ?? 0) + 1,
      created_by_run_id: existing?.created_by_run_id ?? options.runId ?? undefined,
      last_modified_by_run_id: options.runId ?? existing?.last_modified_by_run_id,
    });
    return this.readFile(workspaceId, target.path)!;
  }

  readFile(workspaceId: string, path: string, guard: WorkspaceAccessGuard = {}): WorkspaceFile | undefined {
    if (!this.canAccessWorkspace(workspaceId, guard)) return undefined;
    const target = this.resolvePath(workspaceId, path);
    if (!existsSync(target.fullPath) || !statSync(target.fullPath).isFile()) {
      return undefined;
    }
    return this.fileFromPath(workspaceId, target.path, target.fullPath);
  }

  listWorkspaceFiles(workspaceId: string, filter: WorkspaceListFilter = {}): WorkspaceFile[] {
    if (!this.canAccessWorkspace(workspaceId, filter)) return [];
    const root = this.workspaceRootPath(workspaceId);
    if (!existsSync(root)) return [];
    return this.listFilePaths(root)
      .map((fullPath) => {
        const path = `/${relative(root, fullPath).split(sep).join("/")}`;
        return this.fileFromPath(workspaceId, path, fullPath);
      })
      .filter((file) =>
        !filter.runId ||
        file.created_by_run_id === filter.runId ||
        file.last_modified_by_run_id === filter.runId,
      )
      .sort((a, b) => a.path.localeCompare(b.path));
  }

  deleteFile(workspaceId: string, path: string, guard: WorkspaceAccessGuard = {}): boolean {
    if (!this.canAccessWorkspace(workspaceId, guard)) return false;
    const target = this.resolvePath(workspaceId, path);
    if (!existsSync(target.fullPath) || !statSync(target.fullPath).isFile()) {
      return false;
    }
    unlinkSync(target.fullPath);
    this.meta.delete(this.metaKey(workspaceId, target.path));
    return true;
  }

  close(): void {
    rmSync(this.root, { recursive: true, force: true });
  }

  getWorkspaceRoot(workspaceId: string, guard: WorkspaceAccessGuard = {}): string {
    this.assertWorkspaceAccess(workspaceId, guard);
    const root = this.workspaceRootPath(workspaceId);
    mkdirSync(root, { recursive: true });
    return root;
  }

  private fileFromPath(workspaceId: string, path: string, fullPath: string): WorkspaceFile {
    const content = readFileSync(fullPath, "utf8");
    const stat = statSync(fullPath);
    const meta = this.meta.get(this.metaKey(workspaceId, path));
    const metaBinding = this.workspaceMeta.get(workspaceId);
    return {
      workspace_id: workspaceId,
      org_id: metaBinding?.org_id ?? null,
      owner_user_id: metaBinding?.owner_user_id ?? null,
      thread_id: metaBinding?.thread_id ?? null,
      path,
      content,
      size: Buffer.byteLength(content, "utf8"),
      version: meta?.version ?? 1,
      ...(meta?.created_by_run_id ? { created_by_run_id: meta.created_by_run_id } : {}),
      ...(meta?.last_modified_by_run_id ? { last_modified_by_run_id: meta.last_modified_by_run_id } : {}),
      created_at: meta?.created_at ?? stat.birthtime.toISOString().replace(/\.\d{3}/, ""),
      updated_at: stat.mtime.toISOString().replace(/\.\d{3}/, ""),
    };
  }

  private resolvePath(workspaceId: string, path: string): { path: string; fullPath: string } {
    const normalized = normalizeWorkspacePath(path);
    const root = this.workspaceRootPath(workspaceId);
    const fullPath = resolve(root, normalized.relativePath);
    if (fullPath !== root && !fullPath.startsWith(`${root}${sep}`)) {
      throw new Error(`Invalid workspace path: ${path}`);
    }
    return { path: normalized.path, fullPath };
  }

  private workspaceRootPath(workspaceId: string): string {
    return join(this.root, workspaceDirName(workspaceId));
  }

  private assertWorkspaceAccess(workspaceId: string, guard: WorkspaceAccessGuard = {}): void {
    if (!this.canAccessWorkspace(workspaceId, guard)) {
      throw new Error(`Workspace ${workspaceId} is not accessible`);
    }
  }

  private listFilePaths(root: string): string[] {
    const files: string[] = [];
    for (const entry of readdirSync(root, { withFileTypes: true })) {
      const fullPath = join(root, entry.name);
      if (entry.isDirectory()) files.push(...this.listFilePaths(fullPath));
      if (entry.isFile()) files.push(fullPath);
    }
    return files;
  }

  private metaKey(workspaceId: string, path: string): string {
    return `${workspaceId}\0${path}`;
  }
}
