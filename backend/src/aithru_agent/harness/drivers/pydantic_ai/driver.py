from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import PartDeltaEvent, TextPartDelta
from pydantic_ai.run import AgentRunResultEvent

from aithru_agent.domain import AgentSkill
from aithru_agent.harness.drivers.pydantic_ai.tool_bridge import PydanticAIToolBridge
from aithru_agent.harness.engine import HarnessRunDeps, HarnessStep


class PydanticAIHarnessDriver:
    def __init__(
        self,
        *,
        model: object | str | None = None,
        instructions: str | None = None,
    ) -> None:
        self._model = model
        self._instructions = instructions or "You are Aithru Agent. Help the user complete the task."

    async def run(self, goal: str | None = None, deps: HarnessRunDeps | None = None) -> list[HarnessStep]:
        tools = await self._build_tools(deps) if deps else []
        agent = Agent(
            self._model,
            instructions=self.instructions_for_run(deps.skill if deps else None),
            output_type=str,
            tools=tools,
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

    def instructions_for_run(self, skill: AgentSkill | None = None) -> str:
        if not skill:
            return self._instructions
        return f"{self._instructions}\n\nSkill instructions:\n{skill.instructions}"

    async def _build_tools(self, deps: HarnessRunDeps | None) -> list[Tool]:
        if deps is None:
            return []
        descriptors = await deps.capability_router.list_tools(deps.run_context)
        bridge = PydanticAIToolBridge(
            run=deps.run,
            run_context=deps.run_context,
            event_writer=deps.event_writer,
            capability_router=deps.capability_router,
            store=deps.store,
        )

        def make_tool(tool_name: str, description: str) -> Tool:
            async def aithru_tool(
                ctx: RunContext[None],
                input: dict[str, Any] | None = None,
            ) -> object:
                tool_call_id = ctx.tool_call_id or f"pydantic:{tool_name}:{ctx.run_step}"
                return await bridge.call_tool(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    tool_input=input or {},
                )

            return Tool(
                aithru_tool,
                takes_ctx=True,
                name=tool_name,
                description=description,
            )

        return [make_tool(descriptor.name, descriptor.description) for descriptor in descriptors]
