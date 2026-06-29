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
