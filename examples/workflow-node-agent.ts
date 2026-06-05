import type { AgentTraceEvent } from "@aithru/agent-core";
import { createStaticStructuredModel } from "@aithru/agent-model-test";
import {
  AGENT_CLASSIFY_NODE_TYPE,
  AGENT_NODE_VERSION,
  registerAgentNodes,
} from "@aithru/node-agent";
import { registerCoreNodes } from "@aithru/nodes-core";
import { InMemoryNodeRegistry } from "@aithru/runtime-core";
import { LocalRuntime } from "@aithru/runtime-local";
import type { WorkflowSpec } from "@aithru/spec";

const registry = new InMemoryNodeRegistry();
registerCoreNodes(registry);
registerAgentNodes(registry, {
  resolveModel() {
    return createStaticStructuredModel({
      route: "research",
      confidence: 0.92,
      reason: "The request needs multi-step analysis.",
    });
  },
});

const workflow: WorkflowSpec = {
  schemaVersion: "aithru.workflow/v0",
  id: "workflow_node_agent_demo",
  name: "Node Agent Workflow Demo",
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
  runIdFactory: () => "run_workflow_node_agent_demo",
});

const result = await runtime.run({
  workflow,
  input: {
    request: "Compare Aithru Agent with DeerFlow.",
  },
});

const agentEvents = result.events
  .filter((event) => event.type === "log.info")
  .map((event) => event.payload as AgentTraceEvent);
const artifactEvents = result.events.filter((event) => event.type === "artifact.created");

console.log(JSON.stringify({
  status: result.status,
  output: result.output,
  outputByNode: result.outputByNode,
}, null, 2));

console.log("agent events:");
for (const event of agentEvents) {
  console.log(event.agentEventType);
}

console.log("artifacts:");
console.log(JSON.stringify(artifactEvents.map((event) => event.payload), null, 2));
