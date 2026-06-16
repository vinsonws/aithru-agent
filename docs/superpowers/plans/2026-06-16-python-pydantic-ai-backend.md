# Python Pydantic AI Agent Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the TypeScript Agent backend with a Python FastAPI + Pydantic AI backend that can run DeerFlow-like file/report Agent tasks with replayable events, controlled tools, approvals, artifacts, workspace state, and trace projection.

**Architecture:** Build a Python-first backend under `backend/` with Aithru-owned domain, stream, trace, capability, workspace, artifact, API, and worker layers. Pydantic AI is isolated behind `harness/drivers/pydantic_ai`, while all real actions go through the Aithru capability router. Keep a scripted driver for deterministic tests and use Pydantic AI for the real harness path.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, Pydantic AI, pytest, httpx, uvicorn, in-memory stores for stage 1, optional OpenTelemetry-compatible design.

---

## File Structure

Create the Python backend:

```txt
backend/
  pyproject.toml
  README.md
  src/aithru_agent/
    api/
    application/
    artifacts/
    capabilities/
    domain/
    harness/
    observability/
    persistence/
    platform/
    skills/
    stream/
    trace/
    worker/
    workspace/
  tests/
    unit/
    integration/
    e2e/
```

Keep the TypeScript code until the Python backend passes the e2e file/report run, then delete the old TS packages and scripts in a final cleanup task.

## Task 1: Python Project Skeleton

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/README.md`
- Create: `backend/src/aithru_agent/__init__.py`
- Create: `backend/tests/test_smoke.py`

- [ ] Write a smoke test importing `aithru_agent`.
- [ ] Run `cd backend && uv run pytest tests/test_smoke.py -q` and verify it fails because the package does not exist.
- [ ] Add the package skeleton and `pyproject.toml`.
- [ ] Run the smoke test and verify it passes.
- [ ] Commit with `feat: add python backend skeleton`.

## Task 2: Domain Models

**Files:**
- Create: `backend/src/aithru_agent/domain/*.py`
- Test: `backend/tests/unit/domain/test_models.py`

- [ ] Test that run, event, tool, approval, workspace, artifact, and todo models serialize with stable string IDs and enum values.
- [ ] Run the domain test and verify it fails.
- [ ] Implement Pydantic domain models.
- [ ] Run the domain test and verify it passes.
- [ ] Commit with `feat: add agent domain models`.

## Task 3: Stream Store, Writer, and SSE Encoding

**Files:**
- Create: `backend/src/aithru_agent/stream/events.py`
- Create: `backend/src/aithru_agent/stream/store.py`
- Create: `backend/src/aithru_agent/stream/writer.py`
- Create: `backend/src/aithru_agent/stream/sse.py`
- Test: `backend/tests/unit/stream/test_stream.py`

- [ ] Test event sequence assignment, replay by run, replay after sequence, and SSE formatting.
- [ ] Run the stream test and verify it fails.
- [ ] Implement stream event, in-memory event store, event writer, and SSE helper.
- [ ] Run the stream test and verify it passes.
- [ ] Commit with `feat: add agent event stream`.

## Task 4: In-Memory Persistence

**Files:**
- Create: `backend/src/aithru_agent/persistence/protocols.py`
- Create: `backend/src/aithru_agent/persistence/memory/store.py`
- Test: `backend/tests/unit/persistence/test_memory_store.py`

- [ ] Test create/list/get/update for threads, messages, runs, approvals, workspace files, and artifacts.
- [ ] Run the persistence test and verify it fails.
- [ ] Implement the in-memory store behind focused methods.
- [ ] Run the persistence test and verify it passes.
- [ ] Commit with `feat: add in-memory backend store`.

## Task 5: Workspace, Todo, and Artifact Local Tools

**Files:**
- Create: `backend/src/aithru_agent/capabilities/descriptors.py`
- Create: `backend/src/aithru_agent/capabilities/router.py`
- Create: `backend/src/aithru_agent/capabilities/policy.py`
- Create: `backend/src/aithru_agent/capabilities/local_tools/workspace.py`
- Create: `backend/src/aithru_agent/capabilities/local_tools/todo.py`
- Create: `backend/src/aithru_agent/capabilities/local_tools/artifact.py`
- Test: `backend/tests/unit/capabilities/test_local_tools.py`

- [ ] Test tool listing includes workspace, todo, and artifact tools with risk/scopes.
- [ ] Test read/list/write workspace calls go through the router.
- [ ] Test write/delete can return `waiting_approval` when policy requires approval.
- [ ] Test todo and artifact tool calls emit normalized results.
- [ ] Run the capability tests and verify they fail.
- [ ] Implement descriptors, policy checks, router prepare/execute, and local tools.
- [ ] Run the capability tests and verify they pass.
- [ ] Commit with `feat: add local capability tools`.

## Task 6: Trace Projection

**Files:**
- Create: `backend/src/aithru_agent/trace/spans.py`
- Create: `backend/src/aithru_agent/trace/projector.py`
- Test: `backend/tests/unit/trace/test_trace_projection.py`

- [ ] Test run, model, tool, approval, workspace, artifact, and external spans project from events.
- [ ] Run the trace test and verify it fails.
- [ ] Implement trace span projection from Aithru events.
- [ ] Run the trace test and verify it passes.
- [ ] Commit with `feat: add trace projection`.

## Task 7: Scripted Harness Driver and Worker

**Files:**
- Create: `backend/src/aithru_agent/harness/engine.py`
- Create: `backend/src/aithru_agent/harness/context_builder.py`
- Create: `backend/src/aithru_agent/harness/drivers/scripted/driver.py`
- Create: `backend/src/aithru_agent/worker/queue.py`
- Create: `backend/src/aithru_agent/worker/runner.py`
- Test: `backend/tests/integration/test_scripted_worker.py`

- [ ] Test a run creates todos, executes workspace/artifact tools through the router, writes events, and completes.
- [ ] Test cancellation writes `run.cancelled`.
- [ ] Run the worker tests and verify they fail.
- [ ] Implement the harness interface, context builder, scripted driver, in-process queue, and worker runner.
- [ ] Run the worker tests and verify they pass.
- [ ] Commit with `feat: add scripted agent worker`.

## Task 8: Approval Pause and Resume

**Files:**
- Modify: `backend/src/aithru_agent/worker/runner.py`
- Modify: `backend/src/aithru_agent/capabilities/router.py`
- Create: `backend/src/aithru_agent/application/approval_service.py`
- Test: `backend/tests/integration/test_approval_resume.py`

- [ ] Test a risky write pauses the run, creates an approval, and does not execute the tool.
- [ ] Test approval resolution resumes and completes the tool/run.
- [ ] Test rejection fails the run and records the decision.
- [ ] Run the approval tests and verify they fail.
- [ ] Implement pending approval state and resume flow.
- [ ] Run the approval tests and verify they pass.
- [ ] Commit with `feat: add approval pause resume`.

## Task 9: FastAPI Control Plane

**Files:**
- Create: `backend/src/aithru_agent/api/main.py`
- Create: `backend/src/aithru_agent/api/dependencies.py`
- Create: `backend/src/aithru_agent/api/routes/*.py`
- Create: `backend/src/aithru_agent/application/*.py`
- Test: `backend/tests/integration/test_api.py`

- [ ] Test health, thread/message CRUD, run create/get/events/stream/cancel, approval resolve, workspace file APIs, and artifact APIs using `httpx.AsyncClient`.
- [ ] Run the API tests and verify they fail.
- [ ] Implement FastAPI routes and application services.
- [ ] Run the API tests and verify they pass.
- [ ] Commit with `feat: add agent fastapi backend`.

## Task 10: Pydantic AI Driver

**Files:**
- Create: `backend/src/aithru_agent/harness/drivers/pydantic_ai/driver.py`
- Create: `backend/src/aithru_agent/harness/drivers/pydantic_ai/agent_factory.py`
- Create: `backend/src/aithru_agent/harness/drivers/pydantic_ai/deps.py`
- Create: `backend/src/aithru_agent/harness/drivers/pydantic_ai/tool_bridge.py`
- Create: `backend/src/aithru_agent/harness/drivers/pydantic_ai/event_mapper.py`
- Create: `backend/src/aithru_agent/harness/drivers/pydantic_ai/usage_mapper.py`
- Test: `backend/tests/unit/harness/test_pydantic_event_mapper.py`
- Test: `backend/tests/integration/test_pydantic_driver.py`

- [ ] Test Pydantic AI event mapper converts model, text, tool call, tool result, and final result signals into Aithru event intents.
- [ ] Test tool bridge calls the Aithru capability router and never executes direct filesystem actions.
- [ ] Test the driver can run with a test model or fallback scripted model configuration.
- [ ] Run the Pydantic driver tests and verify they fail.
- [ ] Implement the Pydantic AI driver and tool bridge.
- [ ] Run the Pydantic driver tests and verify they pass.
- [ ] Commit with `feat: add pydantic ai harness driver`.

## Task 11: DeerFlow-Like E2E Demo

**Files:**
- Create: `backend/tests/e2e/test_file_report_agent.py`
- Create: `backend/examples/file_report_agent.py`

- [ ] Test a workspace with input files can produce `/reports/report.md`, a report artifact, final message, replayable events, and trace spans.
- [ ] Run the e2e test and verify it fails.
- [ ] Implement any missing vertical-slice behavior.
- [ ] Run the e2e test and verify it passes.
- [ ] Commit with `feat: add file report agent demo`.

## Task 12: Delete TypeScript Backend and Update Root Tooling

**Files:**
- Delete: `apps/agent-server`
- Delete: `packages`
- Delete: `examples/harness-basic.ts`
- Delete: `pnpm-workspace.yaml`
- Delete: TypeScript config files that are no longer used
- Modify: `README.md`
- Modify: `docs/00-agent-harness-design.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: root project scripts if retained

- [ ] Confirm Python tests pass before deleting TS.
- [ ] Delete old TypeScript backend/packages.
- [ ] Update README and architecture docs to identify Python backend as source of truth.
- [ ] Run repository verification.
- [ ] Commit with `refactor: replace ts backend with python pydantic ai backend`.

## Final Verification

- [ ] Run `cd backend && uv run pytest`.
- [ ] Run `cd backend && uv run python examples/file_report_agent.py`.
- [ ] Run API smoke test against FastAPI app.
- [ ] Run license/dependency check for runtime dependencies.
- [ ] Confirm no TS backend packages remain.
- [ ] Confirm event stream can replay the full file/report run.
- [ ] Confirm trace projection covers model/tool/workspace/artifact spans.
