from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class QueuedRun:
    run_id: str


class InProcessRunQueue:
    def __init__(self) -> None:
        self._items: deque[QueuedRun] = deque()
        self._pending_ids: set[str] = set()

    def enqueue(self, run_id: str) -> None:
        if run_id in self._pending_ids:
            return
        self._items.append(QueuedRun(run_id=run_id))
        self._pending_ids.add(run_id)

    def pop(self) -> QueuedRun | None:
        if not self._items:
            return None
        item = self._items.popleft()
        self._pending_ids.discard(item.run_id)
        return item

