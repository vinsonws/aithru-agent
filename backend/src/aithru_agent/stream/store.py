from collections import defaultdict

from .events import AgentStreamEvent


class InMemoryAgentEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[AgentStreamEvent]] = defaultdict(list)

    async def append(self, event: AgentStreamEvent) -> None:
        self._events[event.run_id].append(event)

    async def list_by_run(self, run_id: str) -> list[AgentStreamEvent]:
        return list(self._events.get(run_id, []))

    async def list_after_sequence(self, run_id: str, after_sequence: int) -> list[AgentStreamEvent]:
        return [
            event
            for event in self._events.get(run_id, [])
            if event.sequence > after_sequence
        ]

    async def next_sequence(self, run_id: str) -> int:
        return len(self._events.get(run_id, [])) + 1

