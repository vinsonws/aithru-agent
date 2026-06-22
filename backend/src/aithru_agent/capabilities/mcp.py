from typing import Literal, Protocol

from pydantic import Field, field_validator

from aithru_agent.domain import AgentToolApprovalPolicy, AgentToolRiskLevel
from aithru_agent.domain.base import AithruBaseModel

from .external import ExternalToolInvocation, ExternalToolResult, ExternalToolSpec


class MCPToolSpec(AithruBaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    risk_level: AgentToolRiskLevel
    required_scopes: list[str] | None = None
    approval_policy: AgentToolApprovalPolicy | Literal["never", "on_risk", "always"]
    metadata: dict | None = None

    @field_validator("name")
    @classmethod
    def _name_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="MCP tool name")

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _schema_must_be_object(cls, value: dict) -> dict:
        if value.get("type") != "object":
            raise ValueError("MCP-like tool schemas must be JSON object schemas")
        return value

    @field_validator("required_scopes")
    @classmethod
    def _scopes_must_not_be_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("MCP-like required scopes cannot contain blank values")
        return scopes


class MCPServerSpec(AithruBaseModel):
    key: str = Field(min_length=1)
    name: str | None = None
    enabled: bool = True
    tools: list[MCPToolSpec]
    metadata: dict | None = None

    @field_validator("key")
    @classmethod
    def _key_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="MCP server key")


class MCPToolInvocation(AithruBaseModel):
    tool_call_id: str
    external_tool_name: str
    server_key: str
    tool_name: str
    input: object
    run_id: str
    org_id: str
    actor_user_id: str
    workspace_id: str
    thread_id: str | None = None
    skill_id: str | None = None


class MCPToolResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"] = "none"


class MCPToolExecutor(Protocol):
    async def execute(self, invocation: MCPToolInvocation) -> MCPToolResult:
        ...


class MCPToolProvider:
    def __init__(self, *, servers: list[MCPServerSpec], executor: MCPToolExecutor) -> None:
        self._servers = [server for server in servers if server.enabled]
        self._executor = executor
        self._by_external_name = {
            _external_name(server.key, tool.name): (server, tool)
            for server in self._servers
            for tool in server.tools
        }

    def list_tools(self) -> list[ExternalToolSpec]:
        return [
            ExternalToolSpec(
                name=external_name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                risk_level=tool.risk_level,
                required_scopes=tool.required_scopes or [_default_scope(server.key, tool.name)],
                approval_policy=tool.approval_policy,
                provider=f"mcp:{server.key}",
                metadata={"server_key": server.key, "tool_name": tool.name},
            )
            for external_name, (server, tool) in self._by_external_name.items()
        ]

    async def execute(self, invocation: ExternalToolInvocation) -> ExternalToolResult:
        if invocation.tool_name not in self._by_external_name:
            return ExternalToolResult(
                status="denied",
                error={"message": f"Unknown MCP-like tool: {invocation.tool_name}"},
                redaction="none",
            )
        result = await self._executor.execute(
            self._mcp_invocation(invocation)
        )
        return ExternalToolResult(
            status=result.status,
            output=result.output,
            error=result.error,
            redaction=result.redaction,
        )

    def external_invocation(
        self,
        *,
        tool_call_id: str,
        external_tool_name: str,
        input: object,
        run_id: str,
        org_id: str,
        actor_user_id: str,
        workspace_id: str,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> ExternalToolInvocation:
        return ExternalToolInvocation(
            tool_call_id=tool_call_id,
            tool_name=external_tool_name,
            input=input,
            run_id=run_id,
            org_id=org_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            skill_id=skill_id,
        )

    def _mcp_invocation(self, invocation: ExternalToolInvocation) -> MCPToolInvocation:
        server, tool = self._by_external_name[invocation.tool_name]
        return MCPToolInvocation(
            tool_call_id=invocation.tool_call_id,
            external_tool_name=invocation.tool_name,
            server_key=server.key,
            tool_name=tool.name,
            input=invocation.input,
            run_id=invocation.run_id,
            org_id=invocation.org_id,
            actor_user_id=invocation.actor_user_id,
            workspace_id=invocation.workspace_id,
            thread_id=invocation.thread_id,
            skill_id=invocation.skill_id,
        )


def _external_name(server_key: str, tool_name: str) -> str:
    return f"mcp.{server_key}.{tool_name}"


def _default_scope(server_key: str, tool_name: str) -> str:
    return f"agent.external.mcp.{server_key}.{tool_name}"


def _slug(value: str, *, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} cannot be blank")
    allowed = all(char.isalnum() or char in {"_", "-"} for char in stripped)
    if not allowed or " " in stripped:
        raise ValueError(f"{label} must contain only letters, numbers, underscores, or hyphens")
    return stripped
