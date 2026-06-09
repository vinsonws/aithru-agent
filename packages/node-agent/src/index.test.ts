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
  AGENT_DEEP_RESEARCH_NODE_TYPE,
  AGENT_NODE_VERSION,
  AGENT_TASK_NODE_TYPE,
  createAgentClassifyNode,
  createAgentDeepResearchNode,
  createAgentTaskNode,
  isAgentNodeType,
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

function deepResearchModel(
  overrides: Partial<Record<AgentModelInput["mode"], (input: AgentModelInput) => AgentModelEvent[]>> = {},
) {
  return new ScriptedModelAdapter({
    events(input) {
      const override = overrides[input.mode];
      if (override) {
        return override(input);
      }

      if (input.mode === "plan") {
        return planEvents("step_source");
      }

      if (input.mode === "execute" && input.step) {
        return [
          {
            type: "final",
            output: {
              sources: [
                {
                  id: "source_local",
                  title: "Local source",
                  uri: "memory://source",
                  content: "Local evidence.",
                },
              ],
              findings: [
                {
                  id: "finding_local",
                  claim: "Local evidence supports the answer.",
                  sourceIds: ["source_local"],
                  confidence: 0.9,
                },
              ],
            },
          },
        ];
      }

      if (input.mode === "execute") {
        return [
          {
            type: "structured.output",
            value: {
              title: "Research report",
              summary: "Research completed from deterministic local evidence.",
              findings: [
                {
                  id: "finding_local",
                  claim: "Local evidence supports the answer.",
                  sourceIds: ["source_local"],
                  confidence: 0.9,
                },
              ],
              sources: [
                {
                  id: "source_local",
                  title: "Local source",
                  uri: "memory://source",
                  content: "Local evidence.",
                },
              ],
              limitations: ["No external search was used."],
            },
          },
        ];
      }

      if (input.mode === "review") {
        return reviewPassedEvents();
      }

      return [];
    },
  });
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

  test("createAgentDeepResearchNode returns the public node definition metadata", () => {
    const node = createAgentDeepResearchNode({
      resolveModel: vi.fn(),
    });

    expect(node).toMatchObject({
      type: AGENT_DEEP_RESEARCH_NODE_TYPE,
      version: AGENT_NODE_VERSION,
      category: "agent",
    });
  });

  test("registerAgentNodes registers classify, task, and deep research nodes", () => {
    const registry = new InMemoryNodeRegistry();

    registerAgentNodes(registry, {
      resolveModel: vi.fn(),
    });

    expect(registry.resolve(AGENT_CLASSIFY_NODE_TYPE, AGENT_NODE_VERSION)).toBeDefined();
    expect(registry.resolve(AGENT_TASK_NODE_TYPE, AGENT_NODE_VERSION)).toBeDefined();
    expect(registry.resolve(AGENT_DEEP_RESEARCH_NODE_TYPE, AGENT_NODE_VERSION)).toBeDefined();
  });

  test("isAgentNodeType includes deep research", () => {
    expect(isAgentNodeType(AGENT_CLASSIFY_NODE_TYPE)).toBe(true);
    expect(isAgentNodeType(AGENT_TASK_NODE_TYPE)).toBe(true);
    expect(isAgentNodeType(AGENT_DEEP_RESEARCH_NODE_TYPE)).toBe(true);
    expect(isAgentNodeType("core.manualTrigger")).toBe(false);
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

describe("agent.deepResearch node", () => {
  test("resolves a model, runs deep-research, passes research options, returns research output, and emits agent events", async () => {
    const runtime = new AgentRuntime();
    const runTask = vi.spyOn(runtime, "runTask");
    const model = deepResearchModel();
    const resolveModel = vi.fn(async () => model);
    const node = createAgentDeepResearchNode({ runtime, resolveModel });
    const { ctx, emitted } = createContext();
    const input = { topic: "Agent runtime boundaries" };
    const outputSchema = { type: "object" };

    const result = await node.execute(ctx, input, {
      goal: "Research the Agent runtime boundary.",
      model: "test-research-model",
      maxSteps: 2,
      timeoutMs: 1_000,
      allowedTools: ["local.readSource"],
      review: true,
      maxSources: 3,
      maxSearchQueries: 4,
      outputSchema,
    });

    expect(resolveModel).toHaveBeenCalledWith({
      model: "test-research-model",
      nodeType: AGENT_DEEP_RESEARCH_NODE_TYPE,
      nodeId: "node_test",
      workflowId: "workflow_test",
      runId: "run_test",
    });
    expect(runTask).toHaveBeenCalledWith(
      "deep-research",
      expect.objectContaining({
        model,
        task: expect.objectContaining({
          id: "run_test:node_test",
          goal: "Research the Agent runtime boundary.",
          input,
          outputSchema,
        }),
        options: {
          maxSteps: 2,
          timeoutMs: 1_000,
          allowedTools: ["local.readSource"],
          review: true,
          maxSources: 3,
          maxSearchQueries: 4,
        },
      }),
    );
    expect(result.output).toMatchObject({
      status: "completed",
      summary: "Research completed from deterministic local evidence.",
      metadata: {
        research: {
          title: "Research report",
          summary: "Research completed from deterministic local evidence.",
          sources: [
            expect.objectContaining({
              id: "source_local",
            }),
          ],
        },
      },
      review: {
        status: "passed",
      },
    });
    expect(result.metadata).toMatchObject({
      agentTaskId: "run_test:node_test",
      summary: "Research completed from deterministic local evidence.",
      research: {
        title: "Research report",
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

  test("bridges deep research tool calls through NodeExecutionContext.callTool", async () => {
    const toolCall: AgentToolRequest = {
      id: "tool_local_source",
      toolName: "local.readSource",
      arguments: { sourceId: "runtime-boundary" },
      reason: "Need local source evidence.",
      stepId: "step_source",
      riskLevel: "dangerous",
    };
    const callTool = vi.fn(
      async (
        _request: ToolExecutionRequest,
      ): Promise<ToolExecutionResult<unknown>> => ({
        output: {
          source: {
            id: "source_runtime",
            title: "Runtime boundary note",
            uri: "memory://runtime-boundary",
            content: "Agent runtime owns bounded intelligent execution.",
          },
          finding: {
            id: "finding_runtime",
            claim: "Tool execution remains host-owned.",
            sourceIds: ["source_runtime"],
            confidence: 0.91,
          },
        },
        metadata: { source: "mock" },
      }),
    );
    const node = createAgentDeepResearchNode({
      resolveModel: async () =>
        deepResearchModel({
          plan() {
            return [
              {
                type: "structured.output",
                value: {
                  id: "plan_test",
                  taskId: "task_test",
                  steps: [
                    {
                      id: "step_source",
                      title: "Read local source",
                      objective: "Read a local source.",
                      allowedTools: ["local.readSource"],
                    },
                  ],
                },
              },
            ];
          },
          execute(input) {
            if (input.step) {
              return [
                { type: "tool_call.proposed", toolCall },
                { type: "final", output: { summary: "Local source read." } },
              ];
            }

            return [
              {
                type: "structured.output",
                value: {
                  title: "Tool bridge report",
                  summary: "Research used the core tool bridge.",
                  findings: [
                    {
                      id: "finding_runtime",
                      claim: "Tool execution remains host-owned.",
                      sourceIds: ["source_runtime"],
                      confidence: 0.91,
                    },
                  ],
                  sources: [
                    {
                      id: "source_runtime",
                      title: "Runtime boundary note",
                      uri: "memory://runtime-boundary",
                    },
                  ],
                },
              },
            ];
          },
        }),
    });
    const { ctx, emitted } = createContext({
      callTool: callTool as NodeExecutionContext["callTool"],
    });

    const result = await node.execute(ctx, {}, {
      goal: "Research local sources.",
      review: false,
    });

    expect(callTool).toHaveBeenCalledTimes(1);
    expect(callTool).toHaveBeenCalledWith({
      toolName: "local.readSource",
      input: { sourceId: "runtime-boundary" },
      riskLevel: "high",
      metadata: {
        agentToolCallId: "tool_local_source",
        reason: "Need local source evidence.",
        stepId: "step_source",
      },
    });
    expect(result.output).toMatchObject({
      status: "completed",
      summary: "Research used the core tool bridge.",
      metadata: {
        research: {
          title: "Tool bridge report",
        },
      },
    });
    expect(agentEventTypes(emitted)).toContain("agent.tool.proposed");
    expect(agentEventTypes(emitted)).toContain("agent.tool.completed");
  });

  test("fails clearly when deep research proposes a tool call and ctx.callTool is missing", async () => {
    const node = createAgentDeepResearchNode({
      resolveModel: async () =>
        deepResearchModel({
          plan() {
            return [
              {
                type: "structured.output",
                value: {
                  id: "plan_test",
                  taskId: "task_test",
                  steps: [
                    {
                      id: "step_source",
                      title: "Read local source",
                      objective: "Read a local source.",
                      allowedTools: ["local.readSource"],
                    },
                  ],
                },
              },
            ];
          },
          execute(input) {
            if (!input.step) {
              return [];
            }

            return [
              {
                type: "tool_call.proposed",
                toolCall: {
                  id: "tool_local_source",
                  toolName: "local.readSource",
                  arguments: { sourceId: "runtime-boundary" },
                  riskLevel: "read",
                },
              },
            ];
          },
        }),
    });
    const { ctx } = createContext();

    await expect(
      node.execute(ctx, {}, { goal: "Research local sources." }),
    ).rejects.toThrow(
      "Agent node requires NodeExecutionContext.callTool to execute tools.",
    );
  });

  test("rejects with AgentTaskFailedError when deep research model yields an error", async () => {
    const node = createAgentDeepResearchNode({
      resolveModel: async () =>
        deepResearchModel({
          plan() {
            return [
              {
                type: "error",
                error: {
                  code: "provider_error",
                  message: "Provider failed.",
                },
              },
            ];
          },
        }),
    });
    const { ctx } = createContext();

    await expect(
      node.execute(ctx, {}, { goal: "Research local sources." }),
    ).rejects.toThrow(AgentTaskFailedError);
  });

  test("passes toolRiskPolicy from config to runtime options", async () => {
    const runtime = new AgentRuntime();
    const runTask = vi.spyOn(runtime, "runTask");
    const policy = { byRiskLevel: { write: "deny" as const } };
    const node = createAgentDeepResearchNode({
      runtime,
      resolveModel: async () => deepResearchModel(),
    });
    const { ctx } = createContext();

    await node.execute(ctx, {}, {
      goal: "Research with risk policy.",
      toolRiskPolicy: policy,
    });

    expect(runTask).toHaveBeenCalledWith(
      "deep-research",
      expect.objectContaining({
        options: expect.objectContaining({
          toolRiskPolicy: policy,
        }),
      }),
    );
  });

  test("returns paused output when deep research tool requires approval", async () => {
    const toolCall: AgentToolRequest = {
      id: "tool_dangerous",
      toolName: "repo.delete",
      arguments: { path: "x" },
      stepId: "step_source",
      riskLevel: "dangerous",
    };
    const callTool = vi.fn(
      async (): Promise<{ output: unknown; metadata?: Record<string, unknown> }> => ({
        output: { ok: true },
      }),
    );
    const node = createAgentDeepResearchNode({
      resolveModel: async () =>
        deepResearchModel({
          plan() {
            return [
              {
                type: "structured.output",
                value: {
                  id: "plan_test",
                  taskId: "task_test",
                  steps: [
                    {
                      id: "step_source",
                      title: "Source step",
                      objective: "Read source.",
                      allowedTools: ["repo.delete"],
                    },
                  ],
                },
              },
            ];
          },
          execute(input) {
            if (input.step) {
              return [
                { type: "tool_call.proposed", toolCall },
                { type: "final", output: { summary: "Step done." } },
              ];
            }

            return [
              {
                type: "structured.output",
                value: { title: "R", summary: "Done.", findings: [], sources: [] },
              },
            ];
          },
        }),
    });
    const { ctx, emitted } = createContext({
      callTool: callTool as NodeExecutionContext["callTool"],
    });

    const result = await node.execute(ctx, {}, {
      goal: "Research with approval.",
      allowedTools: ["repo.delete"],
      toolRiskPolicy: { byRiskLevel: { dangerous: "require_approval" } },
      review: false,
    });

    expect(result.output?.status).toBe("paused");
    expect(result.output?.metadata?.approval).toBeDefined();
    expect(result.output?.resumeState).toBeDefined();
    expect(callTool).not.toHaveBeenCalled();
    expect(agentEventTypes(emitted)).toContain("agent.tool.approval_requested");
    expect(agentEventTypes(emitted)).toContain("agent.task.paused");
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

  test("rejects with tool_not_allowed when config.allowedTools blocks the proposed tool and ctx.callTool is not invoked", async () => {
    const toolCall: AgentToolRequest = {
      id: "tool_write",
      toolName: "repo.write",
      arguments: { path: "README.md", content: "x" },
      stepId: "step_read",
      riskLevel: "write",
    };
    const callTool = vi.fn(
      async (): Promise<{ output: unknown; metadata?: Record<string, unknown> }> => ({
        output: { ok: true },
      }),
    );
    const node = createAgentTaskNode({
      resolveModel: async () =>
        createModeModel({
          plan: planEvents("step_read"),
          execute: [
            { type: "tool_call.proposed", toolCall },
            { type: "final", output: { summary: "Done." } },
          ],
        }),
    });
    const { ctx } = createContext({
      callTool: callTool as NodeExecutionContext["callTool"],
    });

    let caught: unknown;
    try {
      await node.execute(ctx, {}, {
        goal: "Read the README.",
        allowedTools: ["repo.read"],
      });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(AgentTaskFailedError);
    expect((caught as AgentTaskFailedError).agentError).toMatchObject({
      code: "tool_not_allowed",
      message: expect.stringContaining("repo.write"),
    });
    expect(callTool).not.toHaveBeenCalled();
  });

  test("passes toolRiskPolicy from config to runtime options", async () => {
    const runtime = new AgentRuntime();
    const runTask = vi.spyOn(runtime, "runTask");
    const policy = { byRiskLevel: { write: "deny" as const } };
    const node = createAgentTaskNode({
      runtime,
      resolveModel: async () =>
        createModeModel({
          plan: planEvents("step_1"),
          execute: [{ type: "final", output: { summary: "Done." } }],
        }),
    });
    const { ctx } = createContext();

    await node.execute(ctx, {}, {
      goal: "Task with risk policy.",
      toolRiskPolicy: policy,
    });

    expect(runTask).toHaveBeenCalledWith(
      "plan-run-review",
      expect.objectContaining({
        options: expect.objectContaining({
          toolRiskPolicy: policy,
        }),
      }),
    );
  });

  test("rejects with tool_risk_denied when toolRiskPolicy.byRiskLevel denies the tool and ctx.callTool is not invoked", async () => {
    const toolCall: AgentToolRequest = {
      id: "tool_write",
      toolName: "repo.write",
      arguments: { path: "README.md", content: "x" },
      stepId: "step_write",
      riskLevel: "write",
    };
    const callTool = vi.fn(
      async (): Promise<{ output: unknown; metadata?: Record<string, unknown> }> => ({
        output: { ok: true },
      }),
    );
    const node = createAgentTaskNode({
      resolveModel: async () =>
        createModeModel({
          plan: [
            {
              type: "structured.output",
              value: {
                id: "plan_test",
                taskId: "task_test",
                steps: [
                  {
                    id: "step_write",
                    title: "Write step",
                    objective: "Write something.",
                    allowedTools: ["repo.write"],
                  },
                ],
              },
            },
          ],
          execute: [
            { type: "tool_call.proposed", toolCall },
            { type: "final", output: { summary: "Done." } },
          ],
        }),
    });
    const { ctx } = createContext({
      callTool: callTool as NodeExecutionContext["callTool"],
    });

    let caught: unknown;
    try {
      await node.execute(ctx, {}, {
        goal: "Write the README.",
        allowedTools: ["repo.write"],
        toolRiskPolicy: { byRiskLevel: { write: "deny" } },
      });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(AgentTaskFailedError);
    expect((caught as AgentTaskFailedError).agentError).toMatchObject({
      code: "tool_risk_denied",
      message: expect.stringContaining("repo.write"),
    });
    expect(callTool).not.toHaveBeenCalled();
  });

  test("returns paused output when tool requires approval, ctx.callTool not invoked", async () => {
    const toolCall: AgentToolRequest = {
      id: "tool_dangerous",
      toolName: "repo.delete",
      arguments: { path: "important.md" },
      stepId: "step_del",
      riskLevel: "dangerous",
    };
    const callTool = vi.fn(
      async (): Promise<{ output: unknown; metadata?: Record<string, unknown> }> => ({
        output: { ok: true },
      }),
    );
    const node = createAgentTaskNode({
      resolveModel: async () =>
        createModeModel({
          plan: [
            {
              type: "structured.output",
              value: {
                id: "plan_test",
                taskId: "task_test",
                steps: [
                  {
                    id: "step_del",
                    title: "Delete step",
                    objective: "Delete something.",
                    allowedTools: ["repo.delete"],
                  },
                ],
              },
            },
          ],
          execute: [
            { type: "tool_call.proposed", toolCall },
            { type: "final", output: { summary: "Done." } },
          ],
        }),
    });
    const { ctx, emitted } = createContext({
      callTool: callTool as NodeExecutionContext["callTool"],
    });

    const result = await node.execute(ctx, {}, {
      goal: "Delete a file.",
      allowedTools: ["repo.delete"],
      toolRiskPolicy: { byRiskLevel: { dangerous: "require_approval" } },
    });

    expect(result.output?.status).toBe("paused");
    expect(result.output?.metadata?.approval).toBeDefined();
    expect(result.output?.resumeState).toBeDefined();
    expect(result.output?.resumeState?.phase).toBe("plan-run-review.step");
    expect(callTool).not.toHaveBeenCalled();
    expect(agentEventTypes(emitted)).toContain("agent.tool.approval_requested");
    expect(agentEventTypes(emitted)).toContain("agent.task.paused");
  });
});
