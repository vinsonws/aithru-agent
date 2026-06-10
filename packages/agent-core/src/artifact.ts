import type { ArtifactId, OrgId, WorkspaceId, RunId } from "./ids.js";

export type AgentArtifactType =
  | "text"
  | "markdown"
  | "json"
  | "decision"
  | "report"
  | "file"
  | "patch"
  | "workflow_draft";

export type AgentArtifact = {
  id: ArtifactId;
  orgId: OrgId;
  workspaceId: WorkspaceId;
  runId?: RunId;
  type: AgentArtifactType;
  name: string;
  mediaType?: string;
  uri?: string;
  content?: unknown;
  metadata?: Record<string, unknown>;
  createdAt: string;
};
