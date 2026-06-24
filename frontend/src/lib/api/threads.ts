import { apiRequest } from "./client";
import type {
  AgentThread,
  AgentThreadDashboardPage,
  AgentThreadSummary,
  AgentThreadWorkbench,
  AgentMessage,
  AgentRun,
  CreateThreadRequest,
  CreateRunRequest,
  UpdateThreadRequest,
} from "./types";

export const threadsApi = {
  list: (query?: { status?: string; include_meta?: boolean }) =>
    apiRequest<AgentThread[] | { items: AgentThread[] }>("/api/threads", {
      query,
    }),

  dashboard: () => apiRequest<AgentThreadDashboardPage>("/api/threads/dashboard"),

  create: (body: CreateThreadRequest) =>
    apiRequest<AgentThread>("/api/threads", { method: "POST", body }),

  get: (threadId: string) => apiRequest<AgentThread>(`/api/threads/${threadId}`),

  update: (threadId: string, body: UpdateThreadRequest) =>
    apiRequest<AgentThread>(`/api/threads/${threadId}`, { method: "PATCH", body }),

  summary: (threadId: string) =>
    apiRequest<AgentThreadSummary>(`/api/threads/${threadId}/summary`),

  workbench: (threadId: string) =>
    apiRequest<AgentThreadWorkbench>(`/api/threads/${threadId}/workbench`),

  messages: (threadId: string) =>
    apiRequest<AgentMessage[]>(`/api/threads/${threadId}/messages`),

  runs: (threadId: string, query?: { status?: string; limit?: number }) =>
    apiRequest<AgentRun[]>(`/api/threads/${threadId}/runs`, { query }),

  /** Create a run in a thread and stream it. */
  createRun: (threadId: string, body: CreateRunRequest) =>
    apiRequest<AgentRun>(`/api/threads/${threadId}/runs/stream`, {
      method: "POST",
      body,
    }),
};
