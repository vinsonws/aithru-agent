"""Convert Aithru tool descriptors to Pydantic AI tools."""

from collections.abc import Awaitable, Callable
from hashlib import sha1
import re
from typing import Any

from pydantic_ai import RunContext, Tool

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentToolDescriptor


ToolCallback = Callable[[RunContext[PydanticAgentDeps], str, dict[str, Any]], Awaitable[object]]

PYDANTIC_AI_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def build_pydantic_tools(
    tool_specs: list[tuple[AgentToolDescriptor, bool]],
    tool_callback: ToolCallback,
    *,
    expose_safe_tool_names: bool = False,
) -> list[Tool[PydanticAgentDeps]]:
    """Convert Aithru tool descriptors to Pydantic AI tools."""
    tools: list[Tool[PydanticAgentDeps]] = []
    used_names: set[str] = set()

    for descriptor, requires_approval in tool_specs:
        wrapper = _make_tool_wrapper(descriptor.name, tool_callback)
        exposed_name = _exposed_tool_name(
            descriptor.name,
            used_names=used_names,
            expose_safe_tool_names=expose_safe_tool_names,
        )
        tool = Tool.from_schema(
            wrapper,
            takes_ctx=True,
            name=exposed_name,
            description=descriptor.description,
            json_schema=descriptor.input_schema,
        )
        tool.requires_approval = requires_approval
        tools.append(tool)

    return tools


def pydantic_safe_tool_name(tool_name: str) -> str:
    """Return a model-facing tool name accepted by OpenAI-compatible APIs."""
    if PYDANTIC_AI_TOOL_NAME_PATTERN.fullmatch(tool_name):
        return tool_name
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name).strip("_")
    return safe_name or "tool"


def _make_tool_wrapper(
    tool_name: str,
    tool_callback: ToolCallback,
) -> Callable[..., Awaitable[object]]:
    async def tool_wrapper(ctx: RunContext[PydanticAgentDeps], **tool_input: Any) -> object:
        return await tool_callback(ctx, tool_name, tool_input)

    return tool_wrapper


def _exposed_tool_name(
    tool_name: str,
    *,
    used_names: set[str],
    expose_safe_tool_names: bool,
) -> str:
    exposed_name = pydantic_safe_tool_name(tool_name) if expose_safe_tool_names else tool_name
    if exposed_name not in used_names:
        used_names.add(exposed_name)
        return exposed_name

    digest = sha1(tool_name.encode("utf-8")).hexdigest()[:8]
    candidate = f"{exposed_name}_{digest}"
    suffix = 2
    while candidate in used_names:
        candidate = f"{exposed_name}_{digest}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate
