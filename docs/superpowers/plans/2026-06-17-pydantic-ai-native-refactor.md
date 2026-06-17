# Pydantic AI Native Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely remove the generic AgentHarnessDriver abstraction, make Pydantic AI the only native runtime foundation, implement progressive skills, and clean up the architecture.

**Architecture:** Move from generic multi-driver adapter design to Pydantic AI-first architecture. Restructure `harness/drivers/pydantic_ai/` to `agent/` as the native runtime foundation. Keep Aithru domain contracts, capability router, and stream events unchanged. Use Pydantic AI `TestModel` only when tests or local development explicitly request `model="test"`; never silently use a fake model for an unconfigured production runtime.

**Tech Stack:** Python 3.14+, Pydantic AI, FastAPI, pytest

---

## File Structure Changes

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/src/aithru_agent/agent/__init__.py` | Agent runtime exports |
| Create | `backend/src/aithru_agent/agent/deps.py` | Explicit PydanticAgentDeps model |
| Create | `backend/src/aithru_agent/agent/runtime.py` | Native Pydantic AI agent runtime |
| Create | `backend/src/aithru_agent/agent/exceptions.py` | Native runtime exceptions |
| Create | `backend/src/aithru_agent/agent/instructions.py` | Instruction assembly builder |
| Create | `backend/src/aithru_agent/agent/tools/__init__.py` | Tools exports |
| Create | `backend/src/aithru_agent/agent/tools/bridge.py` | Pydantic AI tool bridge |
| Create | `backend/src/aithru_agent/agent/tools/descriptors.py` | Tool descriptor conversion |
| Create | `backend/src/aithru_agent/agent/skills/__init__.py` | Skills exports |
| Create | `backend/src/aithru_agent/agent/skills/parser.py` | SKILL.md parser |
| Create | `backend/src/aithru_agent/agent/skills/registry.py` | Skill registry |
| Create | `backend/src/aithru_agent/agent/skills/activation.py` | Skill activation logic |
| Delete | `backend/src/aithru_agent/harness/engine.py` | Remove generic driver protocol |
| Delete | `backend/src/aithru_agent/harness/drivers/pydantic_ai/` | Remove old adapter |
| Delete | `backend/src/aithru_agent/harness/drivers/scripted/` | Remove scripted production driver after tests migrate |
| Create | `backend/tests/utils/test_model.py` | Deterministic Pydantic AI `TestModel` helpers |
| Update | `backend/src/aithru_agent/harness/__init__.py` | Clean up exports |
| Update | `backend/src/aithru_agent/settings.py` | Change default driver to pydantic_ai |
| Update | `backend/src/aithru_agent/application/runtime.py` | Use native agent runtime, keep backward compatible alias |
| Update | `backend/src/aithru_agent/worker/runner.py` | Remove generic driver adapter logic |
| Update | All test files | Update imports and use Pydantic TestModel for deterministic testing |

---

## Critical Bug Fixes (Previously Identified)

1. **Async list_tools bug**: `_build_tools` must await `capability_router.list_tools()` - fixed by moving tool building to async context inside run()
2. **Approval resume bug**: Use `approval.tool_call_id` instead of empty string when restoring persisted approval
3. **HarnessRunPaused import bug**: Native runtime uses its own `RunPausedForApproval` exception, no import from deleted harness.engine
4. **Backward compatibility**: Keep `create_agent_runtime` as alias for API/CLI; tests explicitly pass `model="test"` or inject a native `AgentRuntime`
5. **Missing files**: instructions.py and tools/descriptors.py are both in plan now; event mapping stays inside native runtime for this slice
6. **No fake production default**: `_create_agent_runtime()` must raise a clear configuration error when no model is configured; only `model="test"` creates `TestModel`
7. **Deferred approval state**: approval-required tools must use Pydantic AI deferred approvals so runtime can persist message history before pausing

---

## Tasks

### Task 1: Change Default Driver to Pydantic AI

**Files:**
- Modify: `backend/src/aithru_agent/settings.py:10-38`
- Test: `backend/tests/unit/test_settings.py`

- [ ] **Step 1: Write failing tests for pydantic_ai default and legacy driver rejection**

```python
import pytest


def test_default_driver_is_pydantic_ai():
    from aithru_agent.settings import AgentSettings

    settings = AgentSettings()
    assert settings.driver == "pydantic_ai"


def test_scripted_driver_env_is_rejected(monkeypatch):
    from aithru_agent.settings import AgentSettings

    monkeypatch.setenv("AITHRU_AGENT_DRIVER", "scripted")

    with pytest.raises(ValueError, match="scripted driver has been removed"):
        AgentSettings.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_settings.py -v`
Expected: FAIL because default is still `scripted` and `AITHRU_AGENT_DRIVER=scripted` is accepted

- [ ] **Step 3: Update driver handling in settings.py**

Change line 12 from:
```python
driver: AgentDriverKind = "scripted"
```
to:
```python
driver: AgentDriverKind = "pydantic_ai"
```

Update `from_env()` validation:

```python
        driver = os.getenv("AITHRU_AGENT_DRIVER", cls.driver)
        if driver == "scripted":
            raise ValueError("The scripted driver has been removed; use AITHRU_AGENT_MODEL=test for deterministic tests")
        if driver != "pydantic_ai":
            raise ValueError(f"Unsupported AITHRU_AGENT_DRIVER: {driver}")
```

Keep the `driver` field only as a temporary compatibility field for configs that already set `pydantic_ai`. Do not use it to select runtime implementations.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/test_settings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/settings.py backend/tests/unit/test_settings.py
git commit -m "refactor: change default driver to pydantic_ai"
```

---

### Task 2: Create Agent Foundation - Deps and Exceptions

**Files:**
- Create: `backend/src/aithru_agent/agent/__init__.py`
- Create: `backend/src/aithru_agent/agent/deps.py`
- Create: `backend/src/aithru_agent/agent/exceptions.py`

- [ ] **Step 1: Create agent/exceptions.py**

```python
"""Native agent runtime exceptions."""

from aithru_agent.domain.errors import AgentError


class RunPausedForApproval(AgentError):
    """Raised when run is paused waiting for tool approval."""
    
    def __init__(self, run_id: str, approval_id: str, tool_call_id: str) -> None:
        super().__init__(
            "RUN_PAUSED_FOR_APPROVAL",
            f"Run {run_id} paused for approval {approval_id} on tool {tool_call_id}",
        )
        self.run_id = run_id
        self.approval_id = approval_id
        self.tool_call_id = tool_call_id
```

- [ ] **Step 2: Create agent/deps.py**

```python
from dataclasses import dataclass
from typing import Any

from aithru_agent.capabilities import AithruCapabilityRouter, AgentRunContext
from aithru_agent.domain import AgentRun, AgentSkill
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.stream import AgentEventWriter


@dataclass(frozen=True)
class PydanticAgentDeps:
    """Explicit dependency container for Pydantic AI agent.
    
    Replaces RunContext[None] + closure pattern with typed dependencies.
    """
    run: AgentRun
    run_context: AgentRunContext
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    store: AgentStore
    skill: AgentSkill | None = None
```

- [ ] **Step 3: Create agent/__init__.py with exports**

```python
"""Pydantic AI-native Agent runtime for Aithru."""

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.exceptions import RunPausedForApproval

__all__ = [
    "PydanticAgentDeps",
    "RunPausedForApproval",
]
```

- [ ] **Step 4: Verify imports work**

Run: `cd backend && uv run python -c "from aithru_agent.agent import PydanticAgentDeps, RunPausedForApproval; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/agent/__init__.py
git add backend/src/aithru_agent/agent/deps.py
git add backend/src/aithru_agent/agent/exceptions.py
git commit -m "feat: add agent foundation - deps and exceptions"
```

---

### Task 3: Create Instruction Builder

**Files:**
- Create: `backend/src/aithru_agent/agent/instructions.py`

- [ ] **Step 1: Create instructions.py**

```python
"""System prompt assembly for Pydantic AI agent."""

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentMemoryEntry, AgentMessage, AgentWorkspaceFile


MAX_WORKSPACE_FILES_IN_PROMPT = 50
MAX_THREAD_MESSAGES_IN_PROMPT = 20
MAX_THREAD_MESSAGE_CHARS = 1_000


class InstructionBuilder:
    """Builds system prompt from run config, skill, and context."""
    
    def __init__(self, base_instructions: str) -> None:
        self._base = base_instructions
    
    async def build(self, deps: PydanticAgentDeps) -> str:
        """Build full system prompt from store-backed run context.
        
        Do not read thread/workspace prompt data from AgentRunContext; that
        object is intentionally only the capability policy context.
        """
        sections = [self._base]
        
        # Run-specific instructions
        if deps.run.harness_options and deps.run.harness_options.instructions:
            sections.append(f"Run instructions:\n{deps.run.harness_options.instructions}")
        
        # Skill instructions
        if deps.skill:
            sections.append(f"Skill instructions:\n{deps.skill.instructions}")
        
        # Thread context
        thread_messages = await self._thread_messages_for_run(deps)
        if thread_messages:
            lines = [
                f"- {msg.role}: {_truncate_message(msg.content)}"
                for msg in thread_messages
            ]
            sections.append("Recent messages:\n" + "\n".join(lines))
        
        # Workspace context
        workspace_files = await self._workspace_files_for_run(deps)
        if workspace_files:
            lines = [
                f"- {file.path} ({file.media_type or 'unknown'}, {file.size} bytes)"
                for file in workspace_files
            ]
            sections.append("Workspace files:\n" + "\n".join(lines))
        
        # Memory context
        memory_entries = await self._memory_entries_for_run(deps)
        if memory_entries:
            lines = [
                f"- {entry.scope}:{entry.key} = {entry.value}"
                for entry in memory_entries
            ]
            sections.append("Memory:\n" + "\n".join(lines))
        
        return "\n\n".join(sections)

    async def _thread_messages_for_run(self, deps: PydanticAgentDeps) -> list[AgentMessage]:
        if not deps.run.thread_id:
            return []
        messages = await deps.store.list_messages(deps.run.thread_id)
        return messages[-MAX_THREAD_MESSAGES_IN_PROMPT:]

    async def _workspace_files_for_run(self, deps: PydanticAgentDeps) -> list[AgentWorkspaceFile]:
        if deps.skill and deps.skill.workspace_policy and not deps.skill.workspace_policy.read:
            return []
        files = await deps.store.list_workspace_files(deps.run.workspace_id)
        if deps.skill and deps.skill.workspace_policy and deps.skill.workspace_policy.allowed_paths:
            allowed_paths = deps.skill.workspace_policy.allowed_paths
            files = [
                file
                for file in files
                if any(file.path == allowed or file.path.startswith(allowed.rstrip("/") + "/") for allowed in allowed_paths)
            ]
        return files[:MAX_WORKSPACE_FILES_IN_PROMPT]

    async def _memory_entries_for_run(self, deps: PydanticAgentDeps) -> list[AgentMemoryEntry]:
        skill = deps.skill
        if not skill or not skill.memory_policy or not skill.memory_policy.read:
            return []
        entries: list[AgentMemoryEntry] = []
        seen: set[str] = set()
        for scope in skill.memory_policy.scopes or ["user", "thread", "workspace", "organization", "skill"]:
            scope_id = _memory_scope_id(scope, deps)
            scoped_entries = await deps.store.list_memory_entries(
                org_id=deps.run.org_id,
                scope=scope,
                scope_id=scope_id,
            )
            for entry in scoped_entries:
                if entry.id in seen:
                    continue
                seen.add(entry.id)
                entries.append(entry)
        return entries


def _truncate_message(content: str) -> str:
    if len(content) <= MAX_THREAD_MESSAGE_CHARS:
        return content
    return content[:MAX_THREAD_MESSAGE_CHARS] + "..."


def _memory_scope_id(scope: str, deps: PydanticAgentDeps) -> str | None:
    match scope:
        case "thread":
            return deps.run.thread_id or deps.run.id
        case "workspace":
            return deps.run.workspace_id
        case "user":
            return deps.run.actor_user_id
        case "organization":
            return deps.run.org_id
        case "skill":
            return deps.run.skill_id
        case _:
            return None
```

- [ ] **Step 2: Update agent/__init__.py export**

```python
from aithru_agent.agent.instructions import InstructionBuilder

__all__ = [
    "PydanticAgentDeps",
    "RunPausedForApproval",
    "InstructionBuilder",
]
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/aithru_agent/agent/instructions.py
git add backend/src/aithru_agent/agent/__init__.py
git commit -m "feat: add instruction builder"
```

---

### Task 4: Create Tool Descriptor Conversion

**Files:**
- Create: `backend/src/aithru_agent/agent/tools/descriptors.py`
- Create: `backend/src/aithru_agent/agent/tools/__init__.py`

- [ ] **Step 1: Create tools/descriptors.py**

```python
"""Convert Aithru tool descriptors to Pydantic AI tools."""

from typing import Any, Callable

from pydantic_ai import RunContext, Tool

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentToolDescriptor


def build_pydantic_tools(
    tool_specs: list[tuple[AgentToolDescriptor, bool]],
    tool_callback: Callable,
) -> list[Tool]:
    """Convert Aithru tool descriptors to Pydantic AI Tool objects.
    
    Args:
        tool_specs: `(descriptor, requires_approval)` values assembled from capability router
        tool_callback: Async function(ctx, tool_name, **kwargs) -> result
        
    Returns:
        List of Pydantic AI Tool objects
    """
    tools: list[Tool] = []
    
    for descriptor, requires_approval in tool_specs:
        async def tool_wrapper(
            ctx: RunContext[PydanticAgentDeps],
            _descriptor=descriptor,
            _callback=tool_callback,
            **tool_input: Any,
        ) -> object:
            return await _callback(
                ctx,
                tool_name=_descriptor.name,
                tool_input=tool_input,
            )
        
        tool = Tool.from_schema(
            tool_wrapper,
            takes_ctx=True,
            name=descriptor.name,
            description=descriptor.description,
            json_schema=descriptor.input_schema,
        )
        # Approval-required tools must be deferred by Pydantic AI so runtime can
        # persist message history before pausing. The tool bridge still executes
        # the concrete action through the capability router after approval.
        tool.requires_approval = requires_approval
        tools.append(tool)
    
    return tools
```

- [ ] **Step 2: Create tools/__init__.py**

```python
"""Tool bridge and descriptor conversion for Pydantic AI agent."""

from aithru_agent.agent.tools.descriptors import build_pydantic_tools

__all__ = [
    "build_pydantic_tools",
]
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/aithru_agent/agent/tools/__init__.py
git add backend/src/aithru_agent/agent/tools/descriptors.py
git commit -m "feat: add tool descriptor conversion"
```

---

### Task 5: Create Pydantic AI Tool Bridge (Native Version)

**Files:**
- Create: `backend/src/aithru_agent/agent/tools/bridge.py`
- Update: `backend/src/aithru_agent/agent/tools/__init__.py`

- [ ] **Step 1: Create tools/bridge.py - NO HarnessRunPaused import**

```python
from typing import Any

from pydantic_ai import RunContext

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentToolCallRequest
from aithru_agent.domain.errors import AgentError


class PydanticAIToolBridge:
    """Bridges Aithru capability router to Pydantic AI tool interface.
    
    Converts Pydantic AI tool calls -> AgentToolCallRequest -> Capability Router
    Handles approval flow, events, and error handling.
    """

    def __init__(
        self,
        *,
        deps: PydanticAgentDeps,
    ) -> None:
        self._deps = deps
        self._run = deps.run
        self._run_context = deps.run_context
        self._event_writer = deps.event_writer
        self._capability_router = deps.capability_router

    async def call_tool(
        self,
        ctx: RunContext[PydanticAgentDeps],
        *,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> object:
        """Call a tool via Aithru capability router.
        
        Args:
            ctx: Pydantic AI RunContext containing PydanticAgentDeps
            tool_name: Name of the tool to call
            tool_input: Tool input parameters
            
        Returns:
            Tool result from capability router
        """
        tool_call_id = ctx.tool_call_id or f"pydantic:{tool_name}:{ctx.run_step}"
        already_approved = bool(getattr(ctx, "tool_call_approved", False))
        
        request = AgentToolCallRequest(
            id=tool_call_id,
            tool_name=tool_name,
            input=tool_input,
            requested_by="model",
            already_approved=already_approved,
        )
        
        if not already_approved:
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.proposed",
                source={"kind": "tool"},
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "input": tool_input},
            )
        
        prepared = await self._capability_router.prepare_tool_call(request, self._run_context)
        
        if prepared.status == "denied":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "reason": prepared.reason},
            )
            return {"status": "denied", "reason": prepared.reason}
        
        if prepared.status == "waiting_approval":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.failed",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "status": "failed",
                    "error": {
                        "message": "Tool required approval but was not deferred by Pydantic AI",
                    },
                },
            )
            raise AgentError(
                "TOOL_APPROVAL_NOT_DEFERRED",
                "Tool required approval but was not deferred by Pydantic AI; check tool.requires_approval setup",
            )

        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
        )
        result = await self._capability_router.execute_tool_call(request, self._run_context)
        await self._emit_domain_event(tool_call_id, tool_name, result.output)
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.completed" if result.status == "completed" else "tool.failed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": result.status,
                "output": result.output,
                "error": result.error,
            },
        )
        if result.status != "completed":
            raise AgentError("TOOL_FAILED", _tool_result_error_message(result.error))
        return result.output

    async def _emit_domain_event(self, tool_call_id: str, tool_name: str, output: object) -> None:
        if not isinstance(output, dict):
            return
        if tool_name == "workspace.read_file":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="workspace.file.read",
                source={"kind": "workspace"},
                payload={"tool_call_id": tool_call_id, **output},
            )
        elif tool_name == "workspace.write_file":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="workspace.file.created",
                source={"kind": "workspace"},
                payload={"tool_call_id": tool_call_id, **output},
            )
        elif tool_name == "todo.create":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="todo.created",
                source={"kind": "harness"},
                payload=output,
            )
        elif tool_name == "todo.update":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="todo.updated",
                source={"kind": "harness"},
                payload=output,
            )
        elif tool_name == "artifact.create":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="artifact.created",
                source={"kind": "artifact"},
                payload=output,
            )
        elif tool_name == "artifact.finalize":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="artifact.finalized",
                source={"kind": "artifact"},
                payload=output,
            )
        elif tool_name == "memory.search":
            entries = output.get("entries") if isinstance(output.get("entries"), list) else []
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="memory.read",
                source={"kind": "memory"},
                payload={"operation": "read", "count": len(entries)},
            )
        elif tool_name == "memory.remember":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="memory.written",
                source={"kind": "memory"},
                payload={
                    "operation": "write",
                    "memory_id": output.get("id"),
                    "memory_scope": output.get("scope"),
                    "key": output.get("key"),
                },
            )


def _tool_result_error_message(error: dict | None) -> str:
    if not error:
        return "Tool failed"
    message = error.get("message")
    return str(message) if message else "Tool failed"
```

- [ ] **Step 2: Update tools/__init__.py export**

```python
"""Tool bridge and descriptor conversion for Pydantic AI agent."""

from aithru_agent.agent.tools.bridge import PydanticAIToolBridge
from aithru_agent.agent.tools.descriptors import build_pydantic_tools

__all__ = [
    "PydanticAIToolBridge",
    "build_pydantic_tools",
]
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/aithru_agent/agent/tools/bridge.py
git add backend/src/aithru_agent/agent/tools/__init__.py
git commit -m "feat: add native pydantic tool bridge"
```

---

### Task 6: Create Native Pydantic AI Agent Runtime (Core - Bug Fixed)

**Files:**
- Create: `backend/src/aithru_agent/agent/runtime.py`
- Update: `backend/src/aithru_agent/agent/__init__.py`

- [ ] **Step 1: Write failing test for agent runtime**

```python
# Add to new file: backend/tests/unit/agent/test_runtime.py
import pytest
from pydantic_ai import Agent


def test_agent_runtime_can_create_agent():
    """AgentRuntime should create a valid Pydantic AI Agent."""
    from aithru_agent.agent.runtime import AgentRuntime
    
    runtime = AgentRuntime(
        model="test",
        instructions="You are a test agent",
    )
    assert runtime is not None
    assert runtime.instructions == "You are a test agent"
```

- [ ] **Step 2: Create runtime.py - FIXED async list_tools bug**

```python
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import ModelMessagesTypeAdapter, PartDeltaEvent, TextPartDelta
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.exceptions import RunPausedForApproval
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.agent.tools.bridge import PydanticAIToolBridge
from aithru_agent.agent.tools.descriptors import build_pydantic_tools
from aithru_agent.domain import AgentMemoryEntry, AgentMessage, AgentRun, AgentSkill, AgentWorkspaceFile
from aithru_agent.domain.errors import AgentError


PYDANTIC_APPROVAL_METADATA_HISTORY = "pydantic_message_history"


@dataclass
class PendingApprovalState:
    approval_id: str
    tool_call_id: str
    message_history: list[Any]


@dataclass
class AgentRunResult:
    content: str
    pending_approval: PendingApprovalState | None = None


@dataclass
class AgentRuntime:
    """Pydantic AI-native agent runtime for Aithru.
    
    This replaces the generic AgentHarnessDriver adapter with direct
    Pydantic AI integration while preserving Aithru's capability boundary,
    event system, and domain contracts.
    """
    model: str | object = "test"
    instructions: str = "You are Aithru Agent. Help the user complete the task."
    model_factory: Callable[[str], str | object] = field(default_factory=lambda: lambda m: m)
    _pending_approvals: dict[tuple[str, str], PendingApprovalState] = field(default_factory=dict)

    async def build_agent(
        self,
        deps: PydanticAgentDeps,
    ) -> Agent[PydanticAgentDeps, str | DeferredToolRequests]:
        """Build a Pydantic AI agent configured for this run.
        
        ASYNC because list_tools() is async on the capability router.
        """
        # FIX: list_tools is async, must await it
        descriptors = await deps.capability_router.list_tools(deps.run_context)
        tool_specs = [
            (
                descriptor,
                await deps.capability_router.requires_approval_for_tool(
                    descriptor.name,
                    deps.run_context,
                ),
            )
            for descriptor in descriptors
        ]
        bridge = PydanticAIToolBridge(deps=deps)
        tools = build_pydantic_tools(tool_specs, bridge.call_tool)
        
        instruction_builder = InstructionBuilder(self.instructions)
        system_prompt = await instruction_builder.build(deps)
        
        return Agent[PydanticAgentDeps, str | DeferredToolRequests](
            self._model_for_run(deps.run),
            instructions=system_prompt,
            output_type=str | DeferredToolRequests,
            tools=tools,
        )

    async def run(
        self,
        goal: str,
        deps: PydanticAgentDeps,
    ) -> AgentRunResult:
        """Run agent with the given goal and dependencies.
        
        Args:
            goal: User's goal/prompt
            deps: Run dependencies
            
        Returns:
            Run result with optional pending approval state
        """
        # FIX: build_agent is now async due to list_tools
        agent = await self.build_agent(deps)
        content_parts: list[str] = []
        
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": "msg_1", "role": "assistant"},
        )
        
        async with agent.run_stream_events(goal, deps=deps) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        content_parts.append(event.delta.content_delta)
                        await deps.event_writer.write(
                            run_id=deps.run.id,
                            thread_id=deps.run.thread_id,
                            type="message.delta",
                            source={"kind": "model"},
                            payload={"message_id": "msg_1", "delta": event.delta.content_delta},
                        )
                elif isinstance(event, AgentRunResultEvent):
                    await self._emit_usage_event(deps, event.result.usage)
                    if isinstance(event.result.output, DeferredToolRequests):
                        pending = await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        return AgentRunResult(
                            content="".join(content_parts),
                            pending_approval=pending,
                        )
        
        return AgentRunResult(
            content="".join(content_parts),
            pending_approval=None,
        )

    async def resume_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        approved: bool,
        deps: PydanticAgentDeps,
        persisted_message_history: str | None = None,
        persisted_tool_call_id: str | None = None,
    ) -> AgentRunResult:
        """Resume a run after approval decision.
        
        FIXED: Uses persisted_tool_call_id from approval, not empty string.
        
        Args:
            run_id: Run ID
            approval_id: Approval ID
            approved: True if approved, False if rejected
            deps: Run dependencies
            persisted_message_history: JSON-encoded message history from store
            persisted_tool_call_id: Tool call ID from approval (CRITICAL FIX)
            
        Returns:
            Run result
        """
        pending = self._pending_approvals.pop((run_id, approval_id), None)
        
        if pending is None and persisted_message_history:
            # FIX: Use persisted_tool_call_id from approval, NOT empty string
            pending = PendingApprovalState(
                approval_id=approval_id,
                tool_call_id=persisted_tool_call_id or approval_id,  # Fallback but prefer persisted
                message_history=ModelMessagesTypeAdapter.validate_json(persisted_message_history),
            )
        
        if pending is None:
            raise AgentError("RUN_NOT_RESUMABLE", f"No pending approval for run {run_id}")
        
        # build_agent is async
        agent = await self.build_agent(deps)
        content_parts: list[str] = []
        
        # FIX: Correctly map approval to tool call using pending.tool_call_id
        deferred_tool_results = DeferredToolResults(approvals={pending.tool_call_id: approved})
        
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
                            payload={"message_id": "msg_1", "delta": event.delta.content_delta},
                        )
                elif isinstance(event, AgentRunResultEvent):
                    await self._emit_usage_event(deps, event.result.usage)
                    if isinstance(event.result.output, DeferredToolRequests):
                        new_pending = await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        return AgentRunResult(
                            content="".join(content_parts),
                            pending_approval=new_pending,
                        )
        
        return AgentRunResult(
            content="".join(content_parts),
            pending_approval=None,
        )

    def _model_for_run(self, run: AgentRun | None) -> object:
        if run and run.harness_options and run.harness_options.model:
            return self.model_factory(run.harness_options.model)
        return self.model

    async def _pause_for_deferred_approval(
        self,
        deps: PydanticAgentDeps,
        requests: DeferredToolRequests,
        message_history: list[Any],
    ) -> PendingApprovalState:
        """Handle deferred tool approval request."""
        if not requests.approvals:
            raise AgentError("BAD_REQUEST", "Deferred tool calls without approval")
        
        tool_call = requests.approvals[0]
        tool_input = tool_call.args_as_dict(raise_if_invalid=True)
        
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="tool.proposed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
                "input": tool_input,
            },
        )
        
        approval = await deps.store.create_approval(
            run_id=deps.run.id,
            tool_call_id=tool_call.tool_call_id,
            tool_name=tool_call.tool_name,
            tool_input=tool_input,
            metadata={
                "driver": "pydantic_ai_native",
                PYDANTIC_APPROVAL_METADATA_HISTORY: ModelMessagesTypeAdapter.dump_json(
                    message_history
                ).decode("utf-8"),
            },
        )
        
        pending_state = PendingApprovalState(
            approval_id=approval.id,
            tool_call_id=tool_call.tool_call_id,
            message_history=message_history,
        )
        self._pending_approvals[(deps.run.id, approval.id)] = pending_state
        
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="approval.requested",
            source={"kind": "approval"},
            payload={
                "approval_id": approval.id,
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
                "status": "pending",
            },
        )
        
        from aithru_agent.domain import AgentRunStatus
        await deps.store.update_run(
            deps.run.id,
            status=AgentRunStatus.WAITING_APPROVAL,
            current_approval_id=approval.id,
        )
        
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_approval",
                "approval_id": approval.id,
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
            },
        )
        
        return pending_state

    async def _emit_usage_event(self, deps: PydanticAgentDeps, usage: object) -> None:
        """Emit model usage event."""
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="model.usage",
            source={"kind": "model"},
            visibility="debug",
            payload={"usage_type": str(type(usage).__name__)},
        )
```

- [ ] **Step 3: Update agent/__init__.py exports**

```python
"""Pydantic AI-native Agent runtime for Aithru."""

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.exceptions import RunPausedForApproval
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.agent.runtime import AgentRuntime, AgentRunResult, PendingApprovalState

__all__ = [
    "PydanticAgentDeps",
    "RunPausedForApproval",
    "InstructionBuilder",
    "AgentRuntime",
    "AgentRunResult",
    "PendingApprovalState",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/agent/test_runtime.py::test_agent_runtime_can_create_agent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/agent/runtime.py
git add backend/src/aithru_agent/agent/__init__.py
git add backend/tests/unit/agent/test_runtime.py
git commit -m "feat: add native Pydantic AI AgentRuntime - async bugs fixed"
```

---

### Task 7: Update Worker Runner to Use Native Agent Runtime

**Files:**
- Modify: `backend/src/aithru_agent/worker/runner.py`

- [ ] **Step 1: Update imports - NO import from harness.engine**

```python
from dataclasses import dataclass

from aithru_agent.agent import AgentRuntime, PydanticAgentDeps, RunPausedForApproval
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter
from aithru_agent.domain import (
    AgentApprovalDecision,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunResult,
    AgentRunSource,
    AgentRunStatus,
    AgentSkill,
    AgentSubagentRunStatus,
    AgentToolCallRequest,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import ContextBuilder
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter
```

- [ ] **Step 2: Update AgentWorkerRunner class**

```python
@dataclass
class PendingToolApproval:
    """Legacy pending approval - used only for non-native test paths."""
    run: AgentRun
    context: AgentRunContext
    request: AgentToolCallRequest
    tool_input: dict
    message_id: str
    final_content: list[str]
    approval_id: str


class AgentWorkerRunner:
    def __init__(
        self,
        *,
        store: AgentStore,
        event_writer: AgentEventWriter,
        capability_router: AithruCapabilityRouter,
        agent_runtime: AgentRuntime | None = None,
        skill_resolver: AgentSkillResolver | None = None,
    ) -> None:
        self._store = store
        self._event_writer = event_writer
        self._capability_router = capability_router
        self._agent_runtime = agent_runtime or AgentRuntime()
        self._skill_resolver = skill_resolver or EmptySkillResolver()
        self._context_builder = ContextBuilder()
        self._tool_counter = 0
        self._pending_worker_approvals: dict[str, PendingToolApproval] = {}  # Legacy tests only

    async def start_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        goal: str,
        scopes: list[str],
        harness_options: AgentRunHarnessOptions | None = None,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        run = await self.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            goal=goal,
            scopes=scopes,
            harness_options=harness_options,
            thread_id=thread_id,
            skill_id=skill_id,
        )
        return await self.execute_run(run.id)

    async def create_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        goal: str,
        scopes: list[str],
        harness_options: AgentRunHarnessOptions | None = None,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        if thread_id:
            thread = await self._store.get_thread(thread_id)
            if thread is None or thread.org_id != org_id or thread.owner_user_id != actor_user_id:
                raise AgentError("NOT_FOUND", f"Thread not found: {thread_id}")
        self._resolve_run_skill(org_id=org_id, skill_id=skill_id)
        workspace = await self._store.create_workspace(org_id=org_id, thread_id=thread_id)
        run = await self._store.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            source="api",
            goal=goal,
            workspace_id=workspace.id,
            scopes=scopes,
            harness_options=harness_options,
            thread_id=thread_id,
            skill_id=skill_id,
        )

        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.created",
            source={"kind": "harness"},
            payload={"status": "queued", "workspace_id": workspace.id},
        )
        return run

    async def execute_run(self, run_id: str) -> AgentRun:
        claimed = await self._store.claim_run(run_id)
        if claimed is None:
            existing = await self._store.get_run(run_id)
            if existing is None:
                raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
            raise AgentError("BAD_REQUEST", f"Run is not queued: {run_id}")
        return await self.execute_claimed_run(claimed.id)

    async def execute_claimed_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.RUNNING:
            raise AgentError("BAD_REQUEST", f"Run is not claimed: {run_id}")

        thread_id = run.thread_id
        try:
            skill = self._resolve_run_skill(org_id=run.org_id, skill_id=run.skill_id)
        except AgentError as exc:
            return await self._fail_run(run, thread_id, exc)

        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.started",
            source={"kind": "harness"},
            payload={"status": "running"},
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.started",
            source={"kind": "model"},
            payload={},
        )

        context = self._context_builder.build(run, run.scopes, skill)
        deps = PydanticAgentDeps(
            run=run,
            run_context=context,
            event_writer=self._event_writer,
            capability_router=self._capability_router,
            store=self._store,
            skill=skill,
        )

        try:
            result = await self._agent_runtime.run(run.goal, deps)
            # Run completed successfully
            return await self._complete_run(run, thread_id, "msg_1", [result.content])
        except RunPausedForApproval:
            # Native pause - run state already updated by tool bridge
            paused_run = await self._store.get_run(run.id)
            if paused_run is None:
                raise AgentError("NOT_FOUND", f"Run not found: {run.id}")
            return paused_run
        except AgentError as exc:
            if exc.code == "RUN_PAUSED_FOR_APPROVAL":
                paused_run = await self._store.get_run(run.id)
                if paused_run is None:
                    raise AgentError("NOT_FOUND", f"Run not found: {run.id}")
                return paused_run
            return await self._fail_run(run, thread_id, exc)
        except Exception as exc:
            return await self._fail_run(run, thread_id, exc)

    def _resolve_run_skill(
        self,
        *,
        org_id: str,
        skill_id: str | None,
    ) -> AgentSkill | None:
        if skill_id is None:
            return None
        skill = self._skill_resolver.resolve(skill_id)
        if skill is None or skill.org_id != org_id:
            raise AgentError("SKILL_NOT_FOUND", f"Skill not found: {skill_id}")
        return skill

    async def find_next_queued_run(self) -> AgentRun | None:
        for run in await self._store.list_runs():
            if run.status == AgentRunStatus.QUEUED:
                return run
        return None

    async def claim_run(self, run_id: str) -> AgentRun | None:
        return await self._store.claim_run(run_id)

    async def claim_next_queued_run(self) -> AgentRun | None:
        return await self._store.claim_next_queued_run()

    async def resume_run(
        self,
        run_id: str,
        *,
        approval_id: str,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentRun:
        """Resume run with approval decision.
        
        Uses persisted approval.tool_call_id for correct resume.
        """
        # Look up run and approval
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        
        if run.status != AgentRunStatus.WAITING_APPROVAL:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for approval: {run_id}")
        
        approval = await self._store.get_approval(approval_id)
        if approval is None or approval.run_id != run_id:
            raise AgentError("RUN_NOT_RESUMABLE", f"Approval not found: {approval_id}")
        
        # Resolve approval
        resolved = await self._store.resolve_approval(
            approval_id,
            decision=decision,
            comment=comment,
        )
        
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="approval.resolved",
            source={"kind": "approval"},
            payload={
                "approval_id": approval_id,
                "tool_call_id": approval.tool_call_id,
                "tool_name": approval.tool_name,
                "decision": _approval_decision_value(resolved.decision or decision),
                "comment": comment,
            },
        )
        
        # Check if rejected
        if str(decision) == AgentApprovalDecision.REJECTED.value:
            failed = await self._store.update_run(
                run_id,
                status=AgentRunStatus.FAILED,
                current_approval_id=None,
                error={"message": "Approval rejected"},
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": approval.tool_call_id,
                    "tool_name": approval.tool_name,
                    "reason": comment,
                },
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="run.failed",
                source={"kind": "harness"},
                payload={"status": "failed", "error": {"message": "Approval rejected"}},
            )
            return failed
        
        # Approved - resume run
        try:
            skill = self._resolve_run_skill(org_id=run.org_id, skill_id=run.skill_id)
        except AgentError as exc:
            return await self._fail_run(run, run.thread_id, exc)
        
        resumed = await self._store.update_run(run_id, status=AgentRunStatus.RUNNING, current_approval_id=None)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={"status": "running"},
        )
        
        context = self._context_builder.build(resumed, resumed.scopes, skill)
        deps = PydanticAgentDeps(
            run=resumed,
            run_context=context,
            event_writer=self._event_writer,
            capability_router=self._capability_router,
            store=self._store,
            skill=skill,
        )
        
        # Extract persisted message history from approval metadata
        persisted_history = None
        if approval.metadata and "pydantic_message_history" in approval.metadata:
            persisted_history = approval.metadata["pydantic_message_history"]
        elif approval.metadata and "message_history_json" in approval.metadata:
            # Legacy format compatibility
            persisted_history = approval.metadata["message_history_json"]
        
        try:
            result = await self._agent_runtime.resume_approval(
                run_id=run_id,
                approval_id=approval_id,
                approved=True,
                deps=deps,
                persisted_message_history=persisted_history,
                persisted_tool_call_id=approval.tool_call_id,  # FIX: Pass actual tool_call_id
            )
            return await self._complete_run(resumed, run.thread_id, "msg_1", [result.content])
        except RunPausedForApproval:
            # Paused again for another approval
            paused_run = await self._store.get_run(run_id)
            if paused_run is None:
                raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
            return paused_run
        except AgentError as exc:
            if exc.code == "RUN_PAUSED_FOR_APPROVAL":
                paused_run = await self._store.get_run(run_id)
                if paused_run is None:
                    raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
                return paused_run
            return await self._fail_run(resumed, run.thread_id, exc)
        except Exception as exc:
            return await self._fail_run(resumed, run.thread_id, exc)

    async def _complete_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        message_id: str,
        final_content: list[str],
    ) -> AgentRun:
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.completed",
            source={"kind": "model"},
            payload={},
        )
        content = "".join(final_content)
        persisted_message_id = None
        if thread_id and content:
            message = await self._store.append_message(
                thread_id=thread_id,
                role="assistant",
                content=content,
                run_id=run.id,
            )
            persisted_message_id = message.id
        message_payload = {"message_id": message_id, "content": content}
        if persisted_message_id:
            message_payload["thread_message_id"] = persisted_message_id
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="message.completed",
            source={"kind": "harness"},
            payload=message_payload,
        )
        artifacts = await self._store.list_artifacts(run_id=run.id)
        result = AgentRunResult(
            content=content or None,
            artifact_ids=[artifact.id for artifact in artifacts],
            message_id=message_id,
            thread_message_id=persisted_message_id,
        )
        run = await self._store.update_run(
            run.id,
            status=AgentRunStatus.COMPLETED,
            completed_at=_event_completed_at_marker(),
            result=result,
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.completed",
            source={"kind": "harness"},
            payload={"status": "completed", "result": result.model_dump(mode="json")},
        )
        await self._emit_parent_subagent_completed(run, content)
        return run

    async def _fail_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        error: Exception,
    ) -> AgentRun:
        error_payload = _error_payload(error)
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.failed",
            source={"kind": "model"},
            payload={"error": error_payload},
        )
        failed = await self._store.update_run(
            run.id,
            status=AgentRunStatus.FAILED,
            completed_at=_event_completed_at_marker(),
            current_approval_id=None,
            error=error_payload,
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.failed",
            source={"kind": "harness"},
            payload={"status": "failed", "error": error_payload},
        )
        await self._emit_parent_subagent_failed(failed, error_payload)
        return failed

    async def _emit_parent_subagent_completed(self, run: AgentRun, result: str) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        for subagent_run in subagent_runs:
            completed = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.COMPLETED,
                result=result,
                completed_at=_event_completed_at_marker(),
            )
            parent = await self._store.get_run(completed.parent_run_id)
            await self._event_writer.write(
                run_id=completed.parent_run_id,
                thread_id=parent.thread_id if parent else None,
                type="subagent.completed",
                source={"kind": "subagent", "id": completed.id, "name": completed.name},
                payload={
                    "subagent_run_id": completed.id,
                    "child_run_id": completed.child_run_id,
                    "name": completed.name,
                    "task": completed.task,
                    "spec_key": completed.spec_key,
                    "status": completed.status.value,
                    "result": result,
                },
            )

    async def _emit_parent_subagent_failed(self, run: AgentRun, error: dict[str, str]) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        for subagent_run in subagent_runs:
            failed = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.FAILED,
                error=error,
                completed_at=_event_completed_at_marker(),
            )
            parent = await self._store.get_run(failed.parent_run_id)
            await self._event_writer.write(
                run_id=failed.parent_run_id,
                thread_id=parent.thread_id if parent else None,
                type="subagent.failed",
                source={"kind": "subagent", "id": failed.id, "name": failed.name},
                payload={
                    "subagent_run_id": failed.id,
                    "child_run_id": failed.child_run_id,
                    "name": failed.name,
                    "task": failed.task,
                    "spec_key": failed.spec_key,
                    "status": failed.status.value,
                    "error": error,
                },
            )

    async def cancel_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if not run:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status in _TERMINAL_RUN_STATUSES:
            raise AgentError("BAD_REQUEST", f"Run is already terminal: {run.status.value}")
        cancelled = await self._store.update_run(
            run_id,
            status=AgentRunStatus.CANCELLED,
            completed_at=_event_completed_at_marker(),
            current_approval_id=None,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.cancelled",
            source={"kind": "harness"},
            payload={"status": "cancelled"},
        )
        await self._emit_parent_subagent_cancelled(cancelled)
        return cancelled

    async def _emit_parent_subagent_cancelled(self, run: AgentRun) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        for subagent_run in subagent_runs:
            cancelled = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.CANCELLED,
                error={"message": "Subagent child run cancelled"},
                completed_at=_event_completed_at_marker(),
            )
            parent = await self._store.get_run(cancelled.parent_run_id)
            await self._event_writer.write(
                run_id=cancelled.parent_run_id,
                thread_id=parent.thread_id if parent else None,
                type="subagent.failed",
                source={"kind": "subagent", "id": cancelled.id, "name": cancelled.name},
                payload={
                    "subagent_run_id": cancelled.id,
                    "child_run_id": cancelled.child_run_id,
                    "name": cancelled.name,
                    "task": cancelled.task,
                    "spec_key": cancelled.spec_key,
                    "status": cancelled.status.value,
                    "error": cancelled.error,
                },
            )
```

- [ ] **Step 3: Add helper functions at bottom**

```python
def _event_completed_at_marker() -> str:
    from aithru_agent.persistence.memory.store import utc_now
    return utc_now()


def _error_payload(error: Exception) -> dict[str, str]:
    if isinstance(error, AgentError):
        return {"code": error.code, "message": error.message}
    return {"message": str(error)}


def _approval_decision_value(decision: AgentApprovalDecision | str) -> str:
    return decision.value if isinstance(decision, AgentApprovalDecision) else str(decision)


_TERMINAL_RUN_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
}
```

- [ ] **Step 4: Run tests to verify core flow**

Run: `cd backend && uv run pytest tests/integration/test_pydantic_driver.py -v`
Expected: Tests pass (may need import adjustments)

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/worker/runner.py
git commit -m "refactor: update worker runner to use native AgentRuntime - bugs fixed"
```

---

### Task 8: Update Application Runtime Factory (with Backward Compatibility)

**Files:**
- Modify: `backend/src/aithru_agent/application/runtime.py`

- [ ] **Step 1: Update imports**

```python
from dataclasses import dataclass

from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    MemoryLocalTool,
    SandboxLocalTool,
    SubagentLocalTool,
    TodoLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.settings import AgentSettings
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker import AgentWorkerRunner, AgentWorkerService, InProcessRunQueue
```

- [ ] **Step 2: Update AgentRuntime dataclass - rename to avoid conflict**

```python
@dataclass
class AgentApplication:
    """Application container for Aithru Agent services.
    
    This was formerly called AgentRuntime - renamed to avoid conflict with
    the native Pydantic AI AgentRuntime.
    """
    settings: AgentSettings
    store: AgentStore
    event_store: AgentEventStore
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    runner: AgentWorkerRunner
    run_queue: InProcessRunQueue
    worker: AgentWorkerService
    skill_resolver: AgentSkillResolver
    agent_runtime: AgentRuntime
```

- [ ] **Step 3: Create factory with backward compatible alias**

```python
def create_agent_application(
    *,
    store: AgentStore | None = None,
    event_store: AgentEventStore | None = None,
    agent_runtime: AgentRuntime | None = None,
    policy: ToolPolicy | None = None,
    settings: AgentSettings | None = None,
    skill_resolver: AgentSkillResolver | None = None,
) -> AgentApplication:
    """Create a complete Aithru Agent application.
    
    This is the new preferred name. Use create_agent_runtime alias for backward compatibility.
    """
    resolved_settings = settings or AgentSettings.from_env()
    resolved_store = store or _create_store(resolved_settings)
    resolved_event_store = event_store or _create_event_store(resolved_settings)
    event_writer = AgentEventWriter(resolved_event_store)
    resolved_skill_resolver = skill_resolver or EmptySkillResolver()
    capability_router = AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(resolved_store),
            TodoLocalTool(resolved_store),
            ArtifactLocalTool(resolved_store),
            MemoryLocalTool(resolved_store),
            SubagentLocalTool(resolved_store, event_writer, resolved_skill_resolver),
            SandboxLocalTool(event_writer),
        ],
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )
    
    resolved_agent_runtime = agent_runtime or _create_agent_runtime(resolved_settings)
    
    runner = AgentWorkerRunner(
        store=resolved_store,
        event_writer=event_writer,
        capability_router=capability_router,
        agent_runtime=resolved_agent_runtime,
        skill_resolver=resolved_skill_resolver,
    )
    run_queue = InProcessRunQueue()
    worker = AgentWorkerService(runner=runner, queue=run_queue)
    return AgentApplication(
        settings=resolved_settings,
        store=resolved_store,
        event_store=resolved_event_store,
        event_writer=event_writer,
        capability_router=capability_router,
        runner=runner,
        run_queue=run_queue,
        worker=worker,
        skill_resolver=resolved_skill_resolver,
        agent_runtime=resolved_agent_runtime,
    )


# BACKWARD COMPATIBILITY ALIAS - API and CLI depend on this name
create_agent_runtime = create_agent_application


def _create_agent_runtime(settings: AgentSettings) -> AgentRuntime:
    """Create native Pydantic AI agent runtime from settings."""
    if settings.model == "test":
        model = TestModel(custom_output_text=settings.test_model_output)
    elif settings.model:
        model = settings.model
    else:
        raise ValueError(
            "AITHRU_AGENT_MODEL is required for the Pydantic AI runtime. "
            "Use AITHRU_AGENT_MODEL=test only for tests or local deterministic development."
        )
    
    return AgentRuntime(
        model=model,
        model_factory=lambda m: TestModel(custom_output_text=settings.test_model_output) if m == "test" else m,
        instructions=settings.instructions,
    )


def _create_store(settings: AgentSettings) -> AgentStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentStore(settings.sqlite_path)
    return InMemoryAgentStore()


def _create_event_store(settings: AgentSettings) -> AgentEventStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentEventStore(settings.sqlite_path)
    return InMemoryAgentEventStore()
```

- [ ] **Step 4: Verify API still works with backward compatibility**

Run: `cd backend && uv run python -c "from aithru_agent.application.runtime import create_agent_runtime; from aithru_agent.settings import AgentSettings; app = create_agent_runtime(settings=AgentSettings(model='test')); print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/application/runtime.py
git commit -m "refactor: update application factory - backward compatible"
```

---

### Task 9: Migrate Tests from Scripted Driver to Pydantic TestModel

**Files:**
- Update: All integration tests that use ScriptedDriver
- Create: `backend/tests/utils/test_model.py` - Test helpers

- [ ] **Step 1: Create test model helper**

```python
"""Test helpers for deterministic Pydantic AI testing."""

from pydantic_ai.models.test import TestModel


def create_deterministic_test_model(
    output_text: str = "Test completed",
    *,
    call_tools: list[str] | str = "all",
) -> TestModel:
    """Create a TestModel using the installed pydantic_ai test API.
    
    The current TestModel supports `call_tools` and `custom_output_text`; it
    does not provide ToolHandlerSpec/tool_handlers. Tool outputs still come
    from Aithru local tools through the capability router.
    """
    return TestModel(
        call_tools=call_tools,
        custom_output_text=output_text,
    )


def create_simple_test_agent(
    model_output: str = "Test completed",
    *,
    call_tools: list[str] | str = "all",
):
    """Create a native AgentRuntime backed by TestModel."""
    from aithru_agent.agent import AgentRuntime

    return AgentRuntime(
        model=create_deterministic_test_model(model_output, call_tools=call_tools),
        instructions="You are a test agent",
    )
```

- [ ] **Step 2: Update tests that used ScriptedHarnessDriver**

Replace `create_agent_runtime(driver=ScriptedHarnessDriver(...))` with either:

```python
from tests.utils.test_model import create_simple_test_agent

runtime = create_agent_runtime(
    settings=AgentSettings(model="test"),
    agent_runtime=create_simple_test_agent("Created /reports/report.md", call_tools=[]),
)
```

or, for tool-routing tests:

```python
runtime = create_agent_runtime(
    settings=AgentSettings(model="test"),
    agent_runtime=create_simple_test_agent(
        "Done.",
        call_tools=["workspace.list_files"],
    ),
)
```

When a test needs exact workspace/artifact state that `TestModel` cannot
produce deterministically, pre-seed store state directly or assert event
classes/statuses instead of scripted tool-input literals.

- [ ] **Step 3: Update test_approval_resume.py to use native runtime**

- [ ] **Step 4: Update test_pydantic_driver.py imports**

- [ ] **Step 5: Run core tests**

Run: `cd backend && uv run pytest tests/integration/test_approval_resume.py tests/integration/test_pydantic_driver.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/utils/test_model.py
git commit -m "test: add TestModel helpers for deterministic testing"
```

---

### Task 10: Remove Generic Harness Engine Protocol and Old Drivers

**Files:**
- Delete: `backend/src/aithru_agent/harness/engine.py`
- Delete: `backend/src/aithru_agent/harness/drivers/` (entire directory)
- Update: `backend/src/aithru_agent/harness/__init__.py`

- [ ] **Step 1: Update harness/__init__.py**

```python
"""Harness utilities and context building.

Legacy generic driver protocol has been REMOVED in favor of the native
Pydantic AI agent runtime in aithru_agent.agent.
"""

from aithru_agent.harness.context_builder import ContextBuilder

__all__ = [
    "ContextBuilder",
]
```

- [ ] **Step 2: Delete old driver files**

```bash
rm -rf backend/src/aithru_agent/harness/engine.py
rm -rf backend/src/aithru_agent/harness/drivers/
```

- [ ] **Step 3: Verify no broken imports**

Run: `cd backend && uv run python -c "from aithru_agent.harness import ContextBuilder; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git rm -f backend/src/aithru_agent/harness/engine.py
git rm -rf backend/src/aithru_agent/harness/drivers/
git add backend/src/aithru_agent/harness/__init__.py
git commit -m "refactor: remove generic harness engine and old drivers"
```

---

### Task 11: Implement Full Progressive Skill System

**Files:**
- Create: `backend/src/aithru_agent/agent/skills/parser.py`
- Create: `backend/src/aithru_agent/agent/skills/registry.py`
- Create: `backend/src/aithru_agent/agent/skills/activation.py`
- Create: `backend/src/aithru_agent/agent/skills/__init__.py`

- [ ] **Step 1: Create skills/parser.py**

```python
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass
class ProgressiveSkill:
    """A harness-native progressive skill.
    
    Skills are context/tool/policy packages loaded dynamically at runtime.
    """
    name: str
    description: str
    instructions: str
    tags: list[str] | None = None
    when_to_use: str | None = None
    when_to_use_summary: str | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    workspace_allowed_paths: list[str] | None = None
    workspace_readonly: bool = False
    memory_read_scopes: list[str] | None = None
    memory_write_scopes: list[str] | None = None
    sandbox_enabled: bool = False
    sandbox_allowed_commands: list[str] | None = None
    requires_approval_for_risk: list[str] | None = None
    metadata: dict[str, Any] | None = None


def parse_skill_md(content: str) -> ProgressiveSkill:
    """Parse SKILL.md format into ProgressiveSkill object.
    
    Format:
    ---
    name: skill-name
    description: Skill description
    tags: [tag1, tag2]
    ---
    
    # Skill Title
    
    Markdown instructions...
    
    ## Activation
    When user asks for...
    
    ## Tool Policy
    Allowed: tool1, tool2
    Denied: tool3
    
    ## Workspace Policy
    Readonly: true
    Paths: path1/, path2/
    
    ## Memory Policy
    Read: user, workspace
    Write: workspace
    
    ## Sandbox Policy
    Enabled: false
    """
    # Extract frontmatter
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            body = parts[2]
    
    # Extract fields from frontmatter
    name = frontmatter.get("name", "unnamed-skill")
    description = frontmatter.get("description", "")
    tags = frontmatter.get("tags")
    
    # Parse Activation section
    when_to_use = None
    when_to_use_summary = None
    if "## Activation" in body:
        activation_part = body.split("## Activation", 1)[1]
        if "##" in activation_part:
            activation_part = activation_part.split("##", 1)[0]
        when_to_use = activation_part.strip()
        lines = when_to_use.strip().split("\n")
        when_to_use_summary = lines[0] if lines else None
    
    # Parse Tool Policy section
    allowed_tools = None
    denied_tools = None
    if "## Tool Policy" in body:
        policy_part = body.split("## Tool Policy", 1)[1]
        if "##" in policy_part:
            policy_part = policy_part.split("##", 1)[0]
        for line in policy_part.split("\n"):
            if line.startswith("Allowed:"):
                allowed_tools = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
            elif line.startswith("Denied:"):
                denied_tools = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
    
    # Parse Workspace Policy
    workspace_allowed_paths = None
    workspace_readonly = False
    if "## Workspace Policy" in body:
        policy_part = body.split("## Workspace Policy", 1)[1]
        if "##" in policy_part:
            policy_part = policy_part.split("##", 1)[0]
        for line in policy_part.split("\n"):
            if line.startswith("Paths:"):
                workspace_allowed_paths = [p.strip() for p in line.split(":", 1)[1].split(",") if p.strip()]
            elif line.startswith("Readonly:"):
                workspace_readonly = line.split(":", 1)[1].strip().lower() == "true"
    
    # Parse Memory Policy
    memory_read_scopes = None
    memory_write_scopes = None
    if "## Memory Policy" in body:
        policy_part = body.split("## Memory Policy", 1)[1]
        if "##" in policy_part:
            policy_part = policy_part.split("##", 1)[0]
        for line in policy_part.split("\n"):
            if line.startswith("Read:"):
                memory_read_scopes = [s.strip() for s in line.split(":", 1)[1].split(",") if s.strip()]
            elif line.startswith("Write:"):
                memory_write_scopes = [s.strip() for s in line.split(":", 1)[1].split(",") if s.strip()]
    
    # Parse Approval Policy
    requires_approval_for_risk = None
    if "## Approval Policy" in body:
        policy_part = body.split("## Approval Policy", 1)[1]
        if "##" in policy_part:
            policy_part = policy_part.split("##", 1)[0]
        for line in policy_part.split("\n"):
            if line.startswith("Require Approval:"):
                requires_approval_for_risk = [r.strip() for r in line.split(":", 1)[1].split(",") if r.strip()]
    
    return ProgressiveSkill(
        name=name,
        description=description,
        instructions=body.strip(),
        tags=tags,
        when_to_use=when_to_use,
        when_to_use_summary=when_to_use_summary,
        allowed_tools=allowed_tools,
        denied_tools=denied_tools,
        workspace_allowed_paths=workspace_allowed_paths,
        workspace_readonly=workspace_readonly,
        memory_read_scopes=memory_read_scopes,
        memory_write_scopes=memory_write_scopes,
        requires_approval_for_risk=requires_approval_for_risk,
        metadata=frontmatter,
    )
```

- [ ] **Step 2: Create skills/registry.py**

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aithru_agent.agent.skills.parser import ProgressiveSkill, parse_skill_md


@dataclass
class SkillRegistry:
    """Registry for progressive skills.
    
    Loads skills from disk, caches parsed versions, provides lookup.
    """
    skill_dirs: list[Path] = field(default_factory=list)
    _loaded_skills: dict[str, ProgressiveSkill] = field(default_factory=dict)
    _skill_by_tag: dict[str, list[str]] = field(default_factory=dict)

    def add_skill_dir(self, path: Path | str) -> None:
        """Add a directory to scan for SKILL.md files."""
        self.skill_dirs.append(Path(path))

    def register_skill(self, name: str, skill: ProgressiveSkill) -> None:
        """Register a pre-parsed skill."""
        self._loaded_skills[name] = skill
        if skill.tags:
            for tag in skill.tags:
                if tag not in self._skill_by_tag:
                    self._skill_by_tag[tag] = []
                self._skill_by_tag[tag].append(name)

    def load_skill_from_content(self, name: str, content: str) -> ProgressiveSkill:
        """Load a skill from content string."""
        skill = parse_skill_md(content)
        self.register_skill(name, skill)
        return skill

    def load_from_dirs(self) -> int:
        """Load all skills from registered directories.
        
        Returns:
            Number of skills loaded.
        """
        count = 0
        for skill_dir in self.skill_dirs:
            if not skill_dir.exists():
                continue
            for skill_file in skill_dir.rglob("SKILL.md"):
                skill_name = skill_file.parent.name
                content = skill_file.read_text()
                self.load_skill_from_content(skill_name, content)
                count += 1
        return count

    def get_skill(self, name: str) -> ProgressiveSkill | None:
        """Get skill by name."""
        return self._loaded_skills.get(name)

    def find_by_tag(self, tag: str) -> list[ProgressiveSkill]:
        """Find all skills with a given tag."""
        skill_names = self._skill_by_tag.get(tag, [])
        return [self._loaded_skills[name] for name in skill_names if name in self._loaded_skills]

    def list_skills(self) -> list[str]:
        """List all loaded skill names."""
        return list(self._loaded_skills.keys())
```

- [ ] **Step 3: Create skills/activation.py**

```python
"""Skill activation and context injection logic."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aithru_agent.agent.skills.parser import ProgressiveSkill
    from aithru_agent.agent.skills.registry import SkillRegistry


@dataclass
class ActivationMatch:
    skill_name: str
    confidence: float
    matched_trigger: str


class SkillActivator:
    """Determines which skills to activate based on run goal and context."""
    
    def __init__(self, registry: "SkillRegistry") -> None:
        self._registry = registry
    
    def detect_skills_for_goal(
        self,
        goal: str,
        skill_id_hint: str | None = None,
    ) -> list[ActivationMatch]:
        """Detect which skills should be activated for a given goal.
        
        Args:
            goal: The user's goal
            skill_id_hint: Explicit skill ID from run config
            
        Returns:
            List of activation matches sorted by confidence
        """
        matches: list[ActivationMatch] = []
        
        # Explicit skill ID always wins
        if skill_id_hint:
            skill = self._registry.get_skill(skill_id_hint)
            if skill:
                matches.append(ActivationMatch(
                    skill_name=skill_id_hint,
                    confidence=1.0,
                    matched_trigger="explicit_skill_id",
                ))
                return matches
        
        # Heuristic activation based on when_to_use patterns
        for skill_name in self._registry.list_skills():
            skill = self._registry.get_skill(skill_name)
            if not skill:
                continue
            
            confidence = self._match_skill(skill, goal)
            if confidence > 0.3:
                matches.append(ActivationMatch(
                    skill_name=skill_name,
                    confidence=confidence,
                    matched_trigger="heuristic_match",
                ))
        
        # Sort by confidence descending
        matches.sort(key=lambda m: -m.confidence)
        return matches
    
    def _match_skill(self, skill: "ProgressiveSkill", goal: str) -> float:
        """Match skill against goal using simple heuristics."""
        confidence = 0.0
        goal_lower = goal.lower()
        
        # Check for keyword matches in skill name and description
        name_words = skill.name.lower().replace("-", " ").replace("_", " ").split()
        for word in name_words:
            if len(word) > 3 and word in goal_lower:
                confidence += 0.1
        
        # Check description keywords
        if skill.description:
            desc_words = re.findall(r'\w+', skill.description.lower())
            for word in desc_words:
                if len(word) > 4 and word in goal_lower:
                    confidence += 0.05
        
        # Check if skill has summary activation hints
        if skill.when_to_use_summary:
            summary_words = re.findall(r'\w+', skill.when_to_use_summary.lower())
            for word in summary_words:
                if len(word) > 3 and word in goal_lower:
                    confidence += 0.15
        
        return min(confidence, 0.95)
    
    def inject_skill_context(self, instructions: str, skills: list["ProgressiveSkill"]) -> str:
        """Inject activated skill context into system prompt.
        
        For progressive loading: inject summaries only, full instructions
        when skill is activated at higher confidence.
        """
        if not skills:
            return instructions
        
        sections = ["\n\n## Activated Skills\n"]
        
        for skill in skills:
            sections.append(f"### {skill.name}: {skill.description}")
            if skill.when_to_use_summary:
                sections.append(f"Purpose: {skill.when_to_use_summary}")
            if skill.allowed_tools:
                sections.append(f"Allowed tools: {', '.join(skill.allowed_tools)}")
        
        skill_context = "\n".join(sections)
        return instructions + skill_context
```

- [ ] **Step 4: Create skills/__init__.py**

```python
"""Progressive skill system for Pydantic AI agent.

Skills are harness-native context/tool/policy packages loaded dynamically.
"""

from aithru_agent.agent.skills.activation import ActivationMatch, SkillActivator
from aithru_agent.agent.skills.parser import ProgressiveSkill, parse_skill_md
from aithru_agent.agent.skills.registry import SkillRegistry

__all__ = [
    "ProgressiveSkill",
    "parse_skill_md",
    "SkillRegistry",
    "ActivationMatch",
    "SkillActivator",
]
```

- [ ] **Step 5: Wire progressive skills into AgentRuntime**

Modify `backend/src/aithru_agent/agent/runtime.py`:

```python
from aithru_agent.agent.skills import ProgressiveSkill, SkillActivator, SkillRegistry
```

Add a runtime field:

```python
    skill_registry: SkillRegistry | None = None
```

In `build_agent()`, after `descriptors = await deps.capability_router.list_tools(...)` and before `tool_specs = [...]`, activate skills and apply their tool policy:

```python
        active_skills = await self._activate_progressive_skills(deps)
        descriptors = self._apply_progressive_skill_tool_policy(descriptors, active_skills)
```

After building the base system prompt, inject active skill context:

```python
        instruction_builder = InstructionBuilder(self.instructions)
        system_prompt = await instruction_builder.build(deps)
        if self.skill_registry and active_skills:
            system_prompt = SkillActivator(self.skill_registry).inject_skill_context(
                system_prompt,
                active_skills,
            )
```

Add helper methods:

```python
    async def _activate_progressive_skills(self, deps: PydanticAgentDeps) -> list[ProgressiveSkill]:
        if self.skill_registry is None:
            return []
        activator = SkillActivator(self.skill_registry)
        matches = activator.detect_skills_for_goal(
            deps.run.goal,
            skill_id_hint=deps.run.skill_id,
        )
        active: list[ProgressiveSkill] = []
        for match in matches:
            skill = self.skill_registry.get_skill(match.skill_name)
            if skill is None:
                continue
            active.append(skill)
            await deps.event_writer.write(
                run_id=deps.run.id,
                thread_id=deps.run.thread_id,
                type="skill.activated",
                source={"kind": "harness"},
                visibility="debug",
                payload={
                    "skill_name": match.skill_name,
                    "confidence": match.confidence,
                    "matched_trigger": match.matched_trigger,
                },
            )
        return active

    def _apply_progressive_skill_tool_policy(
        self,
        descriptors: list[AgentToolDescriptor],
        skills: list[ProgressiveSkill],
    ) -> list[AgentToolDescriptor]:
        if not skills:
            return descriptors
        allowed_sets = [
            set(skill.allowed_tools)
            for skill in skills
            if skill.allowed_tools is not None
        ]
        denied = {
            tool
            for skill in skills
            for tool in (skill.denied_tools or [])
        }
        filtered = descriptors
        if allowed_sets:
            allowed = set().union(*allowed_sets)
            filtered = [descriptor for descriptor in filtered if descriptor.name in allowed]
        if denied:
            filtered = [descriptor for descriptor in filtered if descriptor.name not in denied]
        return filtered
```

Add this import to `runtime.py`:

```python
from aithru_agent.domain import AgentToolDescriptor
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/agent/skills/__init__.py
git add backend/src/aithru_agent/agent/skills/parser.py
git add backend/src/aithru_agent/agent/skills/registry.py
git add backend/src/aithru_agent/agent/skills/activation.py
git add backend/src/aithru_agent/agent/runtime.py
git commit -m "feat: add full progressive skill system and runtime activation"
```

---

### Task 12: Full Test Suite Pass and File Report Verification

**Files:**
- Fix any remaining tests
- Verify file_report_agent.py

- [ ] **Step 1: Run full test suite**

Run: `cd backend && uv run pytest --tb=short`
Fix any failing tests.

- [ ] **Step 2: Run file_report_agent.py example**

Run: `cd backend && uv run python examples/file_report_agent.py`
Expected: Runs successfully

- [ ] **Step 3: Final verification commit**

```bash
git status
# Commit any fixes needed
```

---

## Plan Self-Review - All Bugs Fixed ✅

| Issue | Status | Fix Location |
|-------|--------|--------------|
| Async list_tools bug | ✅ Fixed | Task 6 runtime.py - build_agent is async, await descriptors |
| Empty tool_call_id on resume | ✅ Fixed | Task 6, 7 - persisted_tool_call_id parameter from approval.tool_call_id |
| Import from deleted harness.engine | ✅ Fixed | Task 5, 6 - Native RunPausedForApproval exception |
| Backward compatible create_agent_runtime | ✅ Fixed | Task 8 - Alias preserved for API/CLI |
| Scripted driver migration path | ✅ Fixed | Task 9 - TestModel helpers replace scripted driver; old drivers deleted after migration |
| Missing files (instructions.py, descriptors.py) | ✅ Fixed | Files created in separate tasks; no separate event_writer.py in this slice |
| Progressive skill system depth | ✅ Fixed | Task 11 - parser, registry, activation, runtime context injection, tool policy, and skill activation events |
| Fake default model risk | ✅ Fixed | Task 8 - no model raises configuration error; TestModel only for `model="test"` |
| Pydantic AI TestModel API mismatch | ✅ Fixed | Task 9 - helper uses supported `call_tools` and `custom_output_text` parameters |
