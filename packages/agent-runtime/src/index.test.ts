import type {
  AgentArtifact,
  AgentEngine,
  AgentEngineRunInput,
  AgentError,
  AgentEvent,
  AgentHost,
  AgentModelAdapter,
  AgentModelEvent,
  AgentModelInput,
  AgentResearchReport,
  AgentTask,
  AgentToolRequest,
  AgentToolResult,
} from "@aithru/agent-core";
import {
  ScriptedModelAdapter,
  createStaticStructuredModel,
} from "@aithru/agent-model-test";
import { describe, expect, test, vi } from "vitest";
import {
  AgentRuntime,
  AgentTaskFailedError,
  ClassifyEngine,
  DeepResearchEngine,
  PlanRunReviewEngine,
} from "./index.js";

async function collectEvents(events: AsyncIterable<AgentEvent>) {
  const collected: AgentEvent[] = [];

  for await (const event of events) {
    collected.push(event);
  }

  return collected;
}

function createHost(
  options: {
    callTool?: AgentHost["callTool"];
    createArtifact?: AgentHost["createArtifact"];
  } = {},
) {
  const emitted: AgentEvent[] = [];
  const callTool =
    options.callTool ??
    vi.fn(async (request: AgentToolRequest): Promise<AgentToolResult> => {
      return {
        id: request.id,
        toolName: request.toolName,
        output: { ok: true },
      };
    });

  const host: AgentHost = {
    emit(event) {
      emitted.push(event);
    },
    callTool,
    createArtifact:
      options.createArtifact ??
      (async (draft) => {
        return {
          id: `artifact_${draft.name ?? "unnamed"}`,
          ...draft,
        };
      }),
  };

  return { emitted, host, callTool };
}

function expectEmittedToMatchYielded(
  emitted: AgentEvent[],
  yielded: AgentEvent[],
) {
  expect(emitted).toEqual(yielded);
}

function failedEvent(events: AgentEvent[]) {
  return events.find(
    (event): event is Extract<AgentEvent, { type: "agent.task.failed" }> =>
      event.type === "agent.task.failed",
  );
}

function createModeModel(
  eventsByMode: Partial<Record<AgentModelInput["mode"], AgentModelEvent[]>>,
) {
  return new ScriptedModelAdapter({
    events(input) {
      return eventsByMode[input.mode] ?? [];
    },
  });
}

function createThrowingModel(error: unknown): AgentModelAdapter {
  return {
    name: "throwing-test-model",
    generate() {
      throw error;
    },
  };
}

function planEvents(stepId = "step_1"): AgentModelEvent[] {
  return [
    {
      type: "structured.output",
      value: {
        steps: [
          {
            id: stepId,
            title: "Execute step",
            objective: "Complete one bounded step.",
            allowedTools: ["repo.read"],
          },
        ],
      },
    },
  ];
}

function executeFinalEvents(summary = "Step completed."): AgentModelEvent[] {
  return [
    {
      type: "final",
      output: { summary },
    },
  ];
}

function reviewPassedEvents(): AgentModelEvent[] {
  return [
    {
      type: "structured.output",
      value: {
        status: "passed",
        summary: "The task completed successfully.",
      },
    },
  ];
}

describe("ClassifyEngine", () => {
  test("yields the same ordered events sent to AgentHost.emit", async () => {
    const task: AgentTask = {
      id: "task_classify",
      goal: "Classify this task.",
    };
    const { emitted, host } = createHost();
    const model = createStaticStructuredModel({
      route: "research",
      confidence: 0.92,
      reason: "Needs multi-step analysis.",
    });

    const events = await collectEvents(
      new ClassifyEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.artifact.created",
      "agent.task.completed",
    ]);
    expect(emitted.map((event) => event.type)).toEqual(
      events.map((event) => event.type),
    );
    expect(events.at(-1)).toMatchObject({
      type: "agent.task.completed",
      taskId: "task_classify",
      output: {
        status: "completed",
        summary: "Needs multi-step analysis.",
        metadata: {
          classification: {
            route: "research",
            confidence: 0.92,
            reason: "Needs multi-step analysis.",
          },
        },
      },
    });
  });

  test("fails when the model yields an error event", async () => {
    const task: AgentTask = {
      id: "task_classify_model_error",
      goal: "Classify this task.",
    };
    const error: AgentError = {
      code: "provider_error",
      message: "The provider reported a classification failure.",
    };
    const { emitted, host } = createHost();
    const model = new ScriptedModelAdapter({
      events: [{ type: "error", error }],
    });

    const events = await collectEvents(
      new ClassifyEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toBe(error);
  });

  test("fails when the model throws during generate", async () => {
    const task: AgentTask = {
      id: "task_classify_model_throw",
      goal: "Classify this task.",
    };
    const thrown = new Error("Provider connection failed.");
    const { emitted, host } = createHost();

    const events = await collectEvents(
      new ClassifyEngine().run({
        task,
        model: createThrowingModel(thrown),
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toMatchObject({
      code: "model_exception",
      message: "Provider connection failed.",
    });
    expect(failedEvent(events)?.error.cause).toBe(thrown);
  });

  test("fails when artifact creation throws", async () => {
    const task: AgentTask = {
      id: "task_classify_artifact_throw",
      goal: "Classify this task.",
    };
    const thrown = new Error("Artifact store is unavailable.");
    const { emitted, host } = createHost({
      async createArtifact() {
        throw thrown;
      },
    });
    const model = createStaticStructuredModel({
      route: "research",
      confidence: 0.92,
      reason: "Needs multi-step analysis.",
    });

    const events = await collectEvents(
      new ClassifyEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toMatchObject({
      code: "artifact_exception",
      message: "Artifact store is unavailable.",
    });
    expect(failedEvent(events)?.error.cause).toBe(thrown);
  });
});

describe("PlanRunReviewEngine", () => {
  test("yields the same ordered events sent to AgentHost.emit while tools go through AgentHost.callTool", async () => {
    const task: AgentTask = {
      id: "task_plan_run_review",
      goal: "Read the README and summarize it.",
    };
    const toolCall: AgentToolRequest = {
      id: "tool_read_readme",
      toolName: "repo.read",
      arguments: { path: "README.md" },
      reason: "Need repository context.",
      stepId: "step_read_readme",
      riskLevel: "read",
    };
    const toolResult: AgentToolResult = {
      id: toolCall.id,
      toolName: toolCall.toolName,
      output: {
        content: "# README",
      },
    };
    const callTool = vi.fn(
      async (request: AgentToolRequest): Promise<AgentToolResult> => {
        expect(request).toEqual(toolCall);
        return toolResult;
      },
    );
    const { emitted, host } = createHost({ callTool });
    const model = new ScriptedModelAdapter({
      events(input) {
        if (input.mode === "plan") {
          return [
            {
              type: "structured.output",
              value: {
                id: "plan_read",
                taskId: task.id,
                steps: [
                  {
                    id: "step_read_readme",
                    title: "Read README",
                    objective: "Read README.md through an allowed tool.",
                    allowedTools: ["repo.read"],
                  },
                ],
              },
            },
          ];
        }

        if (input.mode === "execute") {
          return [
            {
              type: "tool_call.proposed",
              toolCall,
            },
            {
              type: "final",
              output: {
                summary: "README was read.",
              },
            },
          ];
        }

        if (input.mode === "review") {
          return [
            {
              type: "structured.output",
              value: {
                status: "passed",
                summary: "The task completed successfully.",
              },
            },
          ];
        }

        return [];
      },
    });

    const events = await collectEvents(
      new PlanRunReviewEngine().run({
        task,
        model,
        host,
        options: {
          maxSteps: 4,
          review: true,
        },
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.tool.proposed",
      "agent.tool.completed",
      "agent.artifact.created",
      "agent.review.started",
      "agent.review.completed",
      "agent.task.completed",
    ]);
    expect(emitted.map((event) => event.type)).toEqual(
      events.map((event) => event.type),
    );
    expect(callTool).toHaveBeenCalledTimes(1);
    expect(callTool).toHaveBeenCalledWith(toolCall);
    expect(
      events.find((event) => event.type === "agent.tool.completed"),
    ).toMatchObject({
      type: "agent.tool.completed",
      result: toolResult,
    });

    const artifactEvent = events.find(
      (
        event,
      ): event is Extract<AgentEvent, { type: "agent.artifact.created" }> =>
        event.type === "agent.artifact.created",
    );
    expect(artifactEvent?.artifact).toEqual<AgentArtifact>({
      id: "artifact_step_read_readme-output",
      type: "json",
      name: "step_read_readme-output",
      content: {
        summary: "README was read.",
      },
      sourceStepId: "step_read_readme",
    });

    expect(events.at(-1)).toMatchObject({
      type: "agent.task.completed",
      output: {
        status: "completed",
        summary: "The task completed successfully.",
        review: {
          status: "passed",
        },
      },
    });
  });

  test("fails when the plan phase yields an error event", async () => {
    const task: AgentTask = {
      id: "task_plan_model_error",
      goal: "Plan the task.",
    };
    const error: AgentError = {
      code: "provider_error",
      message: "The provider could not create a plan.",
    };
    const { emitted, host } = createHost();
    const model = createModeModel({
      plan: [{ type: "error", error }],
    });

    const events = await collectEvents(
      new PlanRunReviewEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toBe(error);
  });

  test("fails when the execute phase yields an error event", async () => {
    const task: AgentTask = {
      id: "task_execute_model_error",
      goal: "Execute the task.",
    };
    const error: AgentError = {
      code: "provider_error",
      message: "The provider could not execute the step.",
    };
    const { emitted, host } = createHost();
    const model = createModeModel({
      plan: planEvents("step_execute"),
      execute: [{ type: "error", error }],
    });

    const events = await collectEvents(
      new PlanRunReviewEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toBe(error);
  });

  test("fails when the review phase yields an error event", async () => {
    const task: AgentTask = {
      id: "task_review_model_error",
      goal: "Review the task.",
    };
    const error: AgentError = {
      code: "provider_error",
      message: "The provider could not review the task.",
    };
    const { emitted, host } = createHost();
    const model = createModeModel({
      plan: planEvents("step_review"),
      execute: executeFinalEvents("Step was executed."),
      review: [{ type: "error", error }],
    });

    const events = await collectEvents(
      new PlanRunReviewEngine().run({
        task,
        model,
        host,
        options: {
          review: true,
        },
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.artifact.created",
      "agent.review.started",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toBe(error);
  });

  test("fails when AgentHost.callTool throws", async () => {
    const task: AgentTask = {
      id: "task_tool_throw",
      goal: "Use a tool.",
    };
    const toolCall: AgentToolRequest = {
      id: "tool_read",
      toolName: "repo.read",
      arguments: { path: "README.md" },
      stepId: "step_tool_throw",
      riskLevel: "read",
    };
    const thrown = new Error("Tool bridge failed.");
    const callTool = vi.fn(async (): Promise<AgentToolResult> => {
      throw thrown;
    });
    const { emitted, host } = createHost({ callTool });
    const model = createModeModel({
      plan: planEvents("step_tool_throw"),
      execute: [
        {
          type: "tool_call.proposed",
          toolCall,
        },
        {
          type: "final",
          output: {
            summary: "Tool result was processed.",
          },
        },
      ],
    });

    const events = await collectEvents(
      new PlanRunReviewEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.tool.proposed",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(callTool).toHaveBeenCalledWith(toolCall);
    expect(failedEvent(events)?.error).toMatchObject({
      code: "tool_exception",
      message: "Tool bridge failed.",
    });
    expect(failedEvent(events)?.error.cause).toBe(thrown);
  });

  test("fails when AgentHost.callTool returns an error result", async () => {
    const task: AgentTask = {
      id: "task_tool_error",
      goal: "Use a tool.",
    };
    const toolCall: AgentToolRequest = {
      id: "tool_read",
      toolName: "repo.read",
      arguments: { path: "README.md" },
      stepId: "step_tool_error",
      riskLevel: "read",
    };
    const error: AgentError = {
      code: "tool_provider_error",
      message: "The tool could not read README.md.",
    };
    const toolResult: AgentToolResult = {
      id: toolCall.id,
      toolName: toolCall.toolName,
      error,
    };
    const callTool = vi.fn(async (): Promise<AgentToolResult> => {
      return toolResult;
    });
    const { emitted, host } = createHost({
      callTool,
    });
    const model = createModeModel({
      plan: planEvents("step_tool_error"),
      execute: [
        {
          type: "tool_call.proposed",
          toolCall,
        },
        {
          type: "final",
          output: {
            summary: "Tool result was processed.",
          },
        },
      ],
    });

    const events = await collectEvents(
      new PlanRunReviewEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.tool.proposed",
      "agent.tool.completed",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(callTool).toHaveBeenCalledWith(toolCall);
    expect(failedEvent(events)?.error).toBe(error);
  });
});

describe("DeepResearchEngine", () => {
  test("yields the same ordered events sent to AgentHost.emit while tools go through AgentHost.callTool", async () => {
    const task: AgentTask = {
      id: "task_deep_research",
      goal: "Research the Aithru Agent runtime boundaries.",
    };
    const source = {
      id: "source_readme",
      title: "README",
      uri: "memory://README.md",
      content: "Aithru Agent owns intelligent execution inside bounded tasks.",
    };
    const finding = {
      id: "finding_boundary",
      claim:
        "Aithru Agent stays inside bounded agent tasks and does not own WorkflowSpec.",
      sourceIds: [source.id],
      confidence: 0.94,
    };
    const report: AgentResearchReport = {
      title: "Aithru Agent Runtime Boundaries",
      summary:
        "Aithru Agent owns bounded intelligent execution, while formal workflows stay in aithru-core.",
      findings: [finding],
      sources: [source],
      limitations: ["No external network source was used."],
    };
    const toolCall: AgentToolRequest = {
      id: "tool_read_readme",
      toolName: "local.readSource",
      arguments: { id: "source_readme" },
      reason: "Use a fake local source for deterministic research.",
      stepId: "step_collect_boundary",
      riskLevel: "read",
    };
    const toolResult: AgentToolResult = {
      id: toolCall.id,
      toolName: toolCall.toolName,
      output: source,
    };
    const callTool = vi.fn(
      async (request: AgentToolRequest): Promise<AgentToolResult> => {
        expect(request).toEqual(toolCall);
        return toolResult;
      },
    );
    const { emitted, host } = createHost({ callTool });
    const model = new ScriptedModelAdapter({
      events(input) {
        if (input.mode === "plan") {
          return [
            {
              type: "structured.output",
              value: {
                id: "plan_deep_research",
                taskId: task.id,
                steps: [
                  {
                    id: "step_collect_boundary",
                    title: "Collect boundary source",
                    objective:
                      "Collect a deterministic local source about runtime boundaries.",
                    allowedTools: ["local.readSource"],
                  },
                ],
              },
            },
          ];
        }

        if (input.mode === "execute" && input.step) {
          return [
            {
              type: "tool_call.proposed",
              toolCall,
            },
            {
              type: "final",
              output: {
                summary: "Collected one local source.",
                sources: [source],
                findings: [finding],
              },
            },
          ];
        }

        if (input.mode === "execute") {
          return [
            {
              type: "structured.output",
              value: report,
            },
          ];
        }

        if (input.mode === "review") {
          return [
            {
              type: "structured.output",
              value: {
                status: "passed",
                summary:
                  "Research report is grounded in the collected local source.",
              },
            },
          ];
        }

        return [];
      },
    });

    const events = await collectEvents(
      new DeepResearchEngine().run({
        task,
        model,
        host,
        options: {
          maxSteps: 1,
          maxSources: 1,
          review: true,
        },
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.tool.proposed",
      "agent.tool.completed",
      "agent.artifact.created",
      "agent.review.started",
      "agent.review.completed",
      "agent.task.completed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(callTool).toHaveBeenCalledTimes(1);
    expect(callTool).toHaveBeenCalledWith(toolCall);
    expect(
      events.find((event) => event.type === "agent.tool.completed"),
    ).toMatchObject({
      type: "agent.tool.completed",
      result: toolResult,
    });

    const artifactEvent = events.find(
      (
        event,
      ): event is Extract<AgentEvent, { type: "agent.artifact.created" }> =>
        event.type === "agent.artifact.created",
    );
    expect(artifactEvent?.artifact).toEqual<AgentArtifact>({
      id: "artifact_deep-research-report",
      type: "report",
      name: "deep-research-report",
      content: report,
      mediaType: "application/json",
    });

    expect(events.at(-1)).toMatchObject({
      type: "agent.task.completed",
      output: {
        status: "completed",
        summary: report.summary,
        artifacts: [artifactEvent?.artifact],
        review: {
          status: "passed",
        },
        metadata: {
          research: report,
        },
      },
    });
  });

  test("AgentRuntime.runTask returns a completed Deep Research output by default", async () => {
    const task: AgentTask = {
      id: "task_runtime_deep_research",
      goal: "Research bounded execution.",
    };
    const report: AgentResearchReport = {
      title: "Bounded Execution",
      summary: "Research completed with one bounded local source.",
      findings: [
        {
          id: "finding_bounded",
          claim: "Deep Research V0 remains bounded by runtime options.",
          sourceIds: ["source_bounded"],
          confidence: 0.9,
        },
      ],
      sources: [
        {
          id: "source_bounded",
          title: "Local source",
          content: "maxSteps and maxSources constrain the run.",
        },
      ],
    };
    const { host } = createHost();
    const model = createModeModel({
      plan: planEvents("step_runtime_research"),
      execute: [{ type: "structured.output", value: report }],
      review: reviewPassedEvents(),
    });

    const output = await new AgentRuntime().runTask("deep-research", {
      task,
      model,
      host,
      options: {
        maxSteps: 0,
        maxSources: 1,
      },
    });

    expect(output).toMatchObject({
      status: "completed",
      summary: report.summary,
      plan: {
        taskId: task.id,
      },
      artifacts: [
        {
          type: "report",
          name: "deep-research-report",
          content: report,
        },
      ],
      review: {
        status: "passed",
      },
      metadata: {
        research: report,
      },
    });
  });

  test("fails when the plan phase yields an error event", async () => {
    const task: AgentTask = {
      id: "task_deep_research_plan_error",
      goal: "Plan a research task.",
    };
    const error: AgentError = {
      code: "provider_error",
      message: "The provider could not create a research plan.",
    };
    const { emitted, host } = createHost();
    const model = createModeModel({
      plan: [{ type: "error", error }],
    });

    const events = await collectEvents(
      new DeepResearchEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toBe(error);
  });

  test("fails when AgentHost.callTool returns an error result during execution", async () => {
    const task: AgentTask = {
      id: "task_deep_research_tool_error",
      goal: "Use a local research tool.",
    };
    const toolCall: AgentToolRequest = {
      id: "tool_local_source",
      toolName: "local.readSource",
      arguments: { id: "source_missing" },
      stepId: "step_tool_error",
      riskLevel: "read",
    };
    const error: AgentError = {
      code: "local_source_missing",
      message: "The local source does not exist.",
    };
    const callTool = vi.fn(async (): Promise<AgentToolResult> => {
      return {
        id: toolCall.id,
        toolName: toolCall.toolName,
        error,
      };
    });
    const { emitted, host } = createHost({
      callTool,
    });
    const model = createModeModel({
      plan: planEvents("step_tool_error"),
      execute: [{ type: "tool_call.proposed", toolCall }],
    });

    const events = await collectEvents(
      new DeepResearchEngine().run({
        task,
        model,
        host,
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.tool.proposed",
      "agent.tool.completed",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(callTool).toHaveBeenCalledWith(toolCall);
    expect(failedEvent(events)?.error).toBe(error);
  });

  test("AgentRuntime.runTask throws AgentTaskFailedError when Deep Research fails", async () => {
    const error: AgentError = {
      code: "provider_error",
      message: "Research planning failed.",
    };
    const { host } = createHost();

    await expect(
      new AgentRuntime().runTask("deep-research", {
        task: {
          id: "task_runtime_deep_research_failure",
          goal: "Fail during research planning.",
        },
        model: createModeModel({
          plan: [{ type: "error", error }],
        }),
        host,
      }),
    ).rejects.toMatchObject({
      name: "AgentTaskFailedError",
      agentError: error,
    });
  });

  test("fails when report artifact creation throws", async () => {
    const task: AgentTask = {
      id: "task_deep_research_artifact_error",
      goal: "Create a research report.",
    };
    const thrown = new Error("Report artifact store failed.");
    const { emitted, host } = createHost({
      async createArtifact() {
        throw thrown;
      },
    });
    const model = createModeModel({
      plan: planEvents("step_artifact_error"),
      execute: [
        {
          type: "structured.output",
          value: {
            title: "Research Report",
            summary: "The synthesized report should become an artifact.",
            findings: [],
            sources: [],
          },
        },
      ],
    });

    const events = await collectEvents(
      new DeepResearchEngine().run({
        task,
        model,
        host,
        options: {
          maxSteps: 0,
        },
      }),
    );

    expect(events.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.task.failed",
    ]);
    expectEmittedToMatchYielded(emitted, events);
    expect(failedEvent(events)?.error).toMatchObject({
      code: "artifact_exception",
      message: "Report artifact store failed.",
    });
    expect(failedEvent(events)?.error.cause).toBe(thrown);
  });
});

describe("AgentRuntime.runTask", () => {
  test("returns the final output from a classify run", async () => {
    const task: AgentTask = {
      id: "task_runtime_classify",
      goal: "Classify this task.",
    };
    const { host } = createHost();
    const model = createStaticStructuredModel({
      route: "simple",
      confidence: 1,
      reason: "Can be handled directly.",
    });

    const output = await new AgentRuntime().runTask("classify", {
      task,
      model,
      host,
    });

    expect(output).toMatchObject({
      status: "completed",
      summary: "Can be handled directly.",
      metadata: {
        classification: {
          route: "simple",
          confidence: 1,
        },
      },
    });
  });

  test("returns the final output from a plan-run-review run", async () => {
    const task: AgentTask = {
      id: "task_runtime_plan_run_review",
      goal: "Read the README and summarize it.",
    };
    const toolCall: AgentToolRequest = {
      id: "tool_read_readme",
      toolName: "repo.read",
      arguments: { path: "README.md" },
      riskLevel: "read",
    };
    const { host } = createHost();
    const model = new ScriptedModelAdapter({
      events(input) {
        if (input.mode === "plan") {
          return [
            {
              type: "structured.output",
              value: {
                steps: [
                  {
                    id: "step_read_readme",
                    title: "Read README",
                    objective: "Read README.md.",
                  },
                ],
              },
            },
          ];
        }

        if (input.mode === "execute") {
          return [
            { type: "tool_call.proposed", toolCall },
            { type: "final", output: { summary: "README was read." } },
          ];
        }

        if (input.mode === "review") {
          return [
            {
              type: "structured.output",
              value: {
                status: "passed",
                summary: "The task completed successfully.",
              },
            },
          ];
        }

        return [];
      },
    });

    const output = await new AgentRuntime().runTask("plan-run-review", {
      task,
      model,
      host,
      options: {
        review: true,
      },
    });

    expect(output).toMatchObject({
      status: "completed",
      summary: "The task completed successfully.",
      plan: {
        taskId: task.id,
      },
      review: {
        status: "passed",
      },
    });
  });

  test.each<{
    name: string;
    engineName: "classify" | "plan-run-review";
    createInput: () => AgentEngineRunInput;
    expectedError: Pick<AgentError, "code" | "message">;
  }>([
    {
      name: "classify model error event",
      engineName: "classify",
      createInput() {
        const error: AgentError = {
          code: "provider_error",
          message: "Model yielded an error.",
        };
        const { host } = createHost();
        return {
          task: {
            id: "task_runtime_classify_model_error",
            goal: "Classify this task.",
          },
          model: new ScriptedModelAdapter({
            events: [{ type: "error", error }],
          }),
          host,
        };
      },
      expectedError: {
        code: "provider_error",
        message: "Model yielded an error.",
      },
    },
    {
      name: "classify model exception",
      engineName: "classify",
      createInput() {
        const { host } = createHost();
        return {
          task: {
            id: "task_runtime_classify_model_exception",
            goal: "Classify this task.",
          },
          model: createThrowingModel(new Error("Model threw.")),
          host,
        };
      },
      expectedError: {
        code: "model_exception",
        message: "Model threw.",
      },
    },
    {
      name: "plan phase model error event",
      engineName: "plan-run-review",
      createInput() {
        const error: AgentError = {
          code: "provider_error",
          message: "Plan failed.",
        };
        const { host } = createHost();
        return {
          task: {
            id: "task_runtime_plan_error",
            goal: "Plan this task.",
          },
          model: createModeModel({
            plan: [{ type: "error", error }],
          }),
          host,
        };
      },
      expectedError: {
        code: "provider_error",
        message: "Plan failed.",
      },
    },
    {
      name: "execute phase model error event",
      engineName: "plan-run-review",
      createInput() {
        const error: AgentError = {
          code: "provider_error",
          message: "Execute failed.",
        };
        const { host } = createHost();
        return {
          task: {
            id: "task_runtime_execute_error",
            goal: "Execute this task.",
          },
          model: createModeModel({
            plan: planEvents("step_runtime_execute_error"),
            execute: [{ type: "error", error }],
          }),
          host,
        };
      },
      expectedError: {
        code: "provider_error",
        message: "Execute failed.",
      },
    },
    {
      name: "review phase model error event",
      engineName: "plan-run-review",
      createInput() {
        const error: AgentError = {
          code: "provider_error",
          message: "Review failed.",
        };
        const { host } = createHost();
        return {
          task: {
            id: "task_runtime_review_error",
            goal: "Review this task.",
          },
          model: createModeModel({
            plan: planEvents("step_runtime_review_error"),
            execute: executeFinalEvents("Step finished."),
            review: [{ type: "error", error }],
          }),
          host,
          options: {
            review: true,
          },
        };
      },
      expectedError: {
        code: "provider_error",
        message: "Review failed.",
      },
    },
    {
      name: "tool exception",
      engineName: "plan-run-review",
      createInput() {
        const toolCall: AgentToolRequest = {
          id: "tool_runtime_throw",
          toolName: "repo.read",
          arguments: { path: "README.md" },
          stepId: "step_runtime_tool_throw",
          riskLevel: "read",
        };
        const { host } = createHost({
          async callTool() {
            throw new Error("Tool threw.");
          },
        });
        return {
          task: {
            id: "task_runtime_tool_throw",
            goal: "Use a tool.",
          },
          model: createModeModel({
            plan: planEvents("step_runtime_tool_throw"),
            execute: [{ type: "tool_call.proposed", toolCall }],
          }),
          host,
        };
      },
      expectedError: {
        code: "tool_exception",
        message: "Tool threw.",
      },
    },
    {
      name: "tool error result",
      engineName: "plan-run-review",
      createInput() {
        const toolCall: AgentToolRequest = {
          id: "tool_runtime_error",
          toolName: "repo.read",
          arguments: { path: "README.md" },
          stepId: "step_runtime_tool_error",
          riskLevel: "read",
        };
        const toolError: AgentError = {
          code: "tool_provider_error",
          message: "Tool returned an error.",
        };
        const { host } = createHost({
          async callTool() {
            return {
              id: toolCall.id,
              toolName: toolCall.toolName,
              error: toolError,
            };
          },
        });
        return {
          task: {
            id: "task_runtime_tool_error",
            goal: "Use a tool.",
          },
          model: createModeModel({
            plan: planEvents("step_runtime_tool_error"),
            execute: [{ type: "tool_call.proposed", toolCall }],
          }),
          host,
        };
      },
      expectedError: {
        code: "tool_provider_error",
        message: "Tool returned an error.",
      },
    },
    {
      name: "artifact exception",
      engineName: "classify",
      createInput() {
        const { host } = createHost({
          async createArtifact() {
            throw new Error("Artifact creation failed.");
          },
        });
        return {
          task: {
            id: "task_runtime_artifact_exception",
            goal: "Classify this task.",
          },
          model: createStaticStructuredModel({
            route: "research",
            confidence: 0.8,
          }),
          host,
        };
      },
      expectedError: {
        code: "artifact_exception",
        message: "Artifact creation failed.",
      },
    },
  ])(
    "throws AgentTaskFailedError for $name",
    async ({ engineName, createInput, expectedError }) => {
      let caught: unknown;

      try {
        await new AgentRuntime().runTask(engineName, createInput());
      } catch (error) {
        caught = error;
      }

      expect(caught).toBeInstanceOf(AgentTaskFailedError);
      expect((caught as AgentTaskFailedError).agentError).toMatchObject(
        expectedError,
      );
    },
  );

  test("throws a clear error when the engine does not exist", async () => {
    const { host } = createHost();

    await expect(
      new AgentRuntime().runTask("missing-engine", {
        task: {
          id: "task_missing_engine",
          goal: "Use a missing engine.",
        },
        model: createStaticStructuredModel({}),
        host,
      }),
    ).rejects.toThrow("Unknown agent engine: missing-engine");
  });

  test("throws a clear error when an engine stream ends without task completion", async () => {
    const incompleteEngine: AgentEngine = {
      name: "incomplete",
      async *run(input) {
        const created: AgentEvent = {
          type: "agent.task.created",
          taskId: input.task.id,
          task: input.task,
        };
        await input.host.emit(created);
        yield created;
      },
    };
    const { host } = createHost();

    await expect(
      new AgentRuntime({ engines: [incompleteEngine] }).runTask("incomplete", {
        task: {
          id: "task_incomplete",
          goal: "End without completion.",
        },
        model: createStaticStructuredModel({}),
        host,
      }),
    ).rejects.toThrow(
      "Agent run completed without agent.task.completed event.",
    );
  });
});
