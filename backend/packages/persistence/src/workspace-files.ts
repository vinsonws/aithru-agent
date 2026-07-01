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
import type { WorkspaceFile } from "./store.js";

interface FileMeta {
  created_at: string;
  version: number;
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

  writeFile(workspaceId: string, path: string, content: string): WorkspaceFile {
    const target = this.resolvePath(workspaceId, path);
    const existing = this.readFile(workspaceId, target.path);
    mkdirSync(dirname(target.fullPath), { recursive: true });
    writeFileSync(target.fullPath, content, "utf8");
    const timestamp = nowIso();
    const key = this.metaKey(workspaceId, target.path);
    this.meta.set(key, {
      created_at: existing?.created_at ?? timestamp,
      version: (existing?.version ?? 0) + 1,
    });
    return this.readFile(workspaceId, target.path)!;
  }

  readFile(workspaceId: string, path: string): WorkspaceFile | undefined {
    const target = this.resolvePath(workspaceId, path);
    if (!existsSync(target.fullPath) || !statSync(target.fullPath).isFile()) {
      return undefined;
    }
    return this.fileFromPath(workspaceId, target.path, target.fullPath);
  }

  listWorkspaceFiles(workspaceId: string): WorkspaceFile[] {
    const root = this.workspaceRootPath(workspaceId);
    if (!existsSync(root)) return [];
    return this.listFilePaths(root)
      .map((fullPath) => {
        const path = `/${relative(root, fullPath).split(sep).join("/")}`;
        return this.fileFromPath(workspaceId, path, fullPath);
      })
      .sort((a, b) => a.path.localeCompare(b.path));
  }

  deleteFile(workspaceId: string, path: string): boolean {
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

  getWorkspaceRoot(workspaceId: string): string {
    const root = this.workspaceRootPath(workspaceId);
    mkdirSync(root, { recursive: true });
    return root;
  }

  private fileFromPath(workspaceId: string, path: string, fullPath: string): WorkspaceFile {
    const content = readFileSync(fullPath, "utf8");
    const stat = statSync(fullPath);
    const meta = this.meta.get(this.metaKey(workspaceId, path));
    return {
      workspace_id: workspaceId,
      path,
      content,
      size: Buffer.byteLength(content, "utf8"),
      version: meta?.version ?? 1,
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
