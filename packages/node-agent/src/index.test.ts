import type {
  AgentModelEvent,
  AgentModelInput,
  AgentTraceEvent,
  AgentToolRequest,
} from "@aithru/agent-core";
import { ScriptedModelAdapter, createStaticStructuredModel } from "@aithru/agent-model-test";
import { AgentRuntime, AgentTaskFailedError } from "@aithru/agent-runtime";
import type {
  ExecutionEventInput,
  NodeExecutionContext,
  ToolExecutionRequest,
  ToolExecutionResult,
} from "@aithru/runtime-core";
import { InMemoryNodeRegistry } from "@aithru/runtime-core";
import { describe, expect, test, vi } from "vitest";
import {
  AGENT_CLASSIFY_NODE_TYPE,
  AGENT_NODE_VERSION,
  AGENT_TASK_NODE_TYPE,
  createAgentClassifyNode,
  createAgentTaskNode,
  registerAgentNodes,
} from "@aithru/node-agent";

function createContext(options: { callTool?: NodeExecutionContext["callTool"] } = {}) {
  const emitted: ExecutionEventInput[] = [];
  const artifactInputs: unknown[] = [];
  let artifactSequence = 0;

  const ctx: NodeExecutionContext = {
    runId: "run_test",
    workflowId: "workflow_test",
    nodeId: "node_test",
    async emit(event) {
      emitted.push(event);
    },
    async getSecret() {
      throw new Error("Secrets are not used by agent node tests.");
    },
    async createArtifact(input) {
      artifactSequence += 1;
      artifactInputs.push(input);
      return {
        id: `artifact_${artifactSequence}`,
        uri: `memory://${input.name ?? artifactSequence}`,
        ...(input.contentType ? { contentType: input.contentType } : {}),
        ...(input.metadata ? { metadata: input.metadata } : {}),
      };
    },
    ...(options.callTool ? { callTool: options.callTool } : {}),
  };

  return { artifactInputs, ctx, emitted };
}

function agentEventTypes(emitted: ExecutionEventInput[]) {
  return agentTraceEvents(emitted).map((event) => event.agentEventType);
}

function agentTraceEvents(emitted: ExecutionEventInput[]) {
  return emitted.map((event) => event.payload as AgentTraceEvent);
}

function createModeModel(eventsByMode: Partial<Record<AgentModelInput["mode"], AgentModelEvent[]>>) {
  return new ScriptedModelAdapter({
    events(input) {
      return eventsByMode[input.mode] ?? [];
    },
  });
}

function planEvents(stepId = "step_1"): AgentModelEvent[] {
  return [
    {
      type: "structured.output",
      value: {
        id: "plan_test",
        taskId: "task_test",
        steps: [
          {
            id: stepId,
            title: "Read context",
            objective: "Read context with a bounded task-local step.",
            allowedTools: ["repo.read"],
          },
        ],
      },
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

describe("agent node factories", () => {
  test("createAgentClassifyNode returns the public node definition metadata", () => {
    const node = createAgentClassifyNode({
      resolveModel: vi.fn(),
    });

    expect(node).toMatchObject({
      type: AGENT_CLASSIFY_NODE_TYPE,
      version: AGENT_NODE_VERSION,
      category: "agent",
    });
  });

  test("createAgentTaskNode returns the public node definition metadata", () => {
    const node = createAgentTaskNode({
      resolveModel: vi.fn(),
    });

    expect(node).toMatchObject({
      type: AGENT_TASK_NODE_TYPE,
      version: AGENT_NODE_VERSION,
      category: "agent",
    });
  });

  test("registerAgentNodes registers classify and task nodes", () => {
    const registry = new InMemoryNodeRegistry();

    registerAgentNodes(registry, {
      resolveModel: vi.fn(),
    });

    expect(registry.resolve(AGENT_CLASSIFY_NODE_TYPE, AGENT_NODE_VERSION)).toBeDefined();
    expect(registry.resolve(AGENT_TASK_NODE_TYPE, AGENT_NODE_VERSION)).toBeDefined();
  });
});

describe("agent.classify node", () => {
  test("resolves a model, runs the classify engine, returns classification output, and emits agent events", async () => {
    const runtime = new AgentRuntime();
    const runTask = vi.spyOn(runtime, "runTask");
    const model = createStaticStructuredModel({
      route: "research",
      confidence: 0.92,
      reason: "Needs multi-step analysis.",
    });
    const resolveModel = vi.fn(async () => model);
    const node = createAgentClassifyNode({ runtime, resolveModel });
    const { ctx, emitted } = createContext();
    const input = { request: "Classify this work." };
    const outputSchema = { type: "object" };

    const result = await node.execute(ctx, input, {
      goal: "Classify this task.",
      routes: ["research", "direct"],
      model: "test-model",
      outputSchema,
    });

    expect(resolveModel).toHaveBeenCalledWith({
      model: "test-model",
      nodeType: AGENT_CLASSIFY_NODE_TYPE,
      nodeId: "node_test",
      workflowId: "workflow_test",
      runId: "run_test",
    });
    expect(runTask).toHaveBeenCalledWith(
      "classify",
      expect.objectContaining({
        model,
        task: expect.objectContaining({
          id: "run_test:node_test",
          goal: "Classify this task.",
          input,
          outputSchema,
        }),
      }),
    );
    expect(result.output).toEqual({
      route: "research",
      confidence: 0.92,
      reason: "Needs multi-step analysis.",
    });
    expect(emitted.map((event) => event.type)).toEqual([
      "log.info",
      "log.info",
      "log.info",
    ]);
    expect(agentEventTypes(emitted)).toEqual([
      "agent.task.created",
      "agent.artifact.created",
      "agent.task.completed",
    ]);
    expect(
      agentTraceEvents(emitted).map((event) => ({
        kind: event.kind,
        phase: event.phase,
      })),
    ).toEqual([
      { kind: "agent.task", phase: "created" },
      { kind: "agent.artifact", phase: "created" },
      { kind: "agent.task", phase: "completed" },
    ]);
    expect(emitted[0]?.metadata).toMatchObject({
      agentEventType: "agent.task.created",
      agentTraceKind: "agent.task",
      agentTracePhase: "created",
    });
    expect(agentTraceEvents(emitted)[0]?.payload.type).toBe("agent.task.created");
  });

  test("fails clearly when the classify runtime task fails", async () => {
    const node = createAgentClassifyNode({
      resolveModel: async () =>
        new ScriptedModelAdapter({
          events: [
            {
              type: "error",
              error: {
                code: "provider_error",
                message: "Provider failed.",
              },
            },
          ],
        }),
    });
    const { ctx } = createContext();

    await expect(
      node.execute(ctx, {}, { goal: "Classify this task.", routes: ["research"] }),
    ).rejects.toThrow(AgentTaskFailedError);
  });
});

describe("agent.task node", () => {
  test("resolves a model, runs plan-run-review, returns task output, and emits agent events", async () => {
    const runtime = new AgentRuntime();
    const runTask = vi.spyOn(runtime, "runTask");
    const model = createModeModel({
      plan: planEvents("step_read"),
      execute: [{ type: "final", output: { summary: "Step completed." } }],
      review: reviewPassedEvents(),
    });
    const resolveModel = vi.fn(async () => model);
    const node = createAgentTaskNode({ runtime, resolveModel });
    const { ctx, emitted } = createContext();

    const result = await node.execute(ctx, { path: "README.md" }, {
      goal: "Read the README.",
      model: "test-model",
      review: true,
    });

    expect(resolveModel).toHaveBeenCalledWith({
      model: "test-model",
      nodeType: AGENT_TASK_NODE_TYPE,
      nodeId: "node_test",
      workflowId: "workflow_test",
      runId: "run_test",
    });
    expect(runTask).toHaveBeenCalledWith(
      "plan-run-review",
      expect.objectContaining({
        model,
        task: expect.objectContaining({
          id: "run_test:node_test",
          goal: "Read the README.",
          input: { path: "README.md" },
        }),
        options: expect.objectContaining({
          review: true,
        }),
      }),
    );
    expect(result.output).toMatchObject({
      status: "completed",
      summary: "The task completed successfully.",
      review: {
        status: "passed",
      },
    });
    expect(agentEventTypes(emitted)).toEqual([
      "agent.task.created",
      "agent.plan.started",
      "agent.plan.completed",
      "agent.step.started",
      "agent.artifact.created",
      "agent.review.started",
      "agent.review.completed",
      "agent.task.completed",
    ]);
  });

  test("bridges model-proposed tool calls through NodeExecutionContext.callTool", async () => {
    const toolCall: AgentToolRequest = {
      id: "tool_read",
      toolName: "repo.read",
      arguments: { path: "README.md" },
      reason: "Need repository context.",
      stepId: "step_read",
      riskLevel: "read",
    };
    const callTool = vi.fn(
      async (
        _request: ToolExecutionRequest,
      ): Promise<ToolExecutionResult<unknown>> => ({
        output: { content: "# README" },
        metadata: { source: "mock" },
      }),
    );
    const node = createAgentTaskNode({
      resolveModel: async () =>
        createModeModel({
          plan: planEvents("step_read"),
          execute: [
            { type: "tool_call.proposed", toolCall },
            { type: "final", output: { summary: "README was read." } },
          ],
          review: reviewPassedEvents(),
        }),
    });
    const { ctx, emitted } = createContext({
      callTool: callTool as NodeExecutionContext["callTool"],
    });

    const result = await node.execute(ctx, {}, { goal: "Read the README." });

    expect(callTool).toHaveBeenCalledTimes(1);
    expect(callTool).toHaveBeenCalledWith({
      toolName: "repo.read",
      input: { path: "README.md" },
      riskLevel: "low",
      metadata: {
        agentToolCallId: "tool_read",
        reason: "Need repository context.",
        stepId: "step_read",
      },
    });
    expect(result.output).toMatchObject({
      status: "completed",
      summary: "The task completed successfully.",
    });

    const toolTraces = agentTraceEvents(emitted).filter(
      (event) => event.kind === "agent.tool",
    );
    expect(
      toolTraces.map((event) => ({
        agentEventType: event.agentEventType,
        phase: event.phase,
        stepId: event.stepId,
        toolName: event.toolName,
      })),
    ).toEqual([
      {
        agentEventType: "agent.tool.proposed",
        phase: "proposed",
        stepId: "step_read",
        toolName: "repo.read",
      },
      {
        agentEventType: "agent.tool.completed",
        phase: "completed",
        stepId: "step_read",
        toolName: "repo.read",
      },
    ]);
    expect(
      emitted.find((event) => event.metadata?.agentEventType === "agent.tool.proposed")
        ?.metadata,
    ).toMatchObject({
      agentEventType: "agent.tool.proposed",
      agentTraceKind: "agent.tool",
      agentTracePhase: "proposed",
    });
  });

  test("fails clearly when a model proposes a tool call and ctx.callTool is missing", async () => {
    const node = createAgentTaskNode({
      resolveModel: async () =>
        createModeModel({
          plan: planEvents("step_read"),
          execute: [
            {
              type: "tool_call.proposed",
              toolCall: {
                id: "tool_read",
                toolName: "repo.read",
                arguments: { path: "README.md" },
                riskLevel: "read",
              },
            },
          ],
        }),
    });
    const { ctx } = createContext();

    await expect(node.execute(ctx, {}, { goal: "Read the README." })).rejects.toThrow(
      "Agent node requires NodeExecutionContext.callTool to execute tools.",
    );
  });
});
