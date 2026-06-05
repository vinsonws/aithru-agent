import type { AgentTraceEvent } from "@aithru/agent-core";
import { createStaticStructuredModel } from "@aithru/agent-model-test";
import { registerCoreNodes } from "@aithru/nodes-core";
import { InMemoryNodeRegistry } from "@aithru/runtime-core";
import { LocalRuntime } from "@aithru/runtime-local";
import type { WorkflowSpec } from "@aithru/spec";
import { describe, expect, test, vi } from "vitest";
import {
  AGENT_CLASSIFY_NODE_TYPE,
  AGENT_NODE_VERSION,
  registerAgentNodes,
} from "@aithru/node-agent";

describe("Aithru Core workflow integration", () => {
  test("runs agent.classify as a formal WorkflowSpec node through LocalRuntime", async () => {
    const registry = new InMemoryNodeRegistry();
    registerCoreNodes(registry);

    const model = createStaticStructuredModel({
      route: "research",
      confidence: 0.92,
      reason: "Needs multi-step analysis.",
    });
    const resolveModel = vi.fn(async () => model);
    registerAgentNodes(registry, { resolveModel });

    const workflow: WorkflowSpec = {
      schemaVersion: "aithru.workflow/v0",
      id: "workflow_agent_classify_integration",
      name: "Agent Classify Integration",
      version: "0.1.0",
      nodes: [
        {
          id: "start",
          type: "core.manualTrigger",
          version: "0.1.0",
        },
        {
          id: "classify",
          type: AGENT_CLASSIFY_NODE_TYPE,
          version: AGENT_NODE_VERSION,
          config: {
            goal: "Classify the incoming workflow request.",
            routes: ["direct", "research"],
            model: "scripted-classifier",
          },
        },
      ],
      edges: [
        {
          id: "edge_start_classify",
          from: "start",
          to: "classify",
        },
      ],
    };

    const runtime = new LocalRuntime({
      registry,
      runIdFactory: () => "run_workflow_agent_classify",
    });
    const result = await runtime.run({
      workflow,
      input: {
        request: "Compare Aithru Agent with DeerFlow.",
      },
    });

    expect(result.status).toBe("completed");
    expect(result.output).toEqual({
      route: "research",
      confidence: 0.92,
      reason: "Needs multi-step analysis.",
    });
    expect(result.outputByNode).toMatchObject({
      start: {
        request: "Compare Aithru Agent with DeerFlow.",
      },
      classify: {
        route: "research",
        confidence: 0.92,
      },
    });
    expect(resolveModel).toHaveBeenCalledWith({
      model: "scripted-classifier",
      nodeType: AGENT_CLASSIFY_NODE_TYPE,
      nodeId: "classify",
      workflowId: workflow.id,
      runId: "run_workflow_agent_classify",
    });

    const agentEvents = result.events
      .filter((event) => event.type === "log.info")
      .map((event) => event.payload as AgentTraceEvent);
    expect(agentEvents.map((event) => event.agentEventType)).toEqual([
      "agent.task.created",
      "agent.artifact.created",
      "agent.task.completed",
    ]);
    expect(agentEvents.map((event) => event.kind)).toEqual([
      "agent.task",
      "agent.artifact",
      "agent.task",
    ]);
  });
});
