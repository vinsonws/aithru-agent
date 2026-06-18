"""Aithru capability boundary for Pydantic AI agents."""

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

from aithru_agent.agent.deps import PydanticAgentDeps

from .approvals import require_approved_tool_call
from .events import mark_aithru_boundary_tool
from .toolset import AithruToolset


@dataclass
class AithruBoundaryCapability(AbstractCapability[PydanticAgentDeps]):
    """Pydantic AI capability that keeps tool execution inside Aithru's router."""

    toolset: AithruToolset = field(default_factory=AithruToolset)

    def get_toolset(self) -> AithruToolset:
        return self.toolset

    async def prepare_tools(
        self,
        ctx: RunContext[PydanticAgentDeps],
        tool_defs: list[ToolDefinition],
    ) -> list[ToolDefinition]:
        del ctx
        return [mark_aithru_boundary_tool(tool_def) for tool_def in tool_defs]

    async def before_tool_execute(
        self,
        ctx: RunContext[PydanticAgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        require_approved_tool_call(
            ctx,
            tool_def,
            metadata={
                "tool_call_id": call.tool_call_id,
                "tool_name": call.tool_name,
                "boundary": "aithru",
            },
        )
        return args
