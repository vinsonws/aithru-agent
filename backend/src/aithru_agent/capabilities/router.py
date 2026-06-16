from typing import Protocol

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
)

from .descriptors import AgentRunContext, AgentToolPrepareResult, ToolPolicy


class AgentToolAdapter(Protocol):
    def list_tools(self) -> list[AgentToolDescriptor]:
        ...

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        ...


class AithruCapabilityRouter:
    def __init__(
        self,
        *,
        adapters: list[AgentToolAdapter],
        policy: ToolPolicy | None = None,
    ) -> None:
        self._adapters = adapters
        self._policy = policy or ToolPolicy()

    async def list_tools(self, context: AgentRunContext) -> list[AgentToolDescriptor]:
        tools: list[AgentToolDescriptor] = []
        for adapter in self._adapters:
            tools.extend(adapter.list_tools())
        tools = [
            tool
            for tool in tools
            if all(scope in context.scopes or "*" in context.scopes for scope in tool.required_scopes)
        ]
        if context.allowed_tools is not None:
            allowed = set(context.allowed_tools)
            tools = [tool for tool in tools if tool.name in allowed]
        return tools

    async def prepare_tool_call(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolPrepareResult:
        descriptor = await self._find_descriptor(request.tool_name, context)
        if descriptor is None:
            return AgentToolPrepareResult(
                status="denied",
                tool_name=request.tool_name,
                reason=f"Unknown tool: {request.tool_name}",
            )
        missing_scope = next(
            (
                scope
                for scope in descriptor.required_scopes
                if scope not in context.scopes and "*" not in context.scopes
            ),
            None,
        )
        if missing_scope:
            return AgentToolPrepareResult(
                status="denied",
                tool_name=request.tool_name,
                reason=f"Missing required scope: {missing_scope}",
            )
        approval_risks = {
            *self._policy.require_approval_for_risk,
            *context.require_approval_for_risk,
        }
        if descriptor.risk_level.value in approval_risks and not request.already_approved:
            return AgentToolPrepareResult(
                status="waiting_approval",
                tool_name=request.tool_name,
                output={"risk_level": descriptor.risk_level.value},
            )
        return AgentToolPrepareResult(status="ready", tool_name=request.tool_name)

    async def execute_tool_call(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        prepared = await self.prepare_tool_call(request, context)
        if prepared.status == "denied":
            return AgentToolCallResult(
                status="denied",
                error={"message": prepared.reason},
                redaction="none",
            )
        if prepared.status == "waiting_approval":
            return AgentToolCallResult(
                status="waiting_approval",
                output=prepared.output,
                redaction="none",
            )

        adapter = self._find_adapter(request.tool_name)
        if adapter is None:
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown tool: {request.tool_name}"},
                redaction="none",
            )
        return await adapter.execute(request, context)

    async def _find_descriptor(
        self,
        tool_name: str,
        context: AgentRunContext,
    ) -> AgentToolDescriptor | None:
        for tool in await self.list_tools(context):
            if tool.name == tool_name:
                return tool
        return None

    def _find_adapter(self, tool_name: str) -> AgentToolAdapter | None:
        for adapter in self._adapters:
            if any(tool.name == tool_name for tool in adapter.list_tools()):
                return adapter
        return None
