# Aithru Agent

Aithru Agent is the Aithru-native TypeScript AI harness backend for
long-running, tool-using, permission-aware intelligent work.

The active backend lives in `backend/`:

```txt
backend/
  Fastify control plane
  TypeBox product contracts
  Aithru-owned harness core and model turn loop
  Capability Router for every real action
  Agent stream / trace / workspace file / presentation / approval / memory / subagent model
```

There is one active backend. The previous Python backend package has been
removed from the tracked repository. The TypeScript backend must not import,
shell out to, or start a Python backend process.

## Product Boundary

Aithru Agent is an AI harness, not a workflow system.

Agent owns:

- Agent Threads and Messages;
- Agent Runs;
- runtime Todos;
- controlled Agent Tools;
- Workspaces;
- Workspace files and presentations;
- Memory entries;
- Subagent delegation;
- Agent-owned Approvals;
- replayable Agent stream events;
- Agent trace projection;
- provider-neutral model events.

Formal `WorkflowSpec` authoring, graph semantics, scheduling, workflow run
storage, and workflow approvals belong to Aithru Core and Aithru Workbench.
Agent may call Workflow capabilities only through explicit capability/tool
boundaries. It must not parse, schedule, or execute workflow graphs.

## Backend Layout

```txt
backend/
  apps/api/src/                 Fastify routes and runtime assembly
  packages/contracts/src/       TypeBox Agent product contracts
  packages/capabilities/src/    descriptors, policy, router, audit projection
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

Important boundaries:

- model adapters normalize provider responses only;
- model adapters never execute tools;
- every real action crosses the `CapabilityRouter`;
- write-risk tools require policy, scope, and approval handling;
- external calls require explicit configuration and allowed hosts;
- Workflow capability runs remain provider-owned;
- stream, trace, workspace file, presentation, memory, approval, and subagent contracts
  are Aithru-owned.

## Run Locally

```bash
cd backend
npm install
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
npm run dev
```

For durable SQLite-backed runtime state:

```powershell
cd backend
$env:DB_PATH=".aithru/agent.sqlite"
npm run dev
```

Default server:

```txt
http://localhost:8000
GET /api/health
```

## Platform Mock Host

For hosted iframe development, run the local Platform mock host plus Agent
frontend/backend:

```bash
./scripts/run-mock.sh
```

On Windows:

```powershell
.\scripts\run-mock.ps1
```

Open:

```txt
http://localhost:19000/apps/agent
```

Production subsystem configuration uses the standard Platform SDK variables:
`AITHRU_PLATFORM_URL`, `AITHRU_APP_KEY`, `AITHRU_CLIENT_SECRET`, and
`AITHRU_PUBLIC_BASE_URL`. The Agent manifest lives in
`aithru-platform-app.yml`.

## Verification

Before finishing backend work, run:

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

The no-Python check is cross-platform and guards `backend` against Python
backend imports, process launches, and package dependencies.

## HTTP API

Primary endpoints:

```txt
GET    /api/health
POST   /api/threads
GET    /api/threads
PATCH  /api/threads/:thread_id
POST   /api/threads/:thread_id/messages
GET    /api/threads/:thread_id/messages

POST   /api/runs
GET    /api/runs
GET    /api/runs/:run_id
GET    /api/runs/:run_id/stream
GET    /api/runs/:run_id/events
GET    /api/runs/:run_id/trace
GET    /api/runs/:run_id/snapshot
GET    /api/runs/:run_id/capability-audit
POST   /api/runs/:run_id/cancel

POST   /api/approvals/:approval_id/resolve
```

## Key Docs

- [Agent Harness Design](./docs/00-agent-harness-design.md)
- [Native TypeScript Agent Backend Replacement Design](./docs/superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md)
