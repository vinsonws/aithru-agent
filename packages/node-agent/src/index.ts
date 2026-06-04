import type {
  AgentClassificationResult,
  AgentPlan,
  AgentReviewResult,
  AgentRunOptions,
} from "@aithru/agent-core";

export const AGENT_CLASSIFY_NODE_TYPE = "agent.classify";
export const AGENT_TASK_NODE_TYPE = "agent.task";
export const AGENT_NODE_VERSION = "0.1.0";

export type AgentClassifyNodeConfig = {
  goal: string;
  routes: string[];
  model?: string;
  outputSchema?: unknown;
  options?: AgentRunOptions;
};

export type AgentClassifyNodeOutput = AgentClassificationResult;

export type AgentTaskNodeConfig = {
  goal: string;
  engine?: "plan-run-review" | (string & {});
  model?: string;
  maxSteps?: number;
  timeoutMs?: number;
  allowedTools?: string[];
  review?: boolean;
  outputSchema?: unknown;
};

export type AgentTaskNodeOutput = {
  status: "completed" | "failed" | "needs_rerun";
  summary: string;
  plan?: AgentPlan;
  artifacts: unknown[];
  review?: AgentReviewResult;
  metadata?: Record<string, unknown>;
};

export type AgentNodeRuntimeBinding = {
  modelName?: string;
  engineName?: string;
};

export function isAgentNodeType(type: string) {
  return type === AGENT_CLASSIFY_NODE_TYPE || type === AGENT_TASK_NODE_TYPE;
}
