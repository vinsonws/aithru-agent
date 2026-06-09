import type {
  AgentArtifact,
  AgentArtifactDraft,
  AgentClassificationResult,
  AgentEngineRunInput,
  AgentError,
  AgentEvent,
  AgentModelEvent,
  AgentModelInput,
  AgentPlan,
  AgentPlanStep,
  AgentReviewResult,
  AgentToolPolicyDecision,
} from "@aithru/agent-core";

export function toAgentError(error: unknown, code = "runtime_error"): AgentError {
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

export function isAgentError(value: unknown): value is AgentError {
  return (
    isObject(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string"
  );
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export async function emitEvent(
  input: AgentEngineRunInput,
  event: AgentEvent,
): Promise<AgentEvent> {
  await input.host.emit(event);
  return event;
}

export async function emitTaskFailed(
  input: AgentEngineRunInput,
  error: AgentError,
): Promise<AgentEvent> {
  return emitEvent(input, {
    type: "agent.task.failed",
    taskId: input.task.id,
    error,
  });
}

export type CollectedModelEvents = {
  events: AgentModelEvent[];
  error?: AgentError;
};

export async function collectModelEvents(
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

export function firstStructuredOutput(events: AgentModelEvent[]) {
  return events.find((event) => event.type === "structured.output")?.value;
}

export function firstFinalOutput(events: AgentModelEvent[]) {
  return events.find((event) => event.type === "final")?.output;
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

export async function createArtifact(
  input: AgentEngineRunInput,
  draft: AgentArtifactDraft,
): Promise<AgentArtifact> {
  if (input.host.createArtifact) {
    return input.host.createArtifact(draft);
  }

  return {
    id: `artifact_${draft.name ?? "unnamed"}`,
    ...draft,
  };
}

export function boundedCount(value: number | undefined, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
  }

  return Math.max(0, Math.floor(value));
}

export function normalizePlan(taskId: string, value: unknown): AgentPlan {
  if (isPlan(value)) {
    return value;
  }

  if (isObject(value) && Array.isArray(value.steps)) {
    return {
      id: typeof value.id === "string" ? value.id : "plan_default",
      taskId,
      steps: value.steps.map((step, index) => normalizePlanStep(step, index)),
    };
  }

  return {
    id: "plan_default",
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

export function normalizePlanStep(value: unknown, index: number): AgentPlanStep {
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

export function isPlan(value: unknown): value is AgentPlan {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.taskId === "string" &&
    Array.isArray(value.steps)
  );
}

export function normalizeClassification(value: unknown): AgentClassificationResult {
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

export function normalizeReview(value: unknown): AgentReviewResult {
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
