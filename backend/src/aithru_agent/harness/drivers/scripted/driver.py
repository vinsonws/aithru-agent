from dataclasses import dataclass
from typing import Any

from aithru_agent.harness.engine import HarnessStep, HarnessToolCall


@dataclass(frozen=True)
class ScriptedStep:
    step: HarnessStep

    @classmethod
    def message(cls, text: str) -> "ScriptedStep":
        return cls(HarnessStep(type="message", text=text))

    @classmethod
    def tool(cls, name: str, input: dict[str, Any]) -> "ScriptedStep":
        return cls(HarnessStep(type="tool", tool_call=HarnessToolCall(name=name, input=input)))

    @classmethod
    def finish(cls) -> "ScriptedStep":
        return cls(HarnessStep(type="finish"))


class ScriptedHarnessDriver:
    def __init__(self, steps: list[ScriptedStep]) -> None:
        self._steps = steps

    async def run(self) -> list[HarnessStep]:
        return [step.step for step in self._steps]

