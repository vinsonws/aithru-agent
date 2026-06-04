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
```

## Examples

```bash
pnpm example:classify
pnpm example:plan-run-review
```

The examples use `@aithru/model-test`, so they do not call a real model provider.

## Current Scope

Implemented in this initial scaffold:

- root pnpm workspace;
- strict TypeScript base config;
- `@aithru/agent-core` contracts;
- `@aithru/model-test` scripted model adapter;
- `@aithru/agent-runtime` minimal classify and plan-run-review engines;
- `@aithru/node-agent` node integration constants and config/output types;
- standalone examples.

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
