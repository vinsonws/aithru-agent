# Aithru Agent

Aithru Agent is the Aithru-native AI harness layer.

It is being redesigned from a small collection of agent runtime engines into a platform-hosted, DeepAgents-like AI harness for long-running, tool-using, skill-driven, permission-aware intelligent work.

## One-line definition

```txt
Aithru Agent = Aithru-native AI harness for skills, tools, workspace files, subagents, sandboxed execution, approvals, artifacts, and traceable intelligent work
```

## Position

```txt
Aithru Platform
  owns identity, org context, authorization, app shell, grants, hosted tokens, service clients, connection policy, and audit

Aithru Workbench
  owns formal WorkflowSpec product UI, workflow run APIs, workflow run/event storage, workflow approvals, and runtime composition with Aithru Core

Aithru Core
  owns WorkflowSpec, graph validation, deterministic workflow contracts, node SDK, runtime contracts, tool contracts, trace, redaction, pause/resume, and primitive nodes

Aithru Agent
  owns AI harness behavior: chat, skills, agent runs, runtime todos, workspace, tool calls, subagents, sandbox/interpreter calls, memory, artifacts, approvals, and Agent trace events
```

Aithru Agent is not a formal workflow system and does not own `WorkflowSpec`.

Formal workflow graph editing, branch semantics, scheduling, versioning, and workflow persistence belong to Aithru Core and Aithru Workbench.

## Design reset

The previous implementation centered on:

```txt
AgentTask
AgentPlan
AgentRuntime
ClassifyEngine
PlanRunReviewEngine
DeepResearchEngine
AgentModelAdapter
@aithru/node-agent
```

Those pieces remain useful primitives, but they are no longer the product center.

The new product center is the harness:

```txt
Agent Thread
  -> messages
  -> selected Skill
  -> Agent Run
  -> runtime todos / plan timeline
  -> tool calls
  -> workspace files
  -> subagents
  -> sandbox/interpreter calls
  -> artifacts
  -> review
  -> approvals
  -> trace/event stream
```

See [Agent Harness Design](./docs/00-agent-harness-design.md) for the target architecture.

## Mental model

Use this analogy carefully:

```txt
LangGraph / low-level agent runtime  -> DeepAgents / high-level agent harness
Aithru Core + Workbench capabilities -> Aithru Agent / high-level AI harness
```

Aithru Core is a deterministic workflow kernel, not LangGraph. Aithru Workbench is a formal workflow product surface. Aithru Agent borrows the high-level harness shape: skills, todos, workspace, tools, subagents, memory, sandbox, approvals, and artifacts.

## Core boundary

Aithru Agent may have workflow-like runtime state, but that state is not a product workflow definition.

```txt
Agent Todo / runtime plan != WorkflowSpec
Subagent task              != Workbench node
Agent workspace operation  != workflow graph step
Agent tool call            != direct external execution
```

Formal workflows are still:

```txt
WorkflowSpec
  -> nodes
  -> edges
  -> validation
  -> branch semantics
  -> scheduler/runtime
  -> workflow run
```

owned by Aithru Core and surfaced through Aithru Workbench.

## Target product concepts

| Concept | Meaning | Rule |
| --- | --- | --- |
| Agent Thread | Conversation and task context under an org/user. | Main chat entry, not a workflow. |
| Agent Skill | Real reusable agent capability with instructions, allowed tools, subagents, workspace policy, memory policy, sandbox policy, approval policy, and output expectations. | Not a DAG. May be referenced by Workbench `agent.*` nodes. |
| Agent Run | One execution of a chat request, skill, API task, delegated task, or Workbench agent node. | Auditable intelligent run. |
| Agent Todo / runtime plan | Harness-maintained task breakdown. | Runtime observability state, not editable workflow graph. |
| Agent Workspace | Thread/run-scoped virtual file and artifact workspace. | Stores files, patches, reports, structured outputs, and workflow draft artifacts. |
| Agent Tool | Capability the harness may request. | Must route through Aithru permission, policy, approval, trace, and redaction. |
| Subagent | Harness-spawned specialized worker such as researcher, coder, reviewer, analyst, or workflow designer. | Internal agent delegation, not Workbench node graph. |
| Sandbox / Interpreter | Controlled execution environment for scripts, code, shell-like work, or analysis. | Never direct model access; always policy-gated. |
| Memory | Optional thread/workspace/project/org memory. | Product host controls scope, retention, and authorization. |
| Artifact | Output such as report, markdown, JSON, patch, file, decision, or workflow draft. | May be opened in Workbench only when it is a WorkflowSpec draft. |
| Approval | Human or policy decision for risky agent action. | Distinct from workflow human approval, but audit-friendly. |

## Aithru Capability Router

Aithru Agent should not execute real capabilities directly from the model loop.

All real actions should pass through an Aithru capability router:

```txt
model proposes tool call
  -> Agent Harness validates skill/tool policy
  -> Aithru Capability Router
  -> Platform/Core/Workbench permission checks
  -> approval if required
  -> concrete capability backend
  -> trace + artifact + redaction
```

Capability backends are:
- Agent-owned local tools (e.g. workspace operations)
- Workflow product capabilities invoked through `CapabilityRun` APIs

Workflow capabilities may be backed by Core nodes, but the backing details
belong to the Workflow product. Agent consumes the curated capability API and
stores linked external run references.

Future sandbox, memory, or MCP behavior must enter Agent through either
Agent-owned local harness interfaces or Workflow product capabilities.

## Current packages

```txt
packages/
  agent-core/             shared harness contracts and types (Thread, Skill, Run, Todo, Workspace, Tool, etc.)
  agent-stream/           AgentStreamEvent protocol, InMemoryEventStore, EventBus, EventWriter, SSE helper
  agent-skills/           Skill manifest parsing, validation, and AgentSkill conversion
  agent-workspace/        AgentWorkspaceProvider interface, InMemoryWorkspaceProvider, path normalization
  agent-tools/            AithruCapabilityRouter interface, StaticCapabilityRouter, tool adapters
  agent-harness/          NativeHarnessEngine, ScriptedModelPort, AgentModelPort interface
  agent-trace/            AgentTraceSpan model and Event → Trace projection
```

Package roles:

| Package | Role |
| --- | --- |
| `@aithru/agent-core` | Pure TypeScript contract types — no runtime dependencies. |
| `@aithru/agent-stream` | Event protocol — envelope types, writers, stores, bus, SSE helper. |
| `@aithru/agent-skills` | Skill manifest definitions, parsing, validation. |
| `@aithru/agent-workspace` | Workspace provider abstractions — in-memory implementation for dev/test. |
| `@aithru/agent-tools` | Capability Router — tool adapters, policy checks, Workflow capability adapter. |
| `@aithru/agent-harness` | Harness engine — NativeHarnessEngine, ScriptedModelPort, event-driven run loop. |
| `@aithru/agent-trace` | AgentTraceSpan model and AgentStreamEvent → trace span projection. |

## Target future packages

```txt
packages/
  agent-subagents/       subagent delegation contracts (interface only)
  agent-sandbox/         sandbox/interpreter interfaces (interface only)
  agent-memory/          memory provider contracts (interface only)
  node-agent/            Workbench/Core workflow node integration

apps/
  agent-server/          Platform subsystem backend
  agent-web/             Platform hosted app frontend
```

These are not yet implemented.

## Workbench integration

### Workbench calls Agent

Workbench can call Agent through formal workflow nodes such as future:

```txt
agent.skill
agent.task
```

The outer graph is still a formal `WorkflowSpec`. Agent owns only the intelligent harness behavior inside the node.

### Agent calls Workflow product

Agent can call Workflow product capabilities and workflows as tools:

```txt
Agent Harness
  -> workflow.invokeCapability tool
  -> Workflow product creates a CapabilityRun
  -> Agent receives result/artifact/trace summary
```

```txt
Agent Harness
  -> workbench.runWorkflow tool
  -> Workbench runs WorkflowSpec
  -> Agent receives result/artifact/trace summary
```

Agent must not parse, schedule, or execute workflow graphs itself. Agent also
must not import Workbench internals or execute raw workflow nodes directly.
Standalone deterministic actions should be exposed by the Workflow product as
curated capabilities and invoked through CapabilityRun APIs.

See [Workflow Capability and Agent Integration](./docs/08-workflow-capability-integration.md).

### Agent creates workflow drafts

Agent can generate a `WorkflowSpec` draft artifact and offer:

```txt
Open in Workbench
Validate in Workbench
Download WorkflowSpec JSON
```

Only Workbench validates, saves, versions, and runs formal workflows.

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
pnpm example:harness-basic
```

`pnpm typecheck` checks package sources, tests, and examples without emitting build output.
`pnpm build` emits package `dist` output and excludes `*.test.ts` files.
`pnpm test` runs Vitest coverage across all packages.
`pnpm example:harness-basic` demonstrates the full NativeHarnessEngine end-to-end with a ScriptedModelPort.

## Boundary rules

- Aithru Agent is an AI harness, not a workflow graph product.
- Core and Workbench own formal workflow definitions and execution semantics.
- Skills are reusable agent capabilities, not DAG workflows.
- Todos and runtime plans are observable run state, not stored workflow definitions.
- Models may propose tool calls, but must not execute tools.
- Sandbox/code/file/network operations must be policy-gated, traceable, and redacted where needed.
- Agent may use Core tools/nodes only through explicit capability adapters.
- Agent may run Workbench workflows only through Workbench APIs/tools.
- Workbench may call Agent only through explicit `agent.*` node integration.
- Core must not depend on Agent packages.

## For coding agents

Read [AGENTS.md](./AGENTS.md) before making repository changes.
