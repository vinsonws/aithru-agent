# Model Reasoning Effort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the composer Reasoning selector control the per-run model thinking depth instead of enabling thinking from the model profile capability alone.

**Architecture:** Model profiles keep capability flags only. Composer maps `quick/thinking/pro/ultra` to a run-level `model_reasoning_effort`, the API validates the requested effort against profile capabilities, and the Pydantic runtime passes that effort as per-run `model_settings`.

**Tech Stack:** FastAPI, Pydantic models, Pydantic AI `ModelSettings.thinking`, React composer state, Node test runner, pytest.

## Global Constraints

- Keep real model actions capability-boundary controlled.
- Do not expose unrestricted local system access or provider credentials.
- Preserve existing model profile capability semantics: `thinking` means allowed, not forced.
- Follow TDD: write and run failing tests before production code.

---

### Task 1: Backend Reasoning Effort Contract

**Files:**
- Modify: `backend/src/aithru_agent/domain/run.py`
- Modify: `backend/src/aithru_agent/api/routes/runs.py`
- Modify: `backend/src/aithru_agent/model_profiles/factory.py`
- Test: `backend/tests/unit/domain/test_models.py`
- Test: `backend/tests/integration/test_model_profile_api.py`
- Test: `backend/tests/unit/model_profiles/test_factory.py`

**Interfaces:**
- Produces: `AgentModelReasoningEffort` enum values `none`, `low`, `medium`, `high`.
- Produces: `AgentRunHarnessOptions.model_reasoning_effort`.
- Consumes: existing `AgentModelProfileEntry.capabilities.thinking`.

- [x] **Step 1: Write failing tests**
  - Assert `AgentRunHarnessOptions(model_reasoning_effort="medium")` round-trips.
  - Assert profile resolution rejects `model_reasoning_effort="medium"` when profile thinking is false.
  - Assert profile factory does not set thinking just because profile thinking is allowed.

- [x] **Step 2: Run tests to verify failure**
  - `cd backend && uv run pytest tests/unit/domain/test_models.py tests/integration/test_model_profile_api.py -k "reasoning or thinking" tests/unit/model_profiles/test_factory.py`

- [x] **Step 3: Implement contract**
  - Add enum and field.
  - Validate non-`none` effort against profile thinking capability.
  - Remove capability-driven default thinking from profile factory.

- [x] **Step 4: Run tests to verify pass**
  - Same command as Step 2.

### Task 2: Runtime Per-Run Model Settings

**Files:**
- Modify: `backend/src/aithru_agent/agent/runtime.py`
- Test: `backend/tests/integration/test_pydantic_driver.py`

**Interfaces:**
- Consumes: `AgentRunHarnessOptions.model_reasoning_effort`.
- Produces: `model_settings={"thinking": False | "low" | "medium" | "high"}` passed to `Agent.run_stream_events`.
- Keeps: `ThinkingPartDelta` mapped to `reasoning.delta`.

- [x] **Step 1: Write failing tests**
  - Use a fake agent to record `model_settings`.
  - Assert `medium` becomes `{"thinking": "medium"}`.
  - Assert `none` becomes `{"thinking": False}`.

- [x] **Step 2: Run tests to verify failure**
  - `cd backend && uv run pytest tests/integration/test_pydantic_driver.py -k reasoning`

- [x] **Step 3: Implement runtime mapping**
  - Add helper converting run effort to Pydantic AI `thinking` value.
  - Pass helper output into every `run_stream_events` call.

- [x] **Step 4: Run tests to verify pass**
  - Same command as Step 2.

### Task 3: Frontend Composer Mapping

**Files:**
- Modify: `frontend/src/features/chat/composerState.ts`
- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/features/conversation/NewThreadPage.tsx`
- Test: `frontend/tests/composer-state.test.mjs`
- Test: `frontend/tests/chat-composer-options.test.mjs`

**Interfaces:**
- Produces: `reasoningEffortForReasoningLevel`.
- Produces: `buildComposerHarnessOptions(profileKey, mode, reasoningLevel)`.

- [x] **Step 1: Write failing tests**
  - Assert `quick -> none`, `thinking -> low`, `pro -> medium`, `ultra -> high`.
  - Assert harness options include `model_reasoning_effort`.

- [x] **Step 2: Run tests to verify failure**
  - `cd frontend && npm test -- tests/composer-state.test.mjs tests/chat-composer-options.test.mjs`

- [x] **Step 3: Implement frontend mapping**
  - Add mapping helper.
  - Pass selected reasoning level when building harness options.

- [x] **Step 4: Run frontend tests and typecheck**
  - `cd frontend && npm test`
  - `cd frontend && npm run typecheck`

### Task 4: Final Verification

**Files:**
- No new source files.

- [x] **Step 1: Run backend verification**
  - `cd backend && uv run pytest`
  - `cd backend && uv run python examples/file_report_agent.py`

- [x] **Step 2: Run frontend verification**
  - `cd frontend && npm test`
  - `cd frontend && npm run typecheck`

- [x] **Step 3: Report**
  - Explain that existing completed runs cannot gain reasoning events.
  - Ask user to restart backend if hot reload is not active before starting a new run.
