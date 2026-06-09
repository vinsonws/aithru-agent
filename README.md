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

Capability backends may include:

- Core tool executors;
- selected Core node adapters;
- Workbench workflow APIs;
- Platform subsystem APIs;
- sandbox executors;
- workspace providers;
- memory providers;
- future MCP adapters.

## Current implemented packages

The current repository still contains the initial primitive implementation:

```txt
packages/
  agent-core/                         primitive Agent contracts and types
  agent-runtime/                      ClassifyEngine, PlanRunReviewEngine, DeepResearchEngine, AgentRuntime
  agent-model-test/                   deterministic scripted model adapters
  agent-model-openai-compatible/      OpenAI-compatible HTTP model adapter
  node-agent/                         workflow NodeDefinition factories
```

Current package roles:

| Package | Current role | Future positioning |
| --- | --- | --- |
| `@aithru/agent-core` | `AgentTask`, `AgentPlan`, events, model adapter, host, artifacts, approval, trace types. | Extend toward harness contracts: Thread, Skill, Run, Todo, Workspace, Tool, Subagent, Memory. |
| `@aithru/agent-runtime` | `ClassifyEngine`, `PlanRunReviewEngine`, `DeepResearchEngine`, `AgentRuntime`. | Keep as compatibility/runtime primitive layer below the harness. |
| `@aithru/agent-model-test` | Deterministic scripted adapter. | Keep for tests and examples. |
| `@aithru/agent-model-openai-compatible` | OpenAI-compatible model adapter. | Keep as provider-neutral model adapter. |
| `@aithru/node-agent` | Workflow nodes for current engines. | Evolve toward skill/harness invocation nodes. |

## Target package direction

Future package shape should move toward:

```txt
packages/
  agent-core/            shared harness contracts
  agent-harness/         main DeepAgents-like harness
  agent-skills/          skill loading, validation, prompt composition
  agent-workspace/       workspace and artifact APIs
  agent-tools/           capability router and adapters
  agent-subagents/       subagent delegation contracts
  agent-sandbox/         sandbox/interpreter interfaces
  agent-memory/          memory provider contracts
  agent-model-*/         model adapters
  node-agent/            Workbench/Core workflow node integration

apps/
  agent-server/          Platform subsystem backend
  agent-web/             Platform hosted app frontend
```

This is a target architecture, not an immediate implementation requirement.

## Workbench integration

### Workbench calls Agent

Workbench can call Agent through formal workflow nodes such as future:

```txt
agent.skill
agent.task
```

The outer graph is still a formal `WorkflowSpec`. Agent owns only the intelligent harness behavior inside the node.

### Agent calls Workbench

Agent can call Workbench workflows as tools:

```txt
Agent Harness
  -> workbench.runWorkflow tool
  -> Workbench runs WorkflowSpec
  -> Agent receives result/artifact/trace summary
```

Agent must not parse, schedule, or execute workflow graphs itself.

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
`pnpm test` runs Vitest coverage for the existing primitive packages.

## Core workflow integration setup

For local development, the Aithru Core public packages must be available beside this repository.

Expected parent workspace layout:

```txt
vinsonws/
  aithru-core/
  aithru-agent/
  pnpm-workspace.yaml
```

Parent `pnpm-workspace.yaml`:

```yaml
packages:
  - "aithru-core/packages/*"
  - "aithru-agent/packages/*"
```

Then run:

```bash
pnpm example:workflow-node-agent
pnpm example:workflow-node-agent-deep-research
```

The workflow examples use `@aithru/runtime-local`, `@aithru/nodes-core`, and `@aithru/agent-model-test`. They do not call a real model provider or the network.

## Optional real-provider example

`example:openai-compatible-classify` demonstrates a manual, opt-in classify task using `@aithru/agent-model-openai-compatible`.

Required environment variables:

```txt
AITHRU_OPENAI_COMPATIBLE_BASE_URL
AITHRU_OPENAI_COMPATIBLE_MODEL
```

Optional:

```txt
AITHRU_OPENAI_COMPATIBLE_API_KEY
```

Example:

```bash
AITHRU_OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com/v1 \
AITHRU_OPENAI_COMPATIBLE_MODEL=deepseek-chat \
AITHRU_OPENAI_COMPATIBLE_API_KEY=... \
pnpm example:openai-compatible-classify
```

The example uses a host whose `callTool` throws if invoked. Model adapters may propose tool calls, but actual tool execution must stay behind the Aithru host/capability layer.

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
