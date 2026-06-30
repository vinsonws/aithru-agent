// Re-export generated OpenAPI component schemas under friendly names.
// This file is the single import surface for backend contract types.
import type { components } from "./schema";

type S = components["schemas"];

export type AgentThread = S["AgentThread"];
export type AgentThreadStatus = S["AgentThreadStatus"];
export type AgentThreadSummary = S["AgentThreadSummary"];
export type AgentThreadDashboardPage = S["AgentThreadDashboardPage"];
export type AgentThreadDashboardItem = S["AgentThreadDashboardItem"];
export type AgentThreadWorkbench = S["AgentThreadWorkbench"];

export type AgentMessage = S["AgentMessage"];

export type AgentRunHarnessOptions = S["AgentRunHarnessOptions"] & {
  mode?: "flash" | "thinking" | "pro" | "ultra" | null;
};
export type AgentRun = Omit<S["AgentRun"], "harness_options"> & {
  harness_options?: AgentRunHarnessOptions | null;
};
export type AgentRunStatus = S["AgentRunStatus"];
export type AgentRunSource = S["AgentRunSource"];
export type AgentRunResult = S["AgentRunResult"];

export type AgentStreamEvent = S["AgentStreamEvent"];
export type AgentStreamVisibility = S["AgentStreamVisibility"];
export type AgentStreamSource = S["AgentStreamSource"];

export type AgentTraceSpan = S["AgentTraceSpan"];

export type AgentTodo = S["AgentTodo"];
export type AgentTodoStatus = S["AgentTodoStatus"];

export type AgentApproval = S["AgentApproval"];
export type AgentApprovalStatus = S["AgentApprovalStatus"];
export type AgentApprovalDecision = S["AgentApprovalDecision"];

export type AgentMemoryEntry = S["AgentMemoryEntry"];
export type AgentMemoryForgetResult = S["AgentMemoryForgetResult"];
export type AgentMemoryCandidate = S["AgentMemoryCandidate"];
export type AgentMemoryCandidateApprovalResult =
  S["AgentMemoryCandidateApprovalResult"];
export type AgentMemoryRecall = S["AgentMemoryRecall"];

export type AgentSkill = S["AgentSkill"];
export type AgentSkillRegistryEntry = S["AgentSkillRegistryEntry"];
export type AgentSkillConfiguration = S["AgentSkillConfiguration"];
export type AgentSkillEnablementResult = S["AgentSkillEnablementResult"];

export type AgentModelProfileEntry = S["AgentModelProfileEntry"];
export type AgentModelProfileEnablementResult =
  S["AgentModelProfileEnablementResult"];

export type AgentExternalToolConfigEntry = S["AgentExternalToolConfigEntry"];
export type AgentExternalToolConfigOperationResult =
  S["AgentExternalToolConfigOperationResult"];

export type AgentToolDescriptor = S["AgentToolDescriptor"];
export type AgentToolRiskLevel = S["AgentToolRiskLevel"];
export type AgentToolApprovalPolicy = S["AgentToolApprovalPolicy"];

export type AgentSubagentSpec = S["AgentSubagentSpec"];
export type AgentSubagentRun = S["AgentSubagentRun"];

export type AgentWorkspaceFile = S["AgentWorkspaceFile"];
export type AgentWorkspaceFileVersion = S["AgentWorkspaceFileVersion"];
export type AgentWorkspaceSnapshot = S["AgentWorkspaceSnapshot"];
export type AgentWorkspaceDiff = S["AgentWorkspaceDiff"];
export type AgentWorkspaceFileReadResult = S["AgentWorkspaceFileReadResult"];
export type AgentWorkspaceUploadResult = S["AgentWorkspaceUploadResult"];
export type AgentWorkspacePatchResult = S["AgentWorkspacePatchResult"];
export type AgentWorkspaceImageViewResult = S["AgentWorkspaceImageViewResult"];

export type AgentRunUsageSummary = S["AgentRunUsageSummary"];
export type AgentRunTreeUsageSnapshot = S["AgentRunTreeUsageSnapshot"];

export type AgentHealthResponse = S["AgentHealthResponse"];
export type LongTermMemoryDeleteResult = S["LongTermMemoryDeleteResult"];
export type LongTermMemoryHealth = S["LongTermMemoryHealth"];
export type RunInspectionSummary = S["RunInspectionSummary"];

// Request bodies
export type CreateThreadRequest = S["CreateThreadRequest"];
export type UpdateThreadRequest = S["UpdateThreadRequest"];
export type CreateRunRequest = S["CreateRunRequest"];
export type CreateMemoryEntryRequest = S["CreateMemoryEntryRequest"];
export type CreateUserSkillPackageRequest = S["CreateUserSkillPackageRequest"];
export type UpdateUserSkillPackageRequest = S["UpdateUserSkillPackageRequest"];
export type ResolveApprovalRequest = S["ResolveApprovalRequest"];
