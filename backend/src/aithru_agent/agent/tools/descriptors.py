"""Convert Aithru tool descriptors to Pydantic AI tools."""

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai import RunContext, Tool

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentToolDescriptor


ToolCallback = Callable[[RunContext[PydanticAgentDeps], str, dict[str, Any]], Awaitable[object]]


def build_pydantic_tools(
    tool_specs: list[tuple[AgentToolDescriptor, bool]],
    tool_callback: ToolCallback,
) -> list[Tool[PydanticAgentDeps]]:
    """Convert Aithru tool descriptors to Pydantic AI tools."""
    tools: list[Tool[PydanticAgentDeps]] = []

    for descriptor, requires_approval in tool_specs:
        wrapper = _make_tool_wrapper(descriptor.name, tool_callback)
        tool = Tool.from_schema(
            wrapper,
            takes_ctx=True,
            name=descriptor.name,
            description=descriptor.description,
            json_schema=descriptor.input_schema,
        )
        tool.requires_approval = requires_approval
        tools.append(tool)

    return tools


def _make_tool_wrapper(
    tool_name: str,
    tool_callback: ToolCallback,
) -> Callable[..., Awaitable[object]]:
    async def tool_wrapper(ctx: RunContext[PydanticAgentDeps], **tool_input: Any) -> object:
        return await tool_callback(ctx, tool_name, tool_input)

    return tool_wrapper
