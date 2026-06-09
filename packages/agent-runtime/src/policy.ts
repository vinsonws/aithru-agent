import type {
  AgentApprovalRequest,
  AgentEngineRunInput,
  AgentError,
  AgentPlanStep,
  AgentResumeInput,
  AgentResumeState,
  AgentRiskLevel,
  AgentRunOptions,
  AgentToolPolicyDecision,
  AgentToolRequest,
} from "@aithru/agent-core";

export function validateToolAllowed(
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

export function effectiveRiskLevel(request: AgentToolRequest): AgentRiskLevel {
  return request.riskLevel ?? "safe";
}

export function resolveRiskDecision(
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

export type ToolRiskEvaluation =
  | { decision: "allow" }
  | { decision: "deny"; error: AgentError }
  | { decision: "require_approval"; approval: AgentApprovalRequest };

export function evaluateToolRiskPolicy(
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
      id: `approval_${Math.random().toString(36).slice(2, 10)}`,
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

export function evaluateToolRiskPolicyForResume(
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

export function validateResumeInput(
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

export function validateResumeStep(
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
