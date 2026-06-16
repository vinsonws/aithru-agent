# Aithru Agent Backend

Python-first backend for Aithru Agent.

This backend owns the Agent API, worker runtime, event stream, trace projection,
workspace, artifacts, approvals, and capability boundary. Pydantic AI powers the
default harness driver but does not define public Aithru product contracts.

## Run

```bash
uv run pytest
uv run python examples/file_report_agent.py
uv run uvicorn aithru_agent.api.main:app --reload
```

`POST /api/agent/runs` creates queued runs by default. A worker executes queued
runs.

For one-process development, use the in-memory default. For an API process and
worker process sharing state, use SQLite:

```bash
export AITHRU_AGENT_PERSISTENCE_BACKEND=sqlite
export AITHRU_AGENT_SQLITE_PATH=.aithru/agent.sqlite

uv run uvicorn aithru_agent.api.main:app --reload
uv run aithru-agent-worker --once
```

The worker can also drain a specific SQLite file directly:

```bash
uv run aithru-agent-worker --once --sqlite-path .aithru/agent.sqlite
```

## Current Capabilities

- FastAPI Agent control plane.
- Queued Agent runs with worker execution.
- In-memory and SQLite persistence backends.
- Agent stream events, SSE formatting, and trace projection.
- Local workspace, todo, artifact, memory, and subagent tools behind the capability router.
- Runtime subagent delegation with parent/child run links, events, and trace spans.
- Pydantic AI harness driver with controlled tool bridge.
- Approval pause semantics for risky Pydantic AI tool calls.
