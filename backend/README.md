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
- Optional Bearer token authentication via `AITHRU_AGENT_API_TOKEN`, with run scope limits from `AITHRU_AGENT_API_SCOPES`.
- Trusted `X-Aithru-Org-Id` and `X-Aithru-User-Id` headers bind identity and filter run, memory, and subagent resources.
- Queued Agent runs with worker execution.
- In-memory and SQLite persistence backends.
- Agent stream events, SSE formatting, and trace projection.
- Run stream follow mode waits for new SSE events until terminal run state or timeout.
- Event writer redaction for common sensitive payload keys before replay or SSE output.
- Run snapshot inspection with events, trace, todos, approvals, workspace file summaries, artifacts, and subagent runs.
- Runtime user input for active threaded runs through persisted messages and stream events.
- Completed assistant replies are persisted back to their Agent Thread for future run context.
- Local workspace, todo, artifact, memory, subagent, and sandbox tools behind the capability router.
- Unknown run skills are rejected before run creation so missing policy cannot fall back to unrestricted execution.
- Run and message APIs validate Agent Thread references before writing related state.
- Workspace file APIs validate workspace references before reading or writing files.
- HTTP workspace writes validate text content before entering persistence.
- Run event and stream reads validate run references before replay.
- Memory tools emit read/write events and trace spans.
- Workspace tools enforce skill path policy at execution time.
- Skill approval policy contributes execution-time approval requirements.
- Runtime subagent delegation with parent/child run links, events, and trace spans.
- Delegated child completion, failure, and cancellation are projected back to the parent run.
- Restricted local Python sandbox execution with stdout/stderr events and trace spans.
- Pydantic AI prompt context with skill instructions, thread summaries, readable memory, and workspace file summaries.
- Pydantic AI harness driver with controlled tool bridge.
- Pydantic AI tools expose Aithru descriptor input schemas directly to the model.
- Approval pause/resume semantics for risky Pydantic AI tool calls, including model continuation after approved tools.
- Pydantic AI approval resume state is persisted on approval metadata for worker restart recovery.
