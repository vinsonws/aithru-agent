from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .events import AgentStreamEvent, AgentStreamRedaction, AgentStreamSource, AgentStreamVisibility
from .redaction import combine_redaction, redact_stream_payload

if TYPE_CHECKING:
    from aithru_agent.persistence.protocols import AgentEventStore


class AgentEventWriter:
    def __init__(self, store: "AgentEventStore") -> None:
        self._store = store

    async def write(
        self,
        *,
        run_id: str,
        type: str,
        source: AgentStreamSource | dict[str, str | None],
        payload: Any,
        thread_id: str | None = None,
        visibility: AgentStreamVisibility | str = AgentStreamVisibility.USER,
        redaction: AgentStreamRedaction | str = AgentStreamRedaction.NONE,
        summary: str | None = None,
    ) -> AgentStreamEvent:
        sequence = await self._store.next_sequence(run_id)
        safe_payload, detected_redaction = redact_stream_payload(payload)
        event = AgentStreamEvent(
            id=f"{run_id}:{sequence}",
            run_id=run_id,
            thread_id=thread_id,
            sequence=sequence,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            type=type,
            source=source,
            visibility=visibility,
            redaction=combine_redaction(redaction, detected_redaction),
            summary=summary,
            payload=safe_payload,
        )
        await self._store.append(event)
        return event
