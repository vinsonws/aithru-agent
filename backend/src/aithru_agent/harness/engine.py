from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class HarnessToolCall:
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class HarnessStep:
    type: Literal["message", "tool", "finish"]
    text: str | None = None
    tool_call: HarnessToolCall | None = None


@dataclass(frozen=True)
class HarnessRunDeps:
    run: Any
    run_context: Any
    event_writer: Any
    capability_router: Any
    store: Any
    skill: Any = None


class HarnessRunPaused(Exception):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run paused: {run_id}")
        self.run_id = run_id


class AgentHarnessDriver(Protocol):
    async def run(self, goal: str | None = None, deps: HarnessRunDeps | None = None) -> list[HarnessStep]:
        ...
