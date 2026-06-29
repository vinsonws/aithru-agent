import type {
  AgentStreamEvent,
  AgentStreamSource,
  AgentStreamVisibilityType,
  AgentStreamRedactionType,
} from "../contracts/types.js";

export type {
  AgentStreamEvent,
  AgentStreamSource,
  AgentStreamVisibilityType,
  AgentStreamRedactionType,
};

export const VISIBILITY = {
  USER: "user" as const,
  DEBUG: "debug" as const,
  AUDIT: "audit" as const,
};

export const REDACTION = {
  NONE: "none" as const,
  PARTIAL: "partial" as const,
  FULL: "full" as const,
};

export const EVENT_TYPES = {
  // Run lifecycle
  RUN_CREATED: "run.created",
  RUN_STARTED: "run.started",
  RUN_COMPLETED: "run.completed",
  RUN_FAILED: "run.failed",
  RUN_CANCELLED: "run.cancelled",
  RUN_PAUSED: "run.paused",
  RUN_RESUMED: "run.resumed",
  // Message lifecycle
  MESSAGE_CREATED: "message.created",
  MESSAGE_DELTA: "message.delta",
  MESSAGE_COMPLETED: "message.completed",
  // Tool lifecycle
  TOOL_PROPOSED: "tool.proposed",
  TOOL_STARTED: "tool.started",
  TOOL_COMPLETED: "tool.completed",
  TOOL_FAILED: "tool.failed",
  TOOL_DENIED: "tool.denied",
  // Approval
  APPROVAL_REQUESTED: "approval.requested",
  APPROVAL_RESOLVED: "approval.resolved",
  // Workspace
  WORKSPACE_FILE_WRITTEN: "workspace.file_written",
  WORKSPACE_FILE_READ: "workspace.file_read",
  // Todo
  TODO_CREATED: "todo.created",
  TODO_UPDATED: "todo.updated",
  // Context
  CONTEXT_PACKET_BUILT: "context.packet.built",
  // Model
  MODEL_REASONING_DELTA: "model.reasoning_delta",
  MODEL_USAGE: "model.usage",
  // External capabilities
  EXTERNAL_RUN_STARTED: "external_run.started",
  EXTERNAL_RUN_RESOLVED: "external_run.resolved",
  EXTERNAL_RUN_FAILED: "external_run.failed",
} as const;
