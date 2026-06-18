# Pydantic AI Harness Platform Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` when turning this into code. This document is intentionally shallow-but-complete: it is a goal-ready architecture and migration plan, not a line-by-line patch script.

**Goal:** Rebase the internal Aithru Agent runtime on Pydantic AI's capability/harness model, using `pydantic-ai-harness` where appropriate, while keeping Aithru's platform APIs, run model, capability router, events, approvals, workspace, artifacts, skills, and child-run observability under Aithru ownership.

**Architecture:** Pydantic AI remains the agent execution runtime. `pydantic-ai-harness` becomes the internal capability composition layer. Aithru provides a custom `AithruBoundaryCapability` so every real tool action still passes through the Aithru Capability Router and emits Aithru events. Public API design should borrow LangGraph Server's threads/runs/stream/join/cancel semantics without splitting Aithru into two services yet.

**Tech Stack:** Python 3.12, FastAPI, Pydantic AI, `pydantic-ai-harness`, Aithru Capability Router, Aithru AgentStore, Aithru AgentStreamEvent, SQLite/in-memory stores.

---

## References

- Pydantic AI Harness: <https://github.com/pydantic/pydantic-ai-harness>
- Pydantic AI capabilities: <https://pydantic.dev/docs/ai/core-concepts/capabilities/>
- Pydantic AI deferred tools: <https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/>
- Pydantic AI UI adapters: <https://pydantic.dev/docs/ai/integrations/ui/overview/>
- LangGraph Agent Server: <https://docs.langchain.com/langsmith/agent-server>
- LangGraph streaming and join semantics: <https://docs.langchain.com/langsmith/streaming>
- LangGraph run stream API shape: <https://docs.langchain.com/langsmith/agent-server-api/thread-runs/create-run-stream-output>
- Current Aithru design docs:
  - `docs/00-agent-harness-design.md`
  - `docs/04-skill-spec.md`
  - `docs/05-capability-router.md`
  - `docs/superpowers/specs/2026-06-16-python-pydantic-ai-agent-backend-design.md`

## Current Position

The current backend is already Pydantic AI-native, but the runtime still hand-assembles several harness concerns:

- `backend/src/aithru_agent/agent/runtime.py` lists tools, activates progressive skills, builds Pydantic tools, handles deferred approvals, and emits streaming model events.
- `backend/src/aithru_agent/agent/tools/bridge.py` correctly routes real tool execution through `AithruCapabilityRouter`.
- `backend/src/aithru_agent/worker/runner.py` owns platform run lifecycle, approval resume, completion, failure, and parent subagent status events.
- `backend/src/aithru_agent/api/main.py` is still a monolithic FastAPI control plane.

The core invariant to preserve:

```txt
model / Pydantic AI
  -> Aithru capability boundary
  -> Aithru Capability Router
  -> policy / scope / approval
  -> concrete local tool or future platform capability
  -> event / trace / artifact / redaction
```

## Target Shape

```txt
FastAPI API
  -> threads / messages / runs / events / approvals / skills / artifacts / workspaces routes
  -> AgentWorkerRunner
  -> AgentRuntime
      -> pydantic_ai.Agent
      -> pydantic-ai-harness capabilities
      -> AithruBoundaryCapability
          -> AithruToolset
          -> AithruCapabilityRouter
          -> EventWriter / Store / Approval / Subagent / Workspace
```

Do not expose Pydantic AI or `pydantic-ai-harness` types as public Aithru API contracts. They are implementation details under `backend/src/aithru_agent/agent`.

## Key Design Decisions

1. **Use `pydantic-ai-harness` at the runtime layer.**
   Treat it as the Pydantic-native harness/capability library. Do not treat it as the Aithru platform.

2. **Keep Aithru platform state authoritative.**
   Threads, runs, child runs, approvals, artifacts, workspaces, memory, events, trace, identity, and policy remain Aithru-owned.

3. **Borrow LangGraph Server's resource model, not its deployment split.**
   Implement route groups and semantics similar to threads/runs/stream/join/cancel, but keep one FastAPI service for now.

4. **Implement subagents as platform child runs with task-tool join semantics.**
   The model gets a DeerFlow/DeepAgents-style `task(...)` tool. Aithru creates a platform child `AgentRun`, links it with `AgentSubagentRun`, streams status, and returns the child result to the parent model.

5. **Upgrade skills into full skill packages.**
   Support `SKILL.md` plus resources/scripts/examples. Map active skills into Pydantic capability-style instructions/tool policy, while Aithru owns install/version/enable/publish/visibility.

6. **Do not directly use harness `FileSystem` or `Shell` for production Aithru actions.**
   They are useful references and may be dev-only capabilities, but production workspace/sandbox actions must continue through Aithru tools and router.

## Phase 1: Dependency And Compatibility Probe

**Purpose:** Confirm that `pydantic-ai-harness` can be added without breaking existing Pydantic AI runtime behavior.

**Files:**

- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Inspect: `backend/src/aithru_agent/agent/runtime.py`
- Inspect: `backend/src/aithru_agent/agent/tools/descriptors.py`
- Inspect: `backend/src/aithru_agent/agent/tools/bridge.py`

**Work:**

- Add `pydantic-ai-harness` as a backend dependency.
- Upgrade `pydantic-ai` / `pydantic-ai-slim` only as far as required by `pydantic-ai-harness`.
- Verify these APIs still work or update call sites:
  - `Agent.run_stream_events`
  - `DeferredToolRequests`
  - `DeferredToolResults`
  - `Tool.from_schema`
  - `tool.requires_approval`
  - `ModelMessagesTypeAdapter`
- Keep behavior unchanged in this phase.

**Verification:**

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

**Exit criteria:**

- Existing tests pass.
- File report example passes.
- No public API behavior changes.

**Status (2026-06-17): Complete.**

- Added `pydantic-ai-harness>=0.3.0` to backend dependencies and lock file.
- Kept locked `pydantic-ai` and `pydantic-ai-slim` at `1.107.0`; no upgrade was required.
- Added `backend/tests/unit/agent/test_pydantic_ai_harness_compatibility.py` to prove the harness package is importable and the current Aithru runtime APIs still exist:
  - `Agent.run_stream_events`;
  - `DeferredToolResults`;
  - `Tool.from_schema`;
  - `tool.requires_approval`;
  - `ModelMessagesTypeAdapter`.
- Kept behavior unchanged and did not expose Pydantic AI or harness types through domain/API/public contracts.
- Verification passed:
  - `uv run pytest`: 131 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.

## Phase 2: Add Aithru Capability Package

**Purpose:** Introduce Pydantic-native capability composition without changing platform semantics.

**Files:**

- Create: `backend/src/aithru_agent/agent/capabilities/__init__.py`
- Create: `backend/src/aithru_agent/agent/capabilities/boundary.py`
- Create: `backend/src/aithru_agent/agent/capabilities/toolset.py`
- Create: `backend/src/aithru_agent/agent/capabilities/events.py`
- Create: `backend/src/aithru_agent/agent/capabilities/approvals.py`
- Create: `backend/tests/agent/test_boundary_capability.py`
- Create: `backend/tests/agent/test_aithru_toolset.py`
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`
- Modify: `backend/src/aithru_agent/agent/tools/descriptors.py`

**Work:**

- Implement `AithruBoundaryCapability`.
- Implement `AithruToolset` that exposes current Aithru `AgentToolDescriptor` entries as Pydantic AI tools.
- Move descriptor-to-tool logic behind the toolset where possible.
- Keep `PydanticAIToolBridge` as the execution adapter, but make it usable by the capability/toolset.
- Add capability hooks for:
  - tool proposal events;
  - tool started/completed/failed events;
  - tool denial;
  - approval-required enforcement;
  - usage/event metadata where available.

**Important boundary:**

The capability may filter, wrap, and observe tools. It must not execute concrete actions directly. Concrete actions still go through `AithruCapabilityRouter`.

**Verification:**

```bash
cd backend
uv run pytest tests/agent/test_boundary_capability.py tests/agent/test_aithru_toolset.py
```

**Exit criteria:**

- A Pydantic AI agent can receive tools from `AithruToolset`.
- Tool execution still goes through `AithruCapabilityRouter`.
- Approval-required tools do not execute unless approved/deferred.

**Status (2026-06-17): Complete.**

- Added internal capability package under `backend/src/aithru_agent/agent/capabilities/`:
  - `AithruBoundaryCapability`;
  - `AithruToolset`;
  - boundary metadata helpers;
  - approval enforcement helpers.
- `AithruToolset` exposes `AgentToolDescriptor` entries as Pydantic AI tools and delegates concrete execution to `PydanticAIToolBridge`.
- `AithruBoundaryCapability` contributes the Aithru toolset, marks tool definitions as capability-router-bound, and raises Pydantic AI `ApprovalRequired` for unapproved approval-required tool calls.
- Added tests:
  - `backend/tests/agent/test_boundary_capability.py`;
  - `backend/tests/agent/test_aithru_toolset.py`.
- Boundary scan found no Pydantic AI or harness imports in `backend/src/aithru_agent/domain` or `backend/src/aithru_agent/api`.
- Verification passed:
  - `uv run pytest tests/agent/test_boundary_capability.py tests/agent/test_aithru_toolset.py`: 6 passed.
  - `uv run pytest`: 137 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.

## Phase 3: Refactor AgentRuntime Assembly

**Purpose:** Make `AgentRuntime` assemble capabilities instead of manually owning all harness behavior.

**Files:**

- Modify: `backend/src/aithru_agent/agent/runtime.py`
- Modify: `backend/src/aithru_agent/agent/instructions.py`
- Modify: `backend/src/aithru_agent/agent/deps.py`
- Add tests under: `backend/tests/agent/test_runtime_capability_assembly.py`

**Work:**

- Change `AgentRuntime.build_agent()` to build a capabilities list:
  - `AithruBoundaryCapability`
  - optional current-time/context capability if needed
  - optional skill capability
  - optional subagent capability
  - optional harness capabilities such as `CodeMode`, `ToolSearch`, or future stable harness capabilities
- Keep `AgentRuntime.run()` responsible for:
  - invoking `run_stream_events`;
  - turning model deltas into `message.delta`;
  - returning final output;
  - pausing for unresolved approvals/subagents when needed.
- Do not push Aithru run persistence into Pydantic AI message history as public state.

**Verification:**

```bash
cd backend
uv run pytest tests/agent/test_runtime_capability_assembly.py
uv run pytest
```

**Exit criteria:**

- Existing agent behavior remains intact.
- New capability assembly path is covered.
- `scripted` or adapter-era driver assumptions are not reintroduced.

**Status (2026-06-17): Complete.**

- Refactored `AgentRuntime.build_agent()` to assemble tools through `AithruBoundaryCapability(AithruToolset(...))` instead of direct raw Pydantic function tools.
- Kept `AgentRuntime.run()` and approval resume responsible for `run_stream_events`, message deltas, usage events, deferred approval persistence, and final output mapping.
- Added `backend/tests/agent/test_runtime_capability_assembly.py` to prove runtime assembly includes the Aithru boundary capability/toolset and no direct function tools.
- Regression verification covered streaming, tool bridge execution, deferred approvals, and approval resume.
- Verification passed:
  - `uv run pytest tests/agent/test_runtime_capability_assembly.py`: 1 passed.
  - `uv run pytest tests/agent/test_runtime_capability_assembly.py tests/integration/test_pydantic_driver.py tests/integration/test_pydantic_tool_bridge.py tests/integration/test_approval_resume.py`: 21 passed.
  - `uv run pytest`: 138 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.

## Phase 4: Platform Child Run Subagent Tool

**Purpose:** Provide DeepAgents/DeerFlow-style `task` semantics while preserving platform child-run observability.

**Files:**

- Create: `backend/src/aithru_agent/agent/capabilities/subagents.py`
- Modify: `backend/src/aithru_agent/capabilities/local_tools/subagent.py`
- Modify: `backend/src/aithru_agent/worker/runner.py`
- Modify: `backend/src/aithru_agent/domain/run.py`
- Modify: `backend/src/aithru_agent/domain/subagent.py`
- Add tests under: `backend/tests/agent/test_subagent_task_tool.py`
- Add tests under: `backend/tests/worker/test_child_run_join.py`

**Work:**

- Expose a model-facing tool:

```txt
task(description, prompt, subagent_type)
```

- On task call:
  - create child `AgentRun` with `source=delegated_task`;
  - create/update `AgentSubagentRun`;
  - enqueue or execute the child run;
  - emit `subagent.started`;
  - wait for terminal child result in the inline MVP;
  - return child result to the parent model as the tool result.
- Keep the child run visible via existing and future run APIs.
- Add a later-compatible status for parent waiting:

```txt
waiting_subagent
```

**MVP behavior:**

- Single-process inline join is acceptable.
- Production queue lease/heartbeat/dead-letter can remain out of scope for this phase.

**Verification:**

```bash
cd backend
uv run pytest tests/agent/test_subagent_task_tool.py tests/worker/test_child_run_join.py
```

**Exit criteria:**

- Parent model can call `task`.
- A child run is visible as a platform run.
- Parent receives child result and can continue.
- Parent events include subagent lifecycle events.

**Status (2026-06-18): Complete.**

- Added model-facing `task(description, prompt, subagent_type)` as an Aithru local tool exposed through `AithruCapabilityRouter`.
- Added internal `SubagentTaskCapability` instructions for Pydantic capability assembly; it does not execute real actions directly.
- Added `waiting_subagent` run status.
- Added inline MVP child-run join via `AgentWorkerRunner.execute_child_run_for_task()`:
  - parent run emits `run.paused` with `waiting_subagent`;
  - child `AgentRun` is created with `source=delegated_task`;
  - child run is executed inline;
  - parent receives `subagent.completed`;
  - parent emits `run.resumed` and receives the child result as the task tool result.
- Kept `subagent.delegate` as the existing queued delegation path.
- Added tests:
  - `backend/tests/agent/test_subagent_task_tool.py`;
  - `backend/tests/worker/test_child_run_join.py`.
- Verification passed:
  - `uv run pytest tests/agent/test_subagent_task_tool.py tests/worker/test_child_run_join.py`: 2 passed.
  - `uv run pytest tests/integration/test_subagents.py tests/agent/test_subagent_task_tool.py tests/worker/test_child_run_join.py`: 7 passed.
  - `uv run pytest`: 140 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.

## Phase 5: Full Skill Package Support

**Purpose:** Treat skills as harness-native progressive capability packages.

**Files:**

- Modify: `backend/src/aithru_agent/domain/skill.py`
- Modify: `backend/src/aithru_agent/skills/loader.py`
- Modify: `backend/src/aithru_agent/skills/resolver.py`
- Create: `backend/src/aithru_agent/agent/capabilities/skills.py`
- Add tests under: `backend/tests/skills/test_skill_package_loader.py`
- Add tests under: `backend/tests/agent/test_skill_capability.py`

**Target layout:**

```txt
skills/{public,custom}/skill-name/
  SKILL.md
  resources/
  scripts/
  examples/
```

**Work:**

- Parse `SKILL.md` frontmatter and body.
- Support enabled/disabled state.
- Support `allowed_tools` and `denied_tools`.
- Inject active skill instructions through a Pydantic capability-style path.
- Keep skill product management Aithru-owned:
  - install;
  - enable/disable;
  - version;
  - publish state;
  - org visibility.

**Important note:**

Do not depend on unstable `pydantic-ai-harness` experimental skills as the sole implementation. Use the Pydantic capability pattern now; later align with stable upstream skills capability if it lands.

**Verification:**

```bash
cd backend
uv run pytest tests/skills/test_skill_package_loader.py tests/agent/test_skill_capability.py
```

**Exit criteria:**

- A skill package can be loaded from disk.
- Active skill instructions affect the run.
- Tool policy is enforced by Aithru router/capability filtering.

**Implementation status (2026-06-18):**

- Added `AgentSkill.enabled` and `AgentSkill.denied_tools` as Aithru-owned
  product policy fields.
- `FileSkillLoader` now supports legacy `skill.json` manifests and
  `skills/{public,custom}/skill-name/SKILL.md` packages with frontmatter,
  instructions, policy sections, version, status, and enabled state.
- `InMemorySkillResolver` resolves only published and enabled skills.
- Added internal `SkillInstructionCapability` for active skill instruction
  injection during runtime capability assembly.
- `ContextBuilder` removes denied tools before exposing the run tool catalog to
  the Aithru capability router.
- Verification so far:
  - `uv run pytest tests/skills/test_skill_package_loader.py tests/agent/test_skill_capability.py`: 5 passed.
  - `uv run pytest tests/unit/skills/test_loader.py tests/unit/agent/test_progressive_skills.py tests/unit/agent/test_instructions.py tests/integration/test_skill_policy.py`: 12 passed.
  - `uv run pytest`: 145 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.
  - Public boundary scan for Pydantic AI / harness capability symbols under
    `backend/src/aithru_agent/domain` and `backend/src/aithru_agent/api`: no
    matches.

## Phase 6: LangGraph-Like API Route Split

**Purpose:** Make the API maintainable and align run/thread semantics with mature agent server conventions.

**Files:**

- Modify: `backend/src/aithru_agent/api/main.py`
- Create: `backend/src/aithru_agent/api/routes/__init__.py`
- Create: `backend/src/aithru_agent/api/routes/health.py`
- Create: `backend/src/aithru_agent/api/routes/threads.py`
- Create: `backend/src/aithru_agent/api/routes/messages.py`
- Create: `backend/src/aithru_agent/api/routes/runs.py`
- Create: `backend/src/aithru_agent/api/routes/events.py`
- Create: `backend/src/aithru_agent/api/routes/approvals.py`
- Create: `backend/src/aithru_agent/api/routes/workspaces.py`
- Create: `backend/src/aithru_agent/api/routes/artifacts.py`
- Create: `backend/src/aithru_agent/api/routes/skills.py`
- Create: `backend/src/aithru_agent/api/dependencies.py`
- Add API tests under: `backend/tests/api/`

**New API shape to introduce while keeping old `/api/agent/...` compatibility:**

```txt
POST /api/threads
GET  /api/threads
GET  /api/threads/{thread_id}
POST /api/threads/{thread_id}/messages
GET  /api/threads/{thread_id}/messages

POST /api/threads/{thread_id}/runs
POST /api/threads/{thread_id}/runs/stream
GET  /api/threads/{thread_id}/runs
GET  /api/threads/{thread_id}/runs/{run_id}
GET  /api/threads/{thread_id}/runs/{run_id}/stream
GET  /api/threads/{thread_id}/runs/{run_id}/join
POST /api/threads/{thread_id}/runs/{run_id}/cancel

POST /api/runs/stream
POST /api/runs/wait
```

**Semantics to borrow from LangGraph Server:**

- `runs/stream`: create and stream one run.
- `runs/{run_id}/stream`: join an existing run stream.
- `runs/{run_id}/join`: wait for terminal state and return final result.
- `cancel`: stop an active run; later support `interrupt` and `rollback`.
- `on_disconnect`: accept `cancel` or `continue`; MVP may only implement best-effort behavior.
- `stream_mode`: accept Aithru modes first; optionally map LangGraph names later.

**Verification:**

```bash
cd backend
uv run pytest tests/api
```

**Exit criteria:**

- `api/main.py` becomes a small app factory and router registrar.
- New route groups pass tests.
- Existing `/api/agent/...` behavior remains compatible.

**Implementation status (2026-06-18):**

- Split the monolithic FastAPI control plane into `api/dependencies.py` and
  route groups under `api/routes/`.
- `api/main.py` now creates the app, installs token middleware, attaches shared
  API dependencies, and registers routers.
- Added route groups for health, threads, messages, runs, events, approvals,
  workspaces, artifacts, skills, memory, and subagents.
- Added new `/api/threads/...`, `/api/runs/...`, `/api/runs/stream`, and
  `/api/runs/wait` paths while preserving existing `/api/agent/...`
  compatibility aliases.
- Added `GET .../join` for waiting on terminal run state and returning the final
  run record.
- Verification so far:
  - `uv run pytest tests/api`: 2 passed.
  - `uv run pytest tests/integration/test_api.py`: 36 passed.
  - `uv run pytest`: 147 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.
  - Public boundary scan for Pydantic AI / harness capability symbols under
    `backend/src/aithru_agent/domain` and `backend/src/aithru_agent/api`: no
    matches.
  - `git diff --check`: no whitespace errors; only Windows line-ending warnings.

## Phase 7: Minimal Worker And Queue Hardening For New Semantics

**Purpose:** Support stream/join/cancel and child-run join without attempting full production queue infrastructure.

**Files:**

- Modify: `backend/src/aithru_agent/worker/runner.py`
- Modify: `backend/src/aithru_agent/worker/queue.py`
- Modify: `backend/src/aithru_agent/persistence/protocols.py`
- Modify: `backend/src/aithru_agent/persistence/sqlite/store.py`
- Modify: `backend/src/aithru_agent/persistence/memory/store.py`
- Add tests under: `backend/tests/worker/`
- Add tests under: `backend/tests/persistence/`

**Work:**

- Add run status support:

```txt
queued
running
waiting_approval
waiting_subagent
completed
failed
cancelled
```

- Add `join_run` helper behavior.
- Add `stream_existing_run` API support using current event store.
- Add resume hooks:
  - `resume_after_approval`;
  - `resume_after_subagent`.
- Keep retry/heartbeat/lease/dead-letter for a later productionization plan.

**Verification:**

```bash
cd backend
uv run pytest tests/worker tests/persistence
```

**Exit criteria:**

- Existing run execution still works.
- Child-run join works in the MVP path.
- API can join or stream a run by id.

**Implementation status (2026-06-18):**

- Added queue hardening so `InProcessRunQueue` deduplicates pending run ids.
- Added `AgentWorkerRunner.join_run()` for waiting on terminal run state.
- Added explicit runner hooks for approval and subagent resume paths:
  `resume_after_approval` and `resume_after_subagent`.
- API join helpers now delegate to `AgentWorkerRunner.join_run()`.
- Memory and SQLite stores validate `update_run` payloads back into
  `AgentRun`, keeping string status updates normalized to `AgentRunStatus`.
- Verification so far:
  - `uv run pytest tests/worker tests/persistence`: 5 passed.
  - `uv run pytest tests/api tests/worker tests/persistence`: 7 passed.
  - `uv run pytest`: 151 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.
  - Public boundary scan for Pydantic AI / harness capability symbols under
    `backend/src/aithru_agent/domain` and `backend/src/aithru_agent/api`: no
    matches.
  - `git diff --check`: no whitespace errors; only Windows line-ending warnings.

## Phase 8: Docs And Migration Notes

**Purpose:** Make the new architecture explicit so future agents do not reintroduce harness adapters or bypass the capability boundary.

**Files:**

- Modify: `docs/00-agent-harness-design.md`
- Modify: `docs/04-skill-spec.md`
- Modify: `docs/05-capability-router.md`
- Modify: `README.md`
- Modify: `backend/README.md` if present or add one if needed.

**Docs updates:**

- State that Aithru Agent runtime is Pydantic AI + `pydantic-ai-harness` capability-based.
- State that Pydantic AI and harness types remain internal implementation details.
- Document the API route groups and compatibility window for `/api/agent/...`.
- Document subagent child-run semantics.
- Document skill package structure.
- Reaffirm the capability boundary:

```txt
models propose tool calls;
models do not execute real actions directly.
```

**Verification:**

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

**Exit criteria:**

- Docs match the implemented architecture.
- Tests and example pass.

**Implementation status (2026-06-18):**

- Updated `docs/00-agent-harness-design.md` with the Phase 1-7 architecture:
  internal capability composition, child-run task semantics, skill package
  support, route groups, and queue/join hardening.
- Updated `docs/04-skill-spec.md` to document `SKILL.md` packages,
  enabled/disabled state, allowed/denied tools, and capability-style
  instruction injection.
- Updated `docs/05-capability-router.md` to document the current
  `AithruBoundaryCapability` / `AithruToolset` / `PydanticAIToolBridge` /
  `AithruCapabilityRouter` path and reaffirm that concrete actions remain
  router-bound.
- Updated `README.md` and `backend/README.md` with the new API route shape,
  skill packages, subagent task joins, and queue/join semantics.
- Boundary audit so far:
  - Public domain/API search for Pydantic AI and pydantic-ai-harness symbols:
    no matches.
  - Real action search confirms Pydantic AI tool execution enters
    `PydanticAIToolBridge`, which calls `AithruCapabilityRouter.execute_tool_call`.
  - Sandbox subprocess execution remains confined to the `sandbox.run_python`
    local tool adapter.
- Verification:
  - `uv run pytest`: 151 passed.
  - `uv run python examples/file_report_agent.py`: run completed with 26 events and artifact `a`.
  - Public boundary scan for Pydantic AI / harness capability symbols under
    `backend/src/aithru_agent/domain` and `backend/src/aithru_agent/api`: no
    matches.
  - Real-action scan: Pydantic AI tool calls route through
    `PydanticAIToolBridge` and `AithruCapabilityRouter.execute_tool_call`;
    subprocess execution appears only in the `sandbox.run_python` local tool.
  - `git diff --check`: no whitespace errors; only Windows line-ending warnings.

## Recommended PR Breakdown

1. **PR 1: Dependency probe + AithruBoundaryCapability**
   - Adds `pydantic-ai-harness`.
   - Introduces internal `agent/capabilities`.
   - Keeps behavior mostly unchanged.

2. **PR 2: Runtime assembly on capabilities**
   - Refactors `AgentRuntime`.
   - Moves tool setup into capability/toolset shape.
   - Preserves approval behavior.

3. **PR 3: Platform child-run task tool**
   - Adds `task` join semantics.
   - Keeps child run platform-visible.

4. **PR 4: Skill package support**
   - Adds `SKILL.md` package loading.
   - Maps skills to capability-style runtime injection.

5. **PR 5: LangGraph-like API route split**
   - Splits `api/main.py`.
   - Adds stream/join/cancel-compatible route shape.

6. **PR 6: Docs and compatibility cleanup**
   - Updates design docs.
   - Keeps or marks old routes as compatibility surface.

## Risks

- `pydantic-ai-harness` is 0.x alpha. Keep imports isolated under `aithru_agent.agent` and avoid leaking its types into public Aithru schemas.
- Experimental harness capabilities may change or disappear. Use stable top-level capabilities when possible; copy concepts, not unstable APIs, for platform-critical behavior.
- Upgrading Pydantic AI may require adapting existing streaming and deferred approval logic.
- Harness `FileSystem` and `Shell` can bypass Aithru platform semantics if used carelessly. Production tools must still route through Aithru Capability Router.
- Child-run inline join is acceptable for MVP but not enough for production-scale distributed workers.
- API route compatibility must be tested so existing `/api/agent/...` callers do not break during migration.

## Non-Goals For This Plan

- Full production queue with heartbeat, lease timeout, retry, and dead-letter.
- Full production sandbox isolation.
- Full browser/web/MCP tool ecosystem.
- Public frontend implementation.
- Replacing Aithru Core `WorkflowSpec` or adding agent-owned workflow graph semantics.

## Final Verification

Before marking the refactor complete:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

The implementation is only complete when:

- Aithru runtime builds Pydantic AI agents through capabilities.
- Every real action still passes through Aithru Capability Router.
- Platform threads/runs/approvals/events/artifacts remain Aithru-owned.
- The `task` tool creates observable child runs and returns joined results to the parent model.
- Full skill packages load and apply tool policy.
- LangGraph-like run stream/join/cancel APIs exist alongside compatibility routes.
