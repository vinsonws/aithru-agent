# Conversation Display Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build trusted inline conversation cards for workspace files and artifacts, with backend-owned card events and frontend timeline rendering.

**Architecture:** Display cards are canonical stream events produced by the harness after capability-controlled tool results. The model may request cards through a constrained `present_resources` tool, but the backend validates resources and emits trusted `display.card.created` events. The frontend projects those events into `RunStreamState`, interleaves cards by stream sequence, and renders them with a small trusted card renderer registry.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Pydantic AI tool bridge, existing Agent stream event store/SSE, React 19, TypeScript, Vite, node:test, Tailwind, lucide-react.

## Global Constraints

- Models may request that existing resources be presented.
- The harness decides which cards are valid, safe, and visible.
- The frontend renders trusted card events in timeline order.
- Do not let the model send arbitrary UI schemas, HTML, component names, or CSS.
- Do not make the frontend infer product cards only from raw tool names.
- Do not create Agent workflow semantics or graph behavior.
- Cards are user-facing summaries; trace remains the inspectable execution record.
- Tool calls must remain capability-router controlled and traceable.
- Real actions must pass through policy, scope, approval, and redaction boundaries.
- V1 card types are `file`, `artifact`, and `generic`; other types remain schema-compatible but unrendered by custom components.
- Card ordering uses the `AgentStreamEvent.sequence` of `display.card.created` and `display.card.updated`.

---

## File Structure

- Create `backend/src/aithru_agent/domain/display.py`: domain models for display cards, resources, actions, and sources.
- Modify `backend/src/aithru_agent/domain/__init__.py`: export display card models for API schema generation.
- Create `backend/src/aithru_agent/stream/display_cards.py`: helpers that build trusted card payloads from capability outputs and stream events.
- Modify `backend/src/aithru_agent/agent/tools/bridge.py`: emit `display.card.created` after successful relevant tool completions.
- Create `backend/src/aithru_agent/capabilities/local_tools/presentation.py`: controlled `present_resources` local tool.
- Modify `backend/src/aithru_agent/capabilities/local_tools/__init__.py`: export `PresentationLocalTool`.
- Modify `backend/src/aithru_agent/application/runtime.py`: register `PresentationLocalTool`.
- Modify `backend/src/aithru_agent/api/snapshots.py`: add display card projection to `RunSnapshotResponse`.
- Modify `backend/src/aithru_agent/api/routes/events.py`: include display cards in direct run snapshots.
- Modify `backend/src/aithru_agent/api/routes/threads.py`: include display cards in thread selected-run snapshots.
- Modify `frontend/src/lib/api/types.ts`: export generated display card types.
- Modify `frontend/src/features/chat/useRunStream.ts`: add display card state and reducer handling.
- Modify `frontend/src/features/chat/chatTimeline.ts`: add `kind: "card"` timeline items and interleave them with assistant process/output segments.
- Create `frontend/src/features/chat/DisplayCard.tsx`: trusted renderer registry for file/artifact/generic cards.
- Leave `frontend/src/features/chat/FileCard.tsx` unchanged unless typecheck reveals an import conflict; inline display cards use the new `DisplayCard.tsx`.
- Modify `frontend/src/features/chat/ChatPanel.tsx`: render card items and wire preview callbacks.
- Modify `frontend/src/i18n/resources/en/chat.json` and `frontend/src/i18n/resources/zh/chat.json`: add card labels.
- Add or modify tests:
  - `backend/tests/unit/domain/test_display_cards.py`
  - `backend/tests/unit/stream/test_display_cards.py`
  - `backend/tests/unit/capabilities/test_local_tools.py`
  - `backend/tests/integration/test_pydantic_tool_bridge.py`
  - `backend/tests/integration/test_api.py`
  - `frontend/tests/use-run-stream.test.mjs`
  - `frontend/tests/chat-timeline.test.mjs`

## Interfaces

Backend produces:

```python
AgentDisplayCard(
    id="card_run_1_tool_1_workspace_file_a_txt",
    thread_id="thread_1",
    run_id="run_1",
    surface="conversation",
    type="file",
    status="ready",
    title="a.txt",
    resource=AgentDisplayCardResource(kind="workspace_file", path="/a.txt"),
    actions=[AgentDisplayCardAction(kind="preview", label="Preview")],
    source=AgentDisplayCardSource(
        created_by="harness",
        tool_call_id="tool_1",
        tool_name="workspace.write_file",
    ),
)
```

Stream events:

```txt
tool.completed
display.card.created
message.delta
```

Frontend state consumes:

```ts
export interface DisplayCardEntry {
  id: string;
  type: "file" | "artifact" | "approval" | "todo" | "memory" | "search_result" | "generic";
  status: "pending" | "ready" | "failed";
  title: string;
  summary?: string;
  surface: "conversation" | "side_panel" | "both";
  resource?: {
    kind: "workspace_file" | "artifact" | "external_url" | "none";
    id?: string;
    path?: string;
    url?: string;
  };
  actions?: Array<{ kind: "preview" | "download" | "open" | "none"; label?: string; target?: string }>;
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
}
```

---

### Task 1: Backend Display Card Domain Models

**Files:**
- Create: `backend/src/aithru_agent/domain/display.py`
- Modify: `backend/src/aithru_agent/domain/__init__.py`
- Test: `backend/tests/unit/domain/test_display_cards.py`

**Interfaces:**
- Produces: `AgentDisplayCard`, `AgentDisplayCardResource`, `AgentDisplayCardAction`, `AgentDisplayCardSource`
- Consumes: `AithruBaseModel`

- [ ] **Step 1: Write failing domain tests**

Add `backend/tests/unit/domain/test_display_cards.py`:

```python
import pytest

from aithru_agent.domain import (
    AgentDisplayCard,
    AgentDisplayCardAction,
    AgentDisplayCardResource,
    AgentDisplayCardSource,
)


def test_workspace_file_card_requires_path_and_forbids_extra_ui_schema() -> None:
    card = AgentDisplayCard(
        id="card_1",
        thread_id="thread_1",
        run_id="run_1",
        surface="conversation",
        type="file",
        status="ready",
        title="a.txt",
        resource=AgentDisplayCardResource(kind="workspace_file", path="/a.txt"),
        actions=[AgentDisplayCardAction(kind="preview", label="Preview")],
        source=AgentDisplayCardSource(
            created_by="harness",
            tool_call_id="tool_1",
            tool_name="workspace.write_file",
        ),
    )

    assert card.resource.path == "/a.txt"
    assert card.type == "file"

    with pytest.raises(ValueError):
        AgentDisplayCardResource(kind="workspace_file")

    with pytest.raises(ValueError):
        AgentDisplayCard(
            id="card_2",
            thread_id="thread_1",
            run_id="run_1",
            surface="conversation",
            type="file",
            status="ready",
            title="a.txt",
            resource=AgentDisplayCardResource(kind="workspace_file", path="/a.txt"),
            source=AgentDisplayCardSource(created_by="model_request"),
            component="DangerousComponent",
        )


def test_artifact_card_requires_id() -> None:
    with pytest.raises(ValueError):
        AgentDisplayCardResource(kind="artifact")

    resource = AgentDisplayCardResource(kind="artifact", id="artifact_1")

    assert resource.id == "artifact_1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_display_cards.py -q
```

Expected: failure importing `AgentDisplayCard` from `aithru_agent.domain`.

- [ ] **Step 3: Add display card models**

Create `backend/src/aithru_agent/domain/display.py`:

```python
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


AgentDisplayCardSurface = Literal["conversation", "side_panel", "both"]
AgentDisplayCardType = Literal[
    "file",
    "artifact",
    "approval",
    "todo",
    "memory",
    "search_result",
    "generic",
]
AgentDisplayCardStatus = Literal["pending", "ready", "failed"]
AgentDisplayCardResourceKind = Literal["workspace_file", "artifact", "external_url", "none"]
AgentDisplayCardActionKind = Literal["preview", "download", "open", "none"]
AgentDisplayCardCreatedBy = Literal["harness", "tool", "model_request"]


class AgentDisplayCardResource(AithruBaseModel):
    kind: AgentDisplayCardResourceKind
    id: str | None = None
    path: str | None = None
    url: str | None = None

    @field_validator("id", "path", "url")
    @classmethod
    def _blank_strings_are_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _resource_has_required_reference(self) -> "AgentDisplayCardResource":
        if self.kind == "workspace_file" and self.path is None:
            raise ValueError("workspace file display card resources require path")
        if self.kind == "artifact" and self.id is None:
            raise ValueError("artifact display card resources require id")
        if self.kind == "external_url" and self.url is None:
            raise ValueError("external url display card resources require url")
        return self


class AgentDisplayCardAction(AithruBaseModel):
    kind: AgentDisplayCardActionKind
    label: str | None = None
    target: str | None = None
    disabled: bool = False


class AgentDisplayCardSource(AithruBaseModel):
    created_by: AgentDisplayCardCreatedBy
    event_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class AgentDisplayCard(AithruBaseModel):
    id: str = Field(min_length=1)
    thread_id: str | None = None
    run_id: str = Field(min_length=1)
    sequence: int | None = Field(default=None, ge=0)
    surface: AgentDisplayCardSurface = "conversation"
    type: AgentDisplayCardType = "generic"
    status: AgentDisplayCardStatus = "ready"
    title: str = Field(min_length=1)
    summary: str | None = None
    resource: AgentDisplayCardResource = Field(default_factory=lambda: AgentDisplayCardResource(kind="none"))
    actions: list[AgentDisplayCardAction] = Field(default_factory=list)
    source: AgentDisplayCardSource
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("display card title cannot be blank")
        return stripped
```

- [ ] **Step 4: Export display card models**

Modify `backend/src/aithru_agent/domain/__init__.py`:

```python
from .display import (
    AgentDisplayCard,
    AgentDisplayCardAction,
    AgentDisplayCardActionKind,
    AgentDisplayCardCreatedBy,
    AgentDisplayCardResource,
    AgentDisplayCardResourceKind,
    AgentDisplayCardSource,
    AgentDisplayCardStatus,
    AgentDisplayCardSurface,
    AgentDisplayCardType,
)
```

Add these names to `__all__` in the same file.

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_display_cards.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/domain/display.py backend/src/aithru_agent/domain/__init__.py backend/tests/unit/domain/test_display_cards.py
git commit -m "feat: add display card domain models"
```

---

### Task 2: Backend Card Projection Helpers

**Files:**
- Create: `backend/src/aithru_agent/stream/display_cards.py`
- Test: `backend/tests/unit/stream/test_display_cards.py`

**Interfaces:**
- Consumes: `AgentRun`, `AgentStreamEvent`, `AgentDisplayCard`
- Produces:
  - `display_cards_for_tool_result(run, tool_call_id, tool_name, output, created_by="harness") -> list[AgentDisplayCard]`
  - `display_cards_from_events(events) -> list[AgentDisplayCard]`

- [ ] **Step 1: Write failing projection tests**

Create `backend/tests/unit/stream/test_display_cards.py`:

```python
from aithru_agent.domain import AgentRun
from aithru_agent.stream.display_cards import (
    display_cards_for_tool_result,
    display_cards_from_events,
)
from aithru_agent.stream.events import AgentStreamEvent, AgentStreamSource


def run() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        thread_id="thread_1",
        actor_user_id="user_1",
        source="api",
        task_msg="write file",
        status="running",
        workspace_id="ws_1",
        scopes=["*"],
        created_at="2026-06-25T00:00:00Z",
        updated_at="2026-06-25T00:00:00Z",
    )


def event(sequence: int, payload: dict) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        thread_id="thread_1",
        sequence=sequence,
        timestamp="2026-06-25T00:00:00Z",
        type="display.card.created",
        source=AgentStreamSource(kind="harness"),
        payload=payload,
    )


def test_workspace_write_file_result_projects_file_card() -> None:
    cards = display_cards_for_tool_result(
        run(),
        tool_call_id="tool_1",
        tool_name="workspace.write_file",
        output={
            "workspace_id": "ws_1",
            "path": "/a.txt",
            "size": 12,
            "media_type": "text/plain",
        },
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.type == "file"
    assert card.title == "a.txt"
    assert card.resource.kind == "workspace_file"
    assert card.resource.path == "/a.txt"
    assert card.source.tool_call_id == "tool_1"
    assert card.source.tool_name == "workspace.write_file"
    assert card.actions[0].kind == "preview"


def test_artifact_result_projects_artifact_card() -> None:
    cards = display_cards_for_tool_result(
        run(),
        tool_call_id="tool_2",
        tool_name="artifact.create",
        output={
            "id": "artifact_1",
            "name": "report.md",
            "type": "markdown",
            "media_type": "text/markdown",
        },
    )

    assert len(cards) == 1
    assert cards[0].type == "artifact"
    assert cards[0].resource.kind == "artifact"
    assert cards[0].resource.id == "artifact_1"


def test_display_cards_from_events_fills_sequence_from_event() -> None:
    cards = display_cards_from_events(
        [
            event(
                7,
                {
                    "card": {
                        "id": "card_1",
                        "run_id": "run_1",
                        "thread_id": "thread_1",
                        "surface": "conversation",
                        "type": "file",
                        "status": "ready",
                        "title": "a.txt",
                        "resource": {"kind": "workspace_file", "path": "/a.txt"},
                        "source": {"created_by": "harness", "tool_call_id": "tool_1"},
                    }
                },
            )
        ]
    )

    assert cards[0].sequence == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/stream/test_display_cards.py -q
```

Expected: failure importing `aithru_agent.stream.display_cards`.

- [ ] **Step 3: Implement projection helpers**

Create `backend/src/aithru_agent/stream/display_cards.py`:

```python
from hashlib import sha1
from typing import Literal

from aithru_agent.domain import (
    AgentDisplayCard,
    AgentDisplayCardAction,
    AgentDisplayCardResource,
    AgentDisplayCardSource,
    AgentRun,
)
from aithru_agent.stream.events import AgentStreamEvent


DisplayCardCreator = Literal["harness", "tool", "model_request"]


def display_cards_for_tool_result(
    run: AgentRun,
    *,
    tool_call_id: str,
    tool_name: str,
    output: object,
    created_by: DisplayCardCreator = "harness",
) -> list[AgentDisplayCard]:
    if not isinstance(output, dict):
        return []
    if tool_name in {"workspace.write_file", "workspace.patch_file"}:
        path = _string_value(output.get("path"))
        if path is None:
            return []
        return [
            _workspace_file_card(
                run,
                path=path,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                created_by=created_by,
                metadata={
                    "workspace_id": _string_value(output.get("workspace_id")) or run.workspace_id,
                    "media_type": _string_value(output.get("media_type")),
                    "size": output.get("size") if isinstance(output.get("size"), int) else None,
                },
            )
        ]
    if tool_name in {"artifact.create", "research.create_report"}:
        artifact = output.get("artifact") if tool_name == "research.create_report" else output
        if not isinstance(artifact, dict):
            return []
        artifact_id = _string_value(artifact.get("id"))
        name = _string_value(artifact.get("name"))
        if artifact_id is None or name is None:
            return []
        return [
            _artifact_card(
                run,
                artifact_id=artifact_id,
                name=name,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                created_by=created_by,
                metadata={
                    "type": _string_value(artifact.get("type")),
                    "media_type": _string_value(artifact.get("media_type")),
                    "uri": _string_value(artifact.get("uri")),
                },
            )
        ]
    if tool_name == "present_resources":
        raw_cards = output.get("cards")
        if not isinstance(raw_cards, list):
            return []
        cards: list[AgentDisplayCard] = []
        for raw_card in raw_cards:
            if isinstance(raw_card, dict):
                cards.append(AgentDisplayCard.model_validate(raw_card))
        return cards
    return []


def display_cards_from_events(events: list[AgentStreamEvent]) -> list[AgentDisplayCard]:
    cards_by_id: dict[str, AgentDisplayCard] = {}
    for event in events:
        if event.type not in {"display.card.created", "display.card.updated"}:
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        raw_card = payload.get("card")
        if not isinstance(raw_card, dict):
            continue
        card = AgentDisplayCard.model_validate(raw_card).model_copy(
            update={
                "sequence": event.sequence,
                "thread_id": raw_card.get("thread_id") or event.thread_id,
                "run_id": raw_card.get("run_id") or event.run_id,
            }
        )
        cards_by_id[card.id] = card
    return sorted(cards_by_id.values(), key=lambda card: card.sequence or 0)


def display_card_event_payload(card: AgentDisplayCard) -> dict:
    return {"card": card.model_dump(mode="json", exclude_none=True)}


def _workspace_file_card(
    run: AgentRun,
    *,
    path: str,
    tool_call_id: str,
    tool_name: str,
    created_by: DisplayCardCreator,
    metadata: dict,
) -> AgentDisplayCard:
    return AgentDisplayCard(
        id=_stable_card_id(run.id, tool_call_id, "workspace_file", path),
        thread_id=run.thread_id,
        run_id=run.id,
        surface="conversation",
        type="file",
        status="ready",
        title=_basename(path),
        summary=path,
        resource=AgentDisplayCardResource(kind="workspace_file", path=path),
        actions=[AgentDisplayCardAction(kind="preview", label="Preview")],
        source=AgentDisplayCardSource(
            created_by=created_by,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        ),
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _artifact_card(
    run: AgentRun,
    *,
    artifact_id: str,
    name: str,
    tool_call_id: str,
    tool_name: str,
    created_by: DisplayCardCreator,
    metadata: dict,
) -> AgentDisplayCard:
    return AgentDisplayCard(
        id=_stable_card_id(run.id, tool_call_id, "artifact", artifact_id),
        thread_id=run.thread_id,
        run_id=run.id,
        surface="conversation",
        type="artifact",
        status="ready",
        title=name,
        resource=AgentDisplayCardResource(kind="artifact", id=artifact_id),
        actions=[
            AgentDisplayCardAction(kind="preview", label="Preview"),
            AgentDisplayCardAction(kind="download", label="Download"),
        ],
        source=AgentDisplayCardSource(
            created_by=created_by,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        ),
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _stable_card_id(run_id: str, tool_call_id: str, kind: str, value: str) -> str:
    digest = sha1(f"{run_id}:{tool_call_id}:{kind}:{value}".encode("utf-8")).hexdigest()[:12]
    return f"card_{digest}"


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or stripped or "file"


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd backend
uv run pytest tests/unit/stream/test_display_cards.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/aithru_agent/stream/display_cards.py backend/tests/unit/stream/test_display_cards.py
git commit -m "feat: project display cards from stream events"
```

---

### Task 3: Automatic Card Event Emission

**Files:**
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`
- Modify: `backend/tests/integration/test_pydantic_tool_bridge.py`

**Interfaces:**
- Consumes: `display_cards_for_tool_result`, `display_card_event_payload`
- Produces: `display.card.created` after successful `tool.completed`

- [ ] **Step 1: Write failing bridge test**

Add this test to `backend/tests/integration/test_pydantic_tool_bridge.py` near the workspace write-file tests:

```python
@pytest.mark.asyncio
async def test_workspace_write_file_emits_display_card_after_tool_completed() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=[]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write a file",
        scopes=["agent.workspace.write", "agent.workspace.read"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    tool_completed_index = event_types.index("tool.completed")
    card_index = event_types.index("display.card.created")

    assert card_index > tool_completed_index
    card_event = events[card_index]
    assert card_event.payload["card"]["type"] == "file"
    assert card_event.payload["card"]["resource"] == {
        "kind": "workspace_file",
        "path": "/a",
    }
    assert card_event.payload["card"]["source"]["tool_name"] == "workspace.write_file"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_workspace_write_file_emits_display_card_after_tool_completed -q
```

Expected: failure because no `display.card.created` event exists.

- [ ] **Step 3: Emit display cards after tool result events**

Modify imports in `backend/src/aithru_agent/agent/tools/bridge.py`:

```python
from aithru_agent.stream.display_cards import (
    display_card_event_payload,
    display_cards_for_tool_result,
)
```

In `call_tool`, immediately after the existing `await self._emit_tool_result_event(...)` call and before the non-completed failure branch, add:

```python
        await self._emit_tool_result_event(tool_call_id, tool_name, result)
        if result.status == "completed":
            await self._emit_display_card_events(tool_call_id, tool_name, result.output)
        if result.status != "completed":
```

Add this method to `PydanticAIToolBridge`:

```python
    async def _emit_display_card_events(
        self,
        tool_call_id: str,
        tool_name: str,
        output: object,
    ) -> None:
        for card in display_cards_for_tool_result(
            self._run,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            output=output,
        ):
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="display.card.created",
                source={"kind": "harness"},
                payload=display_card_event_payload(card),
            )
```

- [ ] **Step 4: Update existing exact event order tests**

In `test_pydantic_approval_resume_executes_persisted_tool_call`, update the expected tail to include the display card after `tool.completed`:

```python
    assert [event.type for event in events][-13:] == [
        "approval.resolved",
        "run.resumed",
        "tool.started",
        "workspace.file.created",
        "tool.completed",
        "display.card.created",
        "message.delta",
        "message.delta",
        "model.usage",
        "model.completed",
        "message.completed",
        "memory.candidate.created",
        "run.completed",
    ]
```

- [ ] **Step 5: Run bridge tests**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/agent/tools/bridge.py backend/tests/integration/test_pydantic_tool_bridge.py
git commit -m "feat: emit display cards from completed tools"
```

---

### Task 4: Controlled `present_resources` Tool

**Files:**
- Create: `backend/src/aithru_agent/capabilities/local_tools/presentation.py`
- Modify: `backend/src/aithru_agent/capabilities/local_tools/__init__.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Modify: `backend/tests/unit/capabilities/test_local_tools.py`

**Interfaces:**
- Produces tool: `present_resources`
- Output shape: `{"cards": [{"id": "card_1", "type": "file"}], "presented": [{"kind": "workspace_file", "path": "/a.txt"}]}`
- Validation: workspace files must exist in the current workspace; artifacts must belong to the current workspace and current run when `artifact.run_id` is set.

- [ ] **Step 1: Write failing local tool tests**

Modify imports in `backend/tests/unit/capabilities/test_local_tools.py`:

```python
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    InputLocalTool,
    MemoryLocalTool,
    PresentationLocalTool,
    ResearchLocalTool,
    TodoLocalTool,
    WorkbenchLocalTool,
    WorkspaceLocalTool,
)
```

Add `PresentationLocalTool(store)` to `make_router()` and to `test_local_tool_input_schemas_define_required_properties()` descriptor adapters.

Add tests:

```python
@pytest.mark.asyncio
async def test_present_resources_tool_presents_existing_workspace_file() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)
    await store.write_workspace_file(
        workspace_id=context.workspace_id,
        path="/a.txt",
        content="hello",
        media_type="text/plain",
    )

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="tool_present",
            tool_name="present_resources",
            input={"resources": [{"kind": "workspace_file", "path": "/a.txt"}]},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["cards"][0]["type"] == "file"
    assert result.output["cards"][0]["resource"] == {
        "kind": "workspace_file",
        "path": "/a.txt",
    }
    assert result.output["cards"][0]["source"]["created_by"] == "model_request"


@pytest.mark.asyncio
async def test_present_resources_tool_denies_missing_workspace_file() -> None:
    store = InMemoryAgentStore()
    context = await make_context(store)
    router = make_router(store)

    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="tool_present",
            tool_name="present_resources",
            input={"resources": [{"kind": "workspace_file", "path": "/missing.txt"}]},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "denied"
    assert result.error == {"message": "Workspace file does not exist: /missing.txt"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/unit/capabilities/test_local_tools.py::test_present_resources_tool_presents_existing_workspace_file tests/unit/capabilities/test_local_tools.py::test_present_resources_tool_denies_missing_workspace_file -q
```

Expected: failure importing `PresentationLocalTool`.

- [ ] **Step 3: Implement `PresentationLocalTool`**

Create `backend/src/aithru_agent/capabilities/local_tools/presentation.py`:

```python
from typing import Literal

from pydantic import Field

from aithru_agent.domain import (
    AgentDisplayCard,
    AgentDisplayCardAction,
    AgentDisplayCardResource,
    AgentDisplayCardSource,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore

from ..descriptors import AgentRunContext


class PresentResourceRef(AithruBaseModel):
    kind: Literal["workspace_file", "artifact"]
    path: str | None = None
    id: str | None = None


class PresentResourcesRequest(AithruBaseModel):
    surface: Literal["conversation", "side_panel", "both"] = "conversation"
    resources: list[PresentResourceRef] = Field(min_length=1)


class PresentationLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="present_resources",
                kind=AgentToolKind.LOCAL_TOOL,
                description=(
                    "Present existing workspace files or artifacts to the user as conversation cards. "
                    "This tool accepts resource references only; it does not accept custom UI."
                ),
                input_schema=PresentResourcesRequest.model_json_schema(),
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read"],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name != "present_resources":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unsupported tool: {request.tool_name}"},
                redaction="none",
            )
        try:
            input_data = PresentResourcesRequest.model_validate(request.input)
            cards = [
                await self._card_for_resource(resource, input_data.surface, request, context)
                for resource in input_data.resources
            ]
        except (AgentError, ValueError) as err:
            return AgentToolCallResult(
                status="denied",
                error={"message": _error_message(err)},
                redaction="none",
            )
        return AgentToolCallResult(
            status="completed",
            output={
                "cards": [card.model_dump(mode="json", exclude_none=True) for card in cards],
                "presented": [
                    card.resource.model_dump(mode="json", exclude_none=True) for card in cards
                ],
            },
            redaction="none",
        )

    async def _card_for_resource(
        self,
        resource: PresentResourceRef,
        surface: Literal["conversation", "side_panel", "both"],
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentDisplayCard:
        if resource.kind == "workspace_file":
            if resource.path is None:
                raise ValueError("workspace_file resources require path")
            file = await _workspace_file(self._store, context.workspace_id, resource.path)
            return AgentDisplayCard(
                id=f"card_{context.run_id}_{request.id}_workspace_{_safe_id(file.path)}",
                thread_id=context.thread_id,
                run_id=context.run_id,
                surface=surface,
                type="file",
                status="ready",
                title=_basename(file.path),
                summary=file.path,
                resource=AgentDisplayCardResource(kind="workspace_file", path=file.path),
                actions=[AgentDisplayCardAction(kind="preview", label="Preview")],
                source=AgentDisplayCardSource(
                    created_by="model_request",
                    tool_call_id=request.id,
                    tool_name=request.tool_name,
                ),
                metadata={
                    "workspace_id": file.workspace_id,
                    "media_type": file.media_type,
                    "size": file.size,
                },
            )
        if resource.id is None:
            raise ValueError("artifact resources require id")
        artifact = await self._store.get_artifact(resource.id)
        if artifact is None:
            raise AgentError("ARTIFACT_NOT_FOUND", f"Artifact does not exist: {resource.id}")
        if artifact.workspace_id != context.workspace_id:
            raise AgentError("ARTIFACT_SCOPE_DENIED", f"Artifact is outside this workspace: {resource.id}")
        if artifact.run_id is not None and artifact.run_id != context.run_id:
            raise AgentError("ARTIFACT_SCOPE_DENIED", f"Artifact is outside this run: {resource.id}")
        return AgentDisplayCard(
            id=f"card_{context.run_id}_{request.id}_artifact_{_safe_id(artifact.id)}",
            thread_id=context.thread_id,
            run_id=context.run_id,
            surface=surface,
            type="artifact",
            status="ready",
            title=artifact.name,
            resource=AgentDisplayCardResource(kind="artifact", id=artifact.id),
            actions=[
                AgentDisplayCardAction(kind="preview", label="Preview"),
                AgentDisplayCardAction(kind="download", label="Download"),
            ],
            source=AgentDisplayCardSource(
                created_by="model_request",
                tool_call_id=request.id,
                tool_name=request.tool_name,
            ),
            metadata={
                "type": artifact.type,
                "media_type": artifact.media_type,
                "uri": artifact.uri,
            },
        )


async def _workspace_file(store: AgentStore, workspace_id: str, path: str):
    files = await store.list_workspace_files(workspace_id)
    for file in files:
        if file.path == path:
            return file
    raise AgentError("WORKSPACE_FILE_NOT_FOUND", f"Workspace file does not exist: {path}")


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or stripped or "file"


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_") or "resource"


def _error_message(err: Exception) -> str:
    if isinstance(err, AgentError):
        return err.message
    return str(err)
```

- [ ] **Step 4: Register the local tool**

Modify `backend/src/aithru_agent/capabilities/local_tools/__init__.py`:

```python
from .presentation import PresentationLocalTool
```

Add `"PresentationLocalTool"` to `__all__`.

Modify imports in `backend/src/aithru_agent/application/runtime.py`:

```python
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    ClarificationLocalTool,
    InputLocalTool,
    MemoryLocalTool,
    PresentationLocalTool,
    ResearchLocalTool,
    SandboxLocalTool,
    SubagentLocalTool,
    TodoLocalTool,
    WorkbenchLocalTool,
    WorkspaceLocalTool,
)
```

Add the tool adapter after `InputLocalTool()`:

```python
        PresentationLocalTool(resolved_store),
```

- [ ] **Step 5: Run local tool tests**

Run:

```bash
cd backend
uv run pytest tests/unit/capabilities/test_local_tools.py -q
```

Expected: pass.

- [ ] **Step 6: Run bridge test for active presentation**

Add this test to `backend/tests/integration/test_pydantic_tool_bridge.py`:

```python
@pytest.mark.asyncio
async def test_present_resources_emits_display_cards_from_validated_tool_output() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file", "present_resources"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=[]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write and present a file",
        scopes=["agent.workspace.write", "agent.workspace.read"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    cards = [event for event in events if event.type == "display.card.created"]

    assert len(cards) >= 1
    assert cards[-1].payload["card"]["source"]["created_by"] in {"harness", "model_request"}
```

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py::test_present_resources_emits_display_cards_from_validated_tool_output -q
```

Expected: pass after `PresentationLocalTool` is registered and `Task 3` bridge emission handles `present_resources` cards.

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/capabilities/local_tools/presentation.py backend/src/aithru_agent/capabilities/local_tools/__init__.py backend/src/aithru_agent/application/runtime.py backend/tests/unit/capabilities/test_local_tools.py backend/tests/integration/test_pydantic_tool_bridge.py
git commit -m "feat: add controlled present resources tool"
```

---

### Task 5: Snapshot Projection and API Schema

**Files:**
- Modify: `backend/src/aithru_agent/api/snapshots.py`
- Modify: `backend/src/aithru_agent/api/routes/events.py`
- Modify: `backend/src/aithru_agent/api/routes/threads.py`
- Modify: `backend/tests/integration/test_api.py`
- Modify: `frontend/src/lib/api/schema.d.ts`
- Modify: `frontend/src/lib/api/types.ts`

**Interfaces:**
- Produces: `RunSnapshotResponse.display_cards: list[AgentDisplayCard]`
- Consumes: `display_cards_from_events(events)`

- [ ] **Step 1: Write failing API snapshot test**

Add a test to `backend/tests/integration/test_api.py` near run snapshot tests:

```python
def test_run_snapshot_includes_display_cards(client) -> None:
    create = client.post(
        "/api/runs",
        json={
            "task_msg": "Write file",
            "scopes": ["agent.workspace.write", "agent.workspace.read"],
            "wait_for_completion": True,
        },
    )
    assert create.status_code == 201
    run_id = create.json()["id"]

    snapshot = client.get(f"/api/runs/{run_id}/snapshot")

    assert snapshot.status_code == 200
    cards = snapshot.json()["display_cards"]
    assert cards
    assert cards[0]["type"] in {"file", "artifact"}
    assert cards[0]["sequence"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
uv run pytest tests/integration/test_api.py::test_run_snapshot_includes_display_cards -q
```

Expected: failure because `display_cards` is absent.

- [ ] **Step 3: Add snapshot field**

Modify imports in `backend/src/aithru_agent/api/snapshots.py`:

```python
from aithru_agent.domain import (
    AgentApproval,
    AgentArtifact,
    AgentDisplayCard,
    AgentRun,
    AgentRunOperatorFollowUpOptions,
    AgentSubagentResultSummary,
    AgentSubagentRun,
    AgentTodo,
    AgentWorkspaceFile,
)
from aithru_agent.stream.display_cards import display_cards_from_events
```

Add a field to `RunSnapshotResponse`:

```python
    display_cards: list[AgentDisplayCard] = Field(default_factory=list)
```

In both `RunSnapshotResponse(...)` constructions, `backend/src/aithru_agent/api/routes/events.py:135` and `backend/src/aithru_agent/api/routes/threads.py:908`, add:

```python
        display_cards=display_cards_from_events(events),
```

Confirm there are no other constructors:

```bash
rg -n "RunSnapshotResponse\\(" backend/src/aithru_agent
```

Expected: one class definition in `backend/src/aithru_agent/api/snapshots.py` and two constructors in `backend/src/aithru_agent/api/routes/events.py` and `backend/src/aithru_agent/api/routes/threads.py`.

- [ ] **Step 4: Run API test**

Run:

```bash
cd backend
uv run pytest tests/integration/test_api.py::test_run_snapshot_includes_display_cards -q
```

Expected: pass.

- [ ] **Step 5: Regenerate frontend OpenAPI schema**

Run this command from the repository root:

```bash
cd backend
AITHRU_AGENT_MODEL=test uv run python - <<'PY' > /tmp/aithru_openapi.json
from aithru_agent.api.main import create_app
import json
print(json.dumps(create_app().openapi()))
PY
cd ../frontend
npm run gen:types
```

Expected: `frontend/src/lib/api/schema.d.ts` changes and contains `AgentDisplayCard`.

- [ ] **Step 6: Export display card frontend types**

Modify `frontend/src/lib/api/types.ts`:

```ts
export type AgentDisplayCard = S["AgentDisplayCard"];
export type AgentDisplayCardAction = S["AgentDisplayCardAction"];
export type AgentDisplayCardResource = S["AgentDisplayCardResource"];
export type AgentDisplayCardSource = S["AgentDisplayCardSource"];
```

- [ ] **Step 7: Typecheck generated contract**

Run:

```bash
cd frontend
npm run typecheck
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/aithru_agent/api/snapshots.py backend/src/aithru_agent/api/routes/events.py backend/src/aithru_agent/api/routes/threads.py backend/tests/integration/test_api.py frontend/src/lib/api/schema.d.ts frontend/src/lib/api/types.ts
git commit -m "feat: expose display cards in run snapshots"
```

---

### Task 6: Frontend Stream State and Timeline

**Files:**
- Modify: `frontend/src/features/chat/useRunStream.ts`
- Modify: `frontend/src/features/chat/chatTimeline.ts`
- Modify: `frontend/tests/use-run-stream.test.mjs`
- Modify: `frontend/tests/chat-timeline.test.mjs`

**Interfaces:**
- Produces: `RunStreamState.displayCards`
- Produces timeline item: `{ kind: "card"; id; sequence; card }`

- [ ] **Step 1: Write failing stream reducer test**

Add to `frontend/tests/use-run-stream.test.mjs`:

```js
test("reduceEvent projects display card events into stream state", async () => {
  const reduceEvent = await loadReduceEvent();
  const projected = reduceEvent(
    state(),
    event(
      "display.card.created",
      {
        card: {
          id: "card_1",
          run_id: "run_1",
          thread_id: "thread_1",
          surface: "conversation",
          type: "file",
          status: "ready",
          title: "a.txt",
          resource: { kind: "workspace_file", path: "/a.txt" },
          actions: [{ kind: "preview", label: "Preview" }],
          source: { created_by: "harness", tool_call_id: "tool_1" },
        },
      },
      16,
    ),
  );

  assert.deepEqual(projected.displayCards, [
    {
      id: "card_1",
      type: "file",
      status: "ready",
      title: "a.txt",
      surface: "conversation",
      resource: { kind: "workspace_file", path: "/a.txt" },
      actions: [{ kind: "preview", label: "Preview" }],
      sequence: 16,
      lastSequence: 16,
      createdAt: "2026-06-23T00:00:00.000Z",
      updatedAt: "2026-06-23T00:00:00.000Z",
    },
  ]);
});
```

- [ ] **Step 2: Write failing timeline interleave test**

Add to `frontend/tests/chat-timeline.test.mjs`:

```js
test("buildChatTimeline interleaves cards between tool completion and assistant output", async () => {
  const { buildChatTimeline } = await loadChatTimeline();
  const timeline = buildChatTimeline(
    baseState({
      modelStartedSequence: 10,
      runCompletedSequence: 30,
      messages: [{ id: "msg_user", role: "user", content: "创建文件", sequence: 2 }],
      reasoningSegments: [{ id: "think_1", content: "准备写文件。", sequence: 11, lastSequence: 12 }],
      toolCalls: [
        { id: "tool_1", toolName: "workspace.write_file", status: "completed", sequence: 14, lastSequence: 15 },
      ],
      displayCards: [
        {
          id: "card_1",
          type: "file",
          status: "ready",
          title: "a.txt",
          surface: "conversation",
          resource: { kind: "workspace_file", path: "/a.txt" },
          sequence: 16,
          lastSequence: 16,
        },
      ],
      assistantOutputSegments: [
        { id: "msg_assistant:output:17", role: "assistant", content: "已创建。", sequence: 17, lastSequence: 18 },
      ],
    }),
  );

  assert.deepEqual(
    timeline.map((item) => {
      if (item.kind === "message") return `message:${item.message.content}`;
      if (item.kind === "assistantProcess") return "process";
      if (item.kind === "card") return `card:${item.card.title}`;
      return item.kind;
    }),
    ["message:创建文件", "process", "card:a.txt", "message:已创建。", "completion"],
  );
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- tests/use-run-stream.test.mjs tests/chat-timeline.test.mjs
```

Expected: failures because `displayCards` and `kind: "card"` are not implemented.

- [ ] **Step 4: Add display card state**

Modify `frontend/src/features/chat/useRunStream.ts`:

```ts
export interface DisplayCardEntry {
  id: string;
  type: "file" | "artifact" | "approval" | "todo" | "memory" | "search_result" | "generic";
  status: "pending" | "ready" | "failed";
  title: string;
  summary?: string;
  surface: "conversation" | "side_panel" | "both";
  resource?: {
    kind: "workspace_file" | "artifact" | "external_url" | "none";
    id?: string;
    path?: string;
    url?: string;
  };
  actions?: Array<{ kind: "preview" | "download" | "open" | "none"; label?: string; target?: string }>;
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
}
```

Add to `RunStreamState`:

```ts
  displayCards: DisplayCardEntry[];
```

Add to `initialState`:

```ts
  displayCards: [],
```

Add display card sequences to `hasProcessEventBetween` so assistant output splits around cards:

```ts
    ...state.displayCards.flatMap((card) => [card.sequence, card.lastSequence]),
```

Add reducer cases:

```ts
    case "display.card.created":
    case "display.card.updated": {
      const rawCard = p.card;
      if (!rawCard || typeof rawCard !== "object") return state;
      const cardPayload = rawCard as Record<string, unknown>;
      const id = (cardPayload.id as string | undefined) ?? event.id;
      const existing = state.displayCards.find((card) => card.id === id);
      const patch: DisplayCardEntry = {
        id,
        type: (cardPayload.type as DisplayCardEntry["type"] | undefined) ?? existing?.type ?? "generic",
        status: (cardPayload.status as DisplayCardEntry["status"] | undefined) ?? existing?.status ?? "ready",
        title: (cardPayload.title as string | undefined) ?? existing?.title ?? "Card",
        summary: (cardPayload.summary as string | undefined) ?? existing?.summary,
        surface: (cardPayload.surface as DisplayCardEntry["surface"] | undefined) ?? existing?.surface ?? "conversation",
        resource: (cardPayload.resource as DisplayCardEntry["resource"] | undefined) ?? existing?.resource,
        actions: (cardPayload.actions as DisplayCardEntry["actions"] | undefined) ?? existing?.actions,
        sequence: existing?.sequence ?? sequenceOf(event),
        lastSequence: sequenceOf(event),
        createdAt: existing?.createdAt ?? event.timestamp,
        updatedAt: event.timestamp,
      };
      return {
        ...state,
        displayCards: existing
          ? state.displayCards.map((card) => (card.id === id ? { ...card, ...patch } : card))
          : [...state.displayCards, patch],
      };
    }
```

- [ ] **Step 5: Add card timeline items**

Modify `frontend/src/features/chat/chatTimeline.ts` imports:

```ts
  DisplayCardEntry,
```

Add to `ChatTimelineItem`:

```ts
  | { kind: "card"; id: string; sequence: number; card: DisplayCardEntry }
```

Add to `KIND_ORDER`:

```ts
  card: 2,
  inlineRequest: 3,
  completion: 4,
```

In `appendRunTimelineItems`, include cards:

```ts
  const displayCards = state.displayCards.filter(
    (card) => card.surface === "conversation" || card.surface === "both",
  );
```

When `outputSegments.length === 0`, push standalone cards after the assistant process block:

```ts
    for (const card of displayCards) {
      items.push({
        kind: "card",
        id: `card:${card.id}`,
        sequence: card.sequence ?? card.lastSequence ?? FALLBACK_SEQUENCE,
        card,
      });
    }
```

In the interleaved `units` array, add:

```ts
    ...displayCards.map((card) => ({
      kind: "card" as const,
      sequence: card.sequence ?? card.lastSequence ?? FALLBACK_SEQUENCE,
      card,
    })),
```

In the loop:

```ts
    if (unit.kind === "card") {
      flushProcessGroup();
      items.push({
        kind: "card",
        id: `card:${unit.card.id}`,
        sequence: normalize(unit.sequence),
        card: unit.card,
      });
      continue;
    }
```

- [ ] **Step 6: Run frontend state/timeline tests**

Run:

```bash
cd frontend
npm test -- tests/use-run-stream.test.mjs tests/chat-timeline.test.mjs
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/chat/useRunStream.ts frontend/src/features/chat/chatTimeline.ts frontend/tests/use-run-stream.test.mjs frontend/tests/chat-timeline.test.mjs
git commit -m "feat: project display cards into chat timeline"
```

---

### Task 7: Frontend Card Rendering and Preview Wiring

**Files:**
- Create: `frontend/src/features/chat/DisplayCard.tsx`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`

**Interfaces:**
- Consumes: `DisplayCardEntry`
- Produces: inline rendered cards with preview callback `onPreviewFile(fileId: string)`

- [ ] **Step 1: Create trusted card renderer**

Create `frontend/src/features/chat/DisplayCard.tsx`:

```tsx
import { Download, ExternalLink, FileText, Image, Package, Search, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { DisplayCardEntry } from "./useRunStream";

interface DisplayCardProps {
  card: DisplayCardEntry;
  onPreviewFile?: (fileId: string) => void;
}

const CARD_ICON = {
  file: FileText,
  artifact: Package,
  approval: ShieldCheck,
  search_result: Search,
  generic: FileText,
  todo: FileText,
  memory: FileText,
} as const;

export function DisplayCard({ card, onPreviewFile }: DisplayCardProps) {
  const { t } = useTranslation("chat");
  const Icon = CARD_ICON[card.type] ?? CARD_ICON.generic;
  const previewId = previewFileId(card);
  const canPreview = Boolean(previewId && onPreviewFile);

  return (
    <div className="py-2">
      <div className="rounded-lg border bg-card p-3 text-sm shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
            {card.type === "file" && isImageLike(card) ? (
              <Image className="h-4 w-4" />
            ) : (
              <Icon className="h-4 w-4" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-foreground">{card.title}</div>
            {card.summary && (
              <div className="truncate text-xs text-muted-foreground">{card.summary}</div>
            )}
          </div>
          {canPreview && (
            <button
              type="button"
              onClick={() => previewId && onPreviewFile?.(previewId)}
              className={cn(
                "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium",
                "text-primary hover:bg-primary/10",
              )}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {t("cards.preview", "Preview")}
            </button>
          )}
          {hasDownload(card) && (
            <a
              href={`/api/artifacts/${encodeURIComponent(card.resource?.id ?? "")}/download`}
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              {t("cards.download", "Download")}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function previewFileId(card: DisplayCardEntry): string | null {
  if (card.resource?.kind === "workspace_file" && card.resource.path) {
    return `ws-${card.resource.path}`;
  }
  if (card.resource?.kind === "artifact" && card.resource.id) {
    return `artifact-${card.resource.id}`;
  }
  return null;
}

function hasDownload(card: DisplayCardEntry): boolean {
  return card.resource?.kind === "artifact" && Boolean(card.resource.id);
}

function isImageLike(card: DisplayCardEntry): boolean {
  const title = card.title.toLowerCase();
  return [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"].some((suffix) =>
    title.endsWith(suffix),
  );
}
```

- [ ] **Step 2: Wire cards into ChatPanel**

Modify imports in `frontend/src/features/chat/ChatPanel.tsx`:

```tsx
import { DisplayCard } from "./DisplayCard";
```

Rename the prop parameter so it is used:

```tsx
  onPreviewFile,
}: {
```

In `timeline.map`, add before inline requests:

```tsx
            if (item.kind === "card") {
              return (
                <div key={item.id} className={ASSISTANT_GUIDE_CLASSNAME}>
                  <DisplayCard card={item.card} onPreviewFile={onPreviewFile} />
                </div>
              );
            }
```

- [ ] **Step 3: Add i18n labels**

Add to `frontend/src/i18n/resources/en/chat.json`:

```json
{
  "cards": {
    "preview": "Preview",
    "download": "Download"
  }
}
```

Merge this with the existing JSON object without removing current keys.

Add to `frontend/src/i18n/resources/zh/chat.json`:

```json
{
  "cards": {
    "preview": "预览",
    "download": "下载"
  }
}
```

Merge this with the existing JSON object without removing current keys.

- [ ] **Step 4: Typecheck and build**

Run:

```bash
cd frontend
npm run typecheck
npm run build
```

Expected: both pass.

- [ ] **Step 5: Browser check**

Start the app if it is not already running:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 15173
```

Open an existing thread with a run that wrote a file, or create a new run asking it to write `/a.txt`. Verify:

```txt
Thought/tool process appears first.
File card appears after the completed write tool.
Final assistant answer appears after the card when streamed after it.
Clicking Preview opens the existing right-side file preview panel.
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/chat/DisplayCard.tsx frontend/src/features/chat/ChatPanel.tsx frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
git commit -m "feat: render display cards in chat"
```

---

### Task 8: Full Verification and Documentation Sync

**Files:**
- Modify: `docs/superpowers/specs/2026-06-25-conversation-display-cards-design.md` only if implementation changes the accepted protocol.

**Interfaces:**
- Consumes: all previous tasks
- Produces: verified backend, frontend, and browser behavior

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd backend
uv run pytest \
  tests/unit/domain/test_display_cards.py \
  tests/unit/stream/test_display_cards.py \
  tests/unit/capabilities/test_local_tools.py \
  tests/integration/test_pydantic_tool_bridge.py \
  tests/integration/test_api.py -q
```

Expected: pass.

- [ ] **Step 2: Run full backend verification required by AGENTS.md**

Run:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

Expected: pass. If the example writes files, verify the stream includes `display.card.created` after relevant `tool.completed` events.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

Expected: pass.

- [ ] **Step 4: Manual browser verification**

Use the local app at `http://127.0.0.1:15173` and verify:

```txt
Cards appear inline, not inside the right sidebar only.
Cards do not appear before their source tool completion.
Cards preserve order when reasoning, tool calls, cards, and assistant text interleave.
Unknown card types render as a generic card instead of crashing.
Preview actions open the existing right-side preview panel.
Refreshing the thread preserves cards from run events.
```

- [ ] **Step 5: Final commit**

If Task 8 changes docs or small fixes:

```bash
git add docs/superpowers/specs/2026-06-25-conversation-display-cards-design.md backend frontend
git commit -m "chore: verify display card flow"
```

If Task 8 makes no file changes, do not create an empty commit.
