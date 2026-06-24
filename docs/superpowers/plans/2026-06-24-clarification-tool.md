# Clarification Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the word-count-based `ClarificationPreflightProcessor` with a model-driven `ask_clarification` tool that the model calls when it needs more information, supporting both free-text responses and clickable options.

**Architecture:** Define `ClarificationLocalTool` as an Aithru capability adapter. When the model calls `ask_clarification`, Pydantic AI returns it as a `DeferredToolRequests.calls` item (external tool). The agent runtime detects the clarification call, writes `input.requested` with structured `question` + `options`, pauses as `waiting_input`. On user response, the worker builds `DeferredToolResults` with the user's text as the tool result and resumes.

**Tech Stack:** Python (pydantic-ai, FastAPI), TypeScript (React, TanStack Query)

## Global Constraints

- All real tool actions must go through the Aithru capability router
- No new workflow semantics (no Agent WorkflowSpec, no graph definitions)
- Sensitive values must not be logged or persisted insecurely
- Backend tests (`uv run pytest`) and file report example must pass
- Frontend must build cleanly (`npx vite build`)
- Follow existing naming conventions: `AgentToolDescriptor`, `AgentToolKind`, `AgentToolRiskLevel`

---

### Task 1: ClarificationLocalTool — tool definition

**Files:**
- Create: `backend/src/aithru_agent/capabilities/local_tools/clarification.py`
- Test: `backend/tests/unit/capabilities/test_clarification_tool.py`
- Modify: `backend/src/aithru_agent/capabilities/local_tools/__init__.py`

**Interfaces:**
- Produces: `ClarificationLocalTool` class with `list_tools() -> list[AgentToolDescriptor]` and `execute(request, context) -> AgentToolCallResult`
- Follows same pattern as `InputLocalTool` in `backend/src/aithru_agent/capabilities/local_tools/input.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/capabilities/test_clarification_tool.py
import pytest
from aithru_agent.capabilities.local_tools.clarification import ClarificationLocalTool
from aithru_agent.capabilities.descriptors import AgentRunContext
from aithru_agent.domain import AgentToolCallRequest


@pytest.fixture
def tool() -> ClarificationLocalTool:
    return ClarificationLocalTool()


@pytest.fixture
def context() -> AgentRunContext:
    return AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        thread_id="thread_1",
        scopes=["agent.input.write"],
    )


def test_lists_ask_clarification_descriptor(tool: ClarificationLocalTool):
    descriptors = tool.list_tools()
    assert len(descriptors) == 1
    d = descriptors[0]
    assert d.name == "ask_clarification"
    assert d.kind == "local_tool"
    assert d.risk_level == "safe"
    assert "agent.input.write" in d.required_scopes
    assert "question" in d.input_schema.get("required", [])
    assert "options" in d.input_schema["properties"]
    assert "clarification_type" in d.input_schema["properties"]
    assert "context" in d.input_schema["properties"]


def test_descriptor_input_schema_allows_options(tool: ClarificationLocalTool):
    d = tool.list_tools()[0]
    options_prop = d.input_schema["properties"]["options"]
    assert options_prop["type"] == "array"
    assert options_prop.get("items", {}).get("type") == "string"


def test_execute_ask_clarification_returns_completed(tool: ClarificationLocalTool, context: AgentRunContext):
    result = tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="ask_clarification",
            input={
                "question": "What topic?",
                "clarification_type": "missing_info",
                "options": ["A", "B"],
            },
            requested_by="model",
        ),
        context,
    )
    assert result.status == "completed"
    assert result.output["question"] == "What topic?"
    assert result.output["options"] == ["A", "B"]


def test_execute_unknown_tool_returns_denied(tool: ClarificationLocalTool, context: AgentRunContext):
    result = tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="unknown_tool",
            input={},
            requested_by="model",
        ),
        context,
    )
    assert result.status == "denied"


def test_execute_missing_question_raises(tool: ClarificationLocalTool, context: AgentRunContext):
    with pytest.raises(ValueError, match="question"):
        tool.execute(
            AgentToolCallRequest(
                id="call_1",
                tool_name="ask_clarification",
                input={"options": ["A"]},
                requested_by="model",
            ),
            context,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/capabilities/test_clarification_tool.py -v`
Expected: FAIL with ImportError (module not found)

- [ ] **Step 3: Write ClarificationLocalTool**

```python
# backend/src/aithru_agent/capabilities/local_tools/clarification.py
from typing import Any

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)

from ..descriptors import AgentRunContext


class ClarificationLocalTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="ask_clarification",
                kind=AgentToolKind.LOCAL_TOOL,
                description=(
                    "Ask the user for clarification before proceeding. "
                    "Use this when the request is ambiguous, incomplete, or you need to "
                    "confirm an approach before taking action. The user will see the "
                    "question and can respond directly or choose from provided options."
                ),
                input_schema={
                    "type": "object",
                    "required": ["question"],
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The clarification question to ask the user.",
                        },
                        "clarification_type": {
                            "type": "string",
                            "enum": [
                                "missing_info",
                                "ambiguous_requirement",
                                "approach_choice",
                                "risk_confirmation",
                                "suggestion",
                            ],
                            "default": "missing_info",
                            "description": "Category of clarification needed.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional background explaining why clarification is needed.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of choices for the user to pick from.",
                        },
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.input.write"],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name != "ask_clarification":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown clarification tool: {request.tool_name}"},
                redaction="none",
            )
        if context.thread_id is None:
            return AgentToolCallResult(
                status="denied",
                error={"message": "Clarification requests require an Agent Thread"},
                redaction="none",
            )
        input_data = _input_dict(request.input)
        question = _required_string(input_data, "question")
        clarification_type = _optional_string(input_data.get("clarification_type")) or "missing_info"
        context_str = _optional_string(input_data.get("context"))
        options = _optional_string_list(input_data.get("options"))
        return AgentToolCallResult(
            status="completed",
            output={
                "tool_call_id": request.id,
                "question": question,
                "clarification_type": clarification_type,
                "context": context_str,
                "options": options,
            },
            redaction="none",
        )


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value


def _required_string(input_data: dict[str, Any], key: str) -> str:
    value = input_data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required input field: {key}")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    stripped = value.strip()
    return stripped or None


def _optional_string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    result = [str(item).strip() for item in value if item is not None and str(item).strip()]
    return result or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/capabilities/test_clarification_tool.py -v`
Expected: 5 PASS

- [ ] **Step 5: Export from __init__.py**

Edit `backend/src/aithru_agent/capabilities/local_tools/__init__.py` — add import and export:

```python
from .clarification import ClarificationLocalTool
```

Add `"ClarificationLocalTool"` to `__all__`.

- [ ] **Step 6: Run all tests to confirm no regressions**

Run: `cd backend && uv run pytest tests/unit/capabilities/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/capabilities/local_tools/clarification.py \
        backend/src/aithru_agent/capabilities/local_tools/__init__.py \
        backend/tests/unit/capabilities/test_clarification_tool.py
git commit -m "feat: add ClarificationLocalTool with ask_clarification descriptor"
```

---

### Task 2: Register ClarificationLocalTool in application runtime

**Files:**
- Modify: `backend/src/aithru_agent/application/runtime.py`

**Interfaces:**
- Consumes: `ClarificationLocalTool` from `capabilities/local_tools/__init__.py`
- Produces: tool is listed via capability router's `list_tools()`, available to model

- [ ] **Step 1: Add import**

Edit `backend/src/aithru_agent/application/runtime.py`, add to existing local_tools import block (around line 27-36):

```python
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    ClarificationLocalTool,   # <-- add this
    InputLocalTool,
    MemoryLocalTool,
    ResearchLocalTool,
    SandboxLocalTool,
    SubagentLocalTool,
    TodoLocalTool,
    WorkbenchLocalTool,
    WorkspaceLocalTool,
)
```

- [ ] **Step 2: Add to tool_adapters list**

In `create_agent_application()`, add `ClarificationLocalTool` to the `tool_adapters` list (around line 119-131). Add it before `InputLocalTool`:

```python
tool_adapters = [
    WorkspaceLocalTool(resolved_store),
    TodoLocalTool(resolved_store),
    ArtifactLocalTool(resolved_store),
    ClarificationLocalTool(),    # <-- add this line
    InputLocalTool(),
    MemoryLocalTool(resolved_store),
    ...
]
```

- [ ] **Step 3: Run backend tests to verify tool is discoverable**

Run: `cd backend && uv run pytest tests/ -v -k "clarification or tool" 2>&1 | tail -20`
Expected: tests pass, no import errors

- [ ] **Step 4: Commit**

```bash
git add backend/src/aithru_agent/application/runtime.py
git commit -m "feat: register ClarificationLocalTool in agent runtime"
```

---

### Task 3: Handle ask_clarification in agent runtime

**Files:**
- Modify: `backend/src/aithru_agent/agent/runtime.py`
- Test: `backend/tests/unit/agent/test_clarification_handling.py`

**Interfaces:**
- Consumes: `DeferredToolRequests` from pydantic_ai, `PydanticAgentDeps`
- Produces: `_pending_clarifications` dict, `resume_clarification()` method

- [ ] **Step 1: Write the test**

```python
# backend/tests/unit/agent/test_clarification_handling.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.messages import ToolCallPart
from aithru_agent.agent.runtime import AgentRuntime, PendingApprovalState
from aithru_agent.domain import AgentRun, AgentRunStatus


@pytest.fixture
def runtime() -> AgentRuntime:
    rt = AgentRuntime(model="test")
    rt.model_factory = lambda _: MagicMock()
    return rt


def make_tool_call_part(name: str, args: dict, call_id: str = "call_1") -> ToolCallPart:
    return ToolCallPart(
        tool_name=name,
        args=args,
        tool_call_id=call_id,
    )


@pytest.mark.asyncio
async def test_detect_clarification_call_in_requests():
    """Verify we can detect ask_clarification in DeferredToolRequests.calls."""
    requests = DeferredToolRequests(
        calls=[
            make_tool_call_part("ask_clarification", {
                "question": "What topic?",
                "clarification_type": "missing_info",
                "options": ["A", "B"],
            }),
        ],
    )
    # The method should detect this as a clarification request
    clarification_call = next(
        (c for c in requests.calls if c.tool_name == "ask_clarification"),
        None,
    )
    assert clarification_call is not None
    assert clarification_call.tool_name == "ask_clarification"
    args = clarification_call.args_as_dict(raise_if_invalid=True)
    assert args["question"] == "What topic?"
    assert args["options"] == ["A", "B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/agent/test_clarification_handling.py -v`
Expected: FAIL (or PASS since this is just testing pydantic_ai types — either way, validate)

- [ ] **Step 3: Extend AgentRuntime to handle clarification DeferredToolRequests**

Edit `backend/src/aithru_agent/agent/runtime.py`:

Add a new field to `AgentRuntime`:

```python
@dataclass
class AgentRuntime:
    model: str | object = "test"
    instructions: str = "You are Aithru Agent. Help the user complete the task."
    model_factory: Callable[[str], str | object] = field(default_factory=lambda: _default_model_factory)
    model_profile_resolver: Callable[[str, str], AgentModelProfileEntry | None] | None = None
    profile_model_factory: Callable[[AgentModelProfileEntry], str | object] | None = None
    skill_registry: SkillRegistry | None = None
    _pending_approvals: dict[tuple[str, str], PendingApprovalState] = field(default_factory=dict)
    _pending_clarifications: dict[str, PendingApprovalState] = field(default_factory=dict)
```

Modify `_pause_for_deferred_approval` to handle clarification calls before the existing approval logic:

```python
async def _pause_for_deferred_approval(
    self,
    deps: PydanticAgentDeps,
    requests: DeferredToolRequests,
    message_history: list[Any],
) -> PendingApprovalState:
    # --- Handle clarification calls ---
    clarification_call = next(
        (c for c in requests.calls if c.tool_name == "ask_clarification"),
        None,
    )
    if clarification_call is not None:
        return await self._handle_clarification_request(
            deps, clarification_call, message_history
        )

    # --- Existing approval handling ---
    if not requests.approvals:
        raise AgentError("BAD_REQUEST", "Deferred tool calls without approval are not supported")
    # ... rest of existing code ...
```

Add `_handle_clarification_request` method:

```python
async def _handle_clarification_request(
    self,
    deps: PydanticAgentDeps,
    tool_call: ToolCallPart,
    message_history: list[Any],
) -> PendingApprovalState:
    """Handle an ask_clarification deferred tool call: write input.requested, pause as waiting_input."""
    args = tool_call.args_as_dict(raise_if_invalid=True)
    question = str(args.get("question", ""))
    clarification_type = str(args.get("clarification_type", "missing_info"))
    context_str = str(args.get("context", "")) if args.get("context") else None
    options = args.get("options")

    input_request_id = f"clarify_{deps.run.id}_{tool_call.tool_call_id}"
    await deps.event_writer.write(
        run_id=deps.run.id,
        thread_id=deps.run.thread_id,
        type="input.requested",
        source={"kind": "harness"},
        payload={
            "input_request_id": input_request_id,
            "tool_call_id": tool_call.tool_call_id,
            "prompt": question,
            "reason": context_str or "The agent needs more information to proceed.",
            "clarification_type": clarification_type,
            "options": options if isinstance(options, list) else None,
        },
    )

    message_history_json = ModelMessagesTypeAdapter.dump_json(message_history).decode("utf-8")
    pending_state = PendingApprovalState(
        approval_id=input_request_id,
        tool_call_id=tool_call.tool_call_id,
        message_history=message_history,
    )
    self._pending_clarifications[deps.run.id] = pending_state

    await deps.store.update_run(
        deps.run.id,
        status=AgentRunStatus.WAITING_INPUT,
    )
    await deps.event_writer.write(
        run_id=deps.run.id,
        thread_id=deps.run.thread_id,
        type="run.paused",
        source={"kind": "harness"},
        payload={
            "status": "waiting_input",
            "pause_reason": "clarification_requested",
            "input_request_id": input_request_id,
        },
    )
    return pending_state
```

Add `resume_clarification` method:

```python
async def resume_clarification(
    self,
    *,
    run_id: str,
    input_text: str,
    deps: PydanticAgentDeps,
) -> AgentRuntimeResult:
    """Resume a run after the user responded to a clarification request."""
    pending = self._pending_clarifications.pop(run_id, None)
    if pending is None:
        raise AgentError("RUN_NOT_RESUMABLE", f"No pending clarification for run {run_id}")

    agent = await self.build_agent(deps)
    content_parts: list[str] = []
    final_output: str | None = None
    message_id = "msg_1"

    from pydantic_ai.messages import ToolReturn

    deferred_tool_results = DeferredToolResults(
        calls={pending.tool_call_id: ToolReturn(input_text)}
    )

    async with agent.run_stream_events(
        message_history=pending.message_history,
        deferred_tool_results=deferred_tool_results,
        deps=deps,
    ) as stream:
        async for event in stream:
            if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                if event.delta.content_delta:
                    content_parts.append(event.delta.content_delta)
                    await deps.event_writer.write(
                        run_id=deps.run.id,
                        thread_id=deps.run.thread_id,
                        type="message.delta",
                        source={"kind": "model"},
                        payload={"message_id": message_id, "delta": event.delta.content_delta},
                    )
            elif isinstance(event, AgentRunResultEvent):
                await self._emit_usage_event(deps, event.result.usage)
                if isinstance(event.result.output, DeferredToolRequests):
                    pending = await self._pause_for_deferred_approval(
                        deps,
                        event.result.output,
                        event.result.all_messages(),
                    )
                    return AgentRuntimeResult(
                        content=_result_content(content_parts, final_output),
                        pending_approval=pending,
                    )
                if isinstance(event.result.output, str):
                    final_output = event.result.output

    return AgentRuntimeResult(
        content=_result_content(content_parts, final_output),
        pending_approval=None,
    )
```

Add import for `ToolCallPart` at the top of the file (add to existing pydantic_ai imports):

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter, PartDeltaEvent, TextPartDelta, ToolCallPart
```

- [ ] **Step 4: Run unit tests**

Run: `cd backend && uv run pytest tests/unit/agent/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/agent/runtime.py \
        backend/tests/unit/agent/test_clarification_handling.py
git commit -m "feat: handle ask_clarification deferred tool calls in agent runtime"
```

---

### Task 4: Worker runner — resume after clarification

**Files:**
- Modify: `backend/src/aithru_agent/worker/runner.py`

**Interfaces:**
- Consumes: `AgentRuntime.resume_clarification()`, `AgentStore`, `AgentEventWriter`
- Produces: extended `resume_after_input()` to detect and resume clarification runs

- [ ] **Step 1: Modify resume_after_input to handle clarification**

Edit `backend/src/aithru_agent/worker/runner.py`. In `resume_after_input`, after resuming the run status to `QUEUED`, check if this is a clarification resume:

```python
async def resume_after_input(self, run_id: str) -> AgentRun:
    run = await self._store.get_run(run_id)
    if run is None:
        raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
    if run.status != AgentRunStatus.WAITING_INPUT:
        raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for input: {run_id}")
    resumed = await self._store.update_run(run_id, status=AgentRunStatus.QUEUED)
    await self._event_writer.write(
        run_id=run_id,
        thread_id=run.thread_id,
        type="run.resumed",
        source={"kind": "harness"},
        payload={"status": "queued", "resume_reason": "input_received"},
    )
    return resumed
```

Actually, the worker's `execute_claimed_run` calls `_agent_runtime.run(run.goal, deps)`. For clarification resumes, we need to call `_agent_runtime.resume_clarification(...)` instead. We need to detect whether the run was paused for clarification vs. old-style input.

The cleanest approach: check if the agent runtime has a pending clarification for this run. Add helper method `has_pending_clarification(run_id)` to `AgentRuntime`:

```python
def has_pending_clarification(self, run_id: str) -> bool:
    return run_id in self._pending_clarifications
```

Then in `execute_claimed_run` in `worker/runner.py`, before the `_agent_runtime.run()` call (around line 237), add a check:

```python
deps = await self._build_deps(run, skill)
try:
    if self._agent_runtime.has_pending_clarification(run.id):
        result = await self._agent_runtime.resume_clarification(
            run_id=run.id,
            input_text=run.goal,  # The goal was set by the user's input
            deps=deps,
        )
    else:
        result = await self._agent_runtime.run(run.goal, deps)
    if result.pending_approval is not None:
        return await self._get_existing_run(run.id)
    return await self._complete_run(run, thread_id, "msg_1", [result.content], skill=skill)
```

Wait — the `run.goal` at resume time is the original goal from run creation, not the user's input. The user's input comes in through the `input.received` event. Let me check how the resume_after_input flow works with the original goal...

Looking at the code: when the user sends input via `POST /api/runs/{run_id}/input`, the API writes an `input.received` event, then calls `resume_waiting_input(run_id)`. The `resume_after_input` method just sets the run back to QUEUED. When `execute_claimed_run` runs, it calls `_agent_runtime.run(run.goal, deps)` — using the **original goal**, not the user's input.

This means the current input flow either:
1. Relies on the input being retrievable from the event store
2. Or the model just continues from where it left off

For clarification, we need the user's actual input text. We should read it from the most recent `input.received` event.

Let me modify the approach: in `worker/runner.py`, add a helper to read the latest user input from the event store:

```python
async def _latest_input_text(self, run_id: str) -> str | None:
    if self._event_store is None:
        return None
    events = await self._event_store.list_by_run(run_id)
    for event in reversed(events):
        if event.type == "input.received":
            payload = event.payload or {}
            value = payload.get("value") or payload.get("message") or payload.get("text", "")
            return str(value) if value else None
    return None
```

Then in `execute_claimed_run`:

```python
if self._agent_runtime.has_pending_clarification(run.id):
    input_text = await self._latest_input_text(run.id) or run.goal
    result = await self._agent_runtime.resume_clarification(
        run_id=run.id,
        input_text=input_text,
        deps=deps,
    )
```

OK, I'll put this into the plan properly.

- [ ] **Step 1: Add has_pending_clarification to AgentRuntime**

In `backend/src/aithru_agent/agent/runtime.py`, add:

```python
def has_pending_clarification(self, run_id: str) -> bool:
    return run_id in self._pending_clarifications
```

- [ ] **Step 2: Add _latest_input_text helper to AgentWorkerRunner**

In `backend/src/aithru_agent/worker/runner.py`, add method to `AgentWorkerRunner`:

```python
async def _latest_input_text(self, run_id: str) -> str | None:
    if self._event_store is None:
        return None
    events = await self._event_store.list_by_run(run_id)
    for event in reversed(events):
        if event.type == "input.received":
            payload = event.payload or {}
            value = payload.get("value") or payload.get("message") or payload.get("text", "")
            return str(value) if value else None
    return None
```

- [ ] **Step 3: Modify execute_claimed_run to detect clarification resume**

In `execute_claimed_run` (around line 237), change the `_agent_runtime.run()` call:

```python
deps = await self._build_deps(run, skill)
try:
    if self._agent_runtime.has_pending_clarification(run.id):
        input_text = await self._latest_input_text(run.id) or run.goal
        result = await self._agent_runtime.resume_clarification(
            run_id=run.id,
            input_text=input_text,
            deps=deps,
        )
    else:
        result = await self._agent_runtime.run(run.goal, deps)
    if result.pending_approval is not None:
        return await self._get_existing_run(run.id)
    return await self._complete_run(run, thread_id, "msg_1", [result.content], skill=skill)
```

Also handle `RunPausedForInput` in the exception handler — already handled in the existing code.

- [ ] **Step 4: Run backend tests**

Run: `cd backend && uv run pytest tests/ -v 2>&1 | tail -30`
Expected: all pass or existing failures unrelated to this change

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/agent/runtime.py \
        backend/src/aithru_agent/worker/runner.py
git commit -m "feat: resume agent after clarification input"
```

---

### Task 5: Simplify ClarificationPreflightProcessor

**Files:**
- Modify: `backend/src/aithru_agent/runtime/processors/clarification.py`
- Modify: `backend/src/aithru_agent/settings.py`

**Interfaces:**
- Consumes: `AgentRuntimeProcessorContext`
- Removes: `clarification_min_goal_words` setting, word-count guard
- Changed behavior: only pauses for truly empty goals (all whitespace/blank)

- [ ] **Step 1: Simplify ClarificationPreflightProcessor**

Edit `backend/src/aithru_agent/runtime/processors/clarification.py`:

```python
from __future__ import annotations

from aithru_agent.domain import AgentRunStatus

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class ClarificationPreflightProcessor(AgentRuntimeProcessor):
    """Guard against completely empty goals.
    
    Model-driven clarification is now handled by the ask_clarification tool.
    This processor only intercepts truly empty goals to avoid sending blank
    input to the model.
    """
    name: str = "clarification_preflight"

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()
        if not _is_empty(context.run.goal):
            return AgentRuntimeProcessorDecision()

        input_request_id = f"empty_goal_{context.run.id}"
        payload = {
            "input_request_id": input_request_id,
            "tool_call_id": input_request_id,
            "prompt": "What should the agent help you with?",
            "reason": "The run goal is empty.",
        }
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="input.requested",
            source={"kind": "harness"},
            payload=payload,
        )
        paused = await context.store.update_run(
            context.run.id,
            status=AgentRunStatus.WAITING_INPUT,
        )
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={"status": "waiting_input", **payload},
        )
        return AgentRuntimeProcessorDecision(paused_run=paused)


def _is_empty(value: str) -> bool:
    return not value or not value.strip()
```

- [ ] **Step 2: Remove clarification_min_goal_words from settings**

Edit `backend/src/aithru_agent/settings.py`:

Remove the `clarification_min_goal_words` field from `AgentProcessorSettings`:

```python
class AgentProcessorSettings(AithruBaseModel):
    clarification_enabled: bool = True
    title_generation_enabled: bool = True
    title_max_words: int = Field(default=6, ge=1, le=12)
    summarization_enabled: bool = True
    summarization_min_message_count: int = Field(default=6, ge=1, le=100)
    memory_extraction_enabled: bool = True
```

Remove the corresponding env var read in `from_env()` (line 343-346):

```python
# Remove these lines:
clarification_min_goal_words=_env_int(
    os.getenv("AITHRU_AGENT_PROCESSOR_CLARIFICATION_MIN_GOAL_WORDS"),
    default=4,
    name="AITHRU_AGENT_PROCESSOR_CLARIFICATION_MIN_GOAL_WORDS",
),
```

Update `_create_processor_runner` in `backend/src/aithru_agent/application/runtime.py` — remove the `min_goal_words` argument:

```python
if settings.processors.clarification_enabled:
    processors.append(ClarificationPreflightProcessor())
```

- [ ] **Step 3: Run tests**

Run: `cd backend && uv run pytest tests/ -v 2>&1 | tail -30`
Expected: tests pass. If any test references `clarification_min_goal_words`, update the test.

- [ ] **Step 4: Commit**

```bash
git add backend/src/aithru_agent/runtime/processors/clarification.py \
        backend/src/aithru_agent/settings.py \
        backend/src/aithru_agent/application/runtime.py
git commit -m "refactor: simplify ClarificationPreflightProcessor to empty-goal guard only"
```

---

### Task 6: Add system prompt guidance for ask_clarification

**Files:**
- Modify: `backend/src/aithru_agent/agent/instructions.py`

- [ ] **Step 1: Add clarification guidance to instruction builder**

In `backend/src/aithru_agent/agent/instructions.py`, in the `build()` method (around line 27-28), append the clarification guidance section after the base instructions:

```python
sections = [self._base]

# Add clarification guidance
sections.append(_CLARIFICATION_GUIDANCE)
```

Add at the bottom of the file:

```python
_CLARIFICATION_GUIDANCE = """## When to Ask for Clarification

You have access to the `ask_clarification` tool. Use it before taking tool actions when:
- The user's goal is too vague to proceed safely
- You need to choose between different approaches — provide `options` (2-5 choices)
- A requested action has important implications that need user confirmation

When providing options, keep them concise. When there are no clear discrete options, ask a focused open-ended question without providing options.

Do NOT use `ask_clarification` for:
- Simple informational questions you can answer directly
- Tasks where the goal is clear enough to start working
- Situations where you already have enough context from the workspace or memory"""
```

- [ ] **Step 2: Run tests**

Run: `cd backend && uv run pytest tests/ -v 2>&1 | tail -10`
Expected: tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/src/aithru_agent/agent/instructions.py
git commit -m "feat: add ask_clarification guidance to system prompt"
```

---

### Task 7: Frontend — expose clarification options in run activity

**Files:**
- Modify: `frontend/src/features/chat/useRunStream.ts`
- Modify: `frontend/src/features/chat/runActivity.ts`

**Interfaces:**
- Consumes: `input.requested` SSE event payload with optional `options` array
- Produces: `InlineRequest.options` field, `RunActivityItem` for clarification

- [ ] **Step 1: Add options to InlineRequest type**

In `frontend/src/features/chat/useRunStream.ts`, add `options` to `InlineRequest`:

```typescript
export interface InlineRequest {
  kind: "input" | "approval" | "external_approval" | "external_run";
  id: string;
  prompt?: string;
  approvalId?: string;
  toolName?: string;
  options?: string[];           // <-- add this
  runId?: string;
  sequence?: number;
  createdAt?: string;
}
```

- [ ] **Step 2: Extract options from input.requested event payload**

In the `case "input.requested":` handler (around line 473), add options extraction:

```typescript
case "input.request":
case "input.requested": {
  const requestId = (p.input_request_id as string) ?? (p.request_id as string) ?? event.id;
  const req: InlineRequest = {
    kind: "input",
    id: requestId,
    prompt: (p.prompt as string) ?? (p.message as string),
    options: Array.isArray(p.options) ? (p.options as string[]) : undefined,  // <-- add
    runId: event.run_id,
    sequence: sequenceOf(event),
    createdAt: event.timestamp,
  };
  return upsertInlineRequest(state, req, "waiting_input");
}
```

- [ ] **Step 3: Expose options in run activity**

In `frontend/src/features/chat/runActivity.ts`, update `RunActivityItem`:

```typescript
export interface RunActivityItem {
  id: string;
  title: string;
  detail?: string;
  status: RunActivityItemStatus;
  source: "todo" | "request" | "tool" | "run";
  options?: string[];            // <-- add
}
```

Update `requestToActivityItem`:

```typescript
function requestToActivityItem(request: InlineRequest): RunActivityItem {
  return {
    id: request.id,
    title: request.prompt || request.toolName || "Agent needs attention",
    detail: request.kind === "input" ? "Reply to continue this run." : "Review this action before the run continues.",
    status: "waiting",
    source: "request",
    options: request.options,    // <-- add
  };
}
```

- [ ] **Step 4: Build frontend to verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/chat/useRunStream.ts \
        frontend/src/features/chat/runActivity.ts
git commit -m "feat: expose clarification options in run activity stream"
```

---

### Task 8: Frontend — render clickable clarification options

**Files:**
- Modify: `frontend/src/features/inspection/tabs/ActivityTab.tsx`
- New: `frontend/src/features/chat/ClarificationOptions.tsx`

**Interfaces:**
- Consumes: `RunActivityItem.options` from run activity
- Produces: Clickable option buttons in the activity tab when clarification has options

- [ ] **Step 1: Create ClarificationOptions component**

```tsx
// frontend/src/features/chat/ClarificationOptions.tsx
import { Button } from "@/components/ui/button";

export function ClarificationOptions({
  options,
  onSelect,
}: {
  options: string[];
  onSelect: (option: string) => void;
}) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map((option, index) => (
        <Button
          key={index}
          variant="outline"
          size="sm"
          className="h-auto rounded-full px-3 py-1 text-xs"
          onClick={() => onSelect(option)}
        >
          {option}
        </Button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Wire into ActivityTab**

In `frontend/src/features/inspection/tabs/ActivityTab.tsx`, import and use `ClarificationOptions`. After the narrative section (around line 40, right after the nextAction block), add:

```tsx
import { ClarificationOptions } from "@/features/chat/ClarificationOptions";

// Inside the component, add a callback for option selection:
const handleOptionSelect = (option: string) => {
  // TODO in a follow-up: dispatch option text to chat composer
  console.log("Selected option:", option);
};

// After the nextAction block in the narrative section:
{activity.current?.options && activity.current.options.length > 0 && (
  <ClarificationOptions
    options={activity.current.options}
    onSelect={handleOptionSelect}
  />
)}
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/chat/ClarificationOptions.tsx \
        frontend/src/features/inspection/tabs/ActivityTab.tsx
git commit -m "feat: render clickable clarification options in activity tab"
```

---

### Task 9: Backend integration test — full clarification flow

**Files:**
- Create: `backend/tests/integration/test_clarification_flow.py`

- [ ] **Step 1: Write integration test**

```python
# backend/tests/integration/test_clarification_flow.py
import pytest
from aithru_agent.capabilities.local_tools.clarification import ClarificationLocalTool
from aithru_agent.capabilities.descriptors import AgentRunContext
from aithru_agent.domain import AgentToolCallRequest


@pytest.fixture
def tool() -> ClarificationLocalTool:
    return ClarificationLocalTool()


@pytest.fixture
def context() -> AgentRunContext:
    return AgentRunContext(
        run_id="run_clarify",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        thread_id="thread_clarify",
        scopes=["agent.input.write"],
    )


def test_clarification_descriptor_is_discoverable(tool: ClarificationLocalTool):
    """The tool descriptor should appear in capability router's tool list."""
    descriptors = tool.list_tools()
    names = [d.name for d in descriptors]
    assert "ask_clarification" in names


def test_clarification_with_options(tool: ClarificationLocalTool, context: AgentRunContext):
    result = tool.execute(
        AgentToolCallRequest(
            id="call_options",
            tool_name="ask_clarification",
            input={
                "question": "Which approach?",
                "clarification_type": "approach_choice",
                "options": ["Option 1", "Option 2", "Option 3"],
            },
            requested_by="model",
        ),
        context,
    )
    assert result.status == "completed"
    assert result.output["question"] == "Which approach?"
    assert result.output["clarification_type"] == "approach_choice"
    assert result.output["options"] == ["Option 1", "Option 2", "Option 3"]


def test_clarification_without_options(tool: ClarificationLocalTool, context: AgentRunContext):
    result = tool.execute(
        AgentToolCallRequest(
            id="call_no_options",
            tool_name="ask_clarification",
            input={
                "question": "What is the project name?",
                "clarification_type": "missing_info",
            },
            requested_by="model",
        ),
        context,
    )
    assert result.status == "completed"
    assert result.output["options"] is None


@pytest.mark.asyncio
async def test_clarification_denied_without_thread(tool: ClarificationLocalTool):
    ctx = AgentRunContext(
        run_id="run_no_thread",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        thread_id=None,
        scopes=["agent.input.write"],
    )
    result = tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="ask_clarification",
            input={"question": "Test?"},
            requested_by="model",
        ),
        ctx,
    )
    assert result.status == "denied"
```

- [ ] **Step 2: Run integration test**

Run: `cd backend && uv run pytest tests/integration/test_clarification_flow.py -v`
Expected: 5 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_clarification_flow.py
git commit -m "test: add integration tests for clarification flow"
```

---

### Task 10: Final verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && uv run pytest -v 2>&1 | tail -50`
Expected: all tests pass

- [ ] **Step 2: Run file report example**

Run: `cd backend && uv run python examples/file_report_agent.py`
Expected: runs to completion

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npx vite build`
Expected: build succeeds

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && node --test tests/`
Expected: all tests pass

- [ ] **Step 5: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: final verification — all tests pass, frontend builds"
```
