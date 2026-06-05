import type { AgentModelEvent, AgentTraceEvent } from "@aithru/agent-core";
import { ScriptedModelAdapter } from "@aithru/agent-model-test";
import {
  AGENT_DEEP_RESEARCH_NODE_TYPE,
  AGENT_NODE_VERSION,
  registerAgentNodes,
} from "@aithru/node-agent";
import { registerCoreNodes } from "@aithru/nodes-core";
import type { ToolExecutionRequest, ToolExecutionResult } from "@aithru/runtime-core";
import { InMemoryNodeRegistry } from "@aithru/runtime-core";
import { LocalRuntime } from "@aithru/runtime-local";
import type { WorkflowSpec } from "@aithru/spec";

const registry = new InMemoryNodeRegistry();
registerCoreNodes(registry);
registerAgentNodes(registry, {
  resolveModel() {
    return new ScriptedModelAdapter({
      events(input): AgentModelEvent[] {
        if (input.mode === "plan") {
          return [
            {
              type: "structured.output",
              value: {
                id: "plan_deep_research_demo",
                taskId: input.task.id,
                steps: [
                  {
                    id: "step_read_source",
                    title: "Read local source",
                    objective: "Read deterministic local evidence through the workflow tool bridge.",
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
              toolCall: {
                id: "tool_read_runtime_boundary",
                toolName: "local.readSource",
                arguments: { sourceId: "runtime-boundary" },
                reason: "Need deterministic local evidence.",
                stepId: input.step.id,
                riskLevel: "read",
              },
            },
            {
              type: "final",
              output: {
                summary: "Local source was read through ctx.callTool.",
              },
            },
          ];
        }

        if (input.mode === "execute") {
          return [
            {
              type: "structured.output",
              value: {
                title: "Deep Research Workflow Node Report",
                summary:
                  "agent.deepResearch completed inside a formal workflow with local tool execution delegated to LocalRuntime.",
                findings: [
                  {
                    id: "finding_runtime_boundary",
                    claim:
                      "The agent.deepResearch node calls AgentRuntime.runTask while tool execution stays host-owned.",
                    sourceIds: ["source_runtime_boundary"],
                    confidence: 0.91,
                  },
                ],
                sources: [
                  {
                    id: "source_runtime_boundary",
                    title: "Runtime boundary note",
                    uri: "memory://runtime-boundary",
                    content:
                      "Aithru Agent owns intelligent execution inside bounded tasks or nodes.",
                  },
                ],
                limitations: [
                  "This example uses scripted model events and a fake local source.",
                ],
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
                summary: "The research report matches the local evidence.",
              },
            },
          ];
        }

        return [];
      },
    });
  },
});

const workflow: WorkflowSpec = {
  schemaVersion: "aithru.workflow/v0",
  id: "workflow_node_agent_deep_research_demo",
  name: "Node Agent Deep Research Workflow Demo",
  version: "0.1.0",
  nodes: [
    {
      id: "start",
      type: "core.manualTrigger",
      version: "0.1.0",
    },
    {
      id: "research",
      type: AGENT_DEEP_RESEARCH_NODE_TYPE,
      version: AGENT_NODE_VERSION,
      config: {
        goal: "Research the Agent runtime and workflow boundary.",
        model: "scripted-deep-research",
        maxSteps: 1,
        timeoutMs: 5_000,
        allowedTools: ["local.readSource"],
        review: true,
        maxSources: 3,
        maxSearchQueries: 0,
      },
    },
  ],
  edges: [
    {
      id: "edge_start_research",
      from: "start",
      to: "research",
    },
  ],
};

const runtime = new LocalRuntime({
  registry,
  runIdFactory: () => "run_workflow_node_agent_deep_research_demo",
  toolExecutors: [
    {
      toolName: "local.readSource",
      async execute(
        request: ToolExecutionRequest<{ sourceId?: string }>,
      ): Promise<ToolExecutionResult> {
        return {
          output: {
            source: {
              id: "source_runtime_boundary",
              title: "Runtime boundary note",
              uri: `memory://${request.input.sourceId ?? "runtime-boundary"}`,
              content:
                "Aithru Agent owns intelligent execution inside bounded tasks or nodes.",
            },
            finding: {
              id: "finding_runtime_boundary",
              claim:
                "The agent.deepResearch node calls AgentRuntime.runTask while tool execution stays host-owned.",
              sourceIds: ["source_runtime_boundary"],
              confidence: 0.91,
            },
          },
          metadata: {
            source: "local-fixture",
          },
        };
      },
    },
  ],
});

const result = await runtime.run({
  workflow,
  input: {
    request: "Explain how agent.deepResearch fits Aithru workflow boundaries.",
  },
});

const agentEvents = result.events
  .filter((event) => event.type === "log.info")
  .map((event) => event.payload as AgentTraceEvent);
const toolEvents = result.events.filter((event) => event.type.startsWith("tool."));

console.log(JSON.stringify({
  status: result.status,
  output: result.output,
  outputByNode: result.outputByNode,
}, null, 2));

console.log("agent events:");
for (const event of agentEvents) {
  console.log(event.agentEventType);
}

console.log("tool events:");
for (const event of toolEvents) {
  console.log(`${event.type}: ${JSON.stringify(event.payload)}`);
}
