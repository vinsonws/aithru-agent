import { apiRequest, openEventStream } from "./client";
import type {
  AgentRun,
  AgentRunStatus,
  AgentStreamEvent,
  AgentTraceSpan,
  AgentTodo,
  AgentApproval,
  AgentArtifact,
  AgentSubagentRun,
  AgentToolDescriptor,
  AgentSubagentSpec,
  AgentRunUsageSummary,
  AgentRunTreeUsageSnapshot,
  AgentMemoryRecall,
  CreateRunRequest,
} from "./types";

export interface RunSnapshot {
  run: AgentRun;
  events?: AgentStreamEvent[];
  trace?: AgentTraceSpan[];
  todos?: AgentTodo[];
  approvals?: AgentApproval[];
  workspace_files?: unknown[];
  artifacts?: AgentArtifact[];
  subagents?: AgentSubagentRun[];
  summary?: unknown;
  [key: string]: unknown;
}

export const runsApi = {
  list: (query?: Record<string, string | number | boolean | undefined>) =>
    apiRequest<AgentRun[] | { items: AgentRun[] }>("/api/runs", { query }),

  create: (body: CreateRunRequest) =>
    apiRequest<AgentRun>("/api/runs", { method: "POST", body }),

  createStream: (body: CreateRunRequest) =>
    apiRequest<AgentRun>("/api/runs/stream", { method: "POST", body }),

  get: (runId: string) => apiRequest<AgentRun>(`/api/runs/${runId}`),

  cancel: (runId: string) =>
    apiRequest<AgentRun>(`/api/runs/${runId}/cancel`, { method: "POST" }),

  resume: (runId: string) =>
    apiRequest<AgentRun>(`/api/runs/${runId}/resume`, { method: "POST" }),

  submitInput: (runId: string, content: string) =>
    apiRequest<AgentRun>(`/api/runs/${runId}/input`, {
      method: "POST",
      body: { content },
    }),

  snapshot: (runId: string) =>
    apiRequest<RunSnapshot>(`/api/runs/${runId}/snapshot`),

  events: (runId: string) =>
    apiRequest<AgentStreamEvent[]>(`/api/runs/${runId}/events`),

  trace: (runId: string) =>
    apiRequest<AgentTraceSpan[]>(`/api/runs/${runId}/trace`),

  tools: (runId: string) =>
    apiRequest<AgentToolDescriptor[]>(`/api/runs/${runId}/tools`),

  subagents: (runId: string) =>
    apiRequest<AgentSubagentRun[]>(`/api/runs/${runId}/subagents`),

  tree: (runId: string) =>
    apiRequest<unknown>(`/api/runs/${runId}/tree`),

  usage: (runId: string) =>
    apiRequest<AgentRunUsageSummary>(`/api/runs/${runId}/usage`),

  treeUsage: (runId: string) =>
    apiRequest<AgentRunTreeUsageSnapshot>(`/api/runs/${runId}/tree/usage`),

  capabilityAudit: (runId: string) =>
    apiRequest<unknown>(`/api/runs/${runId}/capability-audit`),

  memoryRecall: (runId: string) =>
    apiRequest<AgentMemoryRecall>(`/api/runs/${runId}/memory-recall`),

  export: (runId: string) =>
    apiRequest<unknown>(`/api/runs/${runId}/export`),

  /** Live SSE stream of run events. Resolves when the stream closes. */
  stream: (runId: string, onEvent: (e: AgentStreamEvent) => void, signal?: AbortSignal) =>
    openEventStream(`/api/runs/${runId}/stream?follow=true`, onEvent as (e: unknown) => void, signal),

  operatorFollowUp: (runId: string, body: { action_kind: string; task_msg?: string }) =>
    apiRequest<unknown>(`/api/runs/${runId}/operator-actions/follow-up`, {
      method: "POST",
      body,
    }),
};

export type { AgentRunStatus, AgentSubagentSpec };
