import type {
  AgentApprovalRequest,
  AgentArtifact,
  AgentArtifactDraft,
  AgentClassificationResult,
  AgentEvent,
  AgentHost,
  AgentModelAdapter,
  AgentPlan,
  AgentResearchOptions,
  AgentResumeState,
  AgentReviewResult,
  AgentRunOptions,
  AgentTask,
  AgentTaskOutput,
  AgentToolRequest,
  AgentToolResult,
  AgentToolRiskPolicy,
} from "@aithru/agent-core";
import { agentTraceEventFromAgentEvent } from "@aithru/agent-core";
import { AgentRuntime } from "@aithru/agent-runtime";
import { defineNode } from "@aithru/node-sdk";
import type {
  NodeDefinition,
  NodeExecutionContext,
  NodeRegistry,
  ToolExecutionRequest,
  ToolRiskLevel,
} from "@aithru/runtime-core";

export const AGENT_CLASSIFY_NODE_TYPE = "agent.classify";
export const AGENT_TASK_NODE_TYPE = "agent.task";
export const AGENT_DEEP_RESEARCH_NODE_TYPE = "agent.deepResearch";
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
  toolRiskPolicy?: AgentToolRiskPolicy;
  outputSchema?: unknown;
};

export type AgentTaskNodeOutput = {
  status: "completed" | "failed" | "needs_rerun" | "paused";
  summary: string;
  plan?: AgentPlan;
  artifacts: unknown[];
  review?: AgentReviewResult;
  approval?: AgentApprovalRequest;
  resumeState?: AgentResumeState;
  metadata?: Record<string, unknown>;
};

export type AgentDeepResearchNodeConfig = {
  goal: string;
  model?: string;
  maxSteps?: number;
  timeoutMs?: number;
  allowedTools?: string[];
  review?: boolean;
  toolRiskPolicy?: AgentToolRiskPolicy;
  maxSources?: number;
  maxSearchQueries?: number;
  outputSchema?: unknown;
};

export type AgentDeepResearchNodeOutput = AgentTaskNodeOutput;

export type AgentNodeModelResolveInput = {
  model?: string;
  nodeType: string;
  nodeId: string;
  workflowId: string;
  runId: string;
};

export type AgentNodeRuntimeBinding = {
  runtime?: AgentRuntime;
  resolveModel(input: AgentNodeModelResolveInput): AgentModelAdapter | Promise<AgentModelAdapter>;
};

export function isAgentNodeType(type: string) {
  return (
    type === AGENT_CLASSIFY_NODE_TYPE ||
    type === AGENT_TASK_NODE_TYPE ||
    type === AGENT_DEEP_RESEARCH_NODE_TYPE
  );
}

export function createAgentClassifyNode(
  binding: AgentNodeRuntimeBinding,
): NodeDefinition<unknown, AgentClassifyNodeOutput, AgentClassifyNodeConfig> {
  return defineNode<unknown, AgentClassifyNodeOutput, AgentClassifyNodeConfig>({
    type: AGENT_CLASSIFY_NODE_TYPE,
    version: AGENT_NODE_VERSION,
    category: "agent",
    displayName: "Agent Classify",
    description:
      "Classifies bounded workflow input by calling the Aithru Agent runtime.",
    configSchema: {
      kind: "inline",
      schema: {
        type: "object",
        required: ["goal", "routes"],
        additionalProperties: true,
        properties: {
          goal: { type: "string" },
          routes: { type: "array", items: { type: "string" } },
          model: { type: "string" },
          outputSchema: {},
          options: { type: "object" },
        },
      },
    },
    execute: async (ctx, input, config) => {
      const runtime = runtimeFor(binding);
      const model = await resolveModelForNode(binding, ctx, AGENT_CLASSIFY_NODE_TYPE, config.model);
      const task = createAgentTask(ctx, config.goal, input, config.outputSchema, {
        constraints:
          config.routes.length > 0
            ? [`Classify into one of these task-local routes: ${config.routes.join(", ")}.`]
            : [],
      });
      const output = await runtime.runTask("classify", {
        task,
        model,
        host: createAgentHostFromNodeContext(ctx),
        ...(config.options ? { options: config.options } : {}),
      });

      return {
        output: classificationFromTaskOutput(output),
        metadata: {
          agentTaskId: task.id,
          summary: output.summary,
        },
      };
    },
  });
}

export function createAgentTaskNode(
  binding: AgentNodeRuntimeBinding,
): NodeDefinition<unknown, AgentTaskNodeOutput, AgentTaskNodeConfig> {
  return defineNode<unknown, AgentTaskNodeOutput, AgentTaskNodeConfig>({
    type: AGENT_TASK_NODE_TYPE,
    version: AGENT_NODE_VERSION,
    category: "agent",
    displayName: "Agent Task",
    description:
      "Runs a bounded intelligent task by calling the Aithru Agent runtime.",
    configSchema: {
      kind: "inline",
      schema: {
        type: "object",
        required: ["goal"],
        additionalProperties: true,
        properties: {
          goal: { type: "string" },
          engine: { type: "string" },
          model: { type: "string" },
          maxSteps: { type: "number" },
          timeoutMs: { type: "number" },
          allowedTools: { type: "array", items: { type: "string" } },
          review: { type: "boolean" },
          toolRiskPolicy: { type: "object" },
          outputSchema: {},
        },
      },
    },
    execute: async (ctx, input, config) => {
      const runtime = runtimeFor(binding);
      const model = await resolveModelForNode(binding, ctx, AGENT_TASK_NODE_TYPE, config.model);
      const task = createAgentTask(ctx, config.goal, input, config.outputSchema);
      const options = taskOptionsFromConfig(config);
      const output = await runtime.runTask(config.engine ?? "plan-run-review", {
        task,
        model,
        host: createAgentHostFromNodeContext(ctx),
        ...(options ? { options } : {}),
      });

      return {
        output: agentTaskNodeOutputFromTaskOutput(output),
        metadata: {
          agentTaskId: task.id,
          summary: output.summary,
        },
      };
    },
  });
}

export function createAgentDeepResearchNode(
  binding: AgentNodeRuntimeBinding,
): NodeDefinition<unknown, AgentDeepResearchNodeOutput, AgentDeepResearchNodeConfig> {
  return defineNode<unknown, AgentDeepResearchNodeOutput, AgentDeepResearchNodeConfig>({
    type: AGENT_DEEP_RESEARCH_NODE_TYPE,
    version: AGENT_NODE_VERSION,
    category: "agent",
    displayName: "Agent Deep Research",
    description:
      "Runs bounded Deep Research V0 by calling the Aithru Agent runtime.",
    configSchema: {
      kind: "inline",
      schema: {
        type: "object",
        required: ["goal"],
        additionalProperties: true,
        properties: {
          goal: { type: "string" },
          model: { type: "string" },
          maxSteps: { type: "number" },
          timeoutMs: { type: "number" },
          allowedTools: { type: "array", items: { type: "string" } },
          review: { type: "boolean" },
          toolRiskPolicy: { type: "object" },
          maxSources: { type: "number" },
          maxSearchQueries: { type: "number" },
          outputSchema: {},
        },
      },
    },
    execute: async (ctx, input, config) => {
      const runtime = runtimeFor(binding);
      const model = await resolveModelForNode(
        binding,
        ctx,
        AGENT_DEEP_RESEARCH_NODE_TYPE,
        config.model,
      );
      const task = createAgentTask(ctx, config.goal, input, config.outputSchema);
      const options = researchOptionsFromConfig(config);
      const output = await runtime.runTask("deep-research", {
        task,
        model,
        host: createAgentHostFromNodeContext(ctx),
        ...(options ? { options } : {}),
      });
      const research = output.metadata?.research;

      return {
        output: agentTaskNodeOutputFromTaskOutput(output),
        metadata: {
          agentTaskId: task.id,
          summary: output.summary,
          ...(research !== undefined ? { research } : {}),
        },
      };
    },
  });
}

export function registerAgentNodes(
  registry: NodeRegistry,
  binding: AgentNodeRuntimeBinding,
): void {
  registry.register(createAgentClassifyNode(binding));
  registry.register(createAgentTaskNode(binding));
  registry.register(createAgentDeepResearchNode(binding));
}

export function createAgentHostFromNodeContext(ctx: NodeExecutionContext): AgentHost {
  return {
    async emit(event) {
      await emitAgentEvent(ctx, event);
    },

    async callTool(request) {
      if (!ctx.callTool) {
        throw new Error("Agent node requires NodeExecutionContext.callTool to execute tools.");
      }

      const result = await ctx.callTool(coreToolRequestFromAgentToolRequest(request));
      return agentToolResultFromCoreToolResult(request, result);
    },

    async createArtifact(draft) {
      const ref = await ctx.createArtifact(coreArtifactInputFromAgentDraft(draft));
      return agentArtifactFromCoreRef(draft, ref);
    },
  };
}

function runtimeFor(binding: AgentNodeRuntimeBinding): AgentRuntime {
  return binding.runtime ?? new AgentRuntime();
}

async function resolveModelForNode(
  binding: AgentNodeRuntimeBinding,
  ctx: NodeExecutionContext,
  nodeType: string,
  model: string | undefined,
): Promise<AgentModelAdapter> {
  return binding.resolveModel({
    ...(model !== undefined ? { model } : {}),
    nodeType,
    nodeId: ctx.nodeId,
    workflowId: ctx.workflowId,
    runId: ctx.runId,
  });
}

function createAgentTask(
  ctx: NodeExecutionContext,
  goal: string,
  input: unknown,
  outputSchema: unknown,
  options: { constraints?: string[] } = {},
): AgentTask {
  return {
    id: `${ctx.runId}:${ctx.nodeId}`,
    goal,
    input,
    ...(outputSchema !== undefined ? { outputSchema } : {}),
    ...(options.constraints && options.constraints.length > 0
      ? { constraints: options.constraints }
      : {}),
  };
}

function taskOptionsFromConfig(config: AgentTaskNodeConfig): AgentRunOptions | undefined {
  const options: AgentRunOptions = {
    ...(config.maxSteps !== undefined ? { maxSteps: config.maxSteps } : {}),
    ...(config.timeoutMs !== undefined ? { timeoutMs: config.timeoutMs } : {}),
    ...(config.allowedTools !== undefined ? { allowedTools: config.allowedTools } : {}),
    ...(config.review !== undefined ? { review: config.review } : {}),
    ...(config.toolRiskPolicy !== undefined
      ? { toolRiskPolicy: config.toolRiskPolicy }
      : {}),
  };

  return Object.keys(options).length > 0 ? options : undefined;
}

function researchOptionsFromConfig(
  config: AgentDeepResearchNodeConfig,
): AgentResearchOptions | undefined {
  const options: AgentResearchOptions = {
    ...(config.maxSteps !== undefined ? { maxSteps: config.maxSteps } : {}),
    ...(config.timeoutMs !== undefined ? { timeoutMs: config.timeoutMs } : {}),
    ...(config.allowedTools !== undefined ? { allowedTools: config.allowedTools } : {}),
    ...(config.review !== undefined ? { review: config.review } : {}),
    ...(config.toolRiskPolicy !== undefined
      ? { toolRiskPolicy: config.toolRiskPolicy }
      : {}),
    ...(config.maxSources !== undefined ? { maxSources: config.maxSources } : {}),
    ...(config.maxSearchQueries !== undefined
      ? { maxSearchQueries: config.maxSearchQueries }
      : {}),
  };

  return Object.keys(options).length > 0 ? options : undefined;
}

function classificationFromTaskOutput(output: AgentTaskOutput): AgentClassificationResult {
  const classification = output.metadata?.classification;

  if (isClassificationResult(classification)) {
    return classification;
  }

  throw new Error(
    "agent.classify output is missing metadata.classification with route and confidence.",
  );
}

function isClassificationResult(value: unknown): value is AgentClassificationResult {
  return (
    isRecord(value) &&
    typeof value.route === "string" &&
    typeof value.confidence === "number"
  );
}

function agentTaskNodeOutputFromTaskOutput(output: AgentTaskOutput): AgentTaskNodeOutput {
  return {
    status: output.status,
    summary: output.summary,
    artifacts: output.artifacts,
    ...(output.plan ? { plan: output.plan } : {}),
    ...(output.review ? { review: output.review } : {}),
    ...(output.approval ? { approval: output.approval } : {}),
    ...(output.resumeState ? { resumeState: output.resumeState } : {}),
    ...(output.metadata ? { metadata: output.metadata } : {}),
  };
}

async function emitAgentEvent(
  ctx: NodeExecutionContext,
  event: AgentEvent,
): Promise<void> {
  const trace = agentTraceEventFromAgentEvent(event);

  await ctx.emit({
    type: "log.info",
    runId: ctx.runId,
    workflowId: ctx.workflowId,
    nodeId: ctx.nodeId,
    payload: trace,
    metadata: {
      agentEventType: event.type,
      agentTraceKind: trace.kind,
      agentTracePhase: trace.phase,
    },
  });
}

function coreToolRequestFromAgentToolRequest(
  request: AgentToolRequest,
): ToolExecutionRequest {
  return {
    toolName: request.toolName,
    input: request.arguments,
    ...(request.riskLevel ? { riskLevel: coreRiskLevelFor(request.riskLevel) } : {}),
    metadata: {
      agentToolCallId: request.id,
      ...(request.reason ? { reason: request.reason } : {}),
      ...(request.stepId ? { stepId: request.stepId } : {}),
    },
  };
}

function coreRiskLevelFor(riskLevel: AgentToolRequest["riskLevel"]): ToolRiskLevel {
  switch (riskLevel) {
    case "safe":
    case "read":
      return "low";
    case "write":
      return "medium";
    case "dangerous":
      return "high";
    default:
      return "low";
  }
}

function agentToolResultFromCoreToolResult(
  request: AgentToolRequest,
  result: Awaited<ReturnType<NonNullable<NodeExecutionContext["callTool"]>>>,
): AgentToolResult {
  const metadata = {
    ...(result.metadata ?? {}),
    ...(result.artifacts ? { artifacts: result.artifacts } : {}),
  };

  return {
    id: request.id,
    toolName: request.toolName,
    output: result.output,
    ...(Object.keys(metadata).length > 0 ? { metadata } : {}),
  };
}

function coreArtifactInputFromAgentDraft(draft: AgentArtifactDraft) {
  const contentType = draft.mediaType ?? contentTypeForAgentArtifact(draft);

  return {
    ...(draft.name ? { name: draft.name } : {}),
    contentType,
    data: artifactDataFromContent(draft.content),
    metadata: {
      ...(draft.metadata ?? {}),
      agentArtifactType: draft.type,
      ...(draft.sourceStepId ? { sourceStepId: draft.sourceStepId } : {}),
    },
  };
}

function agentArtifactFromCoreRef(
  draft: AgentArtifactDraft,
  ref: Awaited<ReturnType<NodeExecutionContext["createArtifact"]>>,
): AgentArtifact {
  return {
    id: ref.id,
    type: draft.type,
    uri: ref.uri,
    ...(draft.name ? { name: draft.name } : {}),
    ...(draft.content !== undefined ? { content: draft.content } : {}),
    ...(ref.contentType ?? draft.mediaType
      ? { mediaType: ref.contentType ?? draft.mediaType }
      : {}),
    ...(draft.sourceStepId ? { sourceStepId: draft.sourceStepId } : {}),
    metadata: {
      ...(draft.metadata ?? {}),
      ...(ref.metadata ? { coreArtifactMetadata: ref.metadata } : {}),
    },
  };
}

function contentTypeForAgentArtifact(draft: AgentArtifactDraft): string {
  switch (draft.type) {
    case "json":
    case "decision":
      return "application/json";
    case "markdown":
      return "text/markdown";
    case "file":
      return "application/octet-stream";
    case "patch":
    case "report":
    case "text":
      return "text/plain";
  }
}

function artifactDataFromContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  return JSON.stringify(content ?? null);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
