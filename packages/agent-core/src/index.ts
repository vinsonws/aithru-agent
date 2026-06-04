export type AgentStatus =
  | "created"
  | "planning"
  | "running"
  | "paused"
  | "reviewing"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentRiskLevel = "safe" | "read" | "write" | "dangerous";

export type AgentTask = {
  id: string;
  goal: string;
  input?: unknown;
  context?: AgentContextBundle;
  constraints?: string[];
  expectedArtifacts?: AgentArtifactSpec[];
  outputSchema?: unknown;
};

export type AgentContextBundle = {
  summary?: string;
  values?: Record<string, unknown>;
  references?: AgentContextReference[];
};

export type AgentContextReference = {
  id: string;
  title?: string;
  uri?: string;
  content?: unknown;
  metadata?: Record<string, unknown>;
};

export type AgentPlan = {
  id: string;
  taskId: string;
  steps: AgentPlanStep[];
};

export type AgentPlanStep = {
  id: string;
  title: string;
  objective: string;
  allowedTools?: string[];
  expectedOutput?: string;
  riskLevel?: AgentRiskLevel;
};

export type AgentStepStatus =
  | "pending"
  | "running"
  | "waiting_for_tool"
  | "paused_for_approval"
  | "completed"
  | "failed"
  | "skipped";

export type AgentStepRun = {
  id: string;
  planStepId?: string;
  status: AgentStepStatus;
  input?: unknown;
  output?: unknown;
  toolCalls?: AgentToolCallRecord[];
  error?: AgentError;
};

export type AgentRun = {
  id: string;
  taskId: string;
  status: AgentStatus;
  plan?: AgentPlan;
  steps: AgentStepRun[];
  artifacts: AgentArtifact[];
  review?: AgentReviewResult;
  error?: AgentError;
};

export type AgentRunOptions = {
  maxSteps?: number;
  timeoutMs?: number;
  allowedTools?: string[];
  review?: boolean;
  metadata?: Record<string, unknown>;
};

export type AgentToolRequest = {
  id: string;
  toolName: string;
  arguments: unknown;
  reason?: string;
  stepId?: string;
  riskLevel?: AgentRiskLevel;
};

export type AgentToolResult = {
  id: string;
  toolName: string;
  output?: unknown;
  error?: AgentError;
  metadata?: Record<string, unknown>;
};

export type AgentToolCallRecord = {
  request: AgentToolRequest;
  result?: AgentToolResult;
};

export type AgentToolDescriptor = {
  name: string;
  description?: string;
  inputSchema?: unknown;
  riskLevel?: AgentRiskLevel;
};

export type AgentArtifactSpec = {
  type: string;
  name?: string;
  description?: string;
};

export type AgentArtifactDraft = {
  type: AgentArtifactType;
  name?: string;
  content?: unknown;
  mediaType?: string;
  sourceStepId?: string;
  metadata?: Record<string, unknown>;
};

export type AgentArtifact = AgentArtifactDraft & {
  id: string;
  uri?: string;
};

export type AgentArtifactType =
  | "text"
  | "markdown"
  | "json"
  | "decision"
  | "report"
  | "file"
  | "patch";

export type AgentReviewResult = {
  status: "passed" | "needs_rerun" | "failed";
  summary?: string;
  issues?: string[];
  metadata?: Record<string, unknown>;
};

export type AgentClassificationResult = {
  route: string;
  confidence: number;
  reason?: string;
  metadata?: Record<string, unknown>;
};

export type AgentError = {
  code: string;
  message: string;
  cause?: unknown;
  metadata?: Record<string, unknown>;
};

export type AgentEvent =
  | { type: "agent.task.created"; taskId: string; task: AgentTask }
  | { type: "agent.plan.started"; taskId: string }
  | { type: "agent.plan.completed"; taskId: string; plan: AgentPlan }
  | { type: "agent.step.started"; taskId: string; stepId: string; step?: AgentPlanStep }
  | { type: "agent.model.delta"; taskId: string; stepId?: string; text: string }
  | { type: "agent.tool.proposed"; taskId: string; stepId?: string; request: AgentToolRequest }
  | { type: "agent.tool.completed"; taskId: string; stepId?: string; result: AgentToolResult }
  | { type: "agent.artifact.created"; taskId: string; artifact: AgentArtifact }
  | { type: "agent.review.started"; taskId: string }
  | { type: "agent.review.completed"; taskId: string; review: AgentReviewResult }
  | { type: "agent.task.completed"; taskId: string; output: AgentTaskOutput }
  | { type: "agent.task.failed"; taskId: string; error: AgentError };

export type AgentTaskOutput = {
  status: "completed" | "failed" | "needs_rerun";
  summary: string;
  plan?: AgentPlan;
  artifacts: AgentArtifact[];
  review?: AgentReviewResult;
  usage?: AgentUsage;
  metadata?: Record<string, unknown>;
};

export type AgentUsage = {
  inputTokens?: number;
  outputTokens?: number;
  toolCalls?: number;
  cost?: number;
};

export type AgentModelInput = {
  task: AgentTask;
  plan?: AgentPlan;
  step?: AgentPlanStep;
  mode: "classify" | "plan" | "execute" | "review";
  messages?: AgentModelMessage[];
  outputSchema?: unknown;
  tools?: AgentToolDescriptor[];
};

export type AgentModelMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  metadata?: Record<string, unknown>;
};

export type AgentModelEvent =
  | { type: "text.delta"; text: string }
  | { type: "structured.output"; value: unknown }
  | { type: "tool_call.proposed"; toolCall: AgentToolRequest }
  | { type: "final"; output: unknown }
  | { type: "error"; error: AgentError };

export interface AgentModelAdapter {
  name: string;
  generate(input: AgentModelInput): AsyncIterable<AgentModelEvent>;
}

export interface AgentHost {
  emit(event: AgentEvent): void | Promise<void>;
  callTool(request: AgentToolRequest): Promise<AgentToolResult>;
  listTools?(): Promise<AgentToolDescriptor[]>;
  createArtifact?(artifact: AgentArtifactDraft): Promise<AgentArtifact>;
}

export interface AgentEngine {
  name: string;
  run(input: AgentEngineRunInput): AsyncIterable<AgentEvent>;
}

export type AgentEngineRunInput = {
  task: AgentTask;
  model: AgentModelAdapter;
  host: AgentHost;
  options?: AgentRunOptions;
};
