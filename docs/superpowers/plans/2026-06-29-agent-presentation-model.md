# Agent Presentation Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Display Cards with a backend-owned Agent Presentation model that controls file/artifact views and lightweight user-guidance effects.

**Architecture:** Presentation is the single product semantic layer for user-facing resource display. The backend owns validation, view resolution, event emission, API projections, and prompt ledger; the frontend renders only trusted `presentation.*` events and executes only whitelisted effects. This is a breaking replacement: delete `AgentDisplayCard`, `display.card.*`, `display_cards`, `DisplayCard.tsx`, and `DisplayCardEntry` instead of aliasing them.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Pydantic AI harness, TypeScript, React 19, Vite, Node test runner, openapi-typescript.

## Global Constraints

- Do not preserve `AgentDisplayCard`, `display.card.*`, or `display_cards`.
- Do not let the model send arbitrary UI schemas, component names, CSS, JSX, HTML wrappers, frontend route names, or browser scripts.
- Do not let the frontend infer product presentations from raw tool names.
- The model may request presentations; the harness validates resources, views, effects, and actions.
- The frontend renders and executes only trusted presentation events.
- The model sees a ledger of backend-confirmed presentations, not arbitrary DOM state.
- Presentations must not become workflow definitions, graph nodes, checkpoints, or scheduler inputs.
- Real actions remain behind the Aithru capability boundary.
- Preserve event ordering and traceability through canonical stream events.
- HTML preview must be sandboxed.
- When touching backend code, run `cd backend && uv run pytest` and `uv run python examples/file_report_agent.py` before completion.
- When touching frontend code, run focused Node tests, `npm test`, `npm run typecheck`, and `npm run build`.
- The worktree may contain unrelated changes. Do not revert user changes. Stage only files changed by the current task.

---

## File Structure

### Backend Domain And Projection

- Replace `backend/src/aithru_agent/domain/display.py`: define `AgentPresentation*` models in place of `AgentDisplayCard*`.
- Modify `backend/src/aithru_agent/domain/__init__.py`: export presentation models and remove display card exports.
- Create `backend/src/aithru_agent/stream/presentations.py`: projection helpers, view resolution, event payload helpers.
- Delete `backend/src/aithru_agent/stream/display_cards.py`.
- Modify `backend/src/aithru_agent/agent/tools/bridge.py`: emit `presentation.created` after user-facing tool outputs.
- Modify `backend/src/aithru_agent/capabilities/local_tools/presentation.py`: replace `present_resources` with `presentation.present`.

### Backend API And Prompt Context

- Modify `backend/src/aithru_agent/api/snapshots.py`: expose `presentations`, remove `display_cards`.
- Modify `backend/src/aithru_agent/api/routes/threads.py`: use `presentations_from_events`.
- Modify `backend/src/aithru_agent/api/routes/events.py`: use `presentations_from_events`.
- Modify `backend/src/aithru_agent/harness/context_packet.py`: include compact presentation contexts in `AgentRunContextPacket`.
- Modify `backend/src/aithru_agent/domain/context.py`: add `AgentRunContextPresentation`.
- Modify `backend/src/aithru_agent/agent/instructions.py`: render "Presented to user" ledger.
- Modify docs that describe active stream/API contracts, especially `docs/03-stream-protocol.md`, `README.md`, and `backend/README.md`.

### Frontend

- Delete `frontend/src/features/chat/DisplayCard.tsx`.
- Create `frontend/src/features/chat/PresentationItem.tsx`: trusted presentation renderer.
- Modify `frontend/src/features/chat/useRunStream.ts`: replace `DisplayCardEntry`/`displayCards` with `PresentationEntry`/`presentations`.
- Modify `frontend/src/features/chat/chatTimeline.ts`: replace `kind: "card"` with `kind: "presentation"`.
- Modify `frontend/src/features/chat/ChatPanel.tsx`: render `PresentationItem` and apply approved side panel effects.
- Modify `frontend/src/features/chat/artifactLinks.ts`: resolve known artifact links from presentations instead of display cards.
- Modify generated API files: `frontend/src/lib/api/schema.d.ts` and `frontend/src/lib/api/types.ts`.

### Tests

- Replace:
  - `backend/tests/unit/domain/test_display_cards.py`
  - `backend/tests/unit/stream/test_display_cards_stream.py`
  - `frontend/tests/display-card.test.mjs`
- Add:
  - `backend/tests/unit/domain/test_presentations.py`
  - `backend/tests/unit/stream/test_presentations_stream.py`
  - `backend/tests/unit/harness/test_presentation_context.py`
  - `frontend/tests/presentation-item.test.mjs`
- Modify existing backend integration tests that assert `display.card.created` or `display_cards`.
- Modify existing frontend tests that assert `displayCards` or `kind: "card"`.

---

### Task 1: Replace Display Card Domain Models With Presentation Models

**Files:**
- Modify: `backend/src/aithru_agent/domain/display.py`
- Modify: `backend/src/aithru_agent/domain/__init__.py`
- Replace test: `backend/tests/unit/domain/test_display_cards.py` -> `backend/tests/unit/domain/test_presentations.py`

**Interfaces:**
- Produces:
  - `AgentPresentation`
  - `AgentPresentationResource`
  - `AgentPresentationEffect`
  - `AgentPresentationAction`
  - `AgentPresentationSource`
  - literal aliases for status, priority, view, surface, effect, action, resource kind, created_by.
- Consumes: `AithruBaseModel`, Pydantic `Field`, validators.

- [ ] **Step 1: Replace the domain test with failing presentation tests**

Delete `backend/tests/unit/domain/test_display_cards.py` and create `backend/tests/unit/domain/test_presentations.py`:

```python
import pytest

from aithru_agent.domain import (
    AgentPresentation,
    AgentPresentationAction,
    AgentPresentationEffect,
    AgentPresentationResource,
    AgentPresentationSource,
)


def test_artifact_presentation_requires_id_and_allows_html_preview() -> None:
    presentation = AgentPresentation(
        id="presentation_1",
        org_id="org_1",
        thread_id="thread_1",
        run_id="run_1",
        status="ready",
        priority="normal",
        title="index.html",
        reason="Show the generated webpage as an interactive preview.",
        resource=AgentPresentationResource(kind="artifact", id="artifact_1"),
        surfaces=["conversation", "side_panel"],
        preferred_view="html_preview",
        available_views=["html_preview", "source_text", "download"],
        effects=[
            AgentPresentationEffect(kind="open_panel", panel="preview", mode="soft")
        ],
        actions=[
            AgentPresentationAction(kind="open_view", label="Preview", view="html_preview"),
            AgentPresentationAction(kind="open_view", label="Source", view="source_text"),
            AgentPresentationAction(kind="download", label="Download"),
        ],
        source=AgentPresentationSource(
            created_by="harness",
            tool_call_id="tool_1",
            tool_name="artifact.create",
        ),
    )

    assert presentation.resource.id == "artifact_1"
    assert presentation.preferred_view == "html_preview"
    assert presentation.available_views == ["html_preview", "source_text", "download"]
    assert presentation.effects[0].panel == "preview"


def test_resource_validation_rejects_missing_required_references() -> None:
    with pytest.raises(ValueError, match="artifact presentation resources require id"):
        AgentPresentationResource(kind="artifact")

    with pytest.raises(ValueError, match="workspace file presentation resources require path"):
        AgentPresentationResource(kind="workspace_file")

    with pytest.raises(ValueError, match="external url presentation resources require url"):
        AgentPresentationResource(kind="external_url")


def test_preferred_view_must_be_available() -> None:
    with pytest.raises(ValueError, match="preferred view must be in available views"):
        AgentPresentation(
            id="presentation_2",
            org_id="org_1",
            thread_id="thread_1",
            run_id="run_1",
            title="index.html",
            resource=AgentPresentationResource(kind="artifact", id="artifact_1"),
            surfaces=["conversation"],
            preferred_view="html_preview",
            available_views=["source_text", "download"],
            source=AgentPresentationSource(created_by="model_request"),
        )


def test_effects_do_not_accept_freeform_ui_schema() -> None:
    with pytest.raises(ValueError):
        AgentPresentationEffect(
            kind="open_panel",
            panel="preview",
            mode="soft",
            component="DangerousComponent",
        )
```

- [ ] **Step 2: Run the focused domain test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_presentations.py -q
```

Expected: fail importing `AgentPresentation` from `aithru_agent.domain`.

- [ ] **Step 3: Implement presentation models**

Replace `backend/src/aithru_agent/domain/display.py` with:

```python
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


AgentPresentationResourceKind = Literal[
    "artifact",
    "workspace_file",
    "approval",
    "todo",
    "run",
    "trace_span",
    "external_url",
    "none",
]
AgentPresentationStatus = Literal["pending", "ready", "failed", "dismissed"]
AgentPresentationPriority = Literal["low", "normal", "high"]
AgentPresentationView = Literal[
    "html_preview",
    "source_text",
    "markdown",
    "json",
    "image",
    "pdf",
    "diff",
    "approval_review",
    "activity_detail",
    "download",
    "open_external",
    "none",
]
AgentPresentationSurface = Literal[
    "conversation",
    "side_panel",
    "approval_panel",
    "activity",
    "header",
]
AgentPresentationEffectKind = Literal[
    "open_panel",
    "focus_presentation",
    "scroll_to",
    "highlight",
    "none",
]
AgentPresentationEffectMode = Literal["soft", "assertive"]
AgentPresentationActionKind = Literal[
    "open_view",
    "download",
    "approve",
    "reject",
    "retry",
    "continue",
    "open_in_workbench",
    "open_external",
    "copy_reference",
    "none",
]
AgentPresentationCreatedBy = Literal["harness", "tool", "model_request"]


class AgentPresentationResource(AithruBaseModel):
    kind: AgentPresentationResourceKind
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
    def _resource_has_required_reference(self) -> "AgentPresentationResource":
        if self.kind == "artifact" and self.id is None:
            raise ValueError("artifact presentation resources require id")
        if self.kind == "workspace_file" and self.path is None:
            raise ValueError("workspace file presentation resources require path")
        if self.kind in {"approval", "todo", "run", "trace_span"} and self.id is None:
            raise ValueError(f"{self.kind} presentation resources require id")
        if self.kind == "external_url" and self.url is None:
            raise ValueError("external url presentation resources require url")
        return self


class AgentPresentationEffect(AithruBaseModel):
    kind: AgentPresentationEffectKind
    panel: str | None = None
    surface: AgentPresentationSurface | None = None
    presentation_id: str | None = None
    mode: AgentPresentationEffectMode = "soft"

    @model_validator(mode="after")
    def _effect_has_required_target(self) -> "AgentPresentationEffect":
        if self.kind == "open_panel" and self.panel is None:
            raise ValueError("open_panel presentation effects require panel")
        if self.kind in {"focus_presentation", "scroll_to", "highlight"} and self.presentation_id is None:
            raise ValueError(f"{self.kind} presentation effects require presentation_id")
        return self


class AgentPresentationAction(AithruBaseModel):
    kind: AgentPresentationActionKind
    label: str
    view: AgentPresentationView | None = None
    path: str | None = None
    method: Literal["GET", "POST"] | None = None
    requires_confirmation: bool = False


class AgentPresentationSource(AithruBaseModel):
    created_by: AgentPresentationCreatedBy
    event_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class AgentPresentation(AithruBaseModel):
    id: str = Field(min_length=1)
    org_id: str | None = None
    thread_id: str | None = None
    run_id: str = Field(min_length=1)
    sequence: int | None = Field(default=None, ge=0)
    status: AgentPresentationStatus = "ready"
    priority: AgentPresentationPriority = "normal"
    title: str = Field(min_length=1)
    summary: str | None = None
    reason: str | None = None
    resource: AgentPresentationResource = Field(default_factory=lambda: AgentPresentationResource(kind="none"))
    surfaces: list[AgentPresentationSurface] = Field(default_factory=lambda: ["conversation"], min_length=1)
    preferred_view: AgentPresentationView = "none"
    available_views: list[AgentPresentationView] = Field(default_factory=lambda: ["none"], min_length=1)
    effects: list[AgentPresentationEffect] = Field(default_factory=list)
    actions: list[AgentPresentationAction] = Field(default_factory=list)
    source: AgentPresentationSource
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("presentation title cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _preferred_view_must_be_available(self) -> "AgentPresentation":
        if self.preferred_view not in self.available_views:
            raise ValueError("preferred view must be in available views")
        return self
```

- [ ] **Step 4: Update domain exports**

In `backend/src/aithru_agent/domain/__init__.py`, remove all `AgentDisplayCard*` imports and `__all__` entries. Add imports and `__all__` entries for every `AgentPresentation*` symbol defined above.

Use this import block pattern near the existing display import:

```python
from .display import (
    AgentPresentation,
    AgentPresentationAction,
    AgentPresentationActionKind,
    AgentPresentationCreatedBy,
    AgentPresentationEffect,
    AgentPresentationEffectKind,
    AgentPresentationEffectMode,
    AgentPresentationPriority,
    AgentPresentationResource,
    AgentPresentationResourceKind,
    AgentPresentationSource,
    AgentPresentationStatus,
    AgentPresentationSurface,
    AgentPresentationView,
)
```

Add the same names as strings in `__all__`.

- [ ] **Step 5: Run focused domain tests**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_presentations.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/domain/display.py backend/src/aithru_agent/domain/__init__.py backend/tests/unit/domain/test_presentations.py
git rm backend/tests/unit/domain/test_display_cards.py
git commit -m "feat: add agent presentation domain model"
```

---

### Task 2: Add Presentation Stream Projection And View Resolution

**Files:**
- Create: `backend/src/aithru_agent/stream/presentations.py`
- Delete: `backend/src/aithru_agent/stream/display_cards.py`
- Test: `backend/tests/unit/stream/test_presentations_stream.py`

**Interfaces:**
- Consumes: `AgentRun`, `AgentArtifact`, `AgentStreamEvent`, `AgentPresentation`.
- Produces:
  - `presentations_for_tool_result(run, tool_call_id, tool_name, output, created_by="harness") -> list[AgentPresentation]`
  - `presentations_from_events(events) -> list[AgentPresentation]`
  - `presentation_event_payload(presentation) -> dict`
  - `available_views_for_file(name=None, media_type=None, artifact_type=None) -> list[AgentPresentationView]`
  - `preferred_view_for_file(...) -> AgentPresentationView`

- [ ] **Step 1: Write stream projection tests**

Create `backend/tests/unit/stream/test_presentations_stream.py`:

```python
from aithru_agent.domain import AgentRun
from aithru_agent.stream.events import AgentStreamEvent, AgentStreamSource
from aithru_agent.stream.presentations import (
    available_views_for_file,
    presentation_event_payload,
    presentations_for_tool_result,
    presentations_from_events,
)


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
        started_at="2026-06-29T00:00:00Z",
    )


def event(sequence: int, payload: dict, *, type: str = "presentation.created") -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        thread_id="thread_1",
        sequence=sequence,
        timestamp="2026-06-29T00:00:00Z",
        type=type,
        source=AgentStreamSource(kind="harness"),
        payload=payload,
    )


def test_html_name_resolves_html_preview_even_without_media_type() -> None:
    assert available_views_for_file(name="index.html", media_type=None, artifact_type="file") == [
        "html_preview",
        "source_text",
        "download",
    ]


def test_workspace_write_file_result_projects_file_presentation() -> None:
    presentations = presentations_for_tool_result(
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

    assert len(presentations) == 1
    presentation = presentations[0]
    assert presentation.resource.kind == "workspace_file"
    assert presentation.resource.path == "/a.txt"
    assert presentation.title == "a.txt"
    assert presentation.preferred_view == "source_text"
    assert presentation.available_views == ["source_text", "download"]
    assert presentation.source.tool_name == "workspace.write_file"


def test_artifact_result_projects_html_presentation_from_name() -> None:
    presentations = presentations_for_tool_result(
        run(),
        tool_call_id="tool_2",
        tool_name="artifact.create",
        output={
            "id": "artifact_1",
            "name": "index.html",
            "type": "file",
            "media_type": None,
        },
    )

    assert len(presentations) == 1
    presentation = presentations[0]
    assert presentation.resource.kind == "artifact"
    assert presentation.resource.id == "artifact_1"
    assert presentation.preferred_view == "html_preview"
    assert "source_text" in presentation.available_views
    assert presentation.effects[0].kind == "open_panel"


def test_presentations_from_events_fills_sequence_and_preserves_created_sequence_on_update() -> None:
    created = presentations_for_tool_result(
        run(),
        tool_call_id="tool_1",
        tool_name="workspace.write_file",
        output={"path": "/a.txt", "media_type": "text/plain"},
    )[0]
    updated = created.model_copy(update={"status": "failed"})

    presentations = presentations_from_events(
        [
            event(7, presentation_event_payload(created)),
            event(11, presentation_event_payload(updated), type="presentation.updated"),
        ]
    )

    assert len(presentations) == 1
    assert presentations[0].sequence == 7
    assert presentations[0].status == "failed"
```

- [ ] **Step 2: Run the focused stream test and verify it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/stream/test_presentations_stream.py -q
```

Expected: fail importing `aithru_agent.stream.presentations`.

- [ ] **Step 3: Implement `stream/presentations.py`**

Create `backend/src/aithru_agent/stream/presentations.py` with focused helpers:

```python
from hashlib import sha1
from pathlib import PurePosixPath
from typing import Literal

from aithru_agent.domain import (
    AgentPresentation,
    AgentPresentationAction,
    AgentPresentationCreatedBy,
    AgentPresentationEffect,
    AgentPresentationResource,
    AgentPresentationSource,
    AgentPresentationView,
    AgentRun,
)
from aithru_agent.stream.events import AgentStreamEvent


PresentationCreator = AgentPresentationCreatedBy

WORKSPACE_FILE_PRESENTATION_TOOL_NAMES = {
    "workspace.write_file",
    "workspace.patch_file",
    "sandbox.write_file",
    "sandbox.patch_file",
}

ARTIFACT_PRESENTATION_TOOL_NAMES = {
    "artifact.create",
    "research.create_report",
    "sandbox.promote_file",
}


def presentations_for_tool_result(
    run: AgentRun,
    *,
    tool_call_id: str,
    tool_name: str,
    output: object,
    created_by: PresentationCreator = "harness",
) -> list[AgentPresentation]:
    if not isinstance(output, dict):
        return []
    if tool_name in WORKSPACE_FILE_PRESENTATION_TOOL_NAMES:
        path = _string_value(output.get("path"))
        if path is None:
            return []
        name = _basename(path)
        media_type = _string_value(output.get("media_type"))
        views = available_views_for_file(name=name, media_type=media_type)
        return [
            _resource_presentation(
                run,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                created_by=created_by,
                title=name,
                summary=path,
                reason="A workspace file was created or updated.",
                resource=AgentPresentationResource(kind="workspace_file", path=path),
                available_views=views,
                preferred_view=preferred_view_for_file(name=name, media_type=media_type),
                metadata={
                    "workspace_id": _string_value(output.get("workspace_id")) or run.workspace_id,
                    "media_type": media_type,
                    "size": output.get("size") if isinstance(output.get("size"), int) else None,
                },
            )
        ]
    if tool_name in ARTIFACT_PRESENTATION_TOOL_NAMES:
        artifact = output.get("artifact") if tool_name in {"research.create_report", "sandbox.promote_file"} else output
        if not isinstance(artifact, dict):
            return []
        artifact_id = _string_value(artifact.get("id"))
        name = _string_value(artifact.get("name"))
        if artifact_id is None or name is None:
            return []
        media_type = _string_value(artifact.get("media_type"))
        artifact_type = _string_value(artifact.get("type"))
        views = available_views_for_file(name=name, media_type=media_type, artifact_type=artifact_type)
        return [
            _resource_presentation(
                run,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                created_by=created_by,
                title=name,
                summary=_string_value(artifact.get("uri")),
                reason="An artifact was created for the user.",
                resource=AgentPresentationResource(kind="artifact", id=artifact_id),
                available_views=views,
                preferred_view=preferred_view_for_file(
                    name=name,
                    media_type=media_type,
                    artifact_type=artifact_type,
                ),
                metadata={
                    "type": artifact_type,
                    "media_type": media_type,
                    "uri": _string_value(artifact.get("uri")),
                },
            )
        ]
    if tool_name == "presentation.present":
        raw_presentations = output.get("presentations")
        if not isinstance(raw_presentations, list):
            return []
        return [
            AgentPresentation.model_validate(item)
            for item in raw_presentations
            if isinstance(item, dict)
        ]
    return []


def presentations_from_events(events: list[AgentStreamEvent]) -> list[AgentPresentation]:
    presentations_by_id: dict[str, AgentPresentation] = {}
    for event in events:
        if event.type not in {"presentation.created", "presentation.updated"}:
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        raw = payload.get("presentation")
        if not isinstance(raw, dict):
            continue
        presentation = AgentPresentation.model_validate(raw).model_copy(
            update={
                "sequence": event.sequence,
                "thread_id": raw.get("thread_id") or event.thread_id,
                "run_id": raw.get("run_id") or event.run_id,
            }
        )
        existing = presentations_by_id.get(presentation.id)
        if existing is not None and event.type == "presentation.updated":
            presentation = presentation.model_copy(update={"sequence": existing.sequence})
        presentations_by_id[presentation.id] = presentation
    return sorted(presentations_by_id.values(), key=lambda item: item.sequence or 0)


def presentation_event_payload(presentation: AgentPresentation) -> dict:
    return {"presentation": presentation.model_dump(mode="json", exclude_none=True)}


def available_views_for_file(
    *,
    name: str | None = None,
    media_type: str | None = None,
    artifact_type: str | None = None,
) -> list[AgentPresentationView]:
    normalized = (media_type or "").split(";", 1)[0].strip().lower()
    ext = _extension(name)
    if normalized in {"text/html", "application/xhtml+xml"} or ext in {"html", "htm"}:
        return ["html_preview", "source_text", "download"]
    if artifact_type in {"markdown", "report"} or normalized in {"text/markdown", "text/x-markdown"} or ext in {"md", "markdown"}:
        return ["markdown", "source_text", "download"]
    if artifact_type == "json" or normalized == "application/json" or ext == "json":
        return ["json", "source_text", "download"]
    if normalized.startswith("image/") or ext in {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico"}:
        return ["image", "download"]
    if normalized == "application/pdf" or ext == "pdf":
        return ["pdf", "download"]
    if normalized.startswith("text/") or artifact_type in {"text", "decision"} or ext in {"txt", "log", "csv", "css", "js", "ts", "tsx", "py", "yaml", "yml", "toml", "sh", "sql"}:
        return ["source_text", "download"]
    return ["download"]


def preferred_view_for_file(
    *,
    name: str | None = None,
    media_type: str | None = None,
    artifact_type: str | None = None,
) -> AgentPresentationView:
    return available_views_for_file(
        name=name,
        media_type=media_type,
        artifact_type=artifact_type,
    )[0]


def _resource_presentation(
    run: AgentRun,
    *,
    tool_call_id: str,
    tool_name: str,
    created_by: PresentationCreator,
    title: str,
    summary: str | None,
    reason: str,
    resource: AgentPresentationResource,
    available_views: list[AgentPresentationView],
    preferred_view: AgentPresentationView,
    metadata: dict,
) -> AgentPresentation:
    actions = [
        AgentPresentationAction(kind="open_view", label=_view_label(view), view=view)
        for view in available_views
        if view not in {"download"}
    ]
    if "download" in available_views:
        actions.append(AgentPresentationAction(kind="download", label="Download"))
    effects = []
    if preferred_view in {"html_preview", "markdown", "json", "image", "pdf", "source_text"}:
        effects.append(AgentPresentationEffect(kind="open_panel", panel="preview", mode="soft"))
    return AgentPresentation(
        id=_stable_presentation_id(run.id, tool_call_id, resource.kind, resource.id or resource.path or title),
        org_id=run.org_id,
        thread_id=run.thread_id,
        run_id=run.id,
        status="ready",
        priority="normal",
        title=title,
        summary=summary,
        reason=reason,
        resource=resource,
        surfaces=["conversation", "side_panel"] if effects else ["conversation"],
        preferred_view=preferred_view,
        available_views=available_views,
        effects=effects,
        actions=actions,
        source=AgentPresentationSource(
            created_by=created_by,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        ),
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _stable_presentation_id(run_id: str, tool_call_id: str, kind: str, value: str) -> str:
    digest = sha1(f"{run_id}:{tool_call_id}:{kind}:{value}".encode("utf-8")).hexdigest()[:12]
    return f"presentation_{digest}"


def _view_label(view: AgentPresentationView) -> str:
    return {
        "html_preview": "Preview",
        "source_text": "Source",
        "markdown": "Preview",
        "json": "JSON",
        "image": "Preview",
        "pdf": "Preview",
        "diff": "Diff",
        "approval_review": "Review",
        "activity_detail": "Details",
        "open_external": "Open",
        "none": "Open",
        "download": "Download",
    }[view]


def _extension(name: str | None) -> str | None:
    if not name:
        return None
    suffix = PurePosixPath(name).suffix.lower()
    return suffix[1:] if suffix.startswith(".") else None


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or stripped or "file"


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
```

- [ ] **Step 4: Delete the old display card stream helper**

```bash
git rm backend/src/aithru_agent/stream/display_cards.py
```

- [ ] **Step 5: Run focused stream tests**

Run:

```bash
cd backend
uv run pytest tests/unit/stream/test_presentations_stream.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/stream/presentations.py backend/tests/unit/stream/test_presentations_stream.py
git rm backend/tests/unit/stream/test_display_cards_stream.py
git commit -m "feat: project stream presentations"
```

---

### Task 3: Replace `present_resources` With `presentation.present`

**Files:**
- Modify: `backend/src/aithru_agent/capabilities/local_tools/presentation.py`
- Modify: `backend/tests/unit/capabilities/test_local_tools.py`
- Modify: `backend/tests/integration/test_pydantic_tool_bridge.py`

**Interfaces:**
- Consumes: presentation domain models and `available_views_for_file`.
- Produces tool descriptor named `presentation.present`.
- Tool result shape:
  - `presentations: list[dict]`
  - `rejected_requests: list[dict]`

- [ ] **Step 1: Add failing local tool tests**

In `backend/tests/unit/capabilities/test_local_tools.py`, replace or add presentation tests:

```python
async def test_presentation_present_returns_validated_artifact_presentation() -> None:
    store = InMemoryAgentStore()
    artifact = await store.create_artifact(
        org_id="org_1",
        workspace_id="ws_1",
        run_id="run_1",
        type="file",
        name="index.html",
        content="<html></html>",
    )
    tool = PresentationLocalTool(store)
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="presentation.present",
            input={
                "resources": [{"kind": "artifact", "id": artifact.id}],
                "surfaces": ["conversation", "side_panel"],
                "preferred_view": "html_preview",
                "effects": [{"kind": "open_panel", "panel": "preview", "mode": "soft"}],
                "reason": "Show the generated webpage.",
            },
        ),
        AgentRunContext(
            org_id="org_1",
            actor_user_id="user_1",
            run_id="run_1",
            thread_id="thread_1",
            workspace_id="ws_1",
            scopes=["agent.workspace.read"],
        ),
    )

    assert result.status == "completed"
    presentation = result.output["presentations"][0]
    assert presentation["resource"] == {"kind": "artifact", "id": artifact.id}
    assert presentation["preferred_view"] == "html_preview"
    assert "source_text" in presentation["available_views"]
    assert result.output["rejected_requests"] == []


async def test_presentation_present_rejects_unavailable_requested_view() -> None:
    store = InMemoryAgentStore()
    await store.write_workspace_file(
        workspace_id="ws_1",
        path="/notes.txt",
        content="plain",
        media_type="text/plain",
    )
    tool = PresentationLocalTool(store)
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="presentation.present",
            input={
                "resources": [{"kind": "workspace_file", "path": "/notes.txt"}],
                "preferred_view": "html_preview",
            },
        ),
        AgentRunContext(
            org_id="org_1",
            actor_user_id="user_1",
            run_id="run_1",
            thread_id="thread_1",
            workspace_id="ws_1",
            scopes=["agent.workspace.read"],
        ),
    )

    assert result.status == "completed"
    assert result.output["presentations"][0]["preferred_view"] == "source_text"
    assert result.output["rejected_requests"] == [
        {
            "resource": {"kind": "workspace_file", "path": "/notes.txt"},
            "reason": "Requested view html_preview is unavailable; using source_text.",
        }
    ]
```

Adjust imports in the file to include `PresentationLocalTool`, `InMemoryAgentStore`, `AgentToolCallRequest`, and `AgentRunContext` if they are not already present.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
cd backend
uv run pytest tests/unit/capabilities/test_local_tools.py -q -k presentation
```

Expected: fail because the tool descriptor still uses `present_resources`.

- [ ] **Step 3: Rewrite `presentation.py` tool contract**

In `backend/src/aithru_agent/capabilities/local_tools/presentation.py`, replace `PresentResourcesRequest` with:

```python
class PresentResourceRef(AithruBaseModel):
    kind: Literal["workspace_file", "artifact"]
    path: str | None = None
    id: str | None = None


class PresentationEffectRequest(AithruBaseModel):
    kind: Literal["open_panel", "focus_presentation", "scroll_to", "highlight", "none"]
    panel: str | None = None
    surface: Literal["conversation", "side_panel", "approval_panel", "activity", "header"] | None = None
    mode: Literal["soft", "assertive"] = "soft"


class PresentationPresentRequest(AithruBaseModel):
    resources: list[PresentResourceRef] = Field(min_length=1)
    surfaces: list[Literal["conversation", "side_panel", "approval_panel", "activity", "header"]] = Field(
        default_factory=lambda: ["conversation"],
        min_length=1,
    )
    preferred_view: str | None = None
    effects: list[PresentationEffectRequest] = Field(default_factory=list)
    reason: str | None = None
```

Change the tool descriptor:

```python
AgentToolDescriptor(
    name="presentation.present",
    kind=AgentToolKind.LOCAL_TOOL,
    description=(
        "Request that existing workspace files or artifacts be presented to the user. "
        "The harness validates resources, views, surfaces, actions, and effects; "
        "the tool does not accept custom UI schemas."
    ),
    input_schema=PresentationPresentRequest.model_json_schema(),
    output_schema={"type": "object"},
    risk_level=AgentToolRiskLevel.READ,
    required_scopes=["agent.workspace.read"],
    approval_policy="never",
)
```

Use helper functions:

```python
def _coerce_preferred_view(requested: str | None, available: list[str]) -> tuple[str, dict | None]:
    if requested is None or requested in available:
        return requested or available[0], None
    return available[0], {
        "reason": f"Requested view {requested} is unavailable; using {available[0]}.",
    }
```

When building each presentation, set `source.created_by="model_request"` and `source.tool_name="presentation.present"`. Return:

```python
{
    "presentations": [presentation.model_dump(mode="json", exclude_none=True) for presentation in presentations],
    "rejected_requests": rejected_requests,
}
```

- [ ] **Step 4: Remove support for old tool name**

Change the unsupported-tool branch to deny anything except `"presentation.present"`:

```python
if request.tool_name != "presentation.present":
    return AgentToolCallResult(
        status="denied",
        error={"message": f"Unsupported tool: {request.tool_name}"},
        redaction="none",
    )
```

Do not leave an alias for `present_resources`.

- [ ] **Step 5: Update bridge integration test names and assertions**

In `backend/tests/integration/test_pydantic_tool_bridge.py`, replace `present_resources` with `presentation.present`. The test that currently asserts display card events should assert presentation events:

```python
presentations = [event for event in events if event.type == "presentation.created"]
assert len(presentations) >= 1
assert presentations[-1].payload["presentation"]["source"]["created_by"] in {"harness", "model_request"}
```

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
cd backend
uv run pytest tests/unit/capabilities/test_local_tools.py -q -k presentation
uv run pytest tests/integration/test_pydantic_tool_bridge.py -q -k presentation
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/capabilities/local_tools/presentation.py backend/tests/unit/capabilities/test_local_tools.py backend/tests/integration/test_pydantic_tool_bridge.py
git commit -m "feat: add presentation present tool"
```

---

### Task 4: Emit `presentation.*` Events From The Tool Bridge

**Files:**
- Modify: `backend/src/aithru_agent/agent/tools/bridge.py`
- Modify: `backend/tests/integration/test_pydantic_tool_bridge.py`
- Modify: `backend/tests/integration/test_scripted_worker.py`

**Interfaces:**
- Consumes: `presentations_for_tool_result`, `presentation_event_payload`.
- Produces canonical stream events `presentation.created`.

- [ ] **Step 1: Update integration assertions**

In `backend/tests/integration/test_pydantic_tool_bridge.py`, change every `"display.card.created"` assertion to `"presentation.created"`. For ordering tests, use:

```python
event_types = [event.type for event in events]
tool_index = event_types.index("tool.completed")
presentation_index = event_types.index("presentation.created")
assert tool_index < presentation_index
```

In `backend/tests/integration/test_scripted_worker.py`, update expected event type lists to include `presentation.created` instead of `display.card.created`.

- [ ] **Step 2: Run focused integration tests and verify failure**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py tests/integration/test_scripted_worker.py -q -k "presentation or file_report or display"
```

Expected: fail because the bridge still emits `display.card.created`.

- [ ] **Step 3: Update imports and helper names in bridge**

In `backend/src/aithru_agent/agent/tools/bridge.py`, replace:

```python
from aithru_agent.stream.display_cards import (
    display_card_event_payload,
    display_cards_for_tool_result,
)
```

with:

```python
from aithru_agent.stream.presentations import (
    presentation_event_payload,
    presentations_for_tool_result,
)
```

Rename `_emit_display_card_events` to `_emit_presentation_events`.

- [ ] **Step 4: Emit presentation events**

Replace the helper body with:

```python
async def _emit_presentation_events(
    self,
    tool_call_id: str,
    tool_name: str,
    output: object,
) -> None:
    for presentation in presentations_for_tool_result(
        self._run,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        output=output,
    ):
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="presentation.created",
            source={"kind": "harness"},
            payload=presentation_event_payload(presentation),
        )
```

Update the call site after successful tool completion from:

```python
await self._emit_display_card_events(...)
```

to:

```python
await self._emit_presentation_events(...)
```

- [ ] **Step 5: Run focused integration tests**

Run:

```bash
cd backend
uv run pytest tests/integration/test_pydantic_tool_bridge.py tests/integration/test_scripted_worker.py -q -k "presentation or file_report or tool_bridge"
```

Expected: pass for updated tests.

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/agent/tools/bridge.py backend/tests/integration/test_pydantic_tool_bridge.py backend/tests/integration/test_scripted_worker.py
git commit -m "feat: emit presentation stream events"
```

---

### Task 5: Replace API Snapshot Fields And Generated Types

**Files:**
- Modify: `backend/src/aithru_agent/api/snapshots.py`
- Modify: `backend/src/aithru_agent/api/routes/threads.py`
- Modify: `backend/src/aithru_agent/api/routes/events.py`
- Modify: `backend/tests/integration/test_api.py`
- Modify: `frontend/src/lib/api/schema.d.ts`
- Modify: `frontend/src/lib/api/types.ts`

**Interfaces:**
- Produces `presentations: list[AgentPresentation]` in run snapshots and thread workbench projections.
- Removes `display_cards` from API payloads.

- [ ] **Step 1: Update API test**

In `backend/tests/integration/test_api.py`, replace `test_run_snapshot_includes_display_cards` with:

```python
async def test_run_snapshot_includes_presentations_not_display_cards() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (
            await client.post(
                "/api/runs",
                json={
                    "task_msg": "Write file",
                    "scopes": ["agent.workspace.write", "agent.workspace.read"],
                },
            )
        ).json()
        run_id = created["id"]
        await runtime.worker.drain()

        snapshot = (await client.get(f"/api/runs/{run_id}/snapshot")).json()

    assert "display_cards" not in snapshot
    assert snapshot["presentations"]
    assert snapshot["presentations"][0]["resource"]["kind"] in {"workspace_file", "artifact"}
    assert snapshot["presentations"][0]["sequence"] is not None
```

- [ ] **Step 2: Run focused API test and verify failure**

Run:

```bash
cd backend
uv run pytest tests/integration/test_api.py -q -k run_snapshot_includes_presentations
```

Expected: fail because snapshot still exposes `display_cards`.

- [ ] **Step 3: Update snapshot model**

In `backend/src/aithru_agent/api/snapshots.py`:

Replace imports:

```python
from aithru_agent.stream.display_cards import display_cards_from_events
```

with:

```python
from aithru_agent.stream.presentations import presentations_from_events
```

Replace `display_cards` field:

```python
presentations: list[AgentPresentation] = Field(default_factory=list)
```

and import `AgentPresentation` from `aithru_agent.domain`.

- [ ] **Step 4: Update snapshot builders**

In `backend/src/aithru_agent/api/routes/threads.py` and `backend/src/aithru_agent/api/routes/events.py`, replace:

```python
display_cards=display_cards_from_events(events),
```

with:

```python
presentations=presentations_from_events(events),
```

Also update imports from `display_cards_from_events` to `presentations_from_events`.

- [ ] **Step 5: Regenerate OpenAPI types**

Start or reuse the backend app only long enough to fetch OpenAPI. If no server is running, use this local command:

```bash
cd backend
uv run python - <<'PY'
import json
from aithru_agent.api.app import create_app

app = create_app()
with open("/tmp/aithru_openapi.json", "w", encoding="utf-8") as f:
    json.dump(app.openapi(), f)
PY
cd ../frontend
npm run gen:types
```

Expected: `frontend/src/lib/api/schema.d.ts` contains `AgentPresentation` schemas and no `AgentDisplayCard` schemas.

If `create_app()` requires runtime arguments in this repo state, use the existing local dev server OpenAPI endpoint instead:

```bash
curl -sS http://localhost:15173/openapi.json > /tmp/aithru_openapi.json
cd frontend
npm run gen:types
```

- [ ] **Step 6: Update frontend API type exports**

In `frontend/src/lib/api/types.ts`, replace:

```ts
export type AgentDisplayCard = S["AgentDisplayCard"];
export type AgentDisplayCardAction = S["AgentDisplayCardAction"];
export type AgentDisplayCardResource = S["AgentDisplayCardResource"];
export type AgentDisplayCardSource = S["AgentDisplayCardSource"];
```

with:

```ts
export type AgentPresentation = S["AgentPresentation"];
export type AgentPresentationAction = S["AgentPresentationAction"];
export type AgentPresentationEffect = S["AgentPresentationEffect"];
export type AgentPresentationResource = S["AgentPresentationResource"];
export type AgentPresentationSource = S["AgentPresentationSource"];
```

- [ ] **Step 7: Run focused API and type checks**

Run:

```bash
cd backend
uv run pytest tests/integration/test_api.py -q -k run_snapshot_includes_presentations
cd ../frontend
npm run typecheck
```

Expected: backend focused test passes; frontend typecheck may still fail on `displayCards` until frontend tasks are complete. If it fails only for frontend Display Card references, continue to Task 6.

- [ ] **Step 8: Commit**

```bash
git add backend/src/aithru_agent/api/snapshots.py backend/src/aithru_agent/api/routes/threads.py backend/src/aithru_agent/api/routes/events.py backend/tests/integration/test_api.py frontend/src/lib/api/schema.d.ts frontend/src/lib/api/types.ts
git commit -m "feat: expose presentations in run snapshots"
```

---

### Task 6: Add Prompt Presentation Ledger

**Files:**
- Modify: `backend/src/aithru_agent/domain/context.py`
- Modify: `backend/src/aithru_agent/harness/context_packet.py`
- Modify: `backend/src/aithru_agent/agent/instructions.py`
- Test: `backend/tests/unit/harness/test_context_packet_builder.py`
- Test: `backend/tests/unit/agent/test_instructions.py`

**Interfaces:**
- Produces `AgentRunContextPresentation`.
- Adds `presentations` to `AgentRunContextPacket`.
- Renders "Presented to user" in prompt context.

- [ ] **Step 1: Add failing context and instruction tests**

In `backend/tests/unit/agent/test_instructions.py`, add:

```python
async def test_instructions_include_presented_to_user_ledger() -> None:
    store = InMemoryAgentStore()
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="show output",
        scopes=["agent.workspace.read"],
    )
    await store.append_event(
        run_id=run.id,
        thread_id=run.thread_id,
        type="presentation.created",
        source={"kind": "harness"},
        payload={
            "presentation": {
                "id": "presentation_1",
                "org_id": "org_1",
                "thread_id": run.thread_id,
                "run_id": run.id,
                "title": "index.html",
                "resource": {"kind": "artifact", "id": "artifact_1"},
                "surfaces": ["conversation", "side_panel"],
                "preferred_view": "html_preview",
                "available_views": ["html_preview", "source_text", "download"],
                "source": {"created_by": "harness"},
            }
        },
    )
    context_packet = await ContextPacketBuilder().build(run=run, store=store)
    deps = PydanticAgentDeps(
        store=store,
        run=run,
        run_context=AgentRunContext(
            org_id=run.org_id,
            actor_user_id=run.actor_user_id,
            run_id=run.id,
            thread_id=run.thread_id,
            workspace_id=run.workspace_id,
            scopes=run.scopes,
        ),
        context_packet=context_packet,
    )

    prompt = await InstructionBuilder("Base").build(deps)

    assert "Presented to user:" in prompt
    assert "presentation_1: index.html" in prompt
    assert "resource=artifact artifact_1" in prompt
    assert "preferred_view=html_preview" in prompt
```

Adjust constructor details to match existing test helpers in `test_instructions.py`; reuse local fixtures where available.

- [ ] **Step 2: Run focused instruction test and verify failure**

Run:

```bash
cd backend
uv run pytest tests/unit/agent/test_instructions.py -q -k presented_to_user
```

Expected: fail because context packet has no presentation ledger.

- [ ] **Step 3: Add context model**

In `backend/src/aithru_agent/domain/context.py`, add:

```python
class AgentRunContextPresentation(AithruBaseModel):
    id: str
    title: str
    status: str
    resource_kind: str
    resource_id: str | None = None
    resource_path: str | None = None
    surfaces: list[str] = Field(default_factory=list)
    preferred_view: str
    available_views: list[str] = Field(default_factory=list)
    source_sequence: int = Field(ge=0)
```

Add `presentations: list[AgentRunContextPresentation] = Field(default_factory=list)` to `AgentRunContextPacket`.

- [ ] **Step 4: Build presentation contexts from events**

In `backend/src/aithru_agent/harness/context_packet.py`, import:

```python
from aithru_agent.stream.presentations import presentations_from_events
```

After loading run events, build:

```python
presentations = [
    AgentRunContextPresentation(
        id=presentation.id,
        title=presentation.title,
        status=presentation.status,
        resource_kind=presentation.resource.kind,
        resource_id=presentation.resource.id,
        resource_path=presentation.resource.path,
        surfaces=list(presentation.surfaces),
        preferred_view=presentation.preferred_view,
        available_views=list(presentation.available_views),
        source_sequence=presentation.sequence or 0,
    )
    for presentation in presentations_from_events(events)[-10:]
]
```

Pass `presentations=presentations` into `AgentRunContextPacket`.

- [ ] **Step 5: Render prompt ledger**

In `backend/src/aithru_agent/agent/instructions.py`, inside `_render_context_packet`, add:

```python
if packet.presentations:
    lines.append("Presented to user:")
    lines.extend(
        "- "
        f"{presentation.id}: {presentation.title} "
        f"(status={presentation.status}, "
        f"resource={presentation.resource_kind}"
        f"{_resource_reference_suffix(presentation.resource_id, presentation.resource_path)}, "
        f"surfaces={','.join(presentation.surfaces)}, "
        f"preferred_view={presentation.preferred_view}, "
        f"available_views={','.join(presentation.available_views)})"
        for presentation in packet.presentations
    )
```

Add helper:

```python
def _resource_reference_suffix(resource_id: str | None, resource_path: str | None) -> str:
    if resource_id:
        return f" {resource_id}"
    if resource_path:
        return f" {resource_path}"
    return ""
```

- [ ] **Step 6: Run focused context and instruction tests**

Run:

```bash
cd backend
uv run pytest tests/unit/harness/test_context_packet_builder.py tests/unit/agent/test_instructions.py -q -k "presentation or presented_to_user"
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/domain/context.py backend/src/aithru_agent/harness/context_packet.py backend/src/aithru_agent/agent/instructions.py backend/tests/unit/harness/test_context_packet_builder.py backend/tests/unit/agent/test_instructions.py
git commit -m "feat: add presentation ledger to model context"
```

---

### Task 7: Replace Frontend Stream State And Timeline

**Files:**
- Modify: `frontend/src/features/chat/useRunStream.ts`
- Modify: `frontend/src/features/chat/chatTimeline.ts`
- Modify: `frontend/tests/use-run-stream.test.mjs`
- Modify: `frontend/tests/chat-timeline.test.mjs`

**Interfaces:**
- Replaces:
  - `DisplayCardEntry`
  - `displayCards`
  - event handling for `display.card.created` and `display.card.updated`
  - timeline `kind: "card"`
- Produces:
  - `PresentationEntry`
  - `presentations`
  - event handling for `presentation.created` and `presentation.updated`
  - timeline `kind: "presentation"`

- [ ] **Step 1: Update stream tests**

In `frontend/tests/use-run-stream.test.mjs`, replace display card tests with:

```js
test("projectRunEvent handles presentation create and update", async () => {
  const { projectRunEvent, initialRunStreamState } = await loadUseRunStream();
  const created = projectRunEvent(initialRunStreamState, {
    id: "evt_1",
    type: "presentation.created",
    sequence: 10,
    timestamp: "2026-06-29T00:00:00Z",
    payload: {
      presentation: {
        id: "presentation_1",
        run_id: "run_1",
        title: "index.html",
        status: "ready",
        priority: "normal",
        resource: { kind: "artifact", id: "artifact_1" },
        surfaces: ["conversation", "side_panel"],
        preferred_view: "html_preview",
        available_views: ["html_preview", "source_text", "download"],
        effects: [{ kind: "open_panel", panel: "preview", mode: "soft" }],
        actions: [{ kind: "download", label: "Download" }],
        source: { created_by: "harness" },
      },
    },
  });

  assert.equal(created.presentations.length, 1);
  assert.equal(created.presentations[0].preferredView, "html_preview");

  const updated = projectRunEvent(created, {
    id: "evt_2",
    type: "presentation.updated",
    sequence: 12,
    timestamp: "2026-06-29T00:00:01Z",
    payload: {
      presentation: {
        id: "presentation_1",
        status: "failed",
        title: "index.html",
        resource: { kind: "artifact", id: "artifact_1" },
        surfaces: ["conversation"],
        preferred_view: "source_text",
        available_views: ["source_text", "download"],
        source: { created_by: "harness" },
      },
    },
  });

  assert.equal(updated.presentations.length, 1);
  assert.equal(updated.presentations[0].sequence, 10);
  assert.equal(updated.presentations[0].lastSequence, 12);
  assert.equal(updated.presentations[0].status, "failed");
});
```

- [ ] **Step 2: Update timeline tests**

In `frontend/tests/chat-timeline.test.mjs`, replace any state fixture field `displayCards` with `presentations`, and replace expected item kind `"card"` with `"presentation"`.

Use a fixture shape:

```js
presentations: [
  {
    id: "presentation_1",
    title: "index.html",
    status: "ready",
    priority: "normal",
    resource: { kind: "artifact", id: "artifact_1" },
    surfaces: ["conversation", "side_panel"],
    preferredView: "html_preview",
    availableViews: ["html_preview", "source_text", "download"],
    sequence: 8,
  },
],
```

- [ ] **Step 3: Run frontend focused tests and verify failure**

Run:

```bash
cd frontend
node --test tests/use-run-stream.test.mjs tests/chat-timeline.test.mjs
```

Expected: fail because frontend still uses `displayCards`.

- [ ] **Step 4: Replace stream state types**

In `frontend/src/features/chat/useRunStream.ts`, replace `DisplayCardEntry` with:

```ts
export interface PresentationEntry {
  id: string;
  status: "pending" | "ready" | "failed" | "dismissed";
  priority: "low" | "normal" | "high";
  title: string;
  summary?: string;
  reason?: string;
  resource: {
    kind: "artifact" | "workspace_file" | "approval" | "todo" | "run" | "trace_span" | "external_url" | "none";
    id?: string;
    path?: string;
    url?: string;
  };
  surfaces: Array<"conversation" | "side_panel" | "approval_panel" | "activity" | "header">;
  preferredView: "html_preview" | "source_text" | "markdown" | "json" | "image" | "pdf" | "diff" | "approval_review" | "activity_detail" | "download" | "open_external" | "none";
  availableViews: PresentationEntry["preferredView"][];
  effects?: Array<{
    kind: "open_panel" | "focus_presentation" | "scroll_to" | "highlight" | "none";
    panel?: string;
    surface?: PresentationEntry["surfaces"][number];
    presentationId?: string;
    mode?: "soft" | "assertive";
  }>;
  actions?: Array<{
    kind: "open_view" | "download" | "approve" | "reject" | "retry" | "continue" | "open_in_workbench" | "open_external" | "copy_reference" | "none";
    label?: string;
    view?: PresentationEntry["preferredView"];
    path?: string;
    method?: "GET" | "POST";
    requiresConfirmation?: boolean;
  }>;
  sequence?: number;
  lastSequence?: number;
  createdAt?: string;
  updatedAt?: string;
}
```

Change `RunStreamState` field from `displayCards: DisplayCardEntry[]` to `presentations: PresentationEntry[]`.

Update `initialState` accordingly.

- [ ] **Step 5: Handle presentation events**

In `projectRunEvent`, replace the `display.card.*` case with:

```ts
case "presentation.created":
case "presentation.updated": {
  const rawPresentation = p.presentation;
  if (!rawPresentation || typeof rawPresentation !== "object") return state;
  const payload = rawPresentation as Record<string, unknown>;
  const id = (payload.id as string | undefined) ?? event.id;
  const existing = (state.presentations ?? []).find((item) => item.id === id);
  const patch: PresentationEntry = {
    id,
    status: (payload.status as PresentationEntry["status"] | undefined) ?? existing?.status ?? "ready",
    priority: (payload.priority as PresentationEntry["priority"] | undefined) ?? existing?.priority ?? "normal",
    title: (payload.title as string | undefined) ?? existing?.title ?? "Presentation",
    summary: (payload.summary as string | undefined) ?? existing?.summary,
    reason: (payload.reason as string | undefined) ?? existing?.reason,
    resource: (payload.resource as PresentationEntry["resource"] | undefined) ?? existing?.resource ?? { kind: "none" },
    surfaces: (payload.surfaces as PresentationEntry["surfaces"] | undefined) ?? existing?.surfaces ?? ["conversation"],
    preferredView: (payload.preferred_view as PresentationEntry["preferredView"] | undefined) ?? existing?.preferredView ?? "none",
    availableViews: (payload.available_views as PresentationEntry["availableViews"] | undefined) ?? existing?.availableViews ?? ["none"],
    effects: (payload.effects as PresentationEntry["effects"] | undefined) ?? existing?.effects,
    actions: (payload.actions as PresentationEntry["actions"] | undefined) ?? existing?.actions,
    sequence: existing?.sequence ?? sequenceOf(event),
    lastSequence: sequenceOf(event),
    createdAt: existing?.createdAt ?? event.timestamp,
    updatedAt: event.timestamp,
  };
  return {
    ...state,
    presentations: existing
      ? state.presentations.map((item) => (item.id === id ? { ...item, ...patch } : item))
      : [...state.presentations, patch],
  };
}
```

Add a small mapper if the codebase prefers not to cast snake_case directly.

- [ ] **Step 6: Update timeline code**

In `frontend/src/features/chat/chatTimeline.ts`:

Replace imports and item:

```ts
PresentationEntry,
```

```ts
| { kind: "presentation"; id: string; sequence: number; presentation: PresentationEntry }
```

Replace `displayCardsForConversation` with:

```ts
function presentationsForConversation(state: RunStreamState): PresentationEntry[] {
  return (state.presentations ?? []).filter((presentation) =>
    presentation.surfaces.includes("conversation"),
  );
}
```

When appending run items, map:

```ts
...presentations.map((presentation) => ({
  kind: "presentation" as const,
  id: `presentation:${presentation.id}`,
  sequence: presentation.sequence ?? presentation.lastSequence ?? FALLBACK_SEQUENCE,
  presentation,
})),
```

Set `KIND_ORDER.presentation = 2`.

- [ ] **Step 7: Run focused frontend tests**

Run:

```bash
cd frontend
node --test tests/use-run-stream.test.mjs tests/chat-timeline.test.mjs
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/chat/useRunStream.ts frontend/src/features/chat/chatTimeline.ts frontend/tests/use-run-stream.test.mjs frontend/tests/chat-timeline.test.mjs
git commit -m "feat: project presentations in chat stream"
```

---

### Task 8: Replace DisplayCard UI With PresentationItem UI

**Files:**
- Delete: `frontend/src/features/chat/DisplayCard.tsx`
- Create: `frontend/src/features/chat/PresentationItem.tsx`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`
- Replace test: `frontend/tests/display-card.test.mjs` -> `frontend/tests/presentation-item.test.mjs`

**Interfaces:**
- Consumes: `PresentationEntry`, `onPreviewFile(fileId)`.
- Produces trusted inline presentation renderer.

- [ ] **Step 1: Replace UI tests**

Delete `frontend/tests/display-card.test.mjs` and create `frontend/tests/presentation-item.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { build } from "esbuild";
import path from "node:path";
import { pathToFileURL } from "node:url";

async function loadPresentationItem() {
  const outfile = path.resolve(".tmp-tests/presentation-item.mjs");
  await build({
    entryPoints: ["src/features/chat/PresentationItem.tsx"],
    bundle: true,
    platform: "node",
    format: "esm",
    outfile,
    external: ["react", "react-dom/server"],
    alias: {
      "@/lib/utils": path.resolve("src/lib/utils.ts"),
    },
  });
  return import(pathToFileURL(outfile).href + `?t=${Date.now()}`);
}

test("PresentationItem renders only approved actions", async () => {
  const { PresentationItem } = await loadPresentationItem();
  const html = renderToStaticMarkup(
    React.createElement(PresentationItem, {
      presentation: {
        id: "presentation_1",
        title: "index.html",
        status: "ready",
        priority: "normal",
        resource: { kind: "artifact", id: "artifact_1" },
        surfaces: ["conversation", "side_panel"],
        preferredView: "html_preview",
        availableViews: ["html_preview", "source_text", "download"],
        actions: [
          { kind: "open_view", label: "Preview", view: "html_preview" },
          { kind: "download", label: "Download" },
        ],
      },
      onPreviewFile: () => {},
    }),
  );

  assert.match(html, /index\.html/);
  assert.match(html, /Preview/);
  assert.match(html, /Download/);
  assert.doesNotMatch(html, /DangerousComponent/);
});

test("PresentationItem hides preview when html_preview is not available", async () => {
  const { PresentationItem } = await loadPresentationItem();
  const html = renderToStaticMarkup(
    React.createElement(PresentationItem, {
      presentation: {
        id: "presentation_2",
        title: "notes.txt",
        status: "ready",
        priority: "normal",
        resource: { kind: "workspace_file", path: "/notes.txt" },
        surfaces: ["conversation"],
        preferredView: "source_text",
        availableViews: ["source_text", "download"],
        actions: [{ kind: "download", label: "Download" }],
      },
      onPreviewFile: () => {},
    }),
  );

  assert.doesNotMatch(html, /Preview/);
  assert.match(html, /Download/);
});
```

- [ ] **Step 2: Run focused UI test and verify failure**

Run:

```bash
cd frontend
node --test tests/presentation-item.test.mjs
```

Expected: fail because `PresentationItem.tsx` does not exist.

- [ ] **Step 3: Create PresentationItem**

Create `frontend/src/features/chat/PresentationItem.tsx`:

```tsx
import { Download, ExternalLink, FileText, Image, Package, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PresentationEntry } from "./useRunStream";

interface PresentationItemProps {
  presentation: PresentationEntry;
  onPreviewFile?: (fileId: string) => void;
}

export function PresentationItem({ presentation, onPreviewFile }: PresentationItemProps) {
  const previewAction = presentation.actions?.find(
    (action) => action.kind === "open_view" && action.view === presentation.preferredView,
  );
  const downloadAction = presentation.actions?.find((action) => action.kind === "download");
  const previewId = previewFileId(presentation);
  const canPreview = Boolean(previewAction && previewId && onPreviewFile);
  const downloadHref = downloadAction ? downloadUrl(presentation) : null;
  const Icon = iconForPresentation(presentation);

  return (
    <div className="py-2">
      <div className="rounded-lg border bg-card p-3 text-sm shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Icon className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-foreground">{presentation.title}</div>
            {(presentation.reason || presentation.summary) && (
              <div className="truncate text-xs text-muted-foreground">
                {presentation.reason || presentation.summary}
              </div>
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
              {actionLabel(previewAction, "Preview")}
            </button>
          )}
          {downloadHref && (
            <a
              href={downloadHref}
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Download className="h-3.5 w-3.5" />
              {actionLabel(downloadAction, "Download")}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function previewFileId(presentation: PresentationEntry): string | null {
  if (!presentation.availableViews.includes(presentation.preferredView)) return null;
  if (presentation.resource.kind === "workspace_file" && presentation.resource.path) {
    return `ws-${presentation.resource.path}`;
  }
  if (presentation.resource.kind === "artifact" && presentation.resource.id) {
    return `artifact-${presentation.resource.id}`;
  }
  return null;
}

function downloadUrl(presentation: PresentationEntry): string | null {
  if (presentation.resource.kind === "artifact" && presentation.resource.id) {
    return `/api/artifacts/${encodeURIComponent(presentation.resource.id)}/download`;
  }
  return null;
}

function actionLabel(action: NonNullable<PresentationEntry["actions"]>[number] | undefined, fallback: string): string {
  return action?.label?.trim() || fallback;
}

function iconForPresentation(presentation: PresentationEntry) {
  if (presentation.resource.kind === "artifact") return Package;
  if (presentation.resource.kind === "approval") return ShieldCheck;
  if (presentation.preferredView === "image") return Image;
  return FileText;
}
```

- [ ] **Step 4: Render presentations in ChatPanel**

In `frontend/src/features/chat/ChatPanel.tsx`, replace:

```tsx
import { DisplayCard } from "./DisplayCard";
```

with:

```tsx
import { PresentationItem } from "./PresentationItem";
```

Replace the timeline rendering branch:

```tsx
{item.kind === "card" && (
  <DisplayCard card={item.card} onPreviewFile={onPreviewFile} />
)}
```

with:

```tsx
{item.kind === "presentation" && (
  <PresentationItem presentation={item.presentation} onPreviewFile={onPreviewFile} />
)}
```

- [ ] **Step 5: Delete old component**

```bash
git rm frontend/src/features/chat/DisplayCard.tsx frontend/tests/display-card.test.mjs
```

- [ ] **Step 6: Run focused frontend tests**

Run:

```bash
cd frontend
node --test tests/presentation-item.test.mjs tests/chat-timeline.test.mjs
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/chat/PresentationItem.tsx frontend/src/features/chat/ChatPanel.tsx frontend/tests/presentation-item.test.mjs
git rm frontend/src/features/chat/DisplayCard.tsx frontend/tests/display-card.test.mjs
git commit -m "feat: render chat presentations"
```

---

### Task 9: Resolve Artifact Links From Presentations

**Files:**
- Modify: `frontend/src/features/chat/artifactLinks.ts`
- Modify: `frontend/tests/artifact-links.test.mjs`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`

**Interfaces:**
- Consumes: `RunStreamState.presentations`.
- Produces the same external behavior as the current artifact link resolver, but without `DisplayCardEntry`.

- [ ] **Step 1: Update tests to use presentations**

In `frontend/tests/artifact-links.test.mjs`, replace state fixtures:

```js
const state = {
  presentations: [
    {
      id: "presentation_1",
      title: "index.html",
      status: "ready",
      priority: "normal",
      resource: { kind: "artifact", id: "artifact_1" },
      surfaces: ["conversation"],
      preferredView: "html_preview",
      availableViews: ["html_preview", "source_text", "download"],
    },
  ],
};
```

Ensure assertions still expect:

```js
assert.equal(
  resolver("https://aithru.ai/artifact/org_1/artifact_1"),
  "/api/artifacts/artifact_1/content",
);
```

- [ ] **Step 2: Run focused test and verify failure**

Run:

```bash
cd frontend
node --test tests/artifact-links.test.mjs
```

Expected: fail because `artifactLinks.ts` imports `DisplayCardEntry`.

- [ ] **Step 3: Update artifactLinks implementation**

In `frontend/src/features/chat/artifactLinks.ts`, replace `DisplayCardEntry` with `PresentationEntry` and use:

```ts
function artifactIdFromPresentation(presentation: PresentationEntry): string | null {
  if (presentation.resource.kind !== "artifact") return null;
  return typeof presentation.resource.id === "string" && presentation.resource.id.trim()
    ? presentation.resource.id
    : null;
}
```

Replace loops over `state.displayCards` with:

```ts
for (const presentation of state.presentations ?? []) {
  const artifactId = artifactIdFromPresentation(presentation);
  if (artifactId) knownArtifactIds.add(artifactId);
}
```

- [ ] **Step 4: Ensure ChatPanel memo uses presentation states**

In `frontend/src/features/chat/ChatPanel.tsx`, keep the existing call shape but ensure `buildArtifactLinkResolver` receives states that now contain `presentations`. No call-site change is needed if it already passes `activeRunState` and `historicalRunStates`; type errors should guide any rename.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd frontend
node --test tests/artifact-links.test.mjs
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/chat/artifactLinks.ts frontend/tests/artifact-links.test.mjs frontend/src/features/chat/ChatPanel.tsx
git commit -m "feat: resolve artifact links from presentations"
```

---

### Task 10: Add Approved Side Panel Effects

**Files:**
- Modify: `frontend/src/features/chat/ChatPanel.tsx`
- Modify: `frontend/tests/chat-conversation-flow.test.mjs`

**Interfaces:**
- Consumes `PresentationEntry.effects`.
- Produces only whitelisted effect behavior:
  - `open_panel` with `panel: "preview"` opens the existing preview panel through `onPreviewFile`.

- [ ] **Step 1: Add frontend behavior test**

In `frontend/tests/chat-conversation-flow.test.mjs`, add a test around the projection helpers or rendered panel state:

```js
test("chat panel opens preview for approved presentation open_panel effect", async () => {
  const { presentationPreviewTarget } = await loadChatPanelHelpers();
  const target = presentationPreviewTarget({
    id: "presentation_1",
    title: "index.html",
    status: "ready",
    priority: "normal",
    resource: { kind: "artifact", id: "artifact_1" },
    surfaces: ["conversation", "side_panel"],
    preferredView: "html_preview",
    availableViews: ["html_preview", "source_text", "download"],
    effects: [{ kind: "open_panel", panel: "preview", mode: "soft" }],
  });

  assert.equal(target, "artifact-artifact_1");
});
```

If `ChatPanel` has no exported helper test seam, create and export a pure helper:

```ts
export function presentationPreviewTarget(presentation: PresentationEntry): string | null
```

- [ ] **Step 2: Run focused test and verify failure**

Run:

```bash
cd frontend
node --test tests/chat-conversation-flow.test.mjs
```

Expected: fail because helper/effect behavior does not exist.

- [ ] **Step 3: Add helper in ChatPanel**

In `frontend/src/features/chat/ChatPanel.tsx`, add:

```ts
export function presentationPreviewTarget(presentation: PresentationEntry): string | null {
  const openPreview = presentation.effects?.some(
    (effect) => effect.kind === "open_panel" && effect.panel === "preview",
  );
  if (!openPreview) return null;
  if (!presentation.availableViews.includes(presentation.preferredView)) return null;
  if (presentation.resource.kind === "artifact" && presentation.resource.id) {
    return `artifact-${presentation.resource.id}`;
  }
  if (presentation.resource.kind === "workspace_file" && presentation.resource.path) {
    return `ws-${presentation.resource.path}`;
  }
  return null;
}
```

Import `PresentationEntry` type from `./useRunStream`.

- [ ] **Step 4: Apply effect once per presentation**

In the chat panel component, keep a ref:

```ts
const appliedPresentationEffectsRef = React.useRef<Set<string>>(new Set());
```

Add an effect:

```tsx
React.useEffect(() => {
  for (const presentation of activeRunState.presentations ?? []) {
    if (appliedPresentationEffectsRef.current.has(presentation.id)) continue;
    const target = presentationPreviewTarget(presentation);
    if (!target) continue;
    appliedPresentationEffectsRef.current.add(presentation.id);
    onPreviewFile?.(target);
  }
}, [activeRunState.presentations, onPreviewFile]);
```

If historical runs should not auto-open panels, only use `activeRunState.presentations` in this effect.

- [ ] **Step 5: Run focused frontend test**

Run:

```bash
cd frontend
node --test tests/chat-conversation-flow.test.mjs
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/chat/ChatPanel.tsx frontend/tests/chat-conversation-flow.test.mjs
git commit -m "feat: apply approved presentation effects"
```

---

### Task 11: Remove Remaining Display Card References And Update Docs

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/03-stream-protocol.md`
- Modify or mark superseded: `docs/superpowers/plans/2026-06-25-conversation-display-cards.md`
- Modify any tests or docs found by `rg`.

**Interfaces:**
- Produces active docs that describe `presentation.created`, `presentation.updated`, and `presentations`.
- Leaves old Display Card text only in explicitly superseded historical documents if the team wants to keep those files.

- [ ] **Step 1: Run reference scan**

Run:

```bash
rg -n "AgentDisplayCard|DisplayCard|display_cards|displayCards|display\\.card|present_resources|Display Card" \
  backend/src frontend/src backend/tests frontend/tests README.md backend/README.md docs/03-stream-protocol.md docs/superpowers/plans docs/superpowers/specs
```

Expected before cleanup: matches in code, tests, generated types, and old docs.

- [ ] **Step 2: Update stream protocol docs**

In `docs/03-stream-protocol.md`, replace `display.card.created` / `display.card.updated` sections with:

```md
### Presentation Events

`presentation.created` and `presentation.updated` are backend-owned user-facing presentation events.

Payload:

```json
{
  "presentation": {
    "id": "presentation_123",
    "resource": {"kind": "artifact", "id": "artifact_3"},
    "surfaces": ["conversation", "side_panel"],
    "preferred_view": "html_preview",
    "available_views": ["html_preview", "source_text", "download"],
    "effects": [{"kind": "open_panel", "panel": "preview", "mode": "soft"}],
    "actions": [{"kind": "download", "label": "Download"}],
    "source": {"created_by": "harness"}
  }
}
```
```

- [ ] **Step 3: Update README references**

In `README.md` and `backend/README.md`, replace card language with presentation language:

```md
User-facing output presentation is modeled through `AgentPresentation` stream events. The backend validates resources, views, effects, and actions before emitting `presentation.created` or `presentation.updated`; frontend clients render those trusted events as conversation entries or side-panel previews.
```

- [ ] **Step 4: Mark old display card plan as superseded**

At the top of `docs/superpowers/plans/2026-06-25-conversation-display-cards.md`, add:

```md
Status: superseded

Superseded by:

- `docs/superpowers/plans/2026-06-29-agent-presentation-model.md`

This historical plan should not be used for implementation.
```

- [ ] **Step 5: Run reference scan again**

Run:

```bash
rg -n "AgentDisplayCard|DisplayCard|display_cards|displayCards|display\\.card|present_resources" \
  backend/src frontend/src backend/tests frontend/tests README.md backend/README.md docs/03-stream-protocol.md
```

Expected: no matches.

Then run:

```bash
rg -n "AgentDisplayCard|DisplayCard|display_cards|displayCards|display\\.card|present_resources" docs/superpowers
```

Expected: matches only in superseded docs/plans and the new plan's explicit deletion-scope references.

- [ ] **Step 6: Commit**

```bash
git add README.md backend/README.md docs/03-stream-protocol.md docs/superpowers/plans/2026-06-25-conversation-display-cards.md
git commit -m "docs: replace display card references"
```

---

### Task 12: Full Verification And Cleanup

**Files:**
- No planned source edits unless verification exposes missed references or test failures.

**Interfaces:**
- Confirms all backend, frontend, and docs changes work together.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
cd backend
uv run pytest \
  tests/unit/domain/test_presentations.py \
  tests/unit/stream/test_presentations_stream.py \
  tests/unit/capabilities/test_local_tools.py \
  tests/unit/harness/test_context_packet_builder.py \
  tests/unit/agent/test_instructions.py \
  tests/integration/test_pydantic_tool_bridge.py \
  tests/integration/test_scripted_worker.py \
  tests/integration/test_api.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Run full backend verification**

Run:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

Expected: all tests pass and example completes.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
cd frontend
node --test \
  tests/use-run-stream.test.mjs \
  tests/chat-timeline.test.mjs \
  tests/presentation-item.test.mjs \
  tests/artifact-links.test.mjs \
  tests/chat-conversation-flow.test.mjs
```

Expected: pass.

- [ ] **Step 4: Run full frontend verification**

Run:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

Expected: tests, typecheck, and build pass. Existing Vite chunk-size warnings are acceptable if unchanged.

- [ ] **Step 5: Run final deleted-symbol scan**

Run:

```bash
rg -n "AgentDisplayCard|DisplayCardEntry|DisplayCard|display_cards|displayCards|display\\.card|present_resources" \
  backend/src frontend/src backend/tests frontend/tests README.md backend/README.md docs/03-stream-protocol.md
```

Expected: no matches.

- [ ] **Step 6: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intentional files are changed. Do not revert unrelated user changes.

- [ ] **Step 7: Commit verification fixes if any**

If verification required follow-up edits:

```bash
git add <changed-files>
git commit -m "fix: finish presentation migration"
```

If no follow-up edits were needed, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: the plan covers domain models, stream events, presentation tool, automatic projection, API snapshots, frontend timeline/rendering, side-panel effects, prompt ledger, docs cleanup, and verification.
- Breaking replacement: tasks explicitly delete Display Card files, event handling, tests, and API fields.
- Model visibility: Task 6 adds the compact backend-confirmed presentation ledger.
- HTML/text choice: Task 2 resolves `.html` and `text/html` to `html_preview` plus `source_text`; Task 8 renders approved views; Task 10 opens the preview panel only from approved effects.
- Safety boundary: tool inputs remain resource/view/effect intent only, no component/CSS/schema control.
