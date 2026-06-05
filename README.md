# Aithru Agent

Aithru Agent is the intelligent execution layer of the Aithru ecosystem.

## Position

```txt
aithru-core
  owns formal workflows

aithru-agent
  owns intelligent execution inside bounded tasks or nodes
```

Aithru Agent is not a workflow engine and does not own `WorkflowSpec`.

It provides:

- AgentTask
- AgentPlan
- AgentRun
- AgentHost
- AgentEngine
- AgentModelAdapter
- Agent Runtime
- Workflow node integration through `@aithru/node-agent`

## Initial Packages

```txt
packages/
  agent-core/                         contracts and types
  agent-runtime/                      ClassifyEngine, PlanRunReviewEngine, DeepResearchEngine, AgentRuntime
  agent-model-test/                   deterministic scripted model adapters
  agent-model-openai-compatible/      OpenAI-compatible HTTP model adapter
  node-agent/                         workflow NodeDefinition factories
```

`@aithru/node-agent` uses the `node-*` naming style because it is a workflow node package that calls the Agent runtime. It is not the Agent runtime itself.
It currently exposes `agent.classify`, `agent.task`, and `agent.deepResearch` as workflow `NodeDefinition` factories.

## V0 Goal

Build a minimal agent execution loop:

```txt
Task
  -> Plan
  -> Execute
  -> Tool Call through AgentHost
  -> Artifact
  -> Review
  -> Output
```

## Runtime API

`AgentEngine.run()` returns a complete `AsyncIterable<AgentEvent>`.
Every runtime event is first passed to `AgentHost.emit(event)` and then yielded to the caller, so host listeners and direct stream consumers see the same ordered event list.

`AgentRuntime.run(engineName, input)` exposes the event stream directly:

```ts
for await (const event of runtime.run("classify", input)) {
  console.log(event.type);
}
```

`AgentRuntime.runTask(engineName, input)` is the convenience API for callers that only need the final `AgentTaskOutput`.
It consumes the event stream and returns the last `agent.task.completed` output.
If the stream contains `agent.task.failed`, it throws `AgentTaskFailedError` with the failure `AgentError`.

```ts
const output = await runtime.runTask("classify", input);
console.log(output.summary);
```

## Deep Research V0

`DeepResearchEngine` is available as the default `deep-research` runtime engine.
It is a bounded, deterministic-friendly research loop that plans task-local research steps, executes model-proposed tool calls only through `AgentHost.callTool`, synthesizes an `AgentResearchReport`, creates a `report` artifact, and optionally reviews the result.

Deep Research V0 is not a workflow engine and does not own `WorkflowSpec`.
It does not include real web search, MCP, browser automation, built-in browser/shell/GitHub/file tools, memory, or UI/server behavior.
Hosts can provide fake local tools, real provider-backed tools, or workflow bridges, but the engine itself never executes tools directly.

Research runs can be bounded with normal run options such as `maxSteps` and `timeoutMs`, plus research-specific `maxSources` and `maxSearchQueries` options.
`@aithru/node-agent` exposes this engine as `agent.deepResearch`, a formal workflow node that calls `AgentRuntime.runTask("deep-research", ...)` and bridges model-proposed tool calls to core `ctx.callTool`.

## Runtime Failure Semantics

Runtime engines treat model, tool, and artifact failures as task failures:

- `AgentModelEvent.error` is converted into `agent.task.failed`; the runtime does not fall back to default classification, plan, execution, or review output after a model error.
- Model adapter exceptions during `generate(...)` are normalized into `AgentError` and emitted as `agent.task.failed`.
- Tool execution still must go through `AgentHost.callTool`; model adapters must not execute tools.
- `AgentHost.callTool(...)` exceptions become `agent.task.failed`.
- `AgentHost.callTool(...)` results with `error` become `agent.task.failed`.
- Artifact creation exceptions from `host.createArtifact(...)` become `agent.task.failed`.

For all runtime events, including failures, `AgentHost.emit(event)` and yielded events remain identical and ordered.

## Agent Trace Events

`AgentEvent` is the runtime event shape emitted by Agent engines.
`AgentTraceEvent` is an additive, provider-neutral trace-consumption view for Aithru Core integrations and future UI trace viewers.
It groups events by stable `kind` and `phase` fields while preserving the full original `AgentEvent` in `payload`.

`@aithru/node-agent` currently bridges Agent events into Aithru Core execution events as `log.info` events.
Those core events use `AgentTraceEvent` as the payload and include filter-friendly metadata:

- `agentEventType`
- `agentTraceKind`
- `agentTracePhase`

This trace shape does not make `aithru-agent` a workflow engine. Formal workflow execution still belongs to `aithru-core`.

## Install

```bash
corepack enable
corepack prepare pnpm@9.15.0 --activate
pnpm install
```

## Verify

```bash
pnpm typecheck
pnpm build
pnpm test
pnpm example:classify
pnpm example:plan-run-review
pnpm example:node-agent-basic
pnpm example:workflow-node-agent
pnpm example:workflow-node-agent-deep-research
pnpm example:openai-compatible-classify
pnpm example:deep-research
```

`pnpm typecheck` checks package sources, tests, and examples without emitting build output.
`pnpm build` emits package `dist` output and excludes `*.test.ts` files.
`pnpm test` now runs real Vitest coverage for `@aithru/agent-core`, `@aithru/agent-model-test`, `@aithru/agent-model-openai-compatible`, `@aithru/agent-runtime`, and `@aithru/node-agent`.

## Examples

```bash
pnpm example:classify
pnpm example:plan-run-review
pnpm example:node-agent-basic
pnpm example:workflow-node-agent
pnpm example:workflow-node-agent-deep-research
pnpm example:deep-research
```

The examples use `@aithru/agent-model-test`, so they do not call a real model provider by default.
`@aithru/agent-model-openai-compatible` is implemented for real OpenAI-compatible providers, but it is not used by the default examples.
The root package declares local workspace dependencies for these examples so imports stay at package roots.
`example:classify` demonstrates both the event stream API and `runTask`; `example:plan-run-review` demonstrates the full plan/run/review event stream with tool execution through `AgentHost.callTool`.
`example:deep-research` demonstrates bounded Deep Research V0 with a deterministic test model and fake local source tool through `AgentHost.callTool`.
`example:node-agent-basic` demonstrates registering `agent.classify` and `agent.task` NodeDefinitions and executing them directly with a deterministic test model.
`example:workflow-node-agent` demonstrates a formal Aithru Core `WorkflowSpec` running through `LocalRuntime` with `core.manualTrigger -> agent.classify`.
`example:workflow-node-agent-deep-research` demonstrates a formal Aithru Core `WorkflowSpec` running through `LocalRuntime` with `core.manualTrigger -> agent.deepResearch`, scripted model events, and a fake local tool executor.
The standalone runtime examples remain the default examples for runtime-only behavior.

## Optional Real-Provider Example

`example:openai-compatible-classify` demonstrates a manual, opt-in classify task using `@aithru/agent-model-openai-compatible`.
It is included in verification for the no-env skip path. With the required environment variables set, it can make a real network call.

Required environment variables:

- `AITHRU_OPENAI_COMPATIBLE_BASE_URL`
- `AITHRU_OPENAI_COMPATIBLE_MODEL`

Optional environment variable:

- `AITHRU_OPENAI_COMPATIBLE_API_KEY`

If the required variables are missing, the example prints a skip message and exits successfully without a network call.

```bash
AITHRU_OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com/v1 \
AITHRU_OPENAI_COMPATIBLE_MODEL=deepseek-chat \
AITHRU_OPENAI_COMPATIBLE_API_KEY=... \
pnpm example:openai-compatible-classify
```

The example uses a host whose `callTool` throws if invoked. Model adapters may propose tool calls, but actual tool execution remains in `AgentRuntime` through `AgentHost.callTool`.

## Aithru Core Workflow Integration

`@aithru/node-agent` can be registered into an Aithru Core `NodeRegistry` and run by Aithru Core runtime composition. The agent package does not own `WorkflowSpec`; formal workflow validation and execution remain in `aithru-core`.

For local development, the Aithru Core public packages must be available beside this repository. The expected parent workspace layout is:

```txt
vinsonws/
  aithru-core/
  aithru-agent/
  pnpm-workspace.yaml
```

The parent `pnpm-workspace.yaml` should include both package sets:

```yaml
packages:
  - "aithru-core/packages/*"
  - "aithru-agent/packages/*"
```

With those packages available, run:

```bash
pnpm example:workflow-node-agent
pnpm example:workflow-node-agent-deep-research
```

The examples use `@aithru/runtime-local`, `@aithru/nodes-core`, and `@aithru/agent-model-test`. They do not call a real model provider or the network.

## Current Scope

Implemented in this initial scaffold:

- root pnpm workspace;
- strict TypeScript base config;
- `@aithru/agent-core` contracts;
- `@aithru/agent-model-test` scripted model adapter;
- `@aithru/agent-model-openai-compatible` OpenAI-compatible HTTP adapter without the OpenAI SDK;
- `@aithru/agent-runtime` minimal classify, plan-run-review, and bounded Deep Research V0 engines;
- complete `AgentEngine.run()` event streams where `host.emit(event)` and `yield event` receive the same ordered events;
- `AgentRuntime.runTask()` for directly collecting the final `AgentTaskOutput` or throwing `AgentTaskFailedError` on `agent.task.failed`;
- `AgentTraceEvent` taxonomy and `agentTraceEventFromAgentEvent(...)` for stable trace consumption;
- `@aithru/node-agent` `NodeDefinition` factories for `agent.classify`, `agent.task`, and `agent.deepResearch`, with host-injected model resolution and tool bridging through core `ctx.callTool`;
- standalone examples;
- minimal Vitest tests for trace event mapping, scripted model events, static model helpers, OpenAI-compatible request/response parsing, event stream consistency, classification completion, plan-run-review and Deep Research V0 tool execution through `AgentHost.callTool`, runtime failure semantics, `AgentRuntime.runTask()`, node-agent factories, node runtime binding, trace bridging, tool bridging, and LocalRuntime workflow integration.

Repository setup:

- `.npmrc` disables pnpm peer auto-install so optional future `@aithru/node-agent` peers are not fetched during this V0 workspace verification.

Not implemented yet:

- MCP integration;
- browser, shell, GitHub, or file tools;
- durable persistence;
- UI/chat.

## Boundary Rules

- Agent plans are task-local and are not `WorkflowSpec`.
- Formal workflows belong to `aithru-core`.
- Tool execution must go through `AgentHost.callTool`.
- In workflow-node mode, `AgentHost.callTool` should bridge to core `ctx.callTool`.
- Future framework integrations should implement `AgentEngine`; they should not redefine Aithru workflow semantics.
