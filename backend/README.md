# Aithru Agent Backend

Python-first backend for Aithru Agent.

This backend owns the Agent API, worker runtime, event stream, trace projection,
workspace, artifacts, approvals, and capability boundary. Pydantic AI powers the
default harness driver, and `pydantic-ai-harness` is available for internal
capability composition, but neither dependency defines public Aithru product
contracts.

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
- Trusted `X-Aithru-Org-Id` and `X-Aithru-User-Id` headers bind identity and filter run, memory, skill, and subagent resources.
- Queued Agent runs with worker execution.
- In-process queue deduplicates pending run ids; persistent stores can still
  claim queued runs when a queued notification is stale or missing.
- In-memory and SQLite persistence backends.
- Agent stream events, SSE formatting, and trace projection.
- Route-grouped FastAPI control plane with new `/api/threads` and `/api/runs`
  paths plus legacy `/api/agent/...` compatibility aliases.
- Run stream follow mode waits for new SSE events until terminal run state or timeout.
- Event writer redaction for common sensitive payload keys before replay or SSE output.
- Run snapshot inspection with events, trace, todos, approvals, workspace file summaries, artifacts, and subagent runs.
- Completed runs store a result summary with final content, artifact ids, and message references.
- Runtime user input for active threaded runs through persisted messages and stream events.
- Completed assistant replies are persisted back to their Agent Thread for future run context.
- Local workspace, todo, artifact, memory, subagent, and sandbox tools behind the capability router.
- Unknown or cross-organization run skills are rejected before run creation, execution, or approval resume so missing policy cannot fall back to unrestricted execution.
- Run tool inspection validates the run skill boundary before exposing available tools.
- Runs attached to Agent Threads must stay inside the thread organization and owner boundary.
- Run and message APIs validate Agent Thread references before writing related state.
- Workspace file APIs validate workspace references before reading or writing files.
- HTTP workspace writes validate text content before entering persistence.
- Run event and stream reads validate run references before replay.
- Run `join`, `stream`, and `cancel` endpoints are available on new run paths
  without moving run state out of Aithru.
- `AgentWorkerRunner.join_run()` owns run join waiting, and store updates
  validate run status values back into Aithru domain enums.
- Memory tools emit read/write events and trace spans.
- Memory tools bind user/thread/workspace/organization/skill scope ids to the current run context.
- Todo and artifact mutation tools bind object ids to the current run context.
- Workspace tools enforce skill path policy at execution time.
- Skill approval policy contributes execution-time approval requirements.
- Skill packages can be loaded from `SKILL.md` with enabled/disabled state,
  allowed tools, denied tools, and capability-style instruction injection.
- Runtime subagent delegation with parent/child run links, events, and trace spans.
- Model-facing `task(description, prompt, subagent_type)` tool with inline MVP
  child-run join and `waiting_subagent` parent status.
- Subagent delegation validates requested child skills and prevents child scope escalation beyond the parent run.
- Delegated child completion, failure, and cancellation are projected back to the parent run.
- Run cancellation rejects terminal runs and preserves completed/failed audit state.
- Restricted local Python sandbox execution with stdout/stderr events and trace spans.
- Per-run harness options for model selection and additional run instructions.
- Pydantic AI prompt context with skill instructions, thread summaries, readable memory, and workspace file summaries.
- Pydantic AI harness driver with controlled tool bridge.
- Phase 1 `pydantic-ai-harness` compatibility probe covering the internal
  dependency import and Pydantic AI runtime APIs used by Aithru.
- Internal `aithru_agent.agent.capabilities` package with `AithruToolset` and
  `AithruBoundaryCapability` for Pydantic-native tool assembly behind the
  Aithru Capability Router.
- `AgentRuntime.build_agent()` assembles Aithru tools through the internal
  boundary capability instead of direct raw Pydantic function tools.
- Active run skills add `SkillInstructionCapability` while tool exposure remains
  constrained by the Aithru run context and capability router.
- Pydantic AI usage counts are emitted as debug `model.usage` events and projected into model trace spans.
- Pydantic AI tools expose Aithru descriptor input schemas directly to the model.
- Approval pause/resume semantics for risky Pydantic AI tool calls, including model continuation after approved tools.
- Pydantic AI approval resume state is persisted on approval metadata for worker restart recovery.
