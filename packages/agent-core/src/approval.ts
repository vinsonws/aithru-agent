import type { ApprovalId, ToolCallId, RunId } from "./ids.js";

export type AgentApprovalDecision = "approved" | "denied" | "expired";

export type AgentApproval = {
  id: ApprovalId;
  toolCallId: ToolCallId;
  runId: RunId;
  reason: string;
  riskLevel: "safe" | "read" | "write" | "dangerous";
  redactedInput?: unknown;
  status: "pending" | "resolved" | "expired";
  decision?: AgentApprovalDecision;
  decidedBy?: string;
  decidedAt?: string;
  createdAt: string;
};
