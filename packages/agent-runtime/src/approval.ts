import type {
  AgentApprovalRequest,
  AgentArtifact,
  AgentEngineRunInput,
  AgentError,
  AgentEvent,
  AgentModelEvent,
  AgentPlan,
  AgentPlanStep,
  AgentResumeInput,
  AgentResumePhase,
  AgentResumeState,
  AgentTaskOutput,
  AgentToolRequest,
  AgentToolResult,
} from "@aithru/agent-core";
import { emitEvent, emitTaskFailed, toAgentError } from "./utils.js";
import {
  evaluateToolRiskPolicy,
  evaluateToolRiskPolicyForResume,
  validateResumeInput,
  validateResumeStep,
  validateToolAllowed,
} from "./policy.js";

type ResumePreambleContext = {
  approval: AgentApprovalRequest;
  step: AgentPlanStep | undefined;
  resumeState: AgentResumeState;
  plan: AgentPlan;
  toolResult: AgentToolResult;
};

type ResumePhaseConfig = {
  allowedPhases?: AgentResumePhase[];
  requiresStepFor?: AgentResumePhase[];
  forbidsStepFor?: AgentResumePhase[];
};

async function* resumeEnginePreamble(
  input: AgentResumeInput,
  expectedEngineName: string,
  phaseConfig?: ResumePhaseConfig,
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

  // Validate phase exists in allowed list
  if (
    phaseConfig?.allowedPhases &&
    !phaseConfig.allowedPhases.includes(resumeState.phase)
  ) {
    yield await emitTaskFailed(input, {
      code: "invalid_resume_state",
      message: `Resume phase "${resumeState.phase}" is not allowed for engine "${expectedEngineName}".`,
      metadata: {
        phase: resumeState.phase,
        allowedPhases: phaseConfig.allowedPhases,
        expectedEngineName,
      },
    });
    return undefined;
  }

  // Validate step required for this phase
  if (
    phaseConfig?.requiresStepFor?.includes(resumeState.phase)
  ) {
    const stepError = validateResumeStep(resumeState);
    if (stepError) {
      yield await emitTaskFailed(input, stepError);
      return undefined;
    }
  }

  // Validate step forbidden for this phase
  if (
    phaseConfig?.forbidsStepFor?.includes(resumeState.phase) &&
    resumeState.currentStep !== undefined
  ) {
    yield await emitTaskFailed(input, {
      code: "invalid_resume_state",
      message: `Resume phase "${resumeState.phase}" must not have currentStep.`,
      metadata: { phase: resumeState.phase },
    });
    return undefined;
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
      id: `resume_${Math.random().toString(36).slice(2, 10)}`,
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

export type { ResumePreambleContext, ResumePhaseConfig, ProcessToolCallContext, ProcessToolCallResult };
export { resumeEnginePreamble, processToolCallEvent };
