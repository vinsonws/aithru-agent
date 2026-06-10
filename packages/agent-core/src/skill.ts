import type { SkillId, OrgId } from "./ids.js";

export type AgentSkillStatus = "draft" | "published" | "deprecated";

export type AgentWorkspacePolicy = {
  read?: boolean;
  write?: boolean;
  allowedPaths?: string[];
  maxFileSizeBytes?: number;
};

export type AgentMemoryPolicy = {
  read?: boolean;
  write?: boolean;
  scopes?: string[];
};

export type AgentSandboxPolicy = {
  enabled?: boolean;
  network?: "none" | "allowlist" | "full";
  allowedCommands?: string[];
  timeoutMs?: number;
};

export type AgentApprovalPolicy = {
  defaultDecision?: "allow" | "require_approval" | "deny";
  requireApprovalForRisk?: Array<"safe" | "read" | "write" | "dangerous">;
};

export type AgentSkill = {
  id: SkillId;
  orgId: OrgId;
  key: string;
  name: string;
  description?: string;
  instructions: string;
  whenToUse?: string;
  allowedTools: string[];
  allowedSubagents: string[];
  workspacePolicy?: AgentWorkspacePolicy;
  memoryPolicy?: AgentMemoryPolicy;
  sandboxPolicy?: AgentSandboxPolicy;
  approvalPolicy?: AgentApprovalPolicy;
  inputSchema?: unknown;
  outputSchema?: unknown;
  version: string;
  status: AgentSkillStatus;
};
