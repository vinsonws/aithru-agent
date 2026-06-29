from pathlib import PurePosixPath

from aithru_agent.domain import (
    AgentPresentation,
    AgentPresentationCreatedBy,
    AgentPresentationView,
    AgentRun,
)
from aithru_agent.stream.events import AgentStreamEvent


PresentationCreator = AgentPresentationCreatedBy

def presentations_for_tool_result(
    run: AgentRun,
    *,
    tool_call_id: str,
    tool_name: str,
    output: object,
    created_by: PresentationCreator = "harness",
) -> list[AgentPresentation]:
    del run, tool_call_id, created_by
    if tool_name != "presentation.present" or not isinstance(output, dict):
        return []
    raw_presentations = output.get("presentations")
    if not isinstance(raw_presentations, list):
        return []
    return [
        AgentPresentation.model_validate(item)
        for item in raw_presentations
        if isinstance(item, dict)
    ]


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
    file_type: str | None = None,
) -> list[AgentPresentationView]:
    normalized = (media_type or "").split(";", 1)[0].strip().lower()
    ext = _extension(name)
    if normalized in {"text/html", "application/xhtml+xml"} or ext in {"html", "htm"}:
        return ["html_preview", "source_text", "download"]
    if file_type in {"markdown", "report"} or normalized in {"text/markdown", "text/x-markdown"} or ext in {"md", "markdown"}:
        return ["markdown", "source_text", "download"]
    if file_type == "json" or normalized == "application/json" or ext == "json":
        return ["json", "source_text", "download"]
    if normalized.startswith("image/") or ext in {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico"}:
        return ["image", "download"]
    if normalized == "application/pdf" or ext == "pdf":
        return ["pdf", "download"]
    if normalized.startswith("text/") or file_type in {"text", "decision"} or ext in {"txt", "log", "csv", "css", "js", "ts", "tsx", "py", "yaml", "yml", "toml", "sh", "sql"}:
        return ["source_text", "download"]
    return ["download"]


def preferred_view_for_file(
    *,
    name: str | None = None,
    media_type: str | None = None,
    file_type: str | None = None,
) -> AgentPresentationView:
    return available_views_for_file(
        name=name,
        media_type=media_type,
        file_type=file_type,
    )[0]


def _extension(name: str | None) -> str | None:
    if not name:
        return None
    suffix = PurePosixPath(name).suffix.lower()
    return suffix[1:] if suffix.startswith(".") else None
