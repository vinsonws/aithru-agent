import type {
  AgentArtifact,
  AgentEvent,
  AgentHost,
  AgentTask,
  AgentToolRequest,
  AgentToolResult,
} from "@aithru/agent-core";
import { ScriptedModelAdapter, createStaticStructuredModel } from "@aithru/model-test";
import { describe, expect, test, vi } from "vitest";
import { ClassifyEngine, PlanRunReviewEngine } from "./index.js";

async function collectEvents(events: AsyncIterable<AgentEvent>) {
  const collected: AgentEvent[] = [];

  for await (const event of events) {
    collected.push(event);
  }

  return collected;
}

function createHost(options: { callTool?: AgentHost["callTool"] } = {}) {
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
    async createArtifact(draft) {
      return {
        id: `artifact_${draft.name ?? "unnamed"}`,
        ...draft,
      };
    },
  };

  return { emitted, host, callTool };
}

describe("ClassifyEngine", () => {
  test("completes a classification task and emits task completion", async () => {
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
    expect(emitted.map((event) => event.type)).toEqual([
      "agent.task.created",
      "agent.artifact.created",
      "agent.task.completed",
    ]);
  });
});

describe("PlanRunReviewEngine", () => {
  test("plans, executes through AgentHost.callTool, creates an artifact, reviews, and completes", async () => {
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
    const callTool = vi.fn(async (request: AgentToolRequest): Promise<AgentToolResult> => {
      expect(request).toEqual(toolCall);
      return toolResult;
    });
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
    expect(callTool).toHaveBeenCalledTimes(1);
    expect(callTool).toHaveBeenCalledWith(toolCall);
    expect(events.find((event) => event.type === "agent.tool.completed")).toMatchObject({
      type: "agent.tool.completed",
      result: toolResult,
    });

    const artifactEvent = events.find(
      (event): event is Extract<AgentEvent, { type: "agent.artifact.created" }> =>
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
    expect(emitted.map((event) => event.type)).toEqual([
      "agent.task.created",
      ...events.map((event) => event.type),
    ]);
  });
});
