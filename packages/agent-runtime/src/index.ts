import type {
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
  AgentReviewResult,
  AgentTaskOutput,
  AgentToolResult,
} from "@aithru/agent-core";

function createId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

async function emitEvent(
  input: AgentEngineRunInput,
  event: AgentEvent,
): Promise<AgentEvent> {
  await input.host.emit(event);
  return event;
}

async function collectModelEvents(
  input: AgentEngineRunInput,
  mode: "classify" | "plan" | "execute" | "review",
  step?: AgentPlanStep,
) {
  const tools = input.host.listTools ? await input.host.listTools() : undefined;
  const modelInput: AgentModelInput = {
    task: input.task,
    mode,
    ...(step ? { step } : {}),
    ...(input.task.outputSchema !== undefined ? { outputSchema: input.task.outputSchema } : {}),
    ...(tools ? { tools } : {}),
  };
  const events: AgentModelEvent[] = [];

  for await (const event of input.model.generate(modelInput)) {
    events.push(event);
  }

  return events;
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
    ...(typeof value.expectedOutput === "string" ? { expectedOutput: value.expectedOutput } : {}),
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

export class ClassifyEngine implements AgentEngine {
  readonly name = "classify";

  async *run(input: AgentEngineRunInput): AsyncIterable<AgentEvent> {
    yield await emitEvent(input, {
      type: "agent.task.created",
      taskId: input.task.id,
      task: input.task,
    });

    const events = await collectModelEvents(input, "classify");
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
    const artifact = await createArtifact(input, {
      type: "decision",
      name: "classification",
      content: classification,
    });

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

    const planStarted: AgentEvent = { type: "agent.plan.started", taskId: input.task.id };
    yield await emitEvent(input, planStarted);

    const planEvents = await collectModelEvents(input, "plan");
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

    for (const step of plan.steps.slice(0, input.options?.maxSteps ?? plan.steps.length)) {
      const stepStarted: AgentEvent = {
        type: "agent.step.started",
        taskId: input.task.id,
        stepId: step.id,
        step,
      };
      yield await emitEvent(input, stepStarted);

      const stepEvents = await collectModelEvents(input, "execute", step);
      for (const event of stepEvents) {
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
          const proposed: AgentEvent = {
            type: "agent.tool.proposed",
            taskId: input.task.id,
            stepId: step.id,
            request: event.toolCall,
          };
          yield await emitEvent(input, proposed);

          const result: AgentToolResult = await input.host.callTool(event.toolCall);
          const completed: AgentEvent = {
            type: "agent.tool.completed",
            taskId: input.task.id,
            stepId: step.id,
            result,
          };
          yield await emitEvent(input, completed);
        }
      }

      const stepOutput = firstFinalOutput(stepEvents) ?? firstStructuredOutput(stepEvents);
      if (stepOutput !== undefined) {
        const artifact = await createArtifact(input, {
          type: "json",
          name: `${step.id}-output`,
          content: stepOutput,
          sourceStepId: step.id,
        });
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
      const reviewStarted: AgentEvent = { type: "agent.review.started", taskId: input.task.id };
      yield await emitEvent(input, reviewStarted);

      const reviewEvents = await collectModelEvents(input, "review");
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
}

function normalizeReview(value: unknown): AgentReviewResult {
  if (isObject(value)) {
    const status =
      value.status === "needs_rerun" || value.status === "failed" ? value.status : "passed";
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
    for (const engine of options.engines ?? [new ClassifyEngine(), new PlanRunReviewEngine()]) {
      this.engines.set(engine.name, engine);
    }
  }

  run(engineName: string, input: AgentEngineRunInput): AsyncIterable<AgentEvent> {
    const engine = this.engines.get(engineName);
    if (!engine) {
      throw new Error(`Unknown agent engine: ${engineName}`);
    }

    return engine.run(input);
  }

  async runTask(engineName: string, input: AgentEngineRunInput): Promise<AgentTaskOutput> {
    return collectAgentTaskOutput(this.run(engineName, input));
  }
}
