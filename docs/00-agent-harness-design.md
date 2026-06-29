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

Provider SDK objects are not public API contracts. Model adapters never execute
tools, read workspace files directly, write artifacts directly, or own approval
state.

## Capability Boundary

Models may propose tool calls. They must not execute real actions directly.

Every real action follows this path:

```txt
model/provider event
  -> Aithru model turn loop
  -> Aithru Capability Router
  -> skill policy / scope / approval boundary
  -> concrete local tool or external capability adapter
  -> event / trace / artifact / redaction
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
- Artifact;
- Memory;
- Approval;
- Subagent;
- Agent Stream Event;
- Agent Trace Span.

## Local Tools

The TypeScript backend includes controlled local tools for:

- workspace list/read/write/patch/delete;
- todo create/update;
- artifact create/finalize;
- presentation;
- subagent delegation;
- local memory operations.

Workspace and artifact tools are scoped to Agent Workspace storage. They must
not expose unrestricted host filesystem access to model code.

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
- workspace files;
- todos;
- approvals;
- artifacts;
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
