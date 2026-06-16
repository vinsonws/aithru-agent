from pydantic_ai import Agent
from pydantic_ai.messages import PartDeltaEvent, TextPartDelta
from pydantic_ai.run import AgentRunResultEvent

from aithru_agent.harness.engine import HarnessStep


class PydanticAIHarnessDriver:
    def __init__(
        self,
        *,
        model: object | str | None = None,
        instructions: str | None = None,
    ) -> None:
        self._model = model
        self._instructions = instructions or "You are Aithru Agent. Help the user complete the task."

    async def run(self, goal: str | None = None) -> list[HarnessStep]:
        agent = Agent(
            self._model,
            instructions=self._instructions,
            output_type=str,
        )
        steps: list[HarnessStep] = []
        async with agent.run_stream_events(goal or "") as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        steps.append(HarnessStep(type="message", text=event.delta.content_delta))
                elif isinstance(event, AgentRunResultEvent):
                    steps.append(HarnessStep(type="finish"))
        if not steps or steps[-1].type != "finish":
            steps.append(HarnessStep(type="finish"))
        return steps
