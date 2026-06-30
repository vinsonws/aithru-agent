# Native TypeScript Agent Backend Replacement Design

Status: approved design direction

Date: 2026-06-29

## Summary

Aithru Agent replaces the previous Python/Pydantic AI backend with a native
TypeScript backend whose core harness is owned by Aithru.

The replacement must not swap Pydantic AI for another agent framework. Mastra,
LangGraph.js, Vercel AI SDK agent abstractions, Claude Agent SDK, or similar
frameworks must not own the Agent Run loop, tool execution loop, workflow-like
state, memory semantics, approval semantics, or workspace semantics.

Third-party libraries may still be used as infrastructure or protocol adapters:
HTTP serving, schema validation, database access, model API calls, MCP protocol
clients, and OpenAPI generation. They must stay below Aithru's harness and
capability boundary.

The TypeScript backend must not start or depend on a Python backend process.
Python backend source is no longer part of the tracked active backend.

## Product Boundary

The product remains:

```txt
Aithru Agent = platform-hosted AI harness for skills, tools, workspace files,
controlled execution, approvals, artifacts, memory, subagents, and traceable
intelligent work.
```

The replacement keeps the hard boundary:

```txt
Aithru has one formal workflow system:
WorkflowSpec in Aithru Core, surfaced by Aithru Workbench.
```

Agent Runs, runtime Todos, Subagents, tool-call sequences, workspace operations,
continuations, retries, and recovery hints are harness state. They are not
WorkflowSpec graphs, workflow branches, workflow schedulers, or persisted
workflow definitions.

## Non-Goals

Do not add:

- an Agent workflow graph editor;
- Agent-owned WorkflowSpec semantics;
- Agent-owned graph branch semantics;
- Agent-owned workflow scheduler behavior;
- persisted AgentPlan-as-workflow definitions;
- drag-and-drop node/edge editing for Agent plans;
- framework-native workflow concepts as public Agent API contracts;
- framework-native tool execution around the Aithru Capability Router.

## Why Aithru-Owned Core

The previous Python backend established the important product shape:

- Aithru-owned domain contracts;
- canonical AgentStreamEvent event log;
- capability-bound real tool execution;
- approval, redaction, audit, trace, workspace, artifact, memory, and subagent
  boundaries;
- worker-owned pause/resume, retry, cancellation, and recovery semantics.

Replacing Pydantic AI should not discard those boundaries. The main reason to
move to TypeScript is platform and product alignment, not outsourcing the
harness core to another framework.

Proma is a useful reference for a TypeScript/Electron local agent product: its
main-process services own orchestration, sessions, workspaces, permissions, and
event handling. However, Proma's Agent mode still uses Claude Agent SDK as an
execution substrate. Aithru should go one layer deeper: the Aithru TypeScript
backend should own the harness kernel directly and use model SDKs only as model
I/O adapters.

## Technology Choices

Recommended baseline:

```txt
Runtime: Node.js 22 LTS
API: Fastify
Contracts: TypeBox + Ajv + @fastify/swagger
Generated frontend types: openapi-typescript
Persistence: SQLite first, via direct sql.js statement execution with DB_PATH file persistence
Tests: Vitest
Streaming: native Server-Sent Events
Model calls: provider adapters using OpenAI/Anthropic SDKs; OpenAI-compatible vendors use SDK base URLs plus metadata request params
MCP: protocol adapter only, never a tool-execution bypass
```

Allowed infrastructure libraries:

- Fastify for HTTP routing and lifecycle;
- TypeBox, Ajv, or Zod for runtime schema validation;
- OpenAPI generation and openapi-typescript for frontend contracts;
- SQLite storage libraries or drivers used behind Aithru-owned store ports;
- provider SDKs for model APIs;
- MCP SDKs for MCP protocol transport;
- OpenTelemetry exporters for optional observability.

Disallowed core dependencies:

- Pydantic AI;
- Mastra as the harness core;
- LangGraph or LangGraph.js as the harness core;
- Vercel AI SDK agent abstractions as the harness core;
- Claude Agent SDK as the harness core;
- any framework-owned tool runner, workflow runtime, graph state, memory layer,
  or approval layer as a public Agent product contract.

## Repository Layout

The active backend lives in `backend/`:

```txt
backend/
  apps/api/src/                 Fastify routes and runtime assembly
  packages/capabilities/src/    router, policy, adapters, local tools
  packages/contracts/src/       TypeBox schemas and generated TS exports
  packages/external/src/        controlled web, MCP, Workflow adapters
  packages/harness/src/         native Aithru harness kernel
  packages/memory/src/          local memory provider
  packages/model/src/           low-level model provider adapters
  packages/persistence/src/     memory and SQLite stores
  packages/skills/src/          SKILL.md package loading and skill policy
  packages/snapshots/src/       run snapshot, summary, tree projections
  packages/stream/src/          AgentStreamEvent writer/SSE/redaction
  packages/subagents/src/       child-run delegation
  packages/trace/src/           event-to-span projection
  packages/worker/src/          queue, claim, heartbeat, retry, recovery
  tests/
  examples/
```

The previous Python package that originally occupied `backend/` has been
removed from tracked source. The `backend/` directory now contains the native
TypeScript implementation.

## Layer Ownership

### contracts

Own the public JSON shape for:

- AgentThread;
- AgentMessage;
- AgentRun;
- AgentSkill;
- AgentTodo;
- AgentWorkspace;
- AgentArtifact;
- AgentApproval;
- AgentToolDescriptor;
- AgentToolCallRequest;
- AgentToolCallResult;
- AgentStreamEvent;
- AgentTraceSpan;
- RunSnapshotResponse and related inspection projections.

Contracts must be schema-first and generate:

- runtime request/response validation;
- OpenAPI schemas;
- frontend TypeScript types;
- test fixtures for golden compatibility.

### core

Own the self-built Agent Harness kernel:

```txt
core/
  run-loop.ts
  model-turn.ts
  tool-loop.ts
  pause-resume.ts
  context-packet.ts
  subagents.ts
  cancellation.ts
  errors.ts
```

The core has no Fastify dependency, no database driver dependency, and no
provider SDK dependency. It talks to ports:

- model adapter;
- capability router;
- event writer;
- store;
- context packet builder;
- approval service;
- subagent runner;
- cancellation checker.

### model

Own low-level model I/O only.

Model adapters receive Aithru-built message/context input and emit normalized
model turn events:

```ts
export interface AgentModelAdapter {
  createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent>;
}

export type ModelTurnEvent =
  | { type: "text_delta"; delta: string }
  | { type: "reasoning_delta"; delta: string }
  | { type: "tool_call"; id: string; name: string; input: unknown }
  | { type: "usage"; inputTokens: number; outputTokens: number; totalTokens?: number }
  | { type: "completed"; content?: string }
  | { type: "failed"; error: AgentErrorPayload };
```

Rules:

- adapters never execute tools;
- adapters never read workspace files directly;
- adapters never write artifacts directly;
- adapters never own approval state;
- provider-specific stream formats are normalized before reaching the core.

### capabilities

Own every real action boundary:

```ts
export interface CapabilityRouter {
  listTools(ctx: AgentRunContext): Promise<AgentToolDescriptor[]>;
  prepareToolCall(
    req: AgentToolCallRequest,
    ctx: AgentRunContext,
  ): Promise<ToolPrepareResult>;
  executeToolCall(
    req: AgentToolCallRequest,
    ctx: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}
```

The router must enforce:

- known tool descriptor lookup;
- skill allow/deny policy;
- actor scope checks;
- workspace path policy;
- risk and approval policy;
- adapter-level input validation;
- redaction and audit metadata;
- failure recovery policy.

### stream

Own the canonical append-only event log:

```txt
AgentEventWriter.write()
  -> EventStore.append()
  -> SSE replay/follow
  -> trace and inspection projections
```

The TypeScript backend should preserve current SSE wire shape:

```txt
id: {event.id}
event: {event.type}
data: {compact JSON of AgentStreamEvent}
```

### worker

Own queued execution and durable runtime transitions:

- claim acquisition;
- heartbeat renewal;
- stale claim reclamation;
- retry scheduling;
- pause/resume dispatch;
- cancellation checks;
- parent/child join recovery;
- external approval and external run callback handling.

The worker is a harness runtime component, not a workflow scheduler.

## Core Run Loop

The native core should execute in explicit phases:

```txt
load run
  -> verify run is claimable and visible
  -> emit run.started
  -> build context packet
  -> start model turn
  -> emit message/model events
  -> normalize model tool proposals
  -> prepare tool call
  -> pause or execute
  -> return tool result to next model turn
  -> complete, fail, cancel, or pause run
```

Successful safe tool call:

```txt
tool.proposed
tool.started
tool.completed
```

Approval-required tool call:

```txt
tool.proposed
approval.requested
run.paused
```

After approval:

```txt
approval.resolved
run.resumed
tool.started
tool.completed
next model turn
```

Denied tool call:

```txt
tool.proposed
tool.denied
```

Recoverable tool failure:

```txt
tool.proposed
tool.started
tool.failed
tool.recovery.offered
next model turn receives bounded recovery payload
```

## Pause and Resume

The TypeScript core should own resumability directly instead of storing
framework-native message histories.

Persisted run state may contain:

```txt
current_approval_id
current_external_approval
current_external_run
current_input_request
current_tool_call
model_turn_state
tool_results_context
retry_state
claim
```

Resume paths:

- approval resolved;
- input received;
- external approval resolved;
- external run resolved;
- child subagent completed, failed, or cancelled;
- delayed retry became ready;
- stale running claim was reclaimed.

The resume path rebuilds bounded context from Aithru facts and continues the
model turn or next model turn. It does not deserialize framework internals.

## Context Packet

The context packet is an Aithru-owned prompt construction projection. It may
include:

- run task;
- selected skill instructions;
- recent thread messages;
- durable thread summary;
- runtime todos;
- workspace file summaries;
- artifacts and artifact summaries;
- prior tool result summaries;
- active approval/input/external run context;
- scoped memory recall;
- subagent result summaries;
- bounded research continuation context.

It must not include:

- raw secrets;
- unrestricted workspace file contents;
- arbitrary host paths;
- hidden framework state;
- WorkflowSpec graph semantics;
- persisted AgentPlan-as-workflow definitions.

The packet should emit a debug `context.packet.built` event with counts and
budget metadata, not the full prompt.

## Local Tools

P0 local tools:

```txt
workspace.list_files
workspace.read_file
workspace.write_file
workspace.patch_file
workspace.delete_file
todo.create
todo.update
artifact.create
artifact.finalize
input.request
```

P1 local tools:

```txt
workspace.view_image
workspace.promote_file
sandbox.list_files
sandbox.read_file
sandbox.write_file
sandbox.patch_file
sandbox.delete_file
sandbox.diff
sandbox.promote_file
memory.search
memory.remember
subagent.delegate
task
research.create_plan
research.create_report
workbench.workflow_draft.create
```

The initial sandbox must not depend on Python. Recommended P0 behavior:

- disable `sandbox.run_python`;
- add a controlled `sandbox.run_javascript` only if needed;
- keep all sandbox file operations bound to Agent Workspace storage;
- require explicit scopes and approval for write-risk operations.

If Python execution is later required, it must be an optional controlled
interpreter provider behind `sandbox.run_python`, disabled by default, and not
part of the backend runtime.

## Persistence

P0 may use in-memory stores for rapid parity. P1 should add SQLite.

Stores should preserve the same product facts:

- threads;
- messages;
- runs;
- events;
- thread-scoped todos with run provenance;
- approvals;
- workspace ids and ownership; workspace file contents are temporary
  filesystem state, not SQLite rows or file-version records;
- artifacts;
- settings;
- skill packages and registry entries;
- memory entries and candidates once the memory design is split out;
- subagent runs;
- model profiles;
- encrypted secrets in a dedicated secrets table;
- external tool configurations.

The event store is canonical for stream replay and trace projection. Derived
snapshots must remain read-only projections over stored facts.

## API Surface

The TypeScript backend should keep the current `/api` shape unless a route is
intentionally removed through a compatibility decision:

```txt
GET    /api/health
POST   /api/threads
GET    /api/threads
PATCH  /api/threads/{thread_id}
POST   /api/threads/{thread_id}/messages
GET    /api/threads/{thread_id}/messages
POST   /api/threads/{thread_id}/runs
GET    /api/threads/{thread_id}/runs/{run_id}/stream
POST   /api/runs
GET    /api/runs
GET    /api/runs/{run_id}
GET    /api/runs/{run_id}/events
GET    /api/runs/{run_id}/trace
GET    /api/runs/{run_id}/snapshot
POST   /api/runs/{run_id}/input
POST   /api/runs/{run_id}/cancel
POST   /api/runs/{run_id}/resume
GET    /api/approvals
POST   /api/approvals/{approval_id}/resolve
GET    /api/workspaces/{workspace_id}/files
PUT    /api/workspaces/{workspace_id}/files/{path}
GET    /api/artifacts
GET    /api/skills
GET    /api/model-profiles
```

Routes are control-plane APIs. They do not create WorkflowSpec definitions or
grant model-side tool access.

## Error Handling

The TypeScript backend should preserve Aithru error shape:

```txt
code
message
retryable
details
```

Failure categories:

- validation errors;
- policy denials;
- authorization denials;
- approval required;
- cancellation;
- provider/model errors;
- recoverable tool failures;
- non-recoverable tool failures;
- persistence errors;
- external run callback conflicts;
- stale claim conflicts.

Sensitive details must be redacted before user/debug/audit stream persistence.

## Testing Strategy

Required test groups:

- contract schema tests;
- OpenAPI generation tests;
- stream golden tests;
- run status transition tests;
- capability router policy tests;
- approval pause/resume tests;
- input pause/resume tests;
- tool recovery loop tests;
- worker claim/heartbeat/retry tests;
- event-to-trace projection tests;
- workspace path policy tests;
- artifact lifecycle tests;
- subagent child-run join tests;
- frontend generated type compatibility tests;
- no-Python-backend guard tests.

Recommended commands:

```bash
cd backend
npm run typecheck
npm run test
npm run test:contracts
npm run test:stream-golden
npm run test:capability-boundary
npm run examples:file-report
npm run check:no-python-backend
```

`check:no-python-backend` should fail if the TypeScript backend:

- imports or shells out to the Python backend as a server or worker;
- depends on Pydantic or Pydantic AI;
- starts a Python API process;
- starts a Python worker process;
- uses Python as the default sandbox execution path.

## Migration Plan

### P0: runnable TypeScript replacement skeleton

Deliver:

- `backend` workspace package;
- Fastify app;
- schema-first contracts for health, threads, messages, runs, stream events;
- in-memory store;
- event writer and SSE replay/follow;
- worker runner;
- ScriptedHarnessCore for deterministic runs;
- create thread, create message, create run, stream run;
- `examples/file_report_agent.ts` equivalent with no Python backend process.

Acceptance:

- frontend can point at the TypeScript backend;
- a run emits `run.created`, `run.started`, `message.created`,
  `message.delta`, `message.completed`, and `run.completed`;
- no Python backend process is started.

### P1: capability boundary and local tools

Deliver:

- CapabilityRouter;
- tool descriptors;
- skill allow/deny policy;
- actor scope checks;
- approval request/resolve;
- workspace read/write/patch/delete;
- todo create/update;
- artifact create/finalize;
- redaction and trace projection.

Acceptance:

- model proposals cannot execute tools directly;
- write-risk tools can pause for approval;
- denied tools emit audit-friendly events;
- stream and trace ordering are deterministic.

### P2: durable runtime

Deliver:

- SQLite store;
- run claims and heartbeats;
- stale claim reclamation;
- retry policy/state;
- pause/resume recovery;
- run snapshots;
- run summaries and tree projection;
- skill package loader;
- local memory provider;
- subagent delegation and `task(...)` child-run join.

Acceptance:

- worker restart can continue safe paused runs;
- duplicate workers cannot execute the same active run;
- snapshots remain read-only harness projections.

### P3: real model adapters

Deliver:

- provider-neutral `AgentModelAdapter`;
- OpenAI SDK adapter for Responses and Chat Completions, including OpenAI-compatible base URLs;
- Anthropic SDK adapter for Messages;
- test model adapter;
- native model turn loop with tool-call round trips;
- usage events and model profile governance.

Acceptance:

- provider streams normalize into Aithru events;
- model tool calls always pass through CapabilityRouter;
- provider SDK objects do not leak into public contracts.

### P4: external tools and Workflow capabilities

Deliver:

- controlled web search/fetch providers;
- MCP catalog and HTTP/stdio provider adapters;
- Workflow Capability HTTP adapter;
- external approval and external run pause/resume;
- capability audit APIs.

Acceptance:

- external calls require explicit configuration and allowed hosts;
- Workflow capability runs remain provider-owned;
- Agent never parses, schedules, or executes WorkflowSpec graphs.

### P5: remove Python backend

Deliver:

- update README and AGENTS to TS-first active backend;
- remove Python backend package or move it to archival history;
- delete Pydantic/Pydantic AI dependency references;
- update verification commands to TypeScript equivalents.

Acceptance:

- repository has one active backend;
- all verification commands pass;
- documentation no longer describes Python as the active backend.

## Documentation Updates

After P5, README, AGENTS, and backend docs state that the TypeScript backend is
active and list TypeScript verification commands.

Required docs:

- `docs/00-agent-harness-design.md`;
- `README.md`;
- backend TypeScript README/API docs;
- verification command docs;
- architecture docs that currently say Python-first or Pydantic AI-first.

## Risks

### Rebuilding model loop mechanics

Risk: owning the model/tool loop means Aithru must handle streaming,
tool-calling, provider differences, retries, and usage accounting.

Mitigation: keep model adapters small, normalize provider events early, and
lock behavior with model-adapter fixtures.

### Schema migration drift

Risk: legacy contract notes and TypeBox schemas may drift during migration.

Mitigation: freeze OpenAPI and event golden fixtures before implementation and
write compatibility tests against them.

### Durable resume complexity

Risk: approval, input, external run, and subagent resume are easy to couple to
framework internals.

Mitigation: persist Aithru-owned resumable facts only and rebuild model context
from the event/store facts.

### Sandbox parity

Risk: removing Python backend also removes the current Python sandbox default.

Mitigation: explicitly disable Python sandbox in P0 and treat future Python
execution as an optional controlled interpreter provider, not backend runtime.

### Documentation mismatch

Risk: docs may drift and imply a second active backend.

Mitigation: keep active docs TS-first and treat historical Python references as
background only, not runnable backend instructions.

## Acceptance Criteria

The design is successful when:

- the active replacement backend is TypeScript;
- no Python backend process is required or started;
- Aithru owns the core harness loop;
- models cannot execute tools directly;
- every real action crosses the Capability Router;
- Agent remains a harness, not a workflow graph editor or scheduler;
- stream, trace, workspace, artifact, memory, approval, and subagent contracts
  remain Aithru-owned;
- provider SDK and framework objects are not public API contracts;
- frontend clients can continue using generated OpenAPI types and
  AgentStreamEvent SSE.
