import { apiRequest } from "./client";
import type {
  AgentWorkspaceFile,
  AgentWorkspaceFileVersion,
  AgentWorkspaceSnapshot,
  AgentWorkspaceDiff,
  AgentWorkspaceFileReadResult,
  AgentWorkspaceUploadResult,
  AgentWorkspacePatchResult,
  AgentWorkspaceImageViewResult,
  AgentArtifactPromotionResult,
} from "./types";

export interface WorkspaceUploadBody {
  path: string;
  content_base64: string;
  media_type?: string | null;
}

function workspaceUrl(workspaceId: string, suffix: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}${suffix}`;
}

function encodeWorkspacePath(path: string): string {
  return path
    .replace(/^\/+/, "")
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
}

function workspaceFileUrl(workspaceId: string, path: string, suffix = ""): string {
  return workspaceUrl(workspaceId, `/files/${encodeWorkspacePath(path)}${suffix}`);
}

export const workspacesApi = {
  files: (workspaceId: string) =>
    apiRequest<AgentWorkspaceFile[]>(workspaceUrl(workspaceId, "/files")),

  readFile: (workspaceId: string, path: string) =>
    apiRequest<AgentWorkspaceFileReadResult>(workspaceFileUrl(workspaceId, path)),

  writeFile: (workspaceId: string, path: string, body: { content: string; media_type?: string | null }) =>
    apiRequest<AgentWorkspaceFile>(workspaceFileUrl(workspaceId, path), {
      method: "POST",
      body,
    }),

  deleteFile: (workspaceId: string, path: string) =>
    apiRequest<unknown>(workspaceFileUrl(workspaceId, path), {
      method: "DELETE",
    }),

  versions: (workspaceId: string, path: string) =>
    apiRequest<AgentWorkspaceFileVersion[]>(workspaceFileUrl(workspaceId, path, "/versions")),

  patchFile: (
    workspaceId: string,
    path: string,
    body: { edits: Array<{ search: string; replace: string }> },
  ) =>
    apiRequest<AgentWorkspacePatchResult>(
      workspaceFileUrl(workspaceId, path, "/patch"),
      { method: "POST", body },
    ),

  promote: (workspaceId: string, path: string) =>
    apiRequest<AgentArtifactPromotionResult>(
      workspaceFileUrl(workspaceId, path, "/promote"),
      { method: "POST" },
    ),

  convert: (workspaceId: string, path: string) =>
    apiRequest<unknown>(workspaceFileUrl(workspaceId, path, "/convert"), {
      method: "POST",
    }),

  viewImage: (workspaceId: string, path: string) =>
    apiRequest<AgentWorkspaceImageViewResult>(
      workspaceUrl(workspaceId, `/images/${encodeWorkspacePath(path)}/view`),
    ),

  upload: (workspaceId: string, body: WorkspaceUploadBody) =>
    apiRequest<AgentWorkspaceUploadResult>(
      workspaceUrl(workspaceId, "/uploads"),
      { method: "POST", body },
    ),

  snapshot: (workspaceId: string) =>
    apiRequest<AgentWorkspaceSnapshot>(workspaceUrl(workspaceId, "/snapshot")),

  diff: (workspaceId: string, query?: { base_version?: number; target_version?: number }) =>
    apiRequest<AgentWorkspaceDiff>(workspaceUrl(workspaceId, "/diff"), { query }),

  restore: (workspaceId: string, body: { version: number }) =>
    apiRequest<unknown>(workspaceUrl(workspaceId, "/restore"), {
      method: "POST",
      body,
    }),
};
