import type { ToolCallId, SubagentRunId, TodoId, ArtifactId, ApprovalId } from "./ids.js";

export type AgentToolKind =
  | "core_tool"
  | "core_node"
  | "workbench_workflow"
  | "subsystem_api"
  | "workspace"
  | "memory"
  | "sandbox"
  | "mcp";

export type AgentToolRiskLevel = "safe" | "read" | "write" | "dangerous";

export type AgentToolApprovalPolicy = "never" | "on_risk" | "always";

export type AgentToolDescriptor = {
  name: string;
  description: string;
  kind: AgentToolKind;
  inputSchema?: unknown;
  outputSchema?: unknown;
  requiredScopes: string[];
  riskLevel: AgentToolRiskLevel;
  approvalPolicy: AgentToolApprovalPolicy;
  display?: {
    name?: string;
    description?: string;
    icon?: string;
    category?: string;
  };
  metadata?: Record<string, unknown>;
};

export type AgentToolCallRequest = {
  id: ToolCallId;
  toolName: string;
  input: unknown;
  reason?: string;
  requestedBy: "model" | "harness" | "subagent" | "user" | "system";
  subagentRunId?: SubagentRunId;
  todoId?: TodoId;
};

export type AgentToolCallResult = {
  id: ToolCallId;
  toolName: string;
  status: "completed" | "failed" | "denied" | "waiting_approval";
  output?: unknown;
  artifactIds?: ArtifactId[];
  workspaceChanges?: Array<{
    path: string;
    operation: "created" | "updated" | "deleted";
  }>;
  approvalId?: ApprovalId;
  error?: {
    code: string;
    message: string;
    retryable?: boolean;
  };
  redaction: "none" | "partial" | "full";
};
