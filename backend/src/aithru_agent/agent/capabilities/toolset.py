"""Pydantic AI toolset backed by the Aithru Capability Router."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic_ai import AbstractToolset, RunContext
from pydantic_ai.toolsets import FunctionToolset, ToolsetTool

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.tools.bridge import PydanticAIToolBridge
from aithru_agent.agent.tools.descriptors import ToolCallback, build_pydantic_tools
from aithru_agent.domain import AgentToolDescriptor

from .events import metadata_for_descriptor


@dataclass
class AithruToolset(AbstractToolset[PydanticAgentDeps]):
    """Expose Aithru tool descriptors as Pydantic AI tools.

    The toolset owns descriptor-to-Pydantic conversion only. Concrete tool
    execution remains delegated to `PydanticAIToolBridge`, which routes through
    `AithruCapabilityRouter`.
    """

    tool_specs: Sequence[tuple[AgentToolDescriptor, bool]] | None = None
    tool_callback: ToolCallback | None = None
    toolset_id: str | None = "aithru"
    expose_safe_tool_names: bool = False

    @property
    def id(self) -> str | None:
        return self.toolset_id

    async def get_tools(
        self,
        ctx: RunContext[PydanticAgentDeps],
    ) -> dict[str, ToolsetTool[PydanticAgentDeps]]:
        inner = await self._inner_toolset(ctx)
        return await inner.get_tools(ctx)

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[PydanticAgentDeps],
        tool: ToolsetTool[PydanticAgentDeps],
    ) -> Any:
        if tool.toolset is self:
            raise RuntimeError("AithruToolset tool definitions must delegate to an inner toolset")
        return await tool.toolset.call_tool(name, tool_args, ctx, tool)

    async def _inner_toolset(
        self,
        ctx: RunContext[PydanticAgentDeps],
    ) -> FunctionToolset[PydanticAgentDeps]:
        tool_specs = await self._tool_specs(ctx)
        tool_callback = self.tool_callback or PydanticAIToolBridge(deps=ctx.deps).call_tool
        tools = build_pydantic_tools(
            list(tool_specs),
            tool_callback,
            expose_safe_tool_names=self.expose_safe_tool_names,
        )
        for tool, (descriptor, requires_approval) in zip(tools, tool_specs, strict=True):
            aliases = getattr(ctx.deps, "tool_name_aliases", None)
            if aliases is not None:
                aliases[tool.name] = descriptor.name
            tool.metadata = metadata_for_descriptor(
                descriptor,
                requires_approval=requires_approval,
            )
        return FunctionToolset(tools, id=self.toolset_id)

    async def _tool_specs(
        self,
        ctx: RunContext[PydanticAgentDeps],
    ) -> Sequence[tuple[AgentToolDescriptor, bool]]:
        if self.tool_specs is not None:
            return self.tool_specs

        descriptors = await ctx.deps.capability_router.list_tools(ctx.deps.run_context)
        return [
            (
                descriptor,
                await ctx.deps.capability_router.requires_approval_for_tool(
                    descriptor.name,
                    ctx.deps.run_context,
                ),
            )
            for descriptor in descriptors
        ]
