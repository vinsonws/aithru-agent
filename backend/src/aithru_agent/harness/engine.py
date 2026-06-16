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


class AgentHarnessDriver(Protocol):
    async def run(self, goal: str | None = None) -> list[HarnessStep]:
        ...
