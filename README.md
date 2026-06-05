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
  agent-core/      contracts and types
  agent-runtime/   ClassifyEngine, PlanRunReviewEngine, AgentRuntime
  model-test/      deterministic scripted model adapters
  node-agent/      workflow node integration types
```

`@aithru/node-agent` uses the `node-*` naming style because it is a workflow node package that calls the Agent runtime. It is not the Agent runtime itself.

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

```ts
const output = await runtime.runTask("classify", input);
console.log(output.summary);
```

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
```

`pnpm typecheck` checks package sources, tests, and examples without emitting build output.
`pnpm build` emits package `dist` output and excludes `*.test.ts` files.
`pnpm test` now runs real Vitest coverage for `@aithru/model-test` and `@aithru/agent-runtime`; `@aithru/agent-core` and `@aithru/node-agent` remain contract/type packages with no runtime tests yet.

## Examples

```bash
pnpm example:classify
pnpm example:plan-run-review
```

The examples use `@aithru/model-test`, so they do not call a real model provider.
The root package declares local workspace dependencies for these examples so imports stay at package roots.
`example:classify` demonstrates both the event stream API and `runTask`; `example:plan-run-review` demonstrates the full plan/run/review event stream with tool execution through `AgentHost.callTool`.

## Current Scope

Implemented in this initial scaffold:

- root pnpm workspace;
- strict TypeScript base config;
- `@aithru/agent-core` contracts;
- `@aithru/model-test` scripted model adapter;
- `@aithru/agent-runtime` minimal classify and plan-run-review engines;
- complete `AgentEngine.run()` event streams where `host.emit(event)` and `yield event` receive the same ordered events;
- `AgentRuntime.runTask()` for directly collecting the final `AgentTaskOutput`;
- `@aithru/node-agent` node integration constants and config/output types;
- standalone examples;
- minimal Vitest tests for scripted model events, static model helpers, event stream consistency, classification completion, plan-run-review tool execution through `AgentHost.callTool`, and `AgentRuntime.runTask()`.

Repository setup:

- `.npmrc` disables pnpm peer auto-install so optional future `@aithru/node-agent` peers are not fetched during this V0 workspace verification.

Not implemented yet:

- real `NodeDefinition` factories for `agent.classify` and `agent.task`;
- OpenAI-compatible model adapter;
- MCP integration;
- Deep Research dedicated engine/node;
- browser, shell, GitHub, or file tools;
- durable persistence;
- UI/chat.

## Boundary Rules

- Agent plans are task-local and are not `WorkflowSpec`.
- Formal workflows belong to `aithru-core`.
- Tool execution must go through `AgentHost.callTool`.
- In workflow-node mode, `AgentHost.callTool` should bridge to core `ctx.callTool`.
- Future framework integrations should implement `AgentEngine`; they should not redefine Aithru workflow semantics.
