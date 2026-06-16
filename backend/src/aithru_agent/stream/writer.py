from datetime import UTC, datetime
from typing import Any

from .events import AgentStreamEvent, AgentStreamRedaction, AgentStreamSource, AgentStreamVisibility
from .store import InMemoryAgentEventStore


class AgentEventWriter:
    def __init__(self, store: InMemoryAgentEventStore) -> None:
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
        event = AgentStreamEvent(
            id=f"{run_id}:{sequence}",
            run_id=run_id,
            thread_id=thread_id,
            sequence=sequence,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            type=type,
            source=source,
            visibility=visibility,
            redaction=redaction,
            summary=summary,
            payload=payload,
        )
        await self._store.append(event)
        return event

