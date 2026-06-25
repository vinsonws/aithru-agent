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

WORKSPACE_FILE_CARD_TOOL_NAMES = {
    "workspace.write_file",
    "workspace.patch_file",
    "sandbox.write_file",
    "sandbox.patch_file",
}

ARTIFACT_CARD_TOOL_NAMES = {
    "artifact.create",
    "research.create_report",
    "sandbox.promote_file",
}


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
    if tool_name in WORKSPACE_FILE_CARD_TOOL_NAMES:
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
    if tool_name in ARTIFACT_CARD_TOOL_NAMES:
        artifact = output.get("artifact") if tool_name in {"research.create_report", "sandbox.promote_file"} else output
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
        existing = cards_by_id.get(card.id)
        if existing is not None and event.type == "display.card.updated":
            card = card.model_copy(update={"sequence": existing.sequence})
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
