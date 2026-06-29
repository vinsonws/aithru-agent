# Complete Harness Architecture

Status: current product architecture

This document describes the complete Aithru Agent Harness model after the native
TypeScript backend replacement. The active implementation lives under
`backend/`. The previous Python backend package has been removed from tracked
source and is no longer an active implementation target.

## One-line Definition

```txt
Aithru Agent Harness = Thread + Skill + Run + Todos + Workspace + Tools +
Subagents + Sandbox + Memory + Artifacts + Approvals + Stream.
```

## Design Principles

1. Agent is an AI harness, not a formal workflow system.
2. Workbench owns `WorkflowSpec` and formal workflow execution.
3. Agent owns intelligent runtime behavior and harness state.
4. Models may propose actions, but every real action crosses the capability
   boundary.
5. Events are append-only, replayable, and traceable.
6. Product contracts are Aithru-owned TypeScript contracts.
7. Third-party SDKs may sit behind adapters, but no agent framework owns the
   core loop, tools, stream, trace, state, or workflow semantics.

## Boundary Model

```txt
Aithru Platform
  identity, org context, hosted app, grants, token exchange,
  connection policy, audit

Aithru Workbench
  formal WorkflowSpec UI, workflow run APIs, workflow event storage,
  workflow approval endpoints, runtime composition with Aithru Core

Aithru Core
  WorkflowSpec, graph validation, deterministic workflow contracts,
  node SDK, runtime contracts, tool contracts, trace, redaction,
  pause/resume primitives, primitive nodes

Aithru Agent
  AI harness behavior: chat threads, skills, runs, todos, workspace,
  tools, subagents, sandbox, memory, artifacts, approvals, stream events
```

Agent runtime plans, todos, tool-call sequences, and subagent tasks are harness
state. They are not `WorkflowSpec` and must not become editable workflow graphs.

## Complete Capability Map

| Area | Capability | First-class object |
| --- | --- | --- |
| Conversation | Multi-turn context and continuation | `AgentThread`, `AgentMessage` |
| Skills | Reusable capability packages | `AgentSkill`, `SkillPackage` |
| Execution | One intelligent task execution | `AgentRun` |
| Planning | Runtime task breakdown | `AgentTodo` |
| Files | Virtual work directory | `AgentWorkspace`, `WorkspaceFile` |
| Output | Durable result | `AgentArtifact` |
| Tools | Model-requested capabilities | `AgentToolDescriptor`, `AgentToolCall` |
| Subagents | Scoped specialized workers | `SubagentSpec`, `SubagentRun` |
| Sandbox | Controlled code/data execution | `SandboxRun` |
| Memory | Scoped reusable context | `AgentMemoryEntry` |
| Approval | Human/policy decisions | `AgentApproval` |
| Streaming | Realtime/replayable execution events | `AgentStreamEvent` |

## Current Backend Layout

```txt
backend/
  apps/api/src/                 Fastify HTTP/SSE control plane and runtime assembly
  packages/capabilities/src/    descriptors, policy, audit, router, adapters
  packages/contracts/src/       Aithru-owned TypeBox schemas and TypeScript types
  packages/harness/src/         native harness loop, scripted core, model-turn loop
  packages/external/src/        controlled external capability providers
  packages/memory/src/          memory provider interfaces
  packages/model/src/           model adapter interfaces and provider wrappers
  packages/persistence/src/     in-memory and SQLite stores
  packages/skills/src/          SKILL.md loading and registry
  packages/snapshots/src/       read models for API/UI
  packages/stream/src/          AgentStreamEvent writer/store/SSE/redaction
  packages/subagents/src/       subagent runner contracts
  packages/trace/src/           event-to-span projection
  packages/worker/src/          run execution, recovery, external-run continuation
```

## Harness Kernel

The native harness kernel coordinates:

- actor context;
- thread context;
- skill context;
- workspace context;
- memory context;
- todo state;
- tool catalog;
- capability router;
- model adapter;
- approval gateway;
- artifact writer;
- event stream.

The core loop is Aithru-owned. Model providers produce normalized model events;
tool calls are routed through `AithruCapabilityRouter`; stores and streams use
Aithru contracts.

## Full Run Lifecycle

```txt
1. Request enters through Platform hosted app or API.
2. Resolve ActorContext.
3. Create or load AgentThread.
4. Create user AgentMessage when applicable.
5. Resolve AgentSkill.
6. Create AgentRun.
7. Create or attach AgentWorkspace.
8. Load memory according to policy.
9. List tools allowed by skill and actor context.
10. Build model context.
11. Enter native Harness Loop.

Harness Loop:
  a. Model adapter emits text, usage, tool call, or failure events.
  b. Append Aithru stream events.
  c. If todo update, persist todo projection.
  d. If tool call, run capability pipeline.
  e. If subagent call, start subagent run.
  f. If workspace write, persist workspace file and event.
  g. If artifact output, create artifact.
  h. If approval is required, pause run.
  i. If final response, complete assistant message and run.

12. Persist final state.
13. Emit terminal event.
```

## Capability Pipeline

```txt
model proposes action
  -> native model turn loop parses and normalizes request
  -> skill policy check
  -> actor/platform authz check
  -> approval gateway if required
  -> AithruCapabilityRouter
  -> concrete adapter
  -> result normalization
  -> event stream
  -> trace redaction
  -> artifact/workspace update
```

The capability router is defined in [Capability Router](./05-capability-router.md).

## Platform Integration

Agent server is a Platform subsystem. It should eventually use Platform SDK
capabilities for JWT verification, current actor extraction, org-scoped
authorization, hosted app token handling, service token exchange, delegated
token handling, resource registration, and audit reporting.

Browser UI must not receive service client credentials or internal service
tokens.

## Workbench Integration

Workbench calls Agent through explicit node/API boundaries such as future
`agent.skill` and `agent.task` nodes. Workbench remains the formal workflow
owner. Agent owns only harness behavior inside the node.

Agent calls Workflow product capabilities through explicit tools such as
`workflow.invokeCapability` or `workbench.runWorkflow`. Agent must not import
Workbench internals, schedule workflow graphs, or execute raw workflow nodes
directly.

## UI Implication

Agent frontend should feel like a harness product, not a workflow editor.

Recommended product navigation:

```txt
Chat
Skills
Workspace
Runs
Artifacts
Approvals
Tools
Memory
Settings
```

It must not show Agent runtime plans as draggable graphs.

## Architecture Acceptance Criteria

A design or implementation change is acceptable only if:

- Agent remains an AI harness, not a workflow editor.
- Skills remain agent capabilities, not DAG workflows.
- Todos/runtime plans remain runtime state.
- Workspace is first-class.
- Artifacts are first-class.
- Tool calls route through capability boundaries.
- Sandbox and external actions are policy-gated.
- Stream events are structured and replayable.
- Platform identity/authz/audit is preserved.
- Workbench integration is explicit and narrow.
- Core does not depend on Agent.
