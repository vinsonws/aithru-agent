"""Test-only native AgentRuntime helpers for control-plane tests."""

from dataclasses import dataclass
from typing import Any, Literal

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge


@dataclass(frozen=True)
class StepToolCall:
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Step:
    type: Literal["message", "tool", "finish"]
    text: str | None = None
    tool_call: StepToolCall | None = None

    @classmethod
    def message(cls, text: str) -> "Step":
        return cls(type="message", text=text)

    @classmethod
    def tool(cls, name: str, input: dict[str, Any]) -> "Step":
        return cls(type="tool", tool_call=StepToolCall(name=name, input=input))

    @classmethod
    def finish(cls) -> "Step":
        return cls(type="finish")


class ToolContext:
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = False


class StepAgentRuntime(AgentRuntime):
    """AgentRuntime test double that still routes tools through Aithru capabilities."""

    def __init__(self, steps: list[Step]) -> None:
        super().__init__()
        self._steps = steps
        self._tool_counter = 0

    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal
        content: list[str] = []
        message_id = "msg_1"
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": message_id, "role": "assistant"},
        )
        bridge = PydanticAIToolBridge(deps=deps)
        for step in self._steps:
            if step.type == "message" and step.text is not None:
                content.append(step.text)
                await deps.event_writer.write(
                    run_id=deps.run.id,
                    thread_id=deps.run.thread_id,
                    type="message.delta",
                    source={"kind": "model"},
                    payload={"message_id": message_id, "delta": step.text},
                )
            elif step.type == "tool" and step.tool_call is not None:
                self._tool_counter += 1
                await bridge.call_tool(
                    ToolContext(f"toolcall_{self._tool_counter}"),
                    step.tool_call.name,
                    step.tool_call.input,
                )
            elif step.type == "finish":
                break
        return AgentRuntimeResult(content="".join(content))
