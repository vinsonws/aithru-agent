import type { SubagentRunId, RunId } from "./ids.js";
import type { AgentWorkspacePolicy } from "./skill.js";
import type { AgentMemoryPolicy } from "./skill.js";

export type AgentSubagentSpec = {
  key: string;
  name: string;
  instructions: string;
  allowedTools: string[];
  workspacePolicy?: AgentWorkspacePolicy;
  memoryPolicy?: AgentMemoryPolicy;
  contextBudget?: {
    maxInputTokens?: number;
    maxOutputTokens?: number;
  };
};

export type AgentSubagentRun = {
  id: SubagentRunId;
  parentRunId: RunId;
  spec: AgentSubagentSpec;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  startedAt?: string;
  completedAt?: string;
};
