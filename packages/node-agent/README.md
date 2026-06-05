# @aithru/node-agent

Workflow node integration surface for Aithru Agent.

The package name is `node-agent` because these are workflow nodes that call the Agent runtime. They are not the Agent runtime itself.

## Nodes

- `agent.classify`
- `agent.task`
- `agent.deepResearch`

## Runtime Binding

`@aithru/node-agent` does not hardcode a model provider. Host applications pass an `AgentNodeRuntimeBinding` into the node factories:

- `resolveModel(...)` chooses the `AgentModelAdapter` for a workflow run and node.
- `runtime` may provide a custom `AgentRuntime`; otherwise the default runtime is used.

The package does not instantiate `@aithru/agent-model-openai-compatible` or any other real provider by default.

## Factories

```ts
import {
  createAgentClassifyNode,
  createAgentDeepResearchNode,
  createAgentTaskNode,
  registerAgentNodes,
} from "@aithru/node-agent";
```

- `createAgentClassifyNode(binding)` creates the `agent.classify@0.1.0` `NodeDefinition`.
- `createAgentTaskNode(binding)` creates the `agent.task@0.1.0` `NodeDefinition`.
- `createAgentDeepResearchNode(binding)` creates the `agent.deepResearch@0.1.0` `NodeDefinition`.
- `registerAgentNodes(registry, binding)` registers all agent nodes in an Aithru Core `NodeRegistry`.

Typical runtime composition is app-owned:

```ts
import { registerCoreNodes } from "@aithru/nodes-core";
import { InMemoryNodeRegistry } from "@aithru/runtime-core";
import { LocalRuntime } from "@aithru/runtime-local";
import { registerAgentNodes } from "@aithru/node-agent";

const registry = new InMemoryNodeRegistry();
registerCoreNodes(registry);
registerAgentNodes(registry, {
  resolveModel(input) {
    return chooseModelAdapter(input);
  },
});

const runtime = new LocalRuntime({ registry });
```

## agent.deepResearch

`agent.deepResearch` wraps the default Agent runtime `DeepResearchEngine`.
Node execution resolves the model through the host-provided `resolveModel(...)`, builds an `AgentTask` from the node config and incoming workflow input, and calls:

```ts
runtime.runTask("deep-research", {
  task,
  model,
  host,
  options,
});
```

Supported config fields:

- `goal`
- `model`
- `maxSteps`
- `timeoutMs`
- `allowedTools`
- `review`
- `maxSources`
- `maxSearchQueries`
- `outputSchema`

The output shape is compatible with `agent.task`: `status`, `summary`, `artifacts`, optional `plan`, optional `review`, and optional `metadata`.
When Deep Research produces a report, it is returned under `metadata.research` and as a report artifact.

This node does not include real web search, MCP, browser automation, shell access, GitHub access, file tools, memory, UI, or server behavior.
Host applications decide which model adapter to use and which core tool executors are available.

## Tool Bridge

Agent runtime tool calls are bridged through `NodeExecutionContext.callTool`.
Model adapters do not execute tools, and node definitions do not execute tools directly.
If an agent task proposes a tool call and the context does not provide `callTool`, node execution fails with a clear error.

Agent runtime events are emitted through `ctx.emit(...)` as core `log.info` events.
The payload is an `AgentTraceEvent` with the original `AgentEvent` preserved at `payload.payload`.
Metadata includes `agentEventType`, `agentTraceKind`, and `agentTracePhase` for filtering.

## Boundary

- Formal workflow graph belongs to `aithru-core`.
- Intelligent execution belongs to `aithru-agent`.
- This package bridges them.
- `@aithru/node-agent` does not own workflow execution; Aithru Core runtimes such as `LocalRuntime` execute `WorkflowSpec`.
