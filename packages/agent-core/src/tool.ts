import type { ToolCallId, SubagentRunId, TodoId, ArtifactId, ApprovalId } from "./ids.js";

export type AgentToolKind = "local_tool" | "workflow_capability";

export type AgentToolRiskLevel = "safe" | "read" | "write" | "dangerous";

export type AgentToolApprovalPolicy = "never" | "on_risk" | "always";

export type AgentExternalRunRef = {
  kind: "workflow_capability";
  capabilityKey: string;
  capabilityVersion?: string;
  capabilityRunId: string;
  status:
    | "queued"
    | "running"
    | "waiting_approval"
    | "completed"
    | "failed"
    | "cancelled";
  approvalId?: string;
  correlationId?: string;
  traceId?: string;
};

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
  metadata?: {
    provider?: "workspace" | "artifact" | "test";
    capabilityKey?: string;
    capabilityVersion?: string;
    externalApprovalOwner?: "workflow";
    [key: string]: unknown;
  };
};

export type AgentToolCallRequest = {
  id: ToolCallId;
  toolName: string;
  input: unknown;
  reason?: string;
  requestedBy: "model" | "harness" | "subagent" | "user" | "system";
  subagentRunId?: SubagentRunId;
  todoId?: TodoId;
  /** Set true only by the harness after a pending Agent-owned approval is resolved. */
  alreadyApproved?: boolean;
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
  externalRun?: AgentExternalRunRef;
  error?: {
    code: string;
    message: string;
    retryable?: boolean;
  };
  redaction: "none" | "partial" | "full";
};
