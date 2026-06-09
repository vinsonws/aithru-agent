import type {
  AgentApprovalDecision,
  AgentApprovalRequest,
  AgentApprovalResponse,
  AgentArtifact,
  AgentArtifactDraft,
  AgentClassificationResult,
  AgentEngine,
  AgentEngineRunInput,
  AgentError,
  AgentEvent,
  AgentModelEvent,
  AgentModelInput,
  AgentPlan,
  AgentPlanStep,
  AgentResearchFinding,
  AgentResearchOptions,
  AgentResearchReport,
  AgentResearchSource,
  AgentResumeInput,
  AgentResumePhase,
  AgentResumeState,
  AgentReviewResult,
  AgentRiskLevel,
  AgentRunOptions,
  AgentTaskOutput,
  AgentToolPolicyDecision,
  AgentToolRequest,
  AgentToolResult,
} from "@aithru/agent-core";

function createId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function toAgentError(error: unknown, code = "runtime_error"): AgentError {
  if (isAgentError(error)) {
    return error;
  }

  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "Agent runtime error.";

  return {
    code,
    message,
    ...(error !== undefined ? { cause: error } : {}),
  };
}

function isAgentError(value: unknown): value is AgentError {
  return (
    isObject(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string"
  );
}

function validateToolAllowed(
  input: AgentEngineRunInput,
  step: AgentPlanStep | undefined,
  toolName: string,
): AgentError | undefined {
  const globalAllowed = input.options?.allowedTools;
  const stepAllowed = step?.allowedTools;

  if (globalAllowed === undefined && stepAllowed === undefined) {
    return undefined;
  }

  if (globalAllowed !== undefined && !globalAllowed.includes(toolName)) {
    return {
      code: "tool_not_allowed",
      message: `Tool "${toolName}" is not allowed for this agent run or step.`,
      metadata: {
        toolName,
        allowedTools: globalAllowed,
        ...(stepAllowed !== undefined ? { stepAllowedTools: stepAllowed } : {}),
        ...(step?.id !== undefined ? { stepId: step.id } : {}),
      },
    };
  }

  if (stepAllowed !== undefined && !stepAllowed.includes(toolName)) {
    return {
      code: "tool_not_allowed",
      message: `Tool "${toolName}" is not allowed for this agent run or step.`,
      metadata: {
        toolName,
        ...(globalAllowed !== undefined ? { allowedTools: globalAllowed } : {}),
        stepAllowedTools: stepAllowed,
        ...(step?.id !== undefined ? { stepId: step.id } : {}),
      },
    };
  }

  return undefined;
}

function filterAllowedTools(
  tools: AgentModelInput["tools"],
  globalAllowed: string[] | undefined,
  stepAllowed: string[] | undefined,
): AgentModelInput["tools"] {
  if (!tools) return undefined;
  if (globalAllowed === undefined && stepAllowed === undefined) return tools;

  return tools.filter((tool) => {
    if (globalAllowed !== undefined && !globalAllowed.includes(tool.name))
      return false;
    if (stepAllowed !== undefined && !stepAllowed.includes(tool.name))
      return false;
    return true;
  });
}

function effectiveRiskLevel(request: AgentToolRequest): AgentRiskLevel {
  return request.riskLevel ?? "safe";
}

function resolveRiskDecision(
  policy: NonNullable<AgentRunOptions["toolRiskPolicy"]>,
  toolName: string,
  riskLevel: AgentRiskLevel,
): AgentToolPolicyDecision {
  if (policy.byToolName?.[toolName] !== undefined) {
    return policy.byToolName[toolName];
  }
  if (policy.byRiskLevel?.[riskLevel] !== undefined) {
    return policy.byRiskLevel[riskLevel]!;
  }
  if (policy.defaultDecision !== undefined) {
    return policy.defaultDecision;
  }
  return "allow";
}

type ToolRiskEvaluation =
  | { decision: "allow" }
  | { decision: "deny"; error: AgentError }
  | { decision: "require_approval"; approval: AgentApprovalRequest };

function evaluateToolRiskPolicy(
  input: AgentEngineRunInput,
  request: AgentToolRequest,
): ToolRiskEvaluation {
  const policy = input.options?.toolRiskPolicy;
  if (!policy) return { decision: "allow" };

  const riskLevel = effectiveRiskLevel(request);
  const decision = resolveRiskDecision(policy, request.toolName, riskLevel);

  if (decision === "allow") return { decision: "allow" };

  if (decision === "deny") {
    return {
      decision: "deny",
      error: {
        code: "tool_risk_denied",
        message: `Tool "${request.toolName}" with risk level "${riskLevel}" was denied by runtime policy.`,
        metadata: {
          toolName: request.toolName,
          riskLevel,
          decision: "deny" satisfies AgentToolPolicyDecision,
        },
      },
    };
  }

  return {
    decision: "require_approval",
    approval: {
      id: createId("approval"),
      taskId: input.task.id,
      ...(request.stepId !== undefined ? { stepId: request.stepId } : {}),
      toolRequest: request,
      ...(request.reason !== undefined ? { reason: request.reason } : {}),
      riskLevel,
      metadata: {
        decision: "require_approval" satisfies AgentToolPolicyDecision,
      },
    },
  };
}

async function* emitApprovalEvents(
  input: AgentEngineRunInput,
  approval: AgentApprovalRequest,
  resumeState: AgentResumeState,
  plan: AgentPlan | undefined,
  artifacts: AgentArtifact[],
): AsyncGenerator<AgentEvent> {
  yield emitEvent(input, {
    type: "agent.tool.approval_requested",
    taskId: input.task.id,
    ...(approval.stepId !== undefined ? { stepId: approval.stepId } : {}),
    approval,
  });

  const output: AgentTaskOutput = {
    status: "paused",
    summary: `Approval required for tool "${approval.toolRequest.toolName}".`,
    ...(plan ? { plan } : {}),
    artifacts,
    approval,
    resumeState,
    metadata: {
      approval,
      resumeState,
    },
  };

  yield emitEvent(input, {
    type: "agent.task.paused",
    taskId: input.task.id,
    approval,
    output,
  });
}

async function emitEvent(
  input: AgentEngineRunInput,
  event: AgentEvent,
): Promise<AgentEvent> {
  await input.host.emit(event);
  return event;
}

async function emitTaskFailed(
  input: AgentEngineRunInput,
  error: AgentError,
): Promise<AgentEvent> {
  return emitEvent(input, {
    type: "agent.task.failed",
    taskId: input.task.id,
    error,
  });
}

type CollectedModelEvents = {
  events: AgentModelEvent[];
  error?: AgentError;
};

async function collectModelEvents(
  input: AgentEngineRunInput,
  mode: AgentModelInput["mode"],
  step?: AgentPlanStep,
  plan?: AgentPlan,
): Promise<CollectedModelEvents> {
  let tools;
  try {
    tools = input.host.listTools ? await input.host.listTools() : undefined;
  } catch (error) {
    return {
      events: [],
      error: toAgentError(error),
    };
  }

  tools = filterAllowedTools(
    tools,
    input.options?.allowedTools,
    step?.allowedTools,
  );

  const modelInput: AgentModelInput = {
    task: input.task,
    mode,
    ...(step ? { step } : {}),
    ...(plan ? { plan } : {}),
    ...(input.task.outputSchema !== undefined
      ? { outputSchema: input.task.outputSchema }
      : {}),
    ...(tools ? { tools } : {}),
  };
  const events: AgentModelEvent[] = [];

  try {
    for await (const event of input.model.generate(modelInput)) {
      events.push(event);

      if (event.type === "error") {
        return {
          events,
          error: toAgentError(event.error, "model_error"),
        };
      }
    }
  } catch (error) {
    return {
      events,
      error: toAgentError(error, "model_exception"),
    };
  }

  return { events };
}

function firstStructuredOutput(events: AgentModelEvent[]) {
  return events.find((event) => event.type === "structured.output")?.value;
}

function firstFinalOutput(events: AgentModelEvent[]) {
  return events.find((event) => event.type === "final")?.output;
}

function normalizePlan(taskId: string, value: unknown): AgentPlan {
  if (isPlan(value)) {
    return value;
  }

  if (isObject(value) && Array.isArray(value.steps)) {
    return {
      id: typeof value.id === "string" ? value.id : createId("plan"),
      taskId,
      steps: value.steps.map((step, index) => normalizePlanStep(step, index)),
    };
  }

  return {
    id: createId("plan"),
    taskId,
    steps: [
      {
        id: "step_1",
        title: "Execute task",
        objective: "Complete the task with the available context.",
      },
    ],
  };
}

function normalizePlanStep(value: unknown, index: number): AgentPlanStep {
  if (!isObject(value)) {
    return {
      id: `step_${index + 1}`,
      title: `Step ${index + 1}`,
      objective: String(value),
    };
  }

  return {
    id: typeof value.id === "string" ? value.id : `step_${index + 1}`,
    title: typeof value.title === "string" ? value.title : `Step ${index + 1}`,
    objective:
      typeof value.objective === "string"
        ? value.objective
        : typeof value.expectedOutput === "string"
          ? value.expectedOutput
          : "Complete this step.",
    ...(Array.isArray(value.allowedTools)
      ? {
          allowedTools: value.allowedTools.filter(
            (tool): tool is string => typeof tool === "string",
          ),
        }
      : {}),
    ...(typeof value.expectedOutput === "string"
      ? { expectedOutput: value.expectedOutput }
      : {}),
  };
}

function isPlan(value: unknown): value is AgentPlan {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.taskId === "string" &&
    Array.isArray(value.steps)
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function normalizeClassification(value: unknown): AgentClassificationResult {
  if (isObject(value)) {
    return {
      route: typeof value.route === "string" ? value.route : "default",
      confidence: typeof value.confidence === "number" ? value.confidence : 0,
      ...(typeof value.reason === "string" ? { reason: value.reason } : {}),
      ...(isObject(value.metadata) ? { metadata: value.metadata } : {}),
    };
  }

  return { route: String(value ?? "default"), confidence: 0 };
}

async function createArtifact(
  input: AgentEngineRunInput,
  draft: AgentArtifactDraft,
): Promise<AgentArtifact> {
  if (input.host.createArtifact) {
    return input.host.createArtifact(draft);
  }

  return {
    id: createId("artifact"),
    ...draft,
  };
}

const ENGINE_NAMES = {
  classify: "classify",
  planRunReview: "plan-run-review",
  deepResearch: "deep-research",
} as const;

function validateResumeInput(
  input: AgentResumeInput,
  expectedEngineName: string,
): AgentError | undefined {
  const { resumeState, approvalResponse } = input;

  if (resumeState.engineName !== expectedEngineName) {
    return {
      code: "invalid_resume_state",
      message: `Resume state engine "${resumeState.engineName}" does not match "${expectedEngineName}".`,
      metadata: { expectedEngineName, actualEngineName: resumeState.engineName },
    };
  }

  if (resumeState.taskId !== input.task.id) {
    return {
      code: "invalid_resume_state",
      message: "Resume state taskId does not match current task.",
      metadata: { expectedTaskId: input.task.id, actualTaskId: resumeState.taskId },
    };
  }

  if (resumeState.approval.id !== approvalResponse.approvalId) {
    return {
      code: "invalid_resume_state",
      message: "Approval response ID does not match resume state.",
      metadata: {
        expectedApprovalId: resumeState.approval.id,
        actualApprovalId: approvalResponse.approvalId,
      },
    };
  }

  if (
    approvalResponse.decision !== "approved" &&
    approvalResponse.decision !== "rejected"
  ) {
    return {
      code: "invalid_resume_state",
      message: `Unknown approval decision: "${approvalResponse.decision}".`,
      metadata: { decision: approvalResponse.decision },
    };
  }

  return undefined;
}

function validateResumeStep(
  resumeState: AgentResumeState,
): AgentError | undefined {
  if (resumeState.currentStep === undefined) {
    return {
      code: "invalid_resume_state",
      message: "Resume state is missing currentStep.",
      metadata: { phase: resumeState.phase },
    };
  }

  if (resumeState.currentStepIndex === undefined) {
    return {
      code: "invalid_resume_state",
      message: "Resume state is missing currentStepIndex.",
      metadata: { phase: resumeState.phase },
    };
  }

  return undefined;
}

function evaluateToolRiskPolicyForResume(
  input: AgentResumeInput,
  request: AgentToolRequest,
): AgentError | undefined {
  const policy = input.options?.toolRiskPolicy;
  if (!policy) return undefined;

  const riskLevel = effectiveRiskLevel(request);
  const decision = resolveRiskDecision(policy, request.toolName, riskLevel);

  if (decision === "deny") {
    return {
      code: "tool_risk_denied",
      message: `Tool "${request.toolName}" with risk level "${riskLevel}" was denied by runtime policy.`,
      metadata: { toolName: request.toolName, riskLevel, decision: "deny" },
    };
  }

  return undefined;
}

type ResumePreambleContext = {
  approval: AgentApprovalRequest;
  step: AgentPlanStep | undefined;
  resumeState: AgentResumeState;
  plan: AgentPlan;
  toolResult: AgentToolResult;
};

async function* resumeEnginePreamble(
  input: AgentResumeInput,
  expectedEngineName: string,
  phaseConfig?: { requiresStep?: boolean },
): AsyncGenerator<AgentEvent, ResumePreambleContext | undefined> {
  const { resumeState, approvalResponse } = input;

  const validationError = validateResumeInput(input, expectedEngineName);
  if (validationError) {
    yield await emitTaskFailed(input, validationError);
    return undefined;
  }

  const approval = resumeState.approval;
  const plan = resumeState.plan;
  const step = resumeState.currentStep;

  if (!plan) {
    yield await emitTaskFailed(input, {
      code: "invalid_resume_state",
      message: "Resume state is missing plan.",
    });
    return undefined;
  }

  // Validate phase-specific requirements before executing the tool
  if (phaseConfig?.requiresStep) {
    const stepError = validateResumeStep(resumeState);
    if (stepError) {
      yield await emitTaskFailed(input, stepError);
      return undefined;
    }
  }

  yield emitEvent(input, {
    type: "agent.tool.approval_resolved",
    taskId: input.task.id,
    ...(approval.stepId !== undefined ? { stepId: approval.stepId } : {}),
    approval,
    response: approvalResponse,
  });

  if (approvalResponse.decision === "rejected") {
    yield await emitTaskFailed(input, {
      code: "tool_approval_rejected",
      message: `Approval was rejected for tool "${approval.toolRequest.toolName}".`,
      metadata: {
        approvalId: approval.id,
        toolName: approval.toolRequest.toolName,
        ...(approvalResponse.reason !== undefined
          ? { reason: approvalResponse.reason }
          : {}),
      },
    });
    return undefined;
  }

  yield emitEvent(input, {
    type: "agent.task.resumed",
    taskId: input.task.id,
    approval,
    response: approvalResponse,
    resumeState,
  });

  const notAllowedError = validateToolAllowed(
    input,
    step,
    approval.toolRequest.toolName,
  );
  if (notAllowedError) {
    yield await emitTaskFailed(input, notAllowedError);
    return undefined;
  }

  const riskError = evaluateToolRiskPolicyForResume(
    input,
    approval.toolRequest,
  );
  if (riskError) {
    yield await emitTaskFailed(input, riskError);
    return undefined;
  }

  let toolResult: AgentToolResult;
  try {
    toolResult = await input.host.callTool(approval.toolRequest);
  } catch (error) {
    yield await emitTaskFailed(
      input,
      toAgentError(error, "tool_exception"),
    );
    return undefined;
  }

  yield emitEvent(input, {
    type: "agent.tool.completed",
    taskId: input.task.id,
    ...(step ? { stepId: step.id } : {}),
    result: toolResult,
  });

  if (toolResult.error) {
    yield await emitTaskFailed(
      input,
      toAgentError(toolResult.error, "tool_error"),
    );
    return undefined;
  }

  return { approval, step, resumeState, plan, toolResult };
}

function extractResearchCollection(
  resumeState: AgentResumeState,
): ResearchCollection {
  const raw = resumeState.metadata?.researchCollection;
  if (
    raw &&
    typeof raw === "object" &&
    Array.isArray((raw as Record<string, unknown>).sources) &&
    Array.isArray((raw as Record<string, unknown>).findings) &&
    Array.isArray((raw as Record<string, unknown>).notes)
  ) {
    return raw as ResearchCollection;
  }
  return createResearchCollection();
}

type ProcessToolCallContext = {
  input: AgentEngineRunInput;
  step: AgentPlanStep | undefined;
  request: AgentToolRequest;
  plan: AgentPlan | undefined;
  artifacts: AgentArtifact[];
  stepIndex: number | undefined;
  stepEvents: AgentModelEvent[];
  eventIndex: number;
  engineName: string;
  phase: AgentResumePhase;
  extraResumeMetadata?: Record<string, unknown>;
};

type ProcessToolCallResult =
  | { kind: "completed"; result: AgentToolResult }
  | { kind: "paused" }
  | { kind: "failed" };

async function* processToolCallEvent(
  ctx: ProcessToolCallContext,
): AsyncGenerator<AgentEvent, ProcessToolCallResult> {
  const { input, step, request, plan } = ctx;

  yield await emitEvent(input, {
    type: "agent.tool.proposed",
    taskId: input.task.id,
    ...(step ? { stepId: step.id } : {}),
    request,
  });

  const notAllowedError = validateToolAllowed(input, step, request.toolName);
  if (notAllowedError) {
    yield await emitTaskFailed(input, notAllowedError);
    return { kind: "failed" };
  }

  const riskEval = evaluateToolRiskPolicy(input, request);
  if (riskEval.decision === "deny") {
    yield await emitTaskFailed(input, riskEval.error);
    return { kind: "failed" };
  }

  if (riskEval.decision === "require_approval") {
    const resumeState: AgentResumeState = {
      id: createId("resume"),
      engineName: ctx.engineName,
      taskId: input.task.id,
      phase: ctx.phase,
      approval: riskEval.approval,
      ...(plan ? { plan } : {}),
      artifacts: [...ctx.artifacts],
      ...(step ? { currentStep: step } : {}),
      ...(ctx.stepIndex !== undefined
        ? { currentStepIndex: ctx.stepIndex }
        : {}),
      pendingModelEvents: ctx.stepEvents.slice(ctx.eventIndex + 1),
      ...(ctx.extraResumeMetadata
        ? { metadata: ctx.extraResumeMetadata }
        : {}),
    };

    yield* emitApprovalEvents(
      input,
      riskEval.approval,
      resumeState,
      plan,
      ctx.artifacts,
    );
    return { kind: "paused" };
  }

  let result: AgentToolResult;
  try {
    result = await input.host.callTool(request);
  } catch (error) {
    yield await emitTaskFailed(input, toAgentError(error, "tool_exception"));
    return { kind: "failed" };
  }

  yield emitEvent(input, {
    type: "agent.tool.completed",
    taskId: input.task.id,
    ...(step ? { stepId: step.id } : {}),
    result,
  });

  if (result.error) {
    yield await emitTaskFailed(input, toAgentError(result.error, "tool_error"));
    return { kind: "failed" };
  }

  return { kind: "completed", result };
}

export class ClassifyEngine implements AgentEngine {
  readonly name = "classify";

  async *run(input: AgentEngineRunInput): AsyncIterable<AgentEvent> {
    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    const modelResult = await collectModelEvents(input, "classify");
    if (modelResult.error) {
      yield await emitTaskFailed(input, modelResult.error);
      return;
    }

    const events = modelResult.events;
    for (const event of events) {
      if (event.type === "text.delta") {
        const agentEvent: AgentEvent = {
          type: "agent.model.delta",
          taskId: input.task.id,
          text: event.text,
        };
        yield await emitEvent(input, agentEvent);
      }
    }

    const classification = normalizeClassification(
      firstStructuredOutput(events) ?? firstFinalOutput(events),
    );
    let artifact: AgentArtifact;
    try {
      artifact = await createArtifact(input, {
        type: "decision",
        name: "classification",
        content: classification,
      });
    } catch (error) {
      yield await emitTaskFailed(
        input,
        toAgentError(error, "artifact_exception"),
      );
      return;
    }

    const artifactEvent: AgentEvent = {
      type: "agent.artifact.created",
      taskId: input.task.id,
      artifact,
    };
    yield await emitEvent(input, artifactEvent);

    const output: AgentTaskOutput = {
      status: "completed",
      summary: classification.reason ?? `Route: ${classification.route}`,
      artifacts: [artifact],
      metadata: { classification },
    };

    const completedEvent: AgentEvent = {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    };
    yield await emitEvent(input, completedEvent);
  }
}

export class PlanRunReviewEngine implements AgentEngine {
  readonly name = "plan-run-review";

  async *run(input: AgentEngineRunInput): AsyncIterable<AgentEvent> {
    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    const planStarted: AgentEvent = {
      type: "agent.plan.started",
      taskId: input.task.id,
    };
    yield await emitEvent(input, planStarted);

    const planResult = await collectModelEvents(input, "plan");
    if (planResult.error) {
      yield await emitTaskFailed(input, planResult.error);
      return;
    }

    const planEvents = planResult.events;
    const plan = normalizePlan(
      input.task.id,
      firstStructuredOutput(planEvents) ?? firstFinalOutput(planEvents),
    );

    const planCompleted: AgentEvent = {
      type: "agent.plan.completed",
      taskId: input.task.id,
      plan,
    };
    yield await emitEvent(input, planCompleted);

    const artifacts: AgentArtifact[] = [];
    const boundedSteps = plan.steps.slice(
      0,
      input.options?.maxSteps ?? plan.steps.length,
    );

    for (let stepIndex = 0; stepIndex < boundedSteps.length; stepIndex += 1) {
      const step = boundedSteps[stepIndex]!;
      const stepStarted: AgentEvent = {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: step.id,
        step,
      };
      yield await emitEvent(input, stepStarted);

      const stepResult = await collectModelEvents(input, "execute", step);
      if (stepResult.error) {
        yield await emitTaskFailed(input, stepResult.error);
        return;
      }

      const stepEvents = stepResult.events;
      for (
        let eventIndex = 0;
        eventIndex < stepEvents.length;
        eventIndex += 1
      ) {
        const event = stepEvents[eventIndex]!;
        if (event.type === "text.delta") {
          const deltaEvent: AgentEvent = {
            type: "agent.model.delta",
            taskId: input.task.id,
            stepId: step.id,
            text: event.text,
          };
          yield await emitEvent(input, deltaEvent);
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: step.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step,
            request,
            plan,
            artifacts,
            stepIndex,
            stepEvents,
            eventIndex,
            engineName: ENGINE_NAMES.planRunReview,
            phase: "plan-run-review.step",
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
        }
      }

      const stepOutput =
        firstFinalOutput(stepEvents) ?? firstStructuredOutput(stepEvents);
      if (stepOutput !== undefined) {
        let artifact: AgentArtifact;
        try {
          artifact = await createArtifact(input, {
            type: "json",
            name: `${step.id}-output`,
            content: stepOutput,
            sourceStepId: step.id,
          });
        } catch (error) {
          yield await emitTaskFailed(
            input,
            toAgentError(error, "artifact_exception"),
          );
          return;
        }

        artifacts.push(artifact);
        const artifactEvent: AgentEvent = {
          type: "agent.artifact.created",
          taskId: input.task.id,
          artifact,
        };
        yield await emitEvent(input, artifactEvent);
      }
    }

    let review: AgentReviewResult | undefined;
    if (input.options?.review ?? true) {
      const reviewStarted: AgentEvent = {
        type: "agent.review.started",
        taskId: input.task.id,
      };
      yield await emitEvent(input, reviewStarted);

      const reviewResult = await collectModelEvents(input, "review");
      if (reviewResult.error) {
        yield await emitTaskFailed(input, reviewResult.error);
        return;
      }

      const reviewEvents = reviewResult.events;
      review = normalizeReview(
        firstStructuredOutput(reviewEvents) ?? firstFinalOutput(reviewEvents),
      );
      const reviewCompleted: AgentEvent = {
        type: "agent.review.completed",
        taskId: input.task.id,
        review,
      };
      yield await emitEvent(input, reviewCompleted);
    }

    const output: AgentTaskOutput = {
      status:
        review?.status === "needs_rerun"
          ? "needs_rerun"
          : review?.status === "failed"
            ? "failed"
            : "completed",
      summary: review?.summary ?? "Agent task completed.",
      plan,
      artifacts,
      ...(review ? { review } : {}),
    };

    const completedEvent: AgentEvent = {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    };
    yield await emitEvent(input, completedEvent);
  }

  async *resume(
    input: AgentResumeInput,
  ): AsyncIterable<AgentEvent> {
    const preamble = yield* resumeEnginePreamble(
      input,
      ENGINE_NAMES.planRunReview,
      { requiresStep: true },
    );
    if (!preamble) return;

    const { resumeState, step, plan, toolResult } = preamble;

    const stepDefined = step!;
    const stepIndex = resumeState.currentStepIndex!;

    const artifacts: AgentArtifact[] = [...resumeState.artifacts];
    const boundedSteps = plan.steps.slice(
      0,
      input.options?.maxSteps ?? plan.steps.length,
    );

    for (
      let eventIndex = 0;
      eventIndex < resumeState.pendingModelEvents.length;
      eventIndex += 1
    ) {
      const event = resumeState.pendingModelEvents[eventIndex]!;
      if (event.type === "text.delta") {
        yield emitEvent(input, {
          type: "agent.model.delta",
          taskId: input.task.id,
          stepId: stepDefined.id,
          text: event.text,
        });
      }

      if (event.type === "tool_call.proposed") {
        const request: AgentToolRequest = {
          ...event.toolCall,
          stepId: stepDefined.id,
        };
        const result = yield* processToolCallEvent({
          input,
          step: stepDefined,
          request,
          plan,
          artifacts,
          stepIndex,
          stepEvents: resumeState.pendingModelEvents,
          eventIndex,
          engineName: ENGINE_NAMES.planRunReview,
          phase: "plan-run-review.step",
        });
        if (result.kind === "failed") return;
        if (result.kind === "paused") return;
      }
    }

    const pendingOutput =
      firstFinalOutput(resumeState.pendingModelEvents) ??
      firstStructuredOutput(resumeState.pendingModelEvents);
    if (pendingOutput !== undefined) {
      try {
        const artifact = await createArtifact(input, {
          type: "json",
          name: `${stepDefined.id}-output`,
          content: pendingOutput,
          sourceStepId: stepDefined.id,
        });
        artifacts.push(artifact);
        yield emitEvent(input, {
          type: "agent.artifact.created",
          taskId: input.task.id,
          artifact,
        });
      } catch (error) {
        yield await emitTaskFailed(
          input,
          toAgentError(error, "artifact_exception"),
        );
        return;
      }
    }

    for (
      let remainingIndex = stepIndex + 1;
      remainingIndex < boundedSteps.length;
      remainingIndex += 1
    ) {
      const currentStep = boundedSteps[remainingIndex]!;
      yield emitEvent(input, {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: currentStep.id,
        step: currentStep,
      });

      const stepResult = await collectModelEvents(
        input,
        "execute",
        currentStep,
      );
      if (stepResult.error) {
        yield await emitTaskFailed(input, stepResult.error);
        return;
      }

      for (
        let eventIndex = 0;
        eventIndex < stepResult.events.length;
        eventIndex += 1
      ) {
        const event = stepResult.events[eventIndex]!;
        if (event.type === "text.delta") {
          yield emitEvent(input, {
            type: "agent.model.delta",
            taskId: input.task.id,
            stepId: currentStep.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: currentStep.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step: currentStep,
            request,
            plan,
            artifacts,
            stepIndex: remainingIndex,
            stepEvents: stepResult.events,
            eventIndex,
            engineName: ENGINE_NAMES.planRunReview,
            phase: "plan-run-review.step",
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
        }
      }

      const stepOutput =
        firstFinalOutput(stepResult.events) ??
        firstStructuredOutput(stepResult.events);
      if (stepOutput !== undefined) {
        try {
          const artifact = await createArtifact(input, {
            type: "json",
            name: `${currentStep.id}-output`,
            content: stepOutput,
            sourceStepId: currentStep.id,
          });
          artifacts.push(artifact);
          yield emitEvent(input, {
            type: "agent.artifact.created",
            taskId: input.task.id,
            artifact,
          });
        } catch (error) {
          yield await emitTaskFailed(
            input,
            toAgentError(error, "artifact_exception"),
          );
          return;
        }
      }
    }

    let review: AgentReviewResult | undefined;
    if (input.options?.review ?? true) {
      yield emitEvent(input, {
        type: "agent.review.started",
        taskId: input.task.id,
      });

      const reviewResult = await collectModelEvents(input, "review");
      if (reviewResult.error) {
        yield await emitTaskFailed(input, reviewResult.error);
        return;
      }

      const reviewEvents = reviewResult.events;
      review = normalizeReview(
        firstStructuredOutput(reviewEvents) ??
          firstFinalOutput(reviewEvents),
      );
      yield emitEvent(input, {
        type: "agent.review.completed",
        taskId: input.task.id,
        review,
      });
    }

    const output: AgentTaskOutput = {
      status:
        review?.status === "needs_rerun"
          ? "needs_rerun"
          : review?.status === "failed"
            ? "failed"
            : "completed",
      summary: review?.summary ?? "Agent task completed.",
      plan,
      artifacts,
      ...(review ? { review } : {}),
    };

    yield emitEvent(input, {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    });
  }
}

type ResearchCollection = {
  sources: AgentResearchSource[];
  findings: AgentResearchFinding[];
  notes: string[];
};

function createResearchCollection(): ResearchCollection {
  return {
    sources: [],
    findings: [],
    notes: [],
  };
}

function boundedCount(value: number | undefined, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }

  return Math.max(0, Math.floor(value));
}

function collectResearchOutput(
  collection: ResearchCollection,
  value: unknown,
): void {
  if (value === undefined) {
    return;
  }

  if (typeof value === "string") {
    collection.notes.push(value);
    return;
  }

  if (!isObject(value)) {
    return;
  }

  if (isResearchSourceLike(value)) {
    addResearchSource(collection, value);
  }

  if (isResearchFindingLike(value)) {
    addResearchFinding(collection, value);
  }

  if (Array.isArray(value.sources)) {
    for (const source of value.sources) {
      addResearchSource(collection, source);
    }
  }

  if (isObject(value.source)) {
    addResearchSource(collection, value.source);
  }

  if (Array.isArray(value.findings)) {
    for (const finding of value.findings) {
      addResearchFinding(collection, finding);
    }
  }

  if (isObject(value.finding)) {
    addResearchFinding(collection, value.finding);
  }

  if (typeof value.summary === "string") {
    collection.notes.push(value.summary);
  }
}

function addResearchSource(
  collection: ResearchCollection,
  value: unknown,
): void {
  const source = normalizeResearchSource(value, collection.sources.length);
  if (!collection.sources.some((existing) => existing.id === source.id)) {
    collection.sources.push(source);
  }
}

function addResearchFinding(
  collection: ResearchCollection,
  value: unknown,
): void {
  const finding = normalizeResearchFinding(value, collection.findings.length);
  if (!collection.findings.some((existing) => existing.id === finding.id)) {
    collection.findings.push(finding);
  }
}

function isResearchSourceLike(value: Record<string, unknown>): boolean {
  return (
    typeof value.id === "string" ||
    typeof value.uri === "string" ||
    Object.prototype.hasOwnProperty.call(value, "content")
  );
}

function isResearchFindingLike(value: Record<string, unknown>): boolean {
  return typeof value.claim === "string";
}

function normalizeResearchSource(
  value: unknown,
  index: number,
): AgentResearchSource {
  if (isObject(value)) {
    return {
      id: typeof value.id === "string" ? value.id : `source_${index + 1}`,
      ...(typeof value.title === "string" ? { title: value.title } : {}),
      ...(typeof value.uri === "string" ? { uri: value.uri } : {}),
      ...(Object.prototype.hasOwnProperty.call(value, "content")
        ? { content: value.content }
        : {}),
      ...(isObject(value.metadata) ? { metadata: value.metadata } : {}),
    };
  }

  return {
    id: `source_${index + 1}`,
    content: value,
  };
}

function normalizeResearchFinding(
  value: unknown,
  index: number,
): AgentResearchFinding {
  if (isObject(value)) {
    return {
      id: typeof value.id === "string" ? value.id : `finding_${index + 1}`,
      claim:
        typeof value.claim === "string"
          ? value.claim
          : typeof value.summary === "string"
            ? value.summary
            : "Research finding.",
      ...(Array.isArray(value.sourceIds)
        ? {
            sourceIds: value.sourceIds.filter(
              (sourceId): sourceId is string => typeof sourceId === "string",
            ),
          }
        : {}),
      ...(typeof value.confidence === "number"
        ? { confidence: value.confidence }
        : {}),
      ...(isObject(value.metadata) ? { metadata: value.metadata } : {}),
    };
  }

  return {
    id: `finding_${index + 1}`,
    claim: String(value ?? "Research finding."),
  };
}

function normalizeResearchReport(
  taskGoal: string,
  value: unknown,
  collection: ResearchCollection,
  options: AgentResearchOptions | undefined,
): AgentResearchReport {
  const reportValue = isObject(value) ? value : undefined;
  const sources =
    reportValue && Array.isArray(reportValue.sources)
      ? reportValue.sources.map((source, index) =>
          normalizeResearchSource(source, index),
        )
      : collection.sources;
  const findings =
    reportValue && Array.isArray(reportValue.findings)
      ? reportValue.findings.map((finding, index) =>
          normalizeResearchFinding(finding, index),
        )
      : collection.findings;
  const boundedSources = limitResearchSources(sources, options?.maxSources);
  const boundedFindings = alignFindingSourceIds(findings, boundedSources);
  const summary =
    reportValue && typeof reportValue.summary === "string"
      ? reportValue.summary
      : typeof value === "string"
        ? value
        : (collection.notes.at(-1) ?? "Research completed.");

  return {
    title:
      reportValue && typeof reportValue.title === "string"
        ? reportValue.title
        : taskGoal,
    summary,
    findings: boundedFindings,
    sources: boundedSources,
    ...(reportValue && Array.isArray(reportValue.limitations)
      ? {
          limitations: reportValue.limitations.filter(
            (limitation): limitation is string =>
              typeof limitation === "string",
          ),
        }
      : {}),
    ...(reportValue && isObject(reportValue.metadata)
      ? { metadata: reportValue.metadata }
      : {}),
  };
}

function limitResearchSources(
  sources: AgentResearchSource[],
  maxSources: number | undefined,
): AgentResearchSource[] {
  if (typeof maxSources !== "number" || !Number.isFinite(maxSources)) {
    return sources;
  }

  return sources.slice(0, Math.max(0, Math.floor(maxSources)));
}

function alignFindingSourceIds(
  findings: AgentResearchFinding[],
  sources: AgentResearchSource[],
): AgentResearchFinding[] {
  const sourceIds = new Set(sources.map((source) => source.id));

  return findings.map((finding) => {
    if (!finding.sourceIds) {
      return finding;
    }

    return {
      ...finding,
      sourceIds: finding.sourceIds.filter((sourceId) =>
        sourceIds.has(sourceId),
      ),
    };
  });
}

function researchTimeoutError(timeoutMs: number): AgentError {
  return {
    code: "research_timeout",
    message: `Deep Research exceeded timeoutMs (${timeoutMs}).`,
  };
}

export class DeepResearchEngine implements AgentEngine<AgentResearchOptions> {
  readonly name = "deep-research";

  async *run(
    input: AgentEngineRunInput<AgentResearchOptions>,
  ): AsyncIterable<AgentEvent> {
    const options = input.options as AgentResearchOptions | undefined;
    const timeoutMs =
      typeof options?.timeoutMs === "number" &&
      Number.isFinite(options.timeoutMs)
        ? Math.max(0, options.timeoutMs)
        : undefined;
    const deadlineAt =
      timeoutMs === undefined ? undefined : Date.now() + timeoutMs;
    const timedOut = () => deadlineAt !== undefined && Date.now() > deadlineAt;

    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const planStarted: AgentEvent = {
      type: "agent.plan.started",
      taskId: input.task.id,
    };
    yield await emitEvent(input, planStarted);

    const planResult = await collectModelEvents(input, "plan");
    if (planResult.error) {
      yield await emitTaskFailed(input, planResult.error);
      return;
    }

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const plan = normalizePlan(
      input.task.id,
      firstStructuredOutput(planResult.events) ??
        firstFinalOutput(planResult.events),
    );
    const planCompleted: AgentEvent = {
      type: "agent.plan.completed",
      taskId: input.task.id,
      plan,
    };
    yield await emitEvent(input, planCompleted);

    const collection = createResearchCollection();
    const maxSteps = boundedCount(options?.maxSteps, plan.steps.length);
    const boundedSteps = plan.steps.slice(0, maxSteps);

    for (
      let stepIndex = 0;
      stepIndex < boundedSteps.length;
      stepIndex += 1
    ) {
      const step = boundedSteps[stepIndex]!;
      if (timeoutMs !== undefined && timedOut()) {
        yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
        return;
      }

      const stepStarted: AgentEvent = {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: step.id,
        step,
      };
      yield await emitEvent(input, stepStarted);

      const stepResult = await collectModelEvents(input, "execute", step, plan);
      if (stepResult.error) {
        yield await emitTaskFailed(input, stepResult.error);
        return;
      }

      const stepEvents = stepResult.events;
      for (
        let eventIndex = 0;
        eventIndex < stepEvents.length;
        eventIndex += 1
      ) {
        const event = stepEvents[eventIndex]!;
        if (event.type === "text.delta") {
          const deltaEvent: AgentEvent = {
            type: "agent.model.delta",
            taskId: input.task.id,
            stepId: step.id,
            text: event.text,
          };
          yield await emitEvent(input, deltaEvent);
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: step.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step,
            request,
            plan,
            artifacts: [],
            stepIndex,
            stepEvents,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.step",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstFinalOutput(stepEvents) ??
          firstStructuredOutput(stepEvents),
      );
    }

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const synthesisResult = await collectModelEvents(
      input,
      "execute",
      undefined,
      plan,
    );
    if (synthesisResult.error) {
      yield await emitTaskFailed(input, synthesisResult.error);
      return;
    }

    const synthesisEvents = synthesisResult.events;
    for (
      let eventIndex = 0;
      eventIndex < synthesisEvents.length;
      eventIndex += 1
    ) {
      const event = synthesisEvents[eventIndex]!;
      if (event.type === "text.delta") {
        const deltaEvent: AgentEvent = {
          type: "agent.model.delta",
          taskId: input.task.id,
          text: event.text,
        };
        yield await emitEvent(input, deltaEvent);
      }

      if (event.type === "tool_call.proposed") {
        const { stepId: _stepId, ...request } = event.toolCall;
        const result = yield* processToolCallEvent({
          input,
          step: undefined,
          request,
          plan,
          artifacts: [],
          stepIndex: undefined,
          stepEvents: synthesisEvents,
          eventIndex,
          engineName: ENGINE_NAMES.deepResearch,
          phase: "deep-research.synthesis",
          extraResumeMetadata: { researchCollection: collection },
        });
        if (result.kind === "failed") return;
        if (result.kind === "paused") return;
        collectResearchOutput(collection, result.result.output);
      }
    }

    if (timeoutMs !== undefined && timedOut()) {
      yield await emitTaskFailed(input, researchTimeoutError(timeoutMs));
      return;
    }

    const report = normalizeResearchReport(
      input.task.goal,
      firstStructuredOutput(synthesisResult.events) ??
        firstFinalOutput(synthesisResult.events),
      collection,
      options,
    );

    let artifact: AgentArtifact;
    try {
      artifact = await createArtifact(input, {
        type: "report",
        name: "deep-research-report",
        content: report,
        mediaType: "application/json",
      });
    } catch (error) {
      yield await emitTaskFailed(
        input,
        toAgentError(error, "artifact_exception"),
      );
      return;
    }

    const artifactEvent: AgentEvent = {
      type: "agent.artifact.created",
      taskId: input.task.id,
      artifact,
    };
    yield await emitEvent(input, artifactEvent);

    let review: AgentReviewResult | undefined;
    if (options?.review ?? true) {
      const reviewStarted: AgentEvent = {
        type: "agent.review.started",
        taskId: input.task.id,
      };
      yield await emitEvent(input, reviewStarted);

      const reviewResult = await collectModelEvents(
        input,
        "review",
        undefined,
        plan,
      );
      if (reviewResult.error) {
        yield await emitTaskFailed(input, reviewResult.error);
        return;
      }

      review = normalizeReview(
        firstStructuredOutput(reviewResult.events) ??
          firstFinalOutput(reviewResult.events),
      );
      const reviewCompleted: AgentEvent = {
        type: "agent.review.completed",
        taskId: input.task.id,
        review,
      };
      yield await emitEvent(input, reviewCompleted);
    }

    const artifacts = [artifact];
    const output: AgentTaskOutput = {
      status:
        review?.status === "needs_rerun"
          ? "needs_rerun"
          : review?.status === "failed"
            ? "failed"
            : "completed",
      summary: report.summary,
      plan,
      artifacts,
      ...(review ? { review } : {}),
      metadata: {
        research: report,
      },
    };

    const completedEvent: AgentEvent = {
      type: "agent.task.completed",
      taskId: input.task.id,
      output,
    };
    yield await emitEvent(input, completedEvent);
  }

  async *resume(
    input: AgentResumeInput<AgentResearchOptions>,
  ): AsyncIterable<AgentEvent> {
    const preamble = yield* resumeEnginePreamble(
      input,
      ENGINE_NAMES.deepResearch,
    );
    if (!preamble) return;

    const { resumeState, plan, toolResult } = preamble;
    const options = input.options as AgentResearchOptions | undefined;
    const collection = extractResearchCollection(resumeState);
    const currentStep = resumeState.currentStep;

    collectResearchOutput(collection, toolResult.output);

    const phase = resumeState.phase;

    if (phase === "deep-research.step") {
      for (
        let eventIndex = 0;
        eventIndex < resumeState.pendingModelEvents.length;
        eventIndex += 1
      ) {
        const event = resumeState.pendingModelEvents[eventIndex]!;
        if (event.type === "text.delta") {
          yield emitEvent(input, {
            type: "agent.model.delta",
            taskId: input.task.id,
            stepId: currentStep!.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const request: AgentToolRequest = {
            ...event.toolCall,
            stepId: currentStep!.id,
          };
          const result = yield* processToolCallEvent({
            input,
            step: currentStep!,
            request,
            plan,
            artifacts: [],
            stepIndex: resumeState.currentStepIndex,
            stepEvents: resumeState.pendingModelEvents,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.step",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstFinalOutput(resumeState.pendingModelEvents) ??
          firstStructuredOutput(resumeState.pendingModelEvents),
      );

      const boundedSteps = plan.steps.slice(
        0,
        boundedCount(options?.maxSteps, plan.steps.length),
      );
      for (
        let remainingIndex = (resumeState.currentStepIndex ?? 0) + 1;
        remainingIndex < boundedSteps.length;
        remainingIndex += 1
      ) {
        const step = boundedSteps[remainingIndex]!;
        yield emitEvent(input, {
          type: "agent.step.started",
          taskId: input.task.id,
          stepId: step.id,
          step,
        });

        const stepResult = await collectModelEvents(
          input,
          "execute",
          step,
          plan,
        );
        if (stepResult.error) {
          yield await emitTaskFailed(input, stepResult.error);
          return;
        }

        for (
          let eventIndex = 0;
          eventIndex < stepResult.events.length;
          eventIndex += 1
        ) {
          const event = stepResult.events[eventIndex]!;
          if (event.type === "text.delta") {
            yield emitEvent(input, {
              type: "agent.model.delta",
              taskId: input.task.id,
              stepId: step.id,
              text: event.text,
            });
          }

          if (event.type === "tool_call.proposed") {
            const request: AgentToolRequest = {
              ...event.toolCall,
              stepId: step.id,
            };
            const result = yield* processToolCallEvent({
              input,
              step,
              request,
              plan,
              artifacts: [],
              stepIndex: remainingIndex,
              stepEvents: stepResult.events,
              eventIndex,
              engineName: ENGINE_NAMES.deepResearch,
              phase: "deep-research.step",
              extraResumeMetadata: { researchCollection: collection },
            });
            if (result.kind === "failed") return;
            if (result.kind === "paused") return;
            collectResearchOutput(collection, result.result.output);
          }
        }

        collectResearchOutput(
          collection,
          firstFinalOutput(stepResult.events) ??
            firstStructuredOutput(stepResult.events),
        );
      }

      const synthesisResult = await collectModelEvents(
        input,
        "execute",
        undefined,
        plan,
      );
      if (synthesisResult.error) {
        yield await emitTaskFailed(input, synthesisResult.error);
        return;
      }

      for (
        let eventIndex = 0;
        eventIndex < synthesisResult.events.length;
        eventIndex += 1
      ) {
        const event = synthesisResult.events[eventIndex]!;
        if (event.type === "text.delta") {
          yield emitEvent(input, {
            type: "agent.model.delta",
            taskId: input.task.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const { stepId: _stepId, ...request } = event.toolCall;
          const result = yield* processToolCallEvent({
            input,
            step: undefined,
            request,
            plan,
            artifacts: [],
            stepIndex: undefined,
            stepEvents: synthesisResult.events,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.synthesis",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstStructuredOutput(synthesisResult.events) ??
          firstFinalOutput(synthesisResult.events),
      );

      const report = normalizeResearchReport(
        input.task.goal,
        firstStructuredOutput(synthesisResult.events) ??
          firstFinalOutput(synthesisResult.events),
        collection,
        options,
      );

      let artifact: AgentArtifact;
      try {
        artifact = await createArtifact(input, {
          type: "report",
          name: "deep-research-report",
          content: report,
          mediaType: "application/json",
        });
      } catch (error) {
        yield await emitTaskFailed(
          input,
          toAgentError(error, "artifact_exception"),
        );
        return;
      }

      yield emitEvent(input, {
        type: "agent.artifact.created",
        taskId: input.task.id,
        artifact,
      });

      let review: AgentReviewResult | undefined;
      if (options?.review ?? true) {
        yield emitEvent(input, {
          type: "agent.review.started",
          taskId: input.task.id,
        });

        const reviewResult = await collectModelEvents(
          input,
          "review",
          undefined,
          plan,
        );
        if (reviewResult.error) {
          yield await emitTaskFailed(input, reviewResult.error);
          return;
        }

        review = normalizeReview(
          firstStructuredOutput(reviewResult.events) ??
            firstFinalOutput(reviewResult.events),
        );
        yield emitEvent(input, {
          type: "agent.review.completed",
          taskId: input.task.id,
          review,
        });
      }

      const artifacts: AgentArtifact[] = [artifact];
      yield emitEvent(input, {
        type: "agent.task.completed",
        taskId: input.task.id,
        output: {
          status:
            review?.status === "needs_rerun"
              ? "needs_rerun"
              : review?.status === "failed"
                ? "failed"
                : "completed",
          summary: report.summary,
          plan,
          artifacts,
          ...(review ? { review } : {}),
          metadata: {
            research: report,
          },
        },
      });
    } else {
      for (
        let eventIndex = 0;
        eventIndex < resumeState.pendingModelEvents.length;
        eventIndex += 1
      ) {
        const event = resumeState.pendingModelEvents[eventIndex]!;
        if (event.type === "text.delta") {
          yield emitEvent(input, {
            type: "agent.model.delta",
            taskId: input.task.id,
            text: event.text,
          });
        }

        if (event.type === "tool_call.proposed") {
          const { stepId: _stepId, ...request } = event.toolCall;
          const result = yield* processToolCallEvent({
            input,
            step: undefined,
            request,
            plan,
            artifacts: [],
            stepIndex: undefined,
            stepEvents: resumeState.pendingModelEvents,
            eventIndex,
            engineName: ENGINE_NAMES.deepResearch,
            phase: "deep-research.synthesis",
            extraResumeMetadata: { researchCollection: collection },
          });
          if (result.kind === "failed") return;
          if (result.kind === "paused") return;
          collectResearchOutput(collection, result.result.output);
        }
      }

      collectResearchOutput(
        collection,
        firstStructuredOutput(resumeState.pendingModelEvents) ??
          firstFinalOutput(resumeState.pendingModelEvents),
      );

      const report = normalizeResearchReport(
        input.task.goal,
        firstStructuredOutput(resumeState.pendingModelEvents) ??
          firstFinalOutput(resumeState.pendingModelEvents),
        collection,
        options,
      );

      let artifact: AgentArtifact;
      try {
        artifact = await createArtifact(input, {
          type: "report",
          name: "deep-research-report",
          content: report,
          mediaType: "application/json",
        });
      } catch (error) {
        yield await emitTaskFailed(
          input,
          toAgentError(error, "artifact_exception"),
        );
        return;
      }

      yield emitEvent(input, {
        type: "agent.artifact.created",
        taskId: input.task.id,
        artifact,
      });

      let review: AgentReviewResult | undefined;
      if (options?.review ?? true) {
        yield emitEvent(input, {
          type: "agent.review.started",
          taskId: input.task.id,
        });

        const reviewResult = await collectModelEvents(
          input,
          "review",
          undefined,
          plan,
        );
        if (reviewResult.error) {
          yield await emitTaskFailed(input, reviewResult.error);
          return;
        }

        review = normalizeReview(
          firstStructuredOutput(reviewResult.events) ??
            firstFinalOutput(reviewResult.events),
        );
        yield emitEvent(input, {
          type: "agent.review.completed",
          taskId: input.task.id,
          review,
        });
      }

      const artifacts: AgentArtifact[] = [artifact];
      yield emitEvent(input, {
        type: "agent.task.completed",
        taskId: input.task.id,
        output: {
          status:
            review?.status === "needs_rerun"
              ? "needs_rerun"
              : review?.status === "failed"
                ? "failed"
                : "completed",
          summary: report.summary,
          plan,
          artifacts,
          ...(review ? { review } : {}),
          metadata: {
            research: report,
          },
        },
      });
    }
  }
}

function normalizeReview(value: unknown): AgentReviewResult {
  if (isObject(value)) {
    const status =
      value.status === "needs_rerun" || value.status === "failed"
        ? value.status
        : "passed";
    return {
      status,
      ...(typeof value.summary === "string" ? { summary: value.summary } : {}),
      ...(Array.isArray(value.issues)
        ? {
            issues: value.issues.filter(
              (issue): issue is string => typeof issue === "string",
            ),
          }
        : {}),
      ...(isObject(value.metadata) ? { metadata: value.metadata } : {}),
    };
  }

  return {
    status: "passed",
    ...(typeof value === "string" ? { summary: value } : {}),
  };
}

export type AgentRuntimeOptions = {
  engines?: AgentEngine[];
};

export class AgentTaskFailedError extends Error {
  readonly agentError: AgentError;

  constructor(agentError: AgentError) {
    super(`Agent task failed: ${agentError.message}`);
    this.name = "AgentTaskFailedError";
    this.agentError = agentError;
  }
}

export async function collectAgentTaskOutput(
  events: AsyncIterable<AgentEvent>,
): Promise<AgentTaskOutput> {
  let output: AgentTaskOutput | undefined;

  for await (const event of events) {
    if (event.type === "agent.task.failed") {
      throw new AgentTaskFailedError(event.error);
    }

    if (event.type === "agent.task.paused") {
      return event.output;
    }

    if (event.type === "agent.task.completed") {
      output = event.output;
    }
  }

  if (!output) {
    throw new Error("Agent run completed without agent.task.completed event.");
  }

  return output;
}

export class AgentRuntime {
  private readonly engines = new Map<string, AgentEngine>();

  constructor(options: AgentRuntimeOptions = {}) {
    for (const engine of options.engines ?? [
      new ClassifyEngine(),
      new PlanRunReviewEngine(),
      new DeepResearchEngine(),
    ]) {
      this.engines.set(engine.name, engine);
    }
  }

  run<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentEngineRunInput<TOptions>,
  ): AsyncIterable<AgentEvent> {
    const engine = this.engines.get(engineName);
    if (!engine) {
      throw new Error(`Unknown agent engine: ${engineName}`);
    }

    return engine.run(input);
  }

  async runTask<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentEngineRunInput<TOptions>,
  ): Promise<AgentTaskOutput> {
    return collectAgentTaskOutput(this.run(engineName, input));
  }

  resume<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentResumeInput<TOptions>,
  ): AsyncIterable<AgentEvent> {
    const engine = this.engines.get(engineName);
    if (!engine) {
      throw new Error(`Unknown agent engine: ${engineName}`);
    }

    if (!engine.resume) {
      throw new Error(
        `Agent engine does not support resume: ${engineName}`,
      );
    }

    return engine.resume(input);
  }

  async resumeTask<TOptions extends AgentRunOptions = AgentRunOptions>(
    engineName: string,
    input: AgentResumeInput<TOptions>,
  ): Promise<AgentTaskOutput> {
    return collectAgentTaskOutput(this.resume(engineName, input));
  }
}
