# Tool Result Recovery Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a controlled tool-result recovery loop so recoverable tool failures are returned to the model for corrected tool calls while policy, approval, audit, and trace boundaries remain enforced.

**Architecture:** Add typed recovery metadata to `AgentToolCallResult`, classify safe recoverable adapter failures at the tool boundary, and teach the Pydantic AI bridge to return compact recovery payloads only when descriptor policy and retry budget allow it. The worker remains responsible for terminal run failure and infrastructure retry; it does not become the model correction loop.

**Tech Stack:** Python 3, Pydantic models, Pydantic AI bridge, FastAPI backend domain contracts, in-memory and SQLite event stores, pytest.

## Global Constraints

- Models may propose tool calls. They must not execute real actions directly.
- All real actions must pass through the Aithru capability boundary.
- Tool calls must preserve policy, scope, approval, redaction, audit, and event ordering.
- Runtime todos and plans are harness state, not workflow definitions or recovery state machines.
- Worker-level retry must not be used to correct model tool arguments.
- Policy denials, approval requirements, and fatal harness errors remain non-recoverable unless an explicit controlled path says otherwise.
- Backend verification before completion: `cd backend && uv run pytest` and `cd backend && uv run python examples/file_report_agent.py`.

---

## File Structure

- `backend/src/aithru_agent/domain/tool.py`
  Owns stable tool domain models and enum values. Add `AgentToolFailureKind`, `AgentToolRecoveryAction`, `AgentToolRecovery`, and `AgentToolCallResult.recovery`.

- `backend/src/aithru_agent/domain/__init__.py`
  Re-exports new domain types.

- `backend/src/aithru_agent/capabilities/recovery.py`
  New helper module for adapters to construct recoverable and nonrecoverable tool results without duplicating enum strings.

- `backend/src/aithru_agent/agent/deps.py`
  Adds optional `event_store` so the bridge can compute durable recovery budgets from emitted events.

- `backend/src/aithru_agent/worker/runner.py`
  Injects the worker event store into `PydanticAgentDeps`.

- `backend/src/aithru_agent/agent/tools/recovery.py`
  New bridge-side helper module for model-visible payload shaping, attempt key generation, and event-based retry budget counting.

- `backend/src/aithru_agent/agent/tools/bridge.py`
  Uses generic recovery metadata when deciding whether failed/denied results return to the model or raise `TOOL_FAILED`.

- `backend/src/aithru_agent/capabilities/local_tools/workspace.py`
  Moves workspace path correction into the workspace adapter result, with typed recovery metadata and `failure_policy="return_recoverable"` on workspace descriptors that can safely return input-correction failures.

- `backend/tests/unit/domain/test_models.py`
  Covers enum serialization and backward-compatible `AgentToolCallResult`.

- `backend/tests/unit/capabilities/test_tool_recovery.py`
  New tests for adapter helper constructors.

- `backend/tests/unit/agent/test_tool_recovery.py`
  New tests for bridge-side recovery payload and attempt counting helpers.

- `backend/tests/integration/test_pydantic_tool_bridge.py`
  Covers bridge behavior for generic recoverable failures, descriptor policy, budget exhaustion, and workspace path recovery.

- `backend/tests/integration/test_pydantic_driver.py`
  Covers runtime-level model self-correction from a bad workspace path to a corrected workspace path.

---

### Task 1: Domain Recovery Contract

**Files:**
- Modify: `backend/src/aithru_agent/domain/tool.py`
- Modify: `backend/src/aithru_agent/domain/__init__.py`
- Modify: `backend/tests/unit/domain/test_models.py`

**Interfaces:**
- Produces: `AgentToolFailureKind`, `AgentToolRecoveryAction`, `AgentToolRecovery`
- Produces: `AgentToolCallResult.recovery: AgentToolRecovery | None = None`
- Consumed by: adapter helper constructors, bridge recovery handling, stream event payloads

- [ ] **Step 1: Write the failing domain model test**

Append this test to `backend/tests/unit/domain/test_models.py`:

```python
def test_tool_recovery_contract_serializes_stable_values() -> None:
    recovery = AgentToolRecovery(
        recoverable=True,
        kind=AgentToolFailureKind.INVALID_INPUT,
        action=AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT,
        message="Path is outside allowed workspace paths.",
        model_guidance="Retry with an absolute path under /artifacts.",
        suggested_input={"path": "/artifacts/index.html"},
        allowed_values={"allowed_paths": ["/artifacts"]},
        retry_after_ms=None,
        attempt_key="workspace_path_policy",
        max_attempts=2,
    )
    result = AgentToolCallResult(
        status="denied",
        error={"message": "Path is outside allowed workspace paths: index.html"},
        recovery=recovery,
        redaction="none",
    )

    dumped = result.model_dump(mode="json")

    assert dumped["recovery"] == {
        "recoverable": True,
        "kind": "invalid_input",
        "action": "retry_with_corrected_input",
        "message": "Path is outside allowed workspace paths.",
        "model_guidance": "Retry with an absolute path under /artifacts.",
        "suggested_input": {"path": "/artifacts/index.html"},
        "allowed_values": {"allowed_paths": ["/artifacts"]},
        "retry_after_ms": None,
        "attempt_key": "workspace_path_policy",
        "max_attempts": 2,
    }
    assert AgentToolFailureKind.POLICY_DENIED.value == "policy_denied"
    assert AgentToolRecoveryAction.FAIL_RUN.value == "fail_run"
```

Update the import block in the same file to include:

```python
from aithru_agent.domain import (
    AgentToolFailureKind,
    AgentToolRecovery,
    AgentToolRecoveryAction,
)
```

Merge those names into the existing domain import rather than adding a second duplicate import if the file already imports many domain symbols.

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_models.py::test_tool_recovery_contract_serializes_stable_values -q
```

Expected: FAIL with an import error or missing name for `AgentToolRecovery`.

- [ ] **Step 3: Add the domain types**

In `backend/src/aithru_agent/domain/tool.py`, add these classes after `AgentToolFailurePolicy`:

```python
class AgentToolFailureKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    TRANSIENT = "transient"
    EXECUTION_FAILED = "execution_failed"
    AMBIGUOUS_INPUT = "ambiguous_input"
    POLICY_DENIED = "policy_denied"
    APPROVAL_REQUIRED = "approval_required"
    FATAL_SYSTEM = "fatal_system"


class AgentToolRecoveryAction(StrEnum):
    RETURN_TO_MODEL = "return_to_model"
    RETRY_WITH_CORRECTED_INPUT = "retry_with_corrected_input"
    USE_ALTERNATIVE_TOOL = "use_alternative_tool"
    ASK_USER = "ask_user"
    WAIT_OR_DEGRADE = "wait_or_degrade"
    REQUIRE_APPROVAL = "require_approval"
    FAIL_RUN = "fail_run"


class AgentToolRecovery(AithruBaseModel):
    recoverable: bool
    kind: AgentToolFailureKind
    action: AgentToolRecoveryAction
    message: str
    model_guidance: str | None = None
    suggested_input: object | None = None
    allowed_values: dict[str, object] | None = None
    retry_after_ms: int | None = None
    attempt_key: str | None = None
    max_attempts: int = 2
```

Then update `AgentToolCallResult`:

```python
class AgentToolCallResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied", "waiting_approval", "running"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"]
    recovery: AgentToolRecovery | None = None
    external_run: AgentExternalRunRef | None = None
    approval_id: str | None = None
    authorization: AgentAuthorizationDecision | None = None
    audit: AgentCapabilityAuditEvent | None = None
```

- [ ] **Step 4: Export the domain types**

In `backend/src/aithru_agent/domain/__init__.py`, add the new imports inside the existing `.tool` import block:

```python
AgentToolFailureKind,
AgentToolRecovery,
AgentToolRecoveryAction,
```

Add the same three names to `__all__`:

```python
"AgentToolFailureKind",
"AgentToolRecovery",
"AgentToolRecoveryAction",
```

- [ ] **Step 5: Run the domain tests**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/aithru_agent/domain/tool.py backend/src/aithru_agent/domain/__init__.py backend/tests/unit/domain/test_models.py
git commit -m "feat: add tool recovery contract"
```

---

### Task 2: Adapter Recovery Constructors

**Files:**
- Create: `backend/src/aithru_agent/capabilities/recovery.py`
- Create: `backend/tests/unit/capabilities/test_tool_recovery.py`

**Interfaces:**
- Consumes: `AgentToolFailureKind`, `AgentToolRecovery`, `AgentToolRecoveryAction`, `AgentToolCallResult`
- Produces: `recoverable_tool_result(...) -> AgentToolCallResult`
- Produces: `nonrecoverable_tool_result(...) -> AgentToolCallResult`
- Consumed by: workspace and future sandbox/web/external adapters

- [ ] **Step 1: Write the failing constructor tests**

Create `backend/tests/unit/capabilities/test_tool_recovery.py`:

```python
from aithru_agent.capabilities.recovery import (
    nonrecoverable_tool_result,
    recoverable_tool_result,
)
from aithru_agent.domain import AgentToolFailureKind, AgentToolRecoveryAction


def test_recoverable_tool_result_builds_failed_result_with_recovery() -> None:
    result = recoverable_tool_result(
        status="denied",
        kind=AgentToolFailureKind.INVALID_INPUT,
        action=AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT,
        message="Path is outside allowed workspace paths.",
        model_guidance="Use an absolute workspace path under /artifacts.",
        suggested_input={"path": "/artifacts/index.html"},
        allowed_values={"allowed_paths": ["/artifacts"]},
        attempt_key="workspace_path_policy",
        max_attempts=2,
    )

    assert result.status == "denied"
    assert result.error == {"message": "Path is outside allowed workspace paths."}
    assert result.recovery is not None
    assert result.recovery.recoverable is True
    assert result.recovery.kind == AgentToolFailureKind.INVALID_INPUT
    assert result.recovery.action == AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT
    assert result.recovery.suggested_input == {"path": "/artifacts/index.html"}
    assert result.redaction == "none"


def test_nonrecoverable_tool_result_builds_policy_denied_result() -> None:
    result = nonrecoverable_tool_result(
        status="denied",
        kind=AgentToolFailureKind.POLICY_DENIED,
        message="Missing required scope: agent.workspace.write",
    )

    assert result.status == "denied"
    assert result.error == {"message": "Missing required scope: agent.workspace.write"}
    assert result.recovery is not None
    assert result.recovery.recoverable is False
    assert result.recovery.kind == AgentToolFailureKind.POLICY_DENIED
    assert result.recovery.action == AgentToolRecoveryAction.FAIL_RUN
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/capabilities/test_tool_recovery.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'aithru_agent.capabilities.recovery'`.

- [ ] **Step 3: Implement the constructor helpers**

Create `backend/src/aithru_agent/capabilities/recovery.py`:

```python
from typing import Literal

from aithru_agent.domain import (
    AgentToolCallResult,
    AgentToolFailureKind,
    AgentToolRecovery,
    AgentToolRecoveryAction,
)


ToolFailureStatus = Literal["failed", "denied"]


def recoverable_tool_result(
    *,
    status: ToolFailureStatus,
    kind: AgentToolFailureKind,
    action: AgentToolRecoveryAction,
    message: str,
    model_guidance: str | None = None,
    suggested_input: object | None = None,
    allowed_values: dict[str, object] | None = None,
    retry_after_ms: int | None = None,
    attempt_key: str | None = None,
    max_attempts: int = 2,
    error: dict | None = None,
    redaction: Literal["none", "partial", "full"] = "none",
) -> AgentToolCallResult:
    return AgentToolCallResult(
        status=status,
        error=error or {"message": message},
        recovery=AgentToolRecovery(
            recoverable=True,
            kind=kind,
            action=action,
            message=message,
            model_guidance=model_guidance,
            suggested_input=suggested_input,
            allowed_values=allowed_values,
            retry_after_ms=retry_after_ms,
            attempt_key=attempt_key,
            max_attempts=max_attempts,
        ),
        redaction=redaction,
    )


def nonrecoverable_tool_result(
    *,
    status: ToolFailureStatus,
    kind: AgentToolFailureKind,
    message: str,
    action: AgentToolRecoveryAction = AgentToolRecoveryAction.FAIL_RUN,
    error: dict | None = None,
    redaction: Literal["none", "partial", "full"] = "none",
) -> AgentToolCallResult:
    return AgentToolCallResult(
        status=status,
        error=error or {"message": message},
        recovery=AgentToolRecovery(
            recoverable=False,
            kind=kind,
            action=action,
            message=message,
        ),
        redaction=redaction,
    )
```

- [ ] **Step 4: Run the helper tests**

Run:

```bash
cd backend
uv run pytest tests/unit/capabilities/test_tool_recovery.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/src/aithru_agent/capabilities/recovery.py backend/tests/unit/capabilities/test_tool_recovery.py
git commit -m "feat: add tool recovery helpers"
```

---

### Task 3: Generic Bridge Recovery Return

**Files:**
- Create: `backend/src/aithru_agent/agent/tools/recovery.py`
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`
- Modify: `backend/tests/integration/test_pydantic_tool_bridge.py`

**Interfaces:**
- Consumes: `AgentToolCallResult.recovery`
- Produces: `model_visible_recovery_payload(tool_name: str, result: AgentToolCallResult) -> dict[str, object]`
- Produces: `recovery_event_payload(recovery: AgentToolRecovery) -> dict[str, object]`
- Produces bridge behavior: recoverable failed/denied tool results return to the model when descriptor `failure_policy == "return_recoverable"`

- [ ] **Step 1: Add a recoverable failing test adapter**

In `backend/tests/integration/test_pydantic_tool_bridge.py`, add these imports to the existing domain import block:

```python
AgentToolFailureKind,
AgentToolRecoveryAction,
```

Add this import:

```python
from aithru_agent.capabilities.recovery import recoverable_tool_result
```

Add this adapter near `FailingLocalTool`:

```python
class RecoverableLocalTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="local.recoverable",
                kind="local_tool",
                description="Fail with a recoverable invalid input result.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="safe",
                required_scopes=[],
                approval_policy="never",
                failure_policy="return_recoverable",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        return recoverable_tool_result(
            status="failed",
            kind=AgentToolFailureKind.INVALID_INPUT,
            action=AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT,
            message="local input was invalid",
            model_guidance="Retry with value set to corrected.",
            suggested_input={"value": "corrected"},
            allowed_values={"value": ["corrected"]},
            attempt_key="invalid_value",
        )
```

- [ ] **Step 2: Write the failing generic bridge test**

Append this test to `backend/tests/integration/test_pydantic_tool_bridge.py`:

```python
@pytest.mark.asyncio
async def test_pydantic_tool_bridge_returns_generic_recoverable_tool_result() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Use recoverable local tool",
        workspace_id=workspace.id,
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    bridge = PydanticAIToolBridge(
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            capability_router=AithruCapabilityRouter(
                adapters=[RecoverableLocalTool()],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    result = await bridge.call_tool(
        ToolContext("tc_recoverable"),
        tool_name="local.recoverable",
        tool_input={"value": "bad"},
    )
    events = await event_store.list_by_run(run.id)

    assert result == {
        "status": "failed",
        "recoverable": True,
        "tool_name": "local.recoverable",
        "failure_kind": "invalid_input",
        "message": "local input was invalid",
        "guidance": "Retry with value set to corrected.",
        "suggested_input": {"value": "corrected"},
        "allowed_values": {"value": ["corrected"]},
    }
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "tool.failed",
        "tool.recovery.offered",
    ]
    failed_event = next(event for event in events if event.type == "tool.failed")
    assert failed_event.payload["recovery"]["kind"] == "invalid_input"
    offered_event = next(event for event in events if event.type == "tool.recovery.offered")
    assert offered_event.payload["attempt_key"] == "local.recoverable:invalid_value"
    assert offered_event.payload["attempt"] == 1
```

- [ ] **Step 3: Run the test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_generic_recoverable_tool_result -q
```

Expected: FAIL because the bridge still raises or does not emit `tool.recovery.offered`.

- [ ] **Step 4: Add bridge recovery helper functions**

Create `backend/src/aithru_agent/agent/tools/recovery.py`:

```python
from typing import Any

from aithru_agent.domain import AgentToolCallResult, AgentToolRecovery
from aithru_agent.stream import AgentStreamEvent


def recovery_attempt_key(tool_name: str, recovery: AgentToolRecovery) -> str:
    suffix = recovery.attempt_key or recovery.kind.value
    return f"{tool_name}:{suffix}"


def recovery_event_payload(recovery: AgentToolRecovery) -> dict[str, object]:
    return recovery.model_dump(mode="json")


def model_visible_recovery_payload(
    *,
    tool_name: str,
    result: AgentToolCallResult,
) -> dict[str, object]:
    recovery = result.recovery
    if recovery is None:
        raise ValueError("recoverable payload requires result.recovery")
    payload: dict[str, object] = {
        "status": result.status,
        "recoverable": recovery.recoverable,
        "tool_name": tool_name,
        "failure_kind": recovery.kind.value,
        "message": recovery.message,
    }
    if recovery.model_guidance is not None:
        payload["guidance"] = recovery.model_guidance
    if recovery.suggested_input is not None:
        payload["suggested_input"] = recovery.suggested_input
    if recovery.allowed_values is not None:
        payload["allowed_values"] = recovery.allowed_values
    if recovery.retry_after_ms is not None:
        payload["retry_after_ms"] = recovery.retry_after_ms
    return payload


def recovery_attempt_from_events(
    *,
    events: list[AgentStreamEvent],
    attempt_key: str,
) -> int:
    prior = [
        event
        for event in events
        if event.type == "tool.recovery.offered"
        and isinstance(event.payload, dict)
        and event.payload.get("attempt_key") == attempt_key
    ]
    return len(prior) + 1


def recovery_attempt_payload(
    *,
    tool_name: str,
    recovery: AgentToolRecovery,
    attempt: int,
) -> dict[str, Any]:
    attempt_key = recovery_attempt_key(tool_name, recovery)
    return {
        "attempt_key": attempt_key,
        "attempt": attempt,
        "max_attempts": recovery.max_attempts,
        "failure_kind": recovery.kind.value,
        "action": recovery.action.value,
    }
```

- [ ] **Step 5: Use recovery metadata in bridge events and return path**

In `backend/src/aithru_agent/agent/tools/bridge.py`, add imports:

```python
from aithru_agent.agent.tools.recovery import (
    model_visible_recovery_payload,
    recovery_attempt_key,
    recovery_attempt_payload,
    recovery_event_payload,
)
```

Update `_emit_tool_result_event` payload to include recovery:

```python
        recovery = getattr(result, "recovery", None)
        payload = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "output": _event_output_for_tool(
                tool_name,
                getattr(result, "output", None),
            ),
            "error": getattr(result, "error", None),
            "external_run": result.external_run.model_dump(mode="json")
            if getattr(result, "external_run", None) is not None
            else None,
            **_governance_payload(
                getattr(result, "authorization", None),
                getattr(result, "audit", None),
            ),
        }
        if recovery is not None:
            payload["recovery"] = recovery_event_payload(recovery)
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.completed" if status in {"completed", "waiting_approval", "running"} else "tool.failed",
            source={"kind": "tool"},
            payload=payload,
        )
```

Add this private method to `PydanticAIToolBridge`:

```python
    async def _return_recoverable_tool_failure(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        result: object,
    ) -> dict[str, object] | None:
        recovery = getattr(result, "recovery", None)
        if recovery is None or not recovery.recoverable:
            return None
        attempt = 1
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.recovery.offered",
            source={"kind": "tool"},
            visibility="debug",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                **recovery_attempt_payload(
                    tool_name=tool_name,
                    recovery=recovery,
                    attempt=attempt,
                ),
            },
        )
        return model_visible_recovery_payload(tool_name=tool_name, result=result)
```

Then update the failed-result branch in `call_tool` before the existing web/workspace compatibility branches:

```python
        if result.status != "completed":
            if allow_recoverable_failure:
                recoverable_result = await self._return_recoverable_tool_failure(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    result=result,
                )
                if recoverable_result is not None:
                    return recoverable_result
            if is_run_context:
                recoverable_workspace_path_failure = _recoverable_workspace_path_failure(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    error=result.error,
                    allowed_paths=run_context.workspace_allowed_paths,
                )
                if recoverable_workspace_path_failure is not None:
                    return recoverable_workspace_path_failure
            if recoverable_failure is not None:
                return _recoverable_failure_payload(recoverable_failure)
            raise AgentError("TOOL_FAILED", _tool_result_error_message(result.error))
```

- [ ] **Step 6: Run the generic bridge test**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_generic_recoverable_tool_result -q
```

Expected: PASS.

- [ ] **Step 7: Run existing bridge recovery tests**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_still_raises_for_non_recoverable_tool_failures tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_uses_descriptor_failure_policy_for_recovery tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_recoverable_workspace_path_denial -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/src/aithru_agent/agent/tools/recovery.py backend/src/aithru_agent/agent/tools/bridge.py backend/tests/integration/test_pydantic_tool_bridge.py
git commit -m "feat: return generic recoverable tool failures"
```

---

### Task 4: Workspace Path Recovery At The Adapter Boundary

**Files:**
- Modify: `backend/src/aithru_agent/capabilities/local_tools/workspace.py`
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`
- Modify: `backend/tests/integration/test_pydantic_tool_bridge.py`

**Interfaces:**
- Consumes: `recoverable_tool_result(...)`
- Produces: workspace path denials with `AgentToolRecovery`
- Removes: bridge dependency on `_recoverable_workspace_path_failure`

- [ ] **Step 1: Update the workspace path test expectation first**

In `backend/tests/integration/test_pydantic_tool_bridge.py`, update `test_pydantic_tool_bridge_returns_recoverable_workspace_path_denial` expected result to:

```python
    assert result == {
        "status": "denied",
        "recoverable": True,
        "tool_name": "workspace.write_file",
        "failure_kind": "invalid_input",
        "message": "Path is outside allowed workspace paths.",
        "guidance": "Retry with an absolute workspace path under one of the allowed workspace paths.",
        "suggested_input": {"path": "/artifacts/cosmic-dreamscape.html"},
        "allowed_values": {"allowed_paths": ["/workspace", "/artifacts"]},
    }
    assert [event.type for event in events] == [
        "tool.proposed",
        "tool.started",
        "tool.failed",
        "tool.recovery.offered",
    ]
    failed_event = next(event for event in events if event.type == "tool.failed")
    assert failed_event.payload["recovery"]["attempt_key"] == "workspace_path_policy"
```

- [ ] **Step 2: Run the workspace test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_recoverable_workspace_path_denial -q
```

Expected: FAIL because the current bridge returns the old workspace-specific payload.

- [ ] **Step 3: Mark workspace descriptors recoverable where safe**

In `backend/src/aithru_agent/capabilities/local_tools/workspace.py`, add `failure_policy="return_recoverable"` to descriptors for:

```python
workspace.read_file
workspace.view_image
workspace.write_file
workspace.patch_file
workspace.delete_file
```

Do not add it to `workspace.list_files`, because it has no model-correctable path input.

- [ ] **Step 4: Add workspace recovery imports and helper**

In `backend/src/aithru_agent/capabilities/local_tools/workspace.py`, add imports:

```python
from aithru_agent.capabilities.recovery import recoverable_tool_result
from aithru_agent.domain import AgentToolFailureKind, AgentToolRecoveryAction
```

If those names are already imported through the existing `aithru_agent.domain` block, merge them into that block instead of creating duplicate domain imports.

Add this helper near `_deny_if_path_outside_policy`:

```python
def _suggest_workspace_path(path: object, allowed_paths: list[str] | None) -> str | None:
    if not allowed_paths or not isinstance(path, str) or not path.strip():
        return None
    filename = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not filename or filename in {".", ".."}:
        return None
    preferred_root = (
        "/artifacts"
        if "/artifacts" in {_normalize_for_policy(allowed_path) for allowed_path in allowed_paths}
        else allowed_paths[0]
    )
    return f"{preferred_root.rstrip('/')}/{filename}"
```

Update `_deny_if_path_outside_policy`:

```python
def _deny_if_path_outside_policy(path: object, context: AgentRunContext) -> AgentToolCallResult | None:
    if _path_allowed(str(path), context.workspace_allowed_paths):
        return None
    suggested_path = _suggest_workspace_path(path, context.workspace_allowed_paths)
    suggested_input = {"path": suggested_path} if suggested_path is not None else None
    return recoverable_tool_result(
        status="denied",
        kind=AgentToolFailureKind.INVALID_INPUT,
        action=AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT,
        message="Path is outside allowed workspace paths.",
        model_guidance="Retry with an absolute workspace path under one of the allowed workspace paths.",
        suggested_input=suggested_input,
        allowed_values={"allowed_paths": context.workspace_allowed_paths or []},
        attempt_key="workspace_path_policy",
        error={"message": f"Path is outside allowed workspace paths: {path}"},
    )
```

- [ ] **Step 5: Remove the bridge workspace special case**

In `backend/src/aithru_agent/agent/tools/bridge.py`, remove this branch from the failed-result handling:

```python
            if is_run_context:
                recoverable_workspace_path_failure = _recoverable_workspace_path_failure(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    error=result.error,
                    allowed_paths=run_context.workspace_allowed_paths,
                )
                if recoverable_workspace_path_failure is not None:
                    return recoverable_workspace_path_failure
```

Remove these functions from the bottom of the file:

```python
def _recoverable_workspace_path_failure(...)
def _suggest_workspace_path(...)
```

- [ ] **Step 6: Run workspace and bridge tests**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_recoverable_workspace_path_denial tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_generic_recoverable_tool_result -q
```

Expected: PASS.

- [ ] **Step 7: Run workspace policy tests**

Run:

```bash
cd backend
uv run pytest tests/integration/test_workspace_policy.py -q
```

Expected: PASS. If any assertion expects no recovery metadata, update it to assert the original `error.message` remains unchanged and `recovery.kind == "invalid_input"`.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/src/aithru_agent/capabilities/local_tools/workspace.py backend/src/aithru_agent/agent/tools/bridge.py backend/tests/integration/test_pydantic_tool_bridge.py backend/tests/integration/test_workspace_policy.py
git commit -m "feat: classify workspace path recovery"
```

---

### Task 5: Recovery Budget From Events

**Files:**
- Modify: `backend/src/aithru_agent/agent/deps.py`
- Modify: `backend/src/aithru_agent/worker/runner.py`
- Modify: `backend/src/aithru_agent/agent/tools/recovery.py`
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`
- Create: `backend/tests/unit/agent/test_tool_recovery.py`
- Modify: `backend/tests/integration/test_pydantic_tool_bridge.py`

**Interfaces:**
- Produces: `PydanticAgentDeps.event_store: AgentEventStore | None`
- Produces: bridge budget behavior using prior `tool.recovery.offered` events
- Produces: `tool.recovery.exhausted` event before `TOOL_FAILED`

- [ ] **Step 1: Write unit tests for event-based attempt counting**

Create `backend/tests/unit/agent/test_tool_recovery.py`:

```python
from aithru_agent.agent.tools.recovery import recovery_attempt_from_events
from aithru_agent.stream import AgentStreamEvent


def _event(sequence: int, attempt_key: str) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp="2026-06-29T00:00:00Z",
        type="tool.recovery.offered",
        source={"kind": "tool"},
        payload={"attempt_key": attempt_key},
    )


def test_recovery_attempt_from_events_counts_matching_attempt_key() -> None:
    events = [
        _event(1, "workspace.write_file:workspace_path_policy"),
        _event(2, "local.recoverable:invalid_value"),
    ]

    assert recovery_attempt_from_events(
        events=events,
        attempt_key="workspace.write_file:workspace_path_policy",
    ) == 2
```

- [ ] **Step 2: Run the unit test**

Run:

```bash
cd backend
uv run pytest tests/unit/agent/test_tool_recovery.py -q
```

Expected: PASS.

- [ ] **Step 3: Inject event store into Pydantic deps**

In `backend/src/aithru_agent/agent/deps.py`, import `AgentEventStore`:

```python
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
```

Update the dataclass:

```python
    event_store: AgentEventStore | None = None
```

Place it after `event_writer` so callers see writer and store together:

```python
    event_writer: AgentEventWriter
    event_store: AgentEventStore | None = None
    capability_router: AithruCapabilityRouter
```

Because it has a default value, existing tests that construct `PydanticAgentDeps` without `event_store` keep working.

- [ ] **Step 4: Pass event store from worker**

In `backend/src/aithru_agent/worker/runner.py`, update `_build_deps`:

```python
        return PydanticAgentDeps(
            run=run,
            run_context=self._context_builder.build(run, run.scopes, skill),
            event_writer=self._event_writer,
            event_store=self._event_store,
            capability_router=self._capability_router,
            store=self._store,
            skill=skill,
            context_packet=context_packet,
            visible_skill_packages=visible_packages_by_key,
            explicit_skill_key=skill.key if skill is not None else None,
        )
```

- [ ] **Step 5: Add a bridge budget exhaustion test**

Append to `backend/tests/integration/test_pydantic_tool_bridge.py`:

```python
@pytest.mark.asyncio
async def test_pydantic_tool_bridge_exhausts_recoverable_tool_budget() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Use recoverable local tool too many times",
        workspace_id=workspace.id,
    )
    context = AgentRunContext(
        run_id=run.id,
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    bridge = PydanticAIToolBridge(
        deps=PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=writer,
            event_store=event_store,
            capability_router=AithruCapabilityRouter(
                adapters=[RecoverableLocalTool()],
                policy=ToolPolicy(require_approval_for_risk=[]),
            ),
            store=store,
        ),
    )

    first = await bridge.call_tool(
        ToolContext("tc_recoverable_1"),
        tool_name="local.recoverable",
        tool_input={"value": "bad"},
    )
    second = await bridge.call_tool(
        ToolContext("tc_recoverable_2"),
        tool_name="local.recoverable",
        tool_input={"value": "still_bad"},
    )
    with pytest.raises(AgentError) as exc_info:
        await bridge.call_tool(
            ToolContext("tc_recoverable_3"),
            tool_name="local.recoverable",
            tool_input={"value": "still_bad_again"},
        )
    events = await event_store.list_by_run(run.id)

    assert first["recoverable"] is True
    assert second["recoverable"] is True
    assert exc_info.value.code == "TOOL_FAILED"
    assert [event.type for event in events].count("tool.recovery.offered") == 2
    assert [event.type for event in events].count("tool.recovery.exhausted") == 1
    exhausted = next(event for event in events if event.type == "tool.recovery.exhausted")
    assert exhausted.payload["attempt"] == 3
    assert exhausted.payload["max_attempts"] == 2
```

- [ ] **Step 6: Run the exhaustion test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_exhausts_recoverable_tool_budget -q
```

Expected: FAIL because bridge currently always offers recoverable payloads.

- [ ] **Step 7: Implement budget handling in bridge**

Update `_return_recoverable_tool_failure` in `backend/src/aithru_agent/agent/tools/bridge.py`:

```python
    async def _return_recoverable_tool_failure(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        result: object,
    ) -> dict[str, object] | None:
        recovery = getattr(result, "recovery", None)
        if recovery is None or not recovery.recoverable:
            return None
        attempt_key = recovery_attempt_key(tool_name, recovery)
        prior_events = (
            await self._deps.event_store.list_by_run(self._run.id)
            if self._deps.event_store is not None
            else []
        )
        attempt = recovery_attempt_from_events(events=prior_events, attempt_key=attempt_key)
        attempt_payload = recovery_attempt_payload(
            tool_name=tool_name,
            recovery=recovery,
            attempt=attempt,
        )
        if attempt > recovery.max_attempts:
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.recovery.exhausted",
                source={"kind": "tool"},
                visibility="debug",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "error": getattr(result, "error", None),
                    **attempt_payload,
                },
            )
            return None
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.recovery.offered",
            source={"kind": "tool"},
            visibility="debug",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                **attempt_payload,
            },
        )
        return model_visible_recovery_payload(tool_name=tool_name, result=result)
```

Add `recovery_attempt_from_events` to the imports from `aithru_agent.agent.tools.recovery`.

- [ ] **Step 8: Run budget tests**

Run:

```bash
cd backend
uv run pytest tests/unit/agent/test_tool_recovery.py tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_exhausts_recoverable_tool_budget -q
```

Expected: PASS.

- [ ] **Step 9: Run bridge test group**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

Run:

```bash
git add backend/src/aithru_agent/agent/deps.py backend/src/aithru_agent/worker/runner.py backend/src/aithru_agent/agent/tools/recovery.py backend/src/aithru_agent/agent/tools/bridge.py backend/tests/unit/agent/test_tool_recovery.py backend/tests/integration/test_pydantic_tool_bridge.py
git commit -m "feat: enforce tool recovery budget"
```

---

### Task 6: Runtime Self-Correction Integration

**Files:**
- Modify: `backend/tests/integration/test_pydantic_driver.py`
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`

**Interfaces:**
- Consumes: generic recovery return payload
- Produces: integration coverage that a bad workspace path can be corrected within the same run

- [ ] **Step 1: Add a deterministic recovery runtime test**

Append this test helper and test to `backend/tests/integration/test_pydantic_driver.py`. This test intentionally uses a runtime test double instead of `TestModel`, because Pydantic AI's `TestModel` generates schema-based inputs and does not model "read tool result, then choose corrected input."

```python
class WorkspacePathCorrectionRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        bridge = PydanticAIToolBridge(deps=deps)
        first = await bridge.call_tool(
            ToolContext("tc_bad_path"),
            tool_name="workspace.write_file",
            tool_input={"path": "index.html", "content": "<html>bad</html>"},
        )
        assert isinstance(first, dict)
        assert first["recoverable"] is True
        suggested_input = first["suggested_input"]
        assert isinstance(suggested_input, dict)
        corrected_path = suggested_input["path"]
        await bridge.call_tool(
            ToolContext("tc_corrected_path"),
            tool_name="workspace.write_file",
            tool_input={"path": corrected_path, "content": "<html>ok</html>"},
        )
        return AgentRuntimeResult(content=f"wrote {corrected_path}")


@pytest.mark.asyncio
async def test_runtime_can_continue_after_recoverable_workspace_path_failure() -> None:
    runtime = _runtime(
        agent_runtime=WorkspacePathCorrectionRuntime(),
        policy=ToolPolicy(require_approval_for_risk=[]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write a small html artifact.",
        scopes=["agent.workspace.write"],
        workspace_allowed_paths=["/artifacts"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    written = await runtime.store.read_workspace_file(run.workspace_id, "/artifacts/index.html")

    assert run.status == AgentRunStatus.COMPLETED
    assert written.content == "<html>ok</html>"
    assert [event.type for event in events].count("tool.failed") == 1
    assert [event.type for event in events].count("tool.recovery.offered") == 1
    assert [event.type for event in events].count("tool.completed") == 1
    assert "run.failed" not in [event.type for event in events]
```

If `ToolContext` is not available in this file, add the same helper class used in `test_pydantic_tool_bridge.py`:

```python
class ToolContext:
    def __init__(self, tool_call_id: str, *, approved: bool = False) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = approved
```

Ensure imports include:

```python
from aithru_agent.agent import AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
```

- [ ] **Step 2: Run the integration test**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_driver.py::test_runtime_can_continue_after_recoverable_workspace_path_failure -q
```

Expected: PASS after Tasks 1-5 are complete.

- [ ] **Step 3: Add a model-visible payload redaction assertion**

In `test_pydantic_tool_bridge_returns_generic_recoverable_tool_result`, add:

```python
    assert "audit" not in result
    assert "authorization" not in result
    assert "authorization_decision" not in result
```

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_pydantic_tool_bridge_returns_generic_recoverable_tool_result -q
```

Expected: PASS.

- [ ] **Step 4: Run targeted runtime and bridge suites**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_driver.py tests/integration/test_pydantic_tool_bridge.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/tests/integration/test_pydantic_driver.py backend/tests/integration/test_pydantic_tool_bridge.py
git commit -m "test: cover tool recovery continuation"
```

---

### Task 7: Full Verification And Documentation Check

**Files:**
- Modify only if verification exposes stale docs or failing assertions:
  - `docs/05-capability-router.md`
  - `docs/00-agent-harness-design.md`
  - `docs/superpowers/specs/2026-06-29-tool-result-recovery-loop-design.md`

**Interfaces:**
- Consumes: all previous tasks
- Produces: verified backend and example run

- [ ] **Step 1: Run the full backend test suite**

Run:

```bash
cd backend
uv run pytest
```

Expected: PASS.

- [ ] **Step 2: Run the file report example**

Run:

```bash
cd backend
uv run python examples/file_report_agent.py
```

Expected: exits with code 0 and prints/completes the example report flow without `run.failed`.

- [ ] **Step 3: Check for stale bridge special cases**

Run:

```bash
rg -n "_recoverable_workspace_path_failure|_suggest_workspace_path|ResearchRecoverableToolFailure" backend/src/aithru_agent/agent/tools/bridge.py
```

Expected: no matches for `_recoverable_workspace_path_failure` or `_suggest_workspace_path`. `ResearchRecoverableToolFailure` may still remain during the web migration compatibility phase if Task 3 kept web behavior unchanged.

- [ ] **Step 4: Check diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` has no output. `git status --short` shows only intentional files if any verification cleanup remains.

- [ ] **Step 5: Commit verification cleanup if needed**

If Step 1 or Step 2 required documentation or assertion cleanup, commit it:

```bash
git add docs/05-capability-router.md docs/00-agent-harness-design.md docs/superpowers/specs/2026-06-29-tool-result-recovery-loop-design.md backend/tests
git commit -m "docs: align tool recovery implementation notes"
```

If there was no cleanup, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Typed recovery contract: Task 1.
- Adapter-side classification helpers: Task 2.
- Generic bridge return path: Task 3.
- Workspace path recovery moved out of bridge special case: Task 4.
- Retry budget and recovery events: Task 5.
- Runtime continuation after recoverable workspace failure: Task 6.
- Full backend verification: Task 7.

Placeholder scan:

- The plan contains no placeholder steps or open-ended error-handling instructions.

Type consistency:

- Domain types are named `AgentToolFailureKind`, `AgentToolRecoveryAction`, and `AgentToolRecovery` in every task.
- Bridge helper names are consistently `model_visible_recovery_payload`, `recovery_attempt_key`, `recovery_attempt_from_events`, `recovery_attempt_payload`, and `recovery_event_payload`.
- Adapter helper names are consistently `recoverable_tool_result` and `nonrecoverable_tool_result`.
