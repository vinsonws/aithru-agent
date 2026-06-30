# Aithru Agent Harness Design

Status: TypeScript-first active backend

This document describes the active product and architecture direction of
`aithru-agent`.

```txt
Aithru Agent = platform-hosted AI harness for skill-driven, tool-using,
workspace-aware, permission-aware intelligent work.
```

## Product Boundary

Aithru Agent is not a workflow system and does not own `WorkflowSpec`.

Formal workflows remain owned by Aithru Core and surfaced through Aithru
Workbench:

```txt
WorkflowSpec
  -> nodes
  -> edges
  -> validation
  -> branch semantics
  -> scheduler/runtime
  -> workflow run
```

Agent runtime todos, plans, subagents, workspace operations, tool-call
sequences, approvals, snapshots, summaries, and traces are harness state. They
must not become a draggable graph editor or persisted workflow definitions.

## Active Backend

The active backend is the native TypeScript implementation in `backend/`:

```txt
backend/
  apps/api/src/                 Fastify control plane and runtime assembly
  packages/capabilities/src/    capability router, policy, local tools, audit projection
  packages/contracts/src/       TypeBox Agent product contracts
  packages/harness/src/         run loop, model turn loop, retry
  packages/external/src/        controlled web, MCP, Workflow capability adapters
  packages/memory/src/          local memory provider
  packages/model/src/           provider-neutral model adapters and profiles
  packages/persistence/src/     in-memory and SQLite stores
  packages/skills/src/          SKILL.md loader and registry
  packages/snapshots/src/       run snapshot, summary, tree projections
  packages/stream/src/          AgentStreamEvent writer, redaction, SSE
  packages/subagents/src/       child-run delegation
  packages/trace/src/           event-to-span projection
  packages/worker/src/          run execution, recovery, external waits
```

The repository has one active backend. The previous Python backend package has
been removed from tracked source. The TypeScript backend must not import, shell
out to, or start a Python backend process.

## Harness Model

The harness owns explicit phases:

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

Model providers are low-level I/O adapters under
`backend/packages/model/src`. They
receive Aithru-built input and emit normalized model events:

```txt
text_delta
reasoning_delta
tool_call
usage
completed
failed
```

OpenAI and Anthropic-family calls use provider SDKs inside this package.
OpenAI-compatible vendor parameters live in model profile metadata, with small
compatibility patches only for request/response shapes that cannot be expressed
as normal SDK parameters. Provider SDK objects are not public API contracts.
Model adapters never execute tools, read workspace files directly, write
workspace outputs directly, or own approval state.

Run `harness_options.mode` is structured harness state, not prompt text. The
current chat surface uses `flash`, `thinking`, `pro`, and `ultra`: `flash`
disables model thinking, `thinking` enables low-effort thinking, and
`pro`/`ultra` set `is_plan_mode` for extra planning guidance. All four
strengths receive the scoped provider-native tool schema; concrete execution
still goes through the Capability Router. `ultra` may also set
`subagent_enabled`, but subagent tool exposure remains an explicit harness
decision.

### Display History vs Model Context

Agent Thread messages are the complete user-visible conversation record.
Before each model turn, the harness builds a bounded model context packet from
thread messages, recent tool result summaries, and the latest context summary.
The packet is model input only and is not displayed as chat history.

The model turn loop passes scoped provider-native tool definitions to the model
adapter for every chat strength. Concrete execution still goes through the
Capability Router.

Completed tool outputs may be summarized into model-only context so later turns
can reason over what happened without replaying large raw outputs. This summary
does not replace provider-native tool-call transcript replay. Reasoning-capable
providers may require exact assistant reasoning/tool-call fields and matching
tool result messages during live tool-call chains; those provider details stay
inside `backend/packages/model/src`.

After completed model runs, terminal processors may derive a thread title and a
context summary. Memory extraction is intentionally out of scope for this
processor set.

## Capability Boundary

Models may propose tool calls. They must not execute real actions directly.

Every real action follows this path:

```txt
model/provider event
  -> Aithru model turn loop
  -> Aithru Capability Router
  -> skill policy / scope / approval boundary
  -> concrete local tool or external capability adapter
  -> event / trace / workspace file / presentation / redaction
```

Tool-related code must:

- define risk level;
- define required scopes;
- validate allowed and denied tools;
- route through the capability router;
- preserve event order;
- produce inspectable trace and audit events;
- redact sensitive inputs and outputs where needed;
- require approval for risky operations;
- avoid logging tokens, secrets, credentials, or raw sensitive payloads.

## Product Concepts

Agent owns these product resources:

- Agent Thread;
- Agent Message;
- Agent Run;
- Agent Todo;
- Agent Workspace;
- Agent Tool;
- Agent Workspace File;
- Agent Presentation;
- Memory;
- Approval;
- Subagent;
- Agent Stream Event;
- Agent Trace Span.

## Local Tools

The TypeScript backend includes controlled local tools for:

- workspace list/read/write/patch/delete;
- todo create/update;
- model-driven clarification through `ask_clarification`;
- presentation;
- subagent delegation;
- local memory operations.

Workspace tools are scoped to Agent Workspace storage. They must
not expose unrestricted host filesystem access to model code.

Workspace file contents live in temporary filesystem roots, not in SQLite. A
threaded run uses a deterministic workspace id for that thread, so runs in the
same Agent Thread see the same temporary directory. Runs without a thread get
their own temporary workspace id. Workspace paths are normalized under that root
before file operations, and path traversal is rejected.

## Approvals

Approvals guard risky agent actions such as writes, deletes, external calls,
exports, and delegated/background actions.

Approval-required tool calls emit:

```txt
tool.proposed
approval.requested
run.paused
```

After resolution:

```txt
approval.resolved
run.resumed
tool.started
tool.completed
```

Approvals are harness state, not Workbench workflow approval nodes.

## Persistence

P0 may run in memory. Durable runtime uses `SqliteStore` through the
`AgentStore` interface.

Stores preserve:

- threads;
- messages;
- runs;
- events;
- workspace ids and run/thread ownership, while workspace file contents stay in
  temporary filesystem roots;
- thread-scoped todos with run provenance;
- approvals;
- settings;
- model profiles;
- skill registry entries and user skill packages;
- subagent specs;
- external tool configurations;
- context summaries;
- encrypted secret records in a dedicated secrets table;
- claims and leases.

Snapshots, summaries, and run trees are read-only projections over stored facts.
They are not workflow checkpoints, branch semantics, or scheduler state.

## External Capabilities

External calls require explicit configuration and allowed hosts.

The external adapter layer includes:

- controlled web search/fetch;
- MCP catalog and HTTP/stdio provider descriptors;
- Workflow Capability HTTP adapter;
- external run pause/resume coordination.

Workflow capability runs remain provider-owned. Agent stores only external run
references, events, and bounded results. Agent never parses, schedules, or
executes `WorkflowSpec` graphs.

## Verification

Meaningful backend changes should pass:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

The no-Python check is part of the architecture boundary: `backend` must not
depend on a Python backend package or process.

## Replacement Design

The detailed replacement plan and phase acceptance criteria are in:

```txt
docs/superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md
```
