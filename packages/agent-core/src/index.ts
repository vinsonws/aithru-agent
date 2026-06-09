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

export type AgentToolPolicyDecision = "allow" | "deny" | "require_approval";

export type AgentToolRiskPolicy = {
  defaultDecision?: AgentToolPolicyDecision;
  byRiskLevel?: Partial<Record<AgentRiskLevel, AgentToolPolicyDecision>>;
  byToolName?: Record<string, AgentToolPolicyDecision>;
};

export type AgentRunOptions = {
  maxSteps?: number;
  timeoutMs?: number;
  allowedTools?: string[];
  review?: boolean;
  toolRiskPolicy?: AgentToolRiskPolicy;
  metadata?: Record<string, unknown>;
};

export type AgentResearchSource = {
  id: string;
  title?: string;
  uri?: string;
  content?: unknown;
  metadata?: Record<string, unknown>;
};

export type AgentResearchFinding = {
  id: string;
  claim: string;
  sourceIds?: string[];
  confidence?: number;
  metadata?: Record<string, unknown>;
};

export type AgentResearchReport = {
  title: string;
  summary: string;
  findings: AgentResearchFinding[];
  sources: AgentResearchSource[];
  limitations?: string[];
  metadata?: Record<string, unknown>;
};

export type AgentResearchOptions = AgentRunOptions & {
  maxSources?: number;
  maxSearchQueries?: number;
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

export type AgentApprovalRequest = {
  id: string;
  taskId: string;
  stepId?: string;
  toolRequest: AgentToolRequest;
  reason?: string;
  riskLevel: AgentRiskLevel;
  metadata?: Record<string, unknown>;
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
  | {
      type: "agent.step.started";
      taskId: string;
      stepId: string;
      step?: AgentPlanStep;
    }
  | { type: "agent.model.delta"; taskId: string; stepId?: string; text: string }
  | {
      type: "agent.tool.proposed";
      taskId: string;
      stepId?: string;
      request: AgentToolRequest;
    }
  | {
      type: "agent.tool.completed";
      taskId: string;
      stepId?: string;
      result: AgentToolResult;
    }
  | { type: "agent.artifact.created"; taskId: string; artifact: AgentArtifact }
  | { type: "agent.review.started"; taskId: string }
  | {
      type: "agent.review.completed";
      taskId: string;
      review: AgentReviewResult;
    }
  | { type: "agent.task.completed"; taskId: string; output: AgentTaskOutput }
  | { type: "agent.task.failed"; taskId: string; error: AgentError }
  | {
      type: "agent.tool.approval_requested";
      taskId: string;
      stepId?: string;
      approval: AgentApprovalRequest;
    }
  | {
      type: "agent.task.paused";
      taskId: string;
      approval: AgentApprovalRequest;
      output: AgentTaskOutput;
    };

export type AgentTraceEventKind =
  | "agent.task"
  | "agent.plan"
  | "agent.step"
  | "agent.model"
  | "agent.tool"
  | "agent.artifact"
  | "agent.review"
  | "agent.approval"
  | "agent.error";

export type AgentTraceEventPhase =
  | "created"
  | "started"
  | "proposed"
  | "completed"
  | "failed"
  | "requested"
  | "paused"
  | "delta";

export type AgentTraceEvent = {
  kind: AgentTraceEventKind;
  phase: AgentTraceEventPhase;
  agentEventType: AgentEvent["type"];
  taskId?: string;
  stepId?: string;
  toolName?: string;
  artifactId?: string;
  errorCode?: string;
  summary?: string;
  payload: AgentEvent;
};

export type AgentTaskOutput = {
  status: "completed" | "failed" | "needs_rerun" | "paused";
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

export interface AgentEngine<
  TOptions extends AgentRunOptions = AgentRunOptions,
> {
  name: string;
  run(input: AgentEngineRunInput<TOptions>): AsyncIterable<AgentEvent>;
}

export type AgentEngineRunInput<
  TOptions extends AgentRunOptions = AgentRunOptions,
> = {
  task: AgentTask;
  model: AgentModelAdapter;
  host: AgentHost;
  options?: TOptions;
};

export function agentTraceEventFromAgentEvent(
  event: AgentEvent,
): AgentTraceEvent {
  switch (event.type) {
    case "agent.task.created":
      return {
        kind: "agent.task",
        phase: "created",
        agentEventType: event.type,
        taskId: event.taskId,
        summary: event.task.goal,
        payload: event,
      };

    case "agent.task.completed":
      return {
        kind: "agent.task",
        phase: "completed",
        agentEventType: event.type,
        taskId: event.taskId,
        summary: event.output.summary,
        payload: event,
      };

    case "agent.task.failed":
      return {
        kind: "agent.error",
        phase: "failed",
        agentEventType: event.type,
        taskId: event.taskId,
        errorCode: event.error.code,
        summary: event.error.message,
        payload: event,
      };

    case "agent.plan.started":
      return {
        kind: "agent.plan",
        phase: "started",
        agentEventType: event.type,
        taskId: event.taskId,
        payload: event,
      };

    case "agent.plan.completed":
      return {
        kind: "agent.plan",
        phase: "completed",
        agentEventType: event.type,
        taskId: event.taskId,
        summary: `${event.plan.steps.length} step(s) planned`,
        payload: event,
      };

    case "agent.step.started":
      return {
        kind: "agent.step",
        phase: "started",
        agentEventType: event.type,
        taskId: event.taskId,
        stepId: event.stepId,
        ...(event.step?.objective ? { summary: event.step.objective } : {}),
        payload: event,
      };

    case "agent.model.delta":
      return {
        kind: "agent.model",
        phase: "delta",
        agentEventType: event.type,
        taskId: event.taskId,
        ...(event.stepId ? { stepId: event.stepId } : {}),
        summary: event.text,
        payload: event,
      };

    case "agent.tool.proposed":
      return {
        kind: "agent.tool",
        phase: "proposed",
        agentEventType: event.type,
        taskId: event.taskId,
        ...(event.stepId ? { stepId: event.stepId } : {}),
        toolName: event.request.toolName,
        ...(event.request.reason ? { summary: event.request.reason } : {}),
        payload: event,
      };

    case "agent.tool.completed":
      return {
        kind: "agent.tool",
        phase: "completed",
        agentEventType: event.type,
        taskId: event.taskId,
        ...(event.stepId ? { stepId: event.stepId } : {}),
        toolName: event.result.toolName,
        ...(event.result.error ? { errorCode: event.result.error.code } : {}),
        ...(event.result.error ? { summary: event.result.error.message } : {}),
        payload: event,
      };

    case "agent.artifact.created":
      return {
        kind: "agent.artifact",
        phase: "created",
        agentEventType: event.type,
        taskId: event.taskId,
        artifactId: event.artifact.id,
        ...(event.artifact.name ? { summary: event.artifact.name } : {}),
        payload: event,
      };

    case "agent.review.started":
      return {
        kind: "agent.review",
        phase: "started",
        agentEventType: event.type,
        taskId: event.taskId,
        payload: event,
      };

    case "agent.review.completed":
      return {
        kind: "agent.review",
        phase: "completed",
        agentEventType: event.type,
        taskId: event.taskId,
        ...(event.review.summary ? { summary: event.review.summary } : {}),
        payload: event,
      };

    case "agent.tool.approval_requested":
      return {
        kind: "agent.approval",
        phase: "requested",
        agentEventType: event.type,
        taskId: event.taskId,
        ...(event.stepId ? { stepId: event.stepId } : {}),
        toolName: event.approval.toolRequest.toolName,
        summary:
          event.approval.reason ??
          `Approval requested for ${event.approval.toolRequest.toolName}.`,
        payload: event,
      };

    case "agent.task.paused":
      return {
        kind: "agent.task",
        phase: "paused",
        agentEventType: event.type,
        taskId: event.taskId,
        summary: event.output.summary,
        payload: event,
      };
  }
}
