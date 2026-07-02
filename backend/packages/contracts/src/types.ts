import type { Static } from "@sinclair/typebox";
import type {
  AgentThreadSchema,
  AgentMessageSchema,
  AgentRunSchema,
  AgentStreamEventSchema,
  AgentRunSource,
  AgentRunStatus,
  AgentMessageRole,
  AgentThreadStatus,
  AgentStreamVisibility,
  AgentStreamRedaction,
  AgentStreamSourceSchema,
  AgentRunHarnessOptionsSchema,
  AgentRunClaimSchema,
  AgentRunRetryPolicySchema,
  AgentRunRetryStateSchema,
  AgentRunResultSchema,
  AgentModelProviderEntrySchema,
  AgentModelEntrySchema,
  AgentModelProviderWithModelsSchema,
  AgentModelDefaultSelectionSchema,
  CreateModelProviderRequestSchema,
  UpdateModelProviderRequestSchema,
  CreateModelRequestSchema,
  UpdateModelRequestSchema,
  UpdateModelDefaultRequestSchema,
  ModelSecretInputSchema,
  HealthResponseSchema,
  CreateThreadRequestSchema,
  UpdateThreadRequestSchema,
  CreateMessageRequestSchema,
  CreateRunRequestSchema,
} from "./schemas.js";

export type AgentThread = Static<typeof AgentThreadSchema>;
export type AgentMessage = Static<typeof AgentMessageSchema>;
export type AgentRun = Static<typeof AgentRunSchema>;
export type AgentStreamEvent = Static<typeof AgentStreamEventSchema>;
export type AgentRunSourceType = Static<typeof AgentRunSource>;
export type AgentRunStatusType = Static<typeof AgentRunStatus>;
export type AgentMessageRoleType = Static<typeof AgentMessageRole>;
export type AgentThreadStatusType = Static<typeof AgentThreadStatus>;
export type AgentStreamVisibilityType = Static<typeof AgentStreamVisibility>;
export type AgentStreamRedactionType = Static<typeof AgentStreamRedaction>;
export type AgentStreamSource = Static<typeof AgentStreamSourceSchema>;
export type AgentRunHarnessOptions = Static<typeof AgentRunHarnessOptionsSchema>;
export type AgentRunClaim = Static<typeof AgentRunClaimSchema>;
export type AgentRunRetryPolicy = Static<typeof AgentRunRetryPolicySchema>;
export type AgentRunRetryState = Static<typeof AgentRunRetryStateSchema>;
export type AgentRunResult = Static<typeof AgentRunResultSchema>;
export type AgentModelProviderEntry = Static<typeof AgentModelProviderEntrySchema>;
export type AgentModelEntry = Static<typeof AgentModelEntrySchema>;
export type AgentModelProviderWithModels = Static<typeof AgentModelProviderWithModelsSchema>;
export type AgentModelDefaultSelection = Static<typeof AgentModelDefaultSelectionSchema>;
export type CreateModelProviderRequest = Static<typeof CreateModelProviderRequestSchema>;
export type UpdateModelProviderRequest = Static<typeof UpdateModelProviderRequestSchema>;
export type CreateModelRequest = Static<typeof CreateModelRequestSchema>;
export type UpdateModelRequest = Static<typeof UpdateModelRequestSchema>;
export type UpdateModelDefaultRequest = Static<typeof UpdateModelDefaultRequestSchema>;
export type ModelSecretInput = Static<typeof ModelSecretInputSchema>;
export type HealthResponse = Static<typeof HealthResponseSchema>;
export type CreateThreadRequest = Static<typeof CreateThreadRequestSchema>;
export type UpdateThreadRequest = Static<typeof UpdateThreadRequestSchema>;
export type CreateMessageRequest = Static<typeof CreateMessageRequestSchema>;
export type CreateRunRequest = Static<typeof CreateRunRequestSchema>;
