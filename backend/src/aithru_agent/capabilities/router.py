from copy import deepcopy
from typing import Protocol

from aithru_agent.domain import (
    AgentAuthorizationDecision,
    AgentCapabilityAuditEvent,
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
            if context.authorize_scopes(
                tool.required_scopes,
                resource_type="tool",
                resource_id=tool.name,
            ).status == "allowed"
        ]
        if context.allowed_tools is not None:
            allowed = set(context.allowed_tools)
            tools = [tool for tool in tools if tool.name in allowed]
        if context.denied_tools:
            denied = set(context.denied_tools)
            tools = [tool for tool in tools if tool.name not in denied]
        return _tools_with_context_schema(tools, context)

    async def prepare_tool_call(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolPrepareResult:
        descriptor = self._find_any_descriptor(request.tool_name)
        if descriptor is None:
            return AgentToolPrepareResult(
                status="denied",
                tool_name=request.tool_name,
                reason=f"Unknown tool: {request.tool_name}",
            )
        authorization = context.authorize_scopes(
            descriptor.required_scopes,
            resource_type="tool",
            resource_id=descriptor.name,
        )
        if descriptor.name in set(context.denied_tools):
            reason = f"Tool is denied by run policy: {request.tool_name}"
            return AgentToolPrepareResult(
                status="denied",
                tool_name=request.tool_name,
                reason=reason,
                authorization=authorization,
                audit=_audit_event(
                    action="tool.prepare",
                    outcome="denied",
                    request=request,
                    context=context,
                    authorization=authorization,
                    reason=reason,
                ),
            )
        if context.allowed_tools is not None and descriptor.name not in set(context.allowed_tools):
            reason = f"Tool is not allowed by run policy: {request.tool_name}"
            return AgentToolPrepareResult(
                status="denied",
                tool_name=request.tool_name,
                reason=reason,
                authorization=authorization,
                audit=_audit_event(
                    action="tool.prepare",
                    outcome="denied",
                    request=request,
                    context=context,
                    authorization=authorization,
                    reason=reason,
                ),
            )
        if authorization.status == "denied":
            reason = authorization.reason or f"Missing required scope: {authorization.missing_scopes[0]}"
            return AgentToolPrepareResult(
                status="denied",
                tool_name=request.tool_name,
                reason=reason,
                authorization=authorization,
                audit=_audit_event(
                    action="tool.prepare",
                    outcome="denied",
                    request=request,
                    context=context,
                    authorization=authorization,
                    reason=reason,
                ),
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
                authorization=authorization,
                audit=_audit_event(
                    action="tool.prepare",
                    outcome="waiting_approval",
                    request=request,
                    context=context,
                    authorization=authorization,
                    reason=f"Approval required for risk: {descriptor.risk_level.value}",
                ),
            )
        return AgentToolPrepareResult(
            status="ready",
            tool_name=request.tool_name,
            authorization=authorization,
            audit=_audit_event(
                action="tool.prepare",
                outcome="allowed",
                request=request,
                context=context,
                authorization=authorization,
            ),
        )

    async def requires_approval_for_tool(
        self,
        tool_name: str,
        context: AgentRunContext,
    ) -> bool:
        descriptor = self._find_any_descriptor(tool_name)
        if descriptor is None:
            return False
        authorization = context.authorize_scopes(
            descriptor.required_scopes,
            resource_type="tool",
            resource_id=descriptor.name,
        )
        if authorization.status == "denied":
            return False
        if descriptor.name in set(context.denied_tools):
            return False
        if context.allowed_tools is not None and descriptor.name not in set(context.allowed_tools):
            return False
        approval_risks = {
            *self._policy.require_approval_for_risk,
            *context.require_approval_for_risk,
        }
        return descriptor.risk_level.value in approval_risks

    async def get_tool_descriptor(
        self,
        tool_name: str,
        context: AgentRunContext,
    ) -> AgentToolDescriptor | None:
        descriptor = self._find_any_descriptor(tool_name)
        if descriptor is None:
            return None
        authorization = context.authorize_scopes(
            descriptor.required_scopes,
            resource_type="tool",
            resource_id=descriptor.name,
        )
        if authorization.status == "denied":
            return None
        if descriptor.name in set(context.denied_tools):
            return None
        if context.allowed_tools is not None and descriptor.name not in set(context.allowed_tools):
            return None
        return descriptor

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
                authorization=prepared.authorization,
                audit=_audit_event(
                    action="tool.execute",
                    outcome="denied",
                    request=request,
                    context=context,
                    authorization=prepared.authorization,
                    reason=prepared.reason,
                )
                if prepared.authorization is not None
                else None,
            )
        if prepared.status == "waiting_approval":
            return AgentToolCallResult(
                status="waiting_approval",
                output=prepared.output,
                redaction="none",
                authorization=prepared.authorization,
                audit=_audit_event(
                    action="tool.execute",
                    outcome="waiting_approval",
                    request=request,
                    context=context,
                    authorization=prepared.authorization,
                    reason="Approval required",
                )
                if prepared.authorization is not None
                else None,
            )

        adapter = self._find_adapter(request.tool_name)
        if adapter is None:
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown tool: {request.tool_name}"},
                redaction="none",
                authorization=prepared.authorization,
                audit=_audit_event(
                    action="tool.execute",
                    outcome="denied",
                    request=request,
                    context=context,
                    authorization=prepared.authorization,
                    reason=f"Unknown tool: {request.tool_name}",
                )
                if prepared.authorization is not None
                else None,
            )
        result = await adapter.execute(request, context)
        return result.model_copy(
            update={
                "authorization": prepared.authorization,
                "audit": _audit_event(
                    action="tool.execute",
                    outcome=_audit_outcome_for_result(result),
                    request=request,
                    context=context,
                    authorization=prepared.authorization,
                    reason=_result_reason(result),
                )
                if prepared.authorization is not None
                else None,
            }
        )

    def _find_any_descriptor(self, tool_name: str) -> AgentToolDescriptor | None:
        for adapter in self._adapters:
            for tool in adapter.list_tools():
                if tool.name == tool_name:
                    return tool
        return None

    def _find_adapter(self, tool_name: str) -> AgentToolAdapter | None:
        for adapter in self._adapters:
            if any(tool.name == tool_name for tool in adapter.list_tools()):
                return adapter
        return None


def _audit_event(
    *,
    action: str,
    outcome: str,
    request: AgentToolCallRequest,
    context: AgentRunContext,
    authorization: AgentAuthorizationDecision,
    reason: str | None = None,
) -> AgentCapabilityAuditEvent:
    return AgentCapabilityAuditEvent(
        action=action,
        outcome=outcome,
        run_id=context.run_id,
        tool_name=request.tool_name,
        actor=authorization.actor,
        authorization=authorization,
        reason=reason,
    )


def _tools_with_context_schema(
    tools: list[AgentToolDescriptor],
    context: AgentRunContext,
) -> list[AgentToolDescriptor]:
    if not context.workspace_allowed_paths:
        return tools
    return [
        _with_workspace_path_guidance(tool, context.workspace_allowed_paths)
        for tool in tools
    ]


def _with_workspace_path_guidance(
    tool: AgentToolDescriptor,
    allowed_paths: list[str],
) -> AgentToolDescriptor:
    if not tool.name.startswith("workspace."):
        return tool
    schema = deepcopy(tool.input_schema)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return tool
    path_schema = properties.get("path")
    if not isinstance(path_schema, dict):
        return tool

    guidance = (
        "Must be an absolute workspace path under one of: "
        f"{', '.join(allowed_paths)}. Do not use bare filenames."
    )
    existing = path_schema.get("description")
    path_schema["description"] = (
        f"{existing} {guidance}" if isinstance(existing, str) and existing else guidance
    )
    return tool.model_copy(update={"input_schema": schema})


def _audit_outcome_for_result(result: AgentToolCallResult) -> str:
    if result.status == "completed":
        return "completed"
    if result.status == "waiting_approval":
        return "waiting_approval"
    if result.status == "running":
        return "running"
    if result.status == "denied":
        return "denied"
    return "failed"


def _result_reason(result: AgentToolCallResult) -> str | None:
    if not isinstance(result.error, dict):
        return None
    message = result.error.get("message")
    return str(message) if message is not None else None
