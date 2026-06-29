# AGENTS.md

This file gives coding agents working in `vinsonws/aithru-agent` the repository
rules.

Read this before changing code or docs.

## Repository Direction

`aithru-agent` is a TypeScript-first Aithru-native AI harness backend.

Target direction:

```txt
Aithru Agent = platform-hosted AI harness for skills, tools, workspace files,
controlled execution, approvals, artifacts, memory, subagents, and traceable
intelligent work.
```

The active backend is:

```txt
backend-ts/
  Fastify control plane
  Aithru-owned TypeScript harness core
  Aithru capability router
  Agent stream / trace / workspace / artifact / approval / memory / subagent model
```

The tracked Python backend package has been removed. New backend behavior must
not require, import, shell out to, or start a Python backend process.

Primary design docs:

```txt
docs/00-agent-harness-design.md
docs/superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md
```

## Hard Boundaries

Aithru has one formal workflow system:

```txt
WorkflowSpec in Aithru Core, surfaced by Aithru Workbench.
```

Agent runtime todos, plans, subagents, workspace operations, and tool-call
sequences are harness state, not workflow definitions.

Do not add:

- an Agent workflow graph editor;
- Agent-owned WorkflowSpec semantics;
- Agent-owned graph branch semantics;
- Agent-owned workflow scheduler behavior;
- persisted AgentPlan-as-workflow definitions;
- drag-and-drop node/edge editing for Agent plans.

## Capability Boundary

Models may propose tool calls. They must not execute real actions directly.

All real actions must pass through an Aithru capability boundary:

```txt
model / provider adapter
  -> Aithru-owned model turn loop
  -> Aithru Capability Router
  -> policy / scope / approval boundary
  -> concrete local tool or future Workflow Capability API
  -> event / trace / artifact / redaction
```

Do not expose unrestricted local system access, browser automation, external
network calls, database access, Workbench internals, platform credentials, or
service tokens to model code.

## Dependency Direction

Keep dependency direction clear:

```txt
Agent may call Core/Workbench only through explicit APIs or capability tools.
Core must not depend on Agent packages.
Workbench may call Agent through explicit node/API boundaries.
```

Model providers are implementation details under `backend-ts/src/model`.
Provider SDK objects must not become public Aithru API contracts.

## Backend Ownership

Current TypeScript backend modules:

```txt
backend-ts/src/
  api/              Fastify routes
  application/      runtime assembly
  capabilities/     tool descriptors, policy, router, local tools
  contracts/        TypeBox Agent product contracts
  core/             native run loop and model turn loop
  external/         controlled web, MCP, and Workflow capability adapters
  model/            provider-neutral model adapters and profiles
  persistence/      in-memory and SQLite stores
  stream/           AgentStreamEvent writer/store/SSE
  trace/            event-to-span projection
  worker/           Agent run execution
```

Package meanings:

- `contracts`: pure product contracts. No Fastify, provider SDK, or database
  dependency.
- `stream`: canonical event log and SSE formatting.
- `trace`: projection from Agent events to spans.
- `capabilities`: every real tool action enters here.
- `core`: Aithru-owned run loop, model turn loop, and harness state.
- `model`: low-level provider adapters only; they never execute tools.
- `worker`: run execution, pause/resume, cancellation.
- `api`: HTTP control plane only.

## Naming Rules

Prefer these product names:

- Agent Harness
- Agent Thread
- Agent Skill
- Agent Run
- Agent Todo
- Agent Workspace
- Agent Tool
- Subagent
- Sandbox / Interpreter
- Memory
- Artifact
- Approval

Avoid these labels unless referring to a real Aithru Core `WorkflowSpec`:

- Agent workflow
- Agent workflow graph
- Agent graph editor
- sub-workflow
- save AgentPlan as workflow

## Tool And Controlled Execution Rules

Tool calls must be policy-aware and traceable.

When adding tool-related code:

- define risk level;
- define required scopes;
- validate allowed tools from skill/run policy;
- route through the Aithru capability router;
- preserve event order;
- produce inspectable trace events;
- redact sensitive inputs and outputs where needed;
- require approval for risky operations;
- avoid logging tokens, secrets, credentials, or raw sensitive payloads.

## Frontend Rules

Agent frontend, when added, should be a Platform hosted app, not a standalone
global shell. It must not become a workflow graph editor.

## Documentation Rules

When changing design or boundaries:

1. Update `docs/00-agent-harness-design.md`.
2. Update `README.md` if repository positioning changes.
3. Update backend README/API docs if backend ownership changes.
4. Avoid code changes that imply a new architecture without docs.

## Verification Commands

Run these before finishing meaningful backend changes:

```bash
cd backend-ts
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

## Pre-Merge Checklist

- [ ] The change reinforces Agent as an AI harness, not a workflow editor.
- [ ] Todos/runtime plans remain runtime state, not workflow definitions.
- [ ] Models do not execute tools directly.
- [ ] Real tools are capability-boundary controlled.
- [ ] Workbench integration uses explicit API/tool boundaries.
- [ ] Core does not depend on Agent.
- [ ] Sensitive values are not logged or persisted insecurely.
- [ ] Backend tests and file report example pass, or failures are documented.
