# Aithru Agent

Aithru Agent is the Aithru-native AI harness backend for long-running,
tool-using, permission-aware intelligent work.

The backend is now Python-first:

```txt
FastAPI control plane
  + Pydantic AI harness driver
  + Aithru capability router
  + Agent event stream / trace / workspace / artifact / approval model
```

## Product Boundary

Aithru Agent is not a workflow system and does not own `WorkflowSpec`.

Formal workflow authoring, graph semantics, workflow scheduling, workflow run
storage, and workflow approvals belong to Aithru Core and Aithru Workbench.

Agent owns intelligent harness behavior:

- Agent Threads and Messages;
- Agent Runs;
- runtime Todos;
- controlled Agent Tools;
- Workspaces;
- Artifacts;
- Agent-owned Approvals;
- replayable Agent stream events;
- Agent trace projection;
- Pydantic AI-backed harness execution.

## Backend

The active backend lives in:

```txt
backend/
  src/aithru_agent/
    api/              FastAPI routes
    application/      runtime assembly
    capabilities/     tool descriptors, policy, router, local tools
    domain/           Agent product contracts
    harness/          scripted and Pydantic AI drivers
    persistence/      in-memory and SQLite stores
    stream/           AgentStreamEvent writer/store/SSE
    trace/            event-to-span projection
    worker/           queued Agent run execution and worker CLI
```

Pydantic AI powers the default real harness path, but it does not define public
Aithru product contracts. Pydantic AI events, tool calls, and model output are
adapted into Aithru-owned events and tool boundaries.

## Capability Boundary

Models may propose actions, but real actions must go through Aithru tools:

```txt
model / Pydantic AI
  -> Aithru Tool Bridge
  -> Capability Router
  -> policy / scope / approval
  -> local tool or future Workflow Capability API
  -> AgentStreamEvent / trace / artifact
```

Stage 1 local tools:

```txt
workspace.list_files
workspace.read_file
workspace.write_file
workspace.delete_file
todo.create
todo.update
artifact.create
artifact.finalize
```

## Run Locally

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
uv run uvicorn aithru_agent.api.main:app --reload
```

For API and worker processes sharing queued runs:

```bash
export AITHRU_AGENT_PERSISTENCE_BACKEND=sqlite
export AITHRU_AGENT_SQLITE_PATH=.aithru/agent.sqlite

uv run uvicorn aithru_agent.api.main:app --reload
uv run aithru-agent-worker --once
```

## HTTP API

Primary stage-1 endpoints:

```txt
GET    /api/agent/health
POST   /api/agent/threads
GET    /api/agent/threads
POST   /api/agent/threads/{thread_id}/messages
GET    /api/agent/threads/{thread_id}/messages
POST   /api/agent/runs
GET    /api/agent/runs
GET    /api/agent/runs/{run_id}
GET    /api/agent/runs/{run_id}/events
GET    /api/agent/runs/{run_id}/trace
GET    /api/agent/runs/{run_id}/stream
POST   /api/agent/runs/{run_id}/cancel
GET    /api/agent/approvals
POST   /api/agent/approvals/{approval_id}/resolve
GET    /api/agent/workspaces/{workspace_id}/files
GET    /api/agent/workspaces/{workspace_id}/files/{path}
PUT    /api/agent/workspaces/{workspace_id}/files/{path}
DELETE /api/agent/workspaces/{workspace_id}/files/{path}
GET    /api/agent/artifacts
GET    /api/agent/artifacts/{artifact_id}
```

## Verification

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

## Key Design Docs

- [Agent Harness Design](./docs/00-agent-harness-design.md)
- [Harness Engine Adapter Strategy](./docs/06-harness-engine-adapter-strategy.md)
- [Workflow Capability Integration](./docs/08-workflow-capability-integration.md)
- [Python Pydantic AI Backend Design](./docs/superpowers/specs/2026-06-16-python-pydantic-ai-agent-backend-design.md)
