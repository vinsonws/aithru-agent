from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class QueuedRun:
    run_id: str


class InProcessRunQueue:
    def __init__(self) -> None:
        self._items: deque[QueuedRun] = deque()

    def enqueue(self, run_id: str) -> None:
        self._items.append(QueuedRun(run_id=run_id))

    def pop(self) -> QueuedRun | None:
        if not self._items:
            return None
        return self._items.popleft()

