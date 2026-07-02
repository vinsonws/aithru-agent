import { apiRequest } from "./client";
import type {
  AgentApproval,
  AgentApprovalDecision,
  AgentMemoryEntry,
  AgentMemoryForgetResult,
  AgentMemoryCandidate,
  AgentMemoryCandidateApprovalResult,
  AgentSkill,
  AgentSkillRegistryEntry,
  AgentSkillEnablementResult,
  AgentModelProfileEntry,
  AgentModelProfileEnablementResult,
  AgentModelProviderEntry,
  AgentModelEntry,
  AgentModelProviderWithModels,
  AgentModelDefaultSelection,
  AgentExternalToolConfigEntry,
  AgentExternalToolConfigOperationResult,
  AgentHealthResponse,
  LongTermMemoryDeleteResult,
  LongTermMemoryHealth,
  AgentSubagentSpec,
  CreateModelProviderRequest,
  UpdateModelProviderRequest,
  CreateModelRequest,
  UpdateModelRequest,
  UpdateModelDefaultRequest,
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

export const modelProvidersApi = {
  list: () => apiRequest<AgentModelProviderWithModels[]>(`/api/model-providers`),

  create: (body: CreateModelProviderRequest) =>
    apiRequest<AgentModelProviderEntry>(`/api/model-providers`, { method: "POST", body }),

  patch: (key: string, body: UpdateModelProviderRequest) =>
    apiRequest<AgentModelProviderEntry>(`/api/model-providers/${key}`, {
      method: "PATCH",
      body,
    }),

  remove: (key: string) =>
    apiRequest<{ deleted: boolean }>(`/api/model-providers/${key}`, { method: "DELETE" }),

  createModel: (providerKey: string, body: CreateModelRequest) =>
    apiRequest<AgentModelEntry>(`/api/model-providers/${providerKey}/models`, {
      method: "POST",
      body,
    }),

  patchModel: (providerKey: string, modelKey: string, body: UpdateModelRequest) =>
    apiRequest<AgentModelEntry>(`/api/model-providers/${providerKey}/models/${modelKey}`, {
      method: "PATCH",
      body,
    }),

  removeModel: (providerKey: string, modelKey: string) =>
    apiRequest<{ deleted: boolean }>(`/api/model-providers/${providerKey}/models/${modelKey}`, {
      method: "DELETE",
    }),

  getDefault: () => apiRequest<AgentModelDefaultSelection>(`/api/model-default`),

  setDefault: (body: UpdateModelDefaultRequest) =>
    apiRequest<AgentModelDefaultSelection>(`/api/model-default`, { method: "PUT", body }),
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
