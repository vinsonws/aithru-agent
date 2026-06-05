import type { AgentTraceEvent } from "@aithru/agent-core";
import type {
  ExecutionEventInput,
  NodeDefinition,
  NodeExecutionContext,
  NodeRegistry,
  ToolCallInput,
  ToolCallResult,
} from "@aithru/runtime-core";
import { ScriptedModelAdapter, createStaticStructuredModel } from "@aithru/agent-model-test";
import {
  AGENT_CLASSIFY_NODE_TYPE,
  AGENT_NODE_VERSION,
  AGENT_TASK_NODE_TYPE,
  registerAgentNodes,
} from "@aithru/node-agent";

class ExampleRegistry implements NodeRegistry {
  private readonly nodes = new Map<string, NodeDefinition>();

  register(node: NodeDefinition): void {
    this.nodes.set(`${node.type}@${node.version}`, node);
  }

  resolve(type: string, version: string): NodeDefinition | undefined {
    return this.nodes.get(`${type}@${version}`);
  }

  require(type: string, version: string): NodeDefinition {
    const node = this.resolve(type, version);
    if (!node) {
      throw new Error(`Node not registered: ${type}@${version}`);
    }

    return node;
  }

  list(): NodeDefinition[] {
    return [...this.nodes.values()];
  }
}

const registry = new ExampleRegistry();

registerAgentNodes(registry, {
  resolveModel(input) {
    if (input.nodeType === AGENT_CLASSIFY_NODE_TYPE) {
      return createStaticStructuredModel({
        route: "research",
        confidence: 0.92,
        reason: "The request needs multi-step analysis.",
      });
    }

    return new ScriptedModelAdapter({
      events(modelInput) {
        if (modelInput.mode === "plan") {
          return [
            {
              type: "structured.output",
              value: {
                steps: [
                  {
                    id: "step_read_readme",
                    title: "Read README",
                    objective: "Read the repository README.",
                    allowedTools: ["repo.read"],
                  },
                ],
              },
            },
          ];
        }

        if (modelInput.mode === "execute") {
          return [
            {
              type: "tool_call.proposed",
              toolCall: {
                id: "tool_read_readme",
                toolName: "repo.read",
                arguments: { path: "README.md" },
                reason: "Need repository context.",
                riskLevel: "read",
              },
            },
            {
              type: "final",
              output: {
                summary: "README was read successfully.",
              },
            },
          ];
        }

        if (modelInput.mode === "review") {
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
  },
});

const emitted: ExecutionEventInput[] = [];
let artifactSequence = 0;

const ctx: NodeExecutionContext = {
  runId: "run_node_agent_basic",
  workflowId: "workflow_node_agent_basic",
  nodeId: "agent_node",
  async emit(event) {
    emitted.push(event);
    const trace = event.payload as Partial<AgentTraceEvent>;
    console.log(trace.agentEventType ?? event.type);
  },
  async getSecret() {
    throw new Error("This example does not use secrets.");
  },
  async createArtifact(input) {
    artifactSequence += 1;
    return {
      id: `artifact_${artifactSequence}`,
      uri: `memory://${input.name ?? artifactSequence}`,
      ...(input.contentType ? { contentType: input.contentType } : {}),
      ...(input.metadata ? { metadata: input.metadata } : {}),
    };
  },
  async callTool<TInput = unknown, TOutput = unknown>(
    request: ToolCallInput<TInput>,
  ): Promise<ToolCallResult<TOutput>> {
    return {
      output: {
        path: request.input,
        content: "# Demo README\n\nAithru Agent node integration demo.",
      } as TOutput,
      metadata: {
        toolName: request.toolName,
      },
    };
  },
};

const classifyNode = registry.require(AGENT_CLASSIFY_NODE_TYPE, AGENT_NODE_VERSION);
const classifyResult = await classifyNode.execute(
  ctx,
  "Compare Aithru Agent with DeerFlow.",
  {
    goal: "Classify the request into direct or research.",
    routes: ["direct", "research"],
    model: "scripted-classifier",
  },
);

console.log(JSON.stringify(classifyResult.output, null, 2));

const taskNode = registry.require(AGENT_TASK_NODE_TYPE, AGENT_NODE_VERSION);
const taskResult = await taskNode.execute(
  ctx,
  { path: "README.md" },
  {
    goal: "Read the README and summarize it.",
    model: "scripted-plan-run-review",
    review: true,
  },
);

console.log(JSON.stringify(taskResult.output, null, 2));
console.log(`emitted ${emitted.length} bridged agent events`);
