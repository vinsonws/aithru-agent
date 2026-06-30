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
export type HealthResponse = Static<typeof HealthResponseSchema>;
export type CreateThreadRequest = Static<typeof CreateThreadRequestSchema>;
export type UpdateThreadRequest = Static<typeof UpdateThreadRequestSchema>;
export type CreateMessageRequest = Static<typeof CreateMessageRequestSchema>;
export type CreateRunRequest = Static<typeof CreateRunRequestSchema>;
