import { apiRequest } from "./client";
import type {
  AgentApproval,
  AgentApprovalDecision,
  AgentArtifact,
  AgentArtifactDownloadInfo,
  AgentMemoryEntry,
  AgentMemoryForgetResult,
  AgentMemoryCandidate,
  AgentMemoryCandidateApprovalResult,
  AgentSkill,
  AgentSkillRegistryEntry,
  AgentSkillEnablementResult,
  AgentModelProfileEntry,
  AgentModelProfileEnablementResult,
  AgentExternalToolConfigEntry,
  AgentExternalToolConfigOperationResult,
  AgentHealthResponse,
  LongTermMemoryDeleteResult,
  LongTermMemoryHealth,
  AgentSubagentSpec,
  CreateMemoryEntryRequest,
  CreateUserSkillPackageRequest,
  UpdateUserSkillPackageRequest,
} from "./types";

export const approvalsApi = {
  list: (query?: { status?: string; run_id?: string }) =>
    apiRequest<AgentApproval[]>(`/api/approvals`, { query }),

  get: (approvalId: string) =>
    apiRequest<AgentApproval>(`/api/approvals/${approvalId}`),

  resolve: (approvalId: string, body: { decision: AgentApprovalDecision; comment?: string }) =>
    apiRequest<AgentApproval>(`/api/approvals/${approvalId}/resolve`, {
      method: "POST",
      body,
    }),

  resolveExternalApproval: (
    runId: string,
    body: { decision: AgentApprovalDecision; approval_id?: string; comment?: string },
  ) =>
    apiRequest<AgentRun>(`/api/runs/${runId}/external-approval/resolve`, {
      method: "POST",
      body,
    }),

  resolveExternalRun: (runId: string, body: Record<string, unknown>) =>
    apiRequest<unknown>(`/api/runs/${runId}/external-run/resolve`, {
      method: "POST",
      body,
    }),
};

// re-export to avoid an extra import of AgentRun for the external-approval return
import type { AgentRun } from "./types";

export const artifactsApi = {
  list: (query?: {
    run_id?: string;
    workspace_id?: string;
    artifact_type?: string;
    finalized?: boolean;
    include_meta?: boolean;
    limit?: number;
    offset?: number;
  }) => apiRequest<AgentArtifact[] | { items: AgentArtifact[] }>(`/api/artifacts`, { query }),

  get: (artifactId: string) => apiRequest<AgentArtifact>(`/api/artifacts/${artifactId}`),

  content: (artifactId: string) =>
    apiRequest<Response>(`/api/artifacts/${artifactId}/content`, { raw: true }),

  downloadInfo: (artifactId: string) =>
    apiRequest<AgentArtifactDownloadInfo>(`/api/artifacts/${artifactId}/download`),
};

export const memoryApi = {
  list: (query?: { scope?: string; include_expired?: boolean; limit?: number }) =>
    apiRequest<AgentMemoryEntry[]>(`/api/memory`, { query }),

  create: (body: CreateMemoryEntryRequest) =>
    apiRequest<AgentMemoryEntry>(`/api/memory`, { method: "POST", body }),

  forget: (memoryId: string) =>
    apiRequest<AgentMemoryForgetResult>(`/api/memory/${memoryId}`, { method: "DELETE" }),

  candidates: (query?: { status?: string }) =>
    apiRequest<AgentMemoryCandidate[]>(`/api/memory-candidates`, { query }),

  approveCandidate: (candidateId: string) =>
    apiRequest<AgentMemoryCandidateApprovalResult>(
      `/api/memory-candidates/${candidateId}/approve`,
      { method: "POST" },
    ),

  rejectCandidate: (candidateId: string) =>
    apiRequest<AgentMemoryCandidateApprovalResult>(
      `/api/memory-candidates/${candidateId}/reject`,
      { method: "POST" },
    ),
};

export const longTermMemoryApi = {
  health: () => apiRequest<LongTermMemoryHealth>(`/api/long-term-memory/health`),

  forget: (memoryId: string) =>
    apiRequest<LongTermMemoryDeleteResult>(`/api/long-term-memory/${memoryId}`, {
      method: "DELETE",
    }),
};

export const skillsApi = {
  list: () => apiRequest<AgentSkill[]>(`/api/skills`),

  get: (key: string) => apiRequest<AgentSkill>(`/api/skills/${key}`),

  registry: () => apiRequest<AgentSkillRegistryEntry[]>(`/api/skill-registry`),

  registryEntry: (key: string) =>
    apiRequest<AgentSkillRegistryEntry>(`/api/skill-registry/${key}`),

  enable: (key: string) =>
    apiRequest<AgentSkillEnablementResult>(`/api/skill-registry/${key}/enable`, {
      method: "POST",
    }),

  disable: (key: string) =>
    apiRequest<AgentSkillEnablementResult>(`/api/skill-registry/${key}/disable`, {
      method: "POST",
    }),

  createUser: (body: CreateUserSkillPackageRequest) =>
    apiRequest<AgentSkillRegistryEntry>("/api/skill-registry/user", {
      method: "POST",
      body,
    }),

  updateUser: (key: string, body: UpdateUserSkillPackageRequest) =>
    apiRequest<AgentSkillRegistryEntry>(`/api/skill-registry/user/${key}`, {
      method: "PATCH",
      body,
    }),

  subagents: () => apiRequest<AgentSubagentSpec[]>(`/api/subagents`),
};

export const modelProfilesApi = {
  list: () => apiRequest<AgentModelProfileEntry[]>(`/api/model-profiles`),

  get: (key: string) => apiRequest<AgentModelProfileEntry>(`/api/model-profiles/${key}`),

  create: (body: Record<string, unknown>) =>
    apiRequest<AgentModelProfileEntry>(`/api/model-profiles`, { method: "POST", body }),

  patch: (key: string, body: Record<string, unknown>) =>
    apiRequest<AgentModelProfileEntry>(`/api/model-profiles/${key}`, {
      method: "PATCH",
      body,
    }),

  enable: (key: string) =>
    apiRequest<AgentModelProfileEnablementResult>(`/api/model-profiles/${key}/enable`, {
      method: "POST",
    }),

  disable: (key: string) =>
    apiRequest<AgentModelProfileEnablementResult>(`/api/model-profiles/${key}/disable`, {
      method: "POST",
    }),
};

export const externalToolsApi = {
  list: () => apiRequest<AgentExternalToolConfigEntry[]>(`/api/external-tools/configs`),

  get: (key: string) =>
    apiRequest<AgentExternalToolConfigEntry>(`/api/external-tools/configs/${key}`),

  create: (body: Record<string, unknown>) =>
    apiRequest<AgentExternalToolConfigEntry>(`/api/external-tools/configs`, {
      method: "POST",
      body,
    }),

  update: (key: string, body: Record<string, unknown>) =>
    apiRequest<AgentExternalToolConfigEntry>(`/api/external-tools/configs/${key}`, {
      method: "PATCH",
      body,
    }),

  enable: (key: string) =>
    apiRequest<AgentExternalToolConfigOperationResult>(`/api/external-tools/configs/${key}/enable`, {
      method: "POST",
    }),

  disable: (key: string) =>
    apiRequest<AgentExternalToolConfigOperationResult>(`/api/external-tools/configs/${key}/disable`, {
      method: "POST",
    }),
};

export const healthApi = {
  check: () => apiRequest<AgentHealthResponse>(`/api/health`),
};
