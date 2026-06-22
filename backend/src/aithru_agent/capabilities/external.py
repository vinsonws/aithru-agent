from typing import Literal, Protocol

from pydantic import Field, field_validator

from aithru_agent.domain import (
    AgentToolApprovalPolicy,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolFailurePolicy,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.base import AithruBaseModel

from .descriptors import AgentRunContext


class ExternalToolSpec(AithruBaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    risk_level: AgentToolRiskLevel
    required_scopes: list[str]
    approval_policy: AgentToolApprovalPolicy | Literal["never", "on_risk", "always"]
    failure_policy: AgentToolFailurePolicy | Literal["fail_run", "return_recoverable"] = (
        AgentToolFailurePolicy.FAIL_RUN
    )
    provider: str = Field(min_length=1)
    metadata: dict | None = None

    @field_validator("name", "provider")
    @classmethod
    def _value_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("external tool values cannot be blank")
        return stripped

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _schema_must_be_object(cls, value: dict) -> dict:
        if value.get("type") != "object":
            raise ValueError("external tool schemas must be JSON object schemas")
        return value

    @field_validator("required_scopes")
    @classmethod
    def _scopes_must_not_be_blank(cls, value: list[str]) -> list[str]:
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("external tool scopes cannot contain blank values")
        return scopes


class ExternalToolInvocation(AithruBaseModel):
    tool_call_id: str
    tool_name: str
    input: object
    run_id: str
    org_id: str
    actor_user_id: str
    workspace_id: str
    thread_id: str | None = None
    skill_id: str | None = None


class ExternalToolResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"]


class ExternalToolProvider(Protocol):
    def list_tools(self) -> list[ExternalToolSpec]:
        ...

    async def execute(self, invocation: ExternalToolInvocation) -> ExternalToolResult:
        ...


class ExternalToolAdapter:
    def __init__(self, provider: ExternalToolProvider) -> None:
        self._provider = provider

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name=spec.name,
                kind=AgentToolKind.EXTERNAL_TOOL,
                description=spec.description,
                input_schema=spec.input_schema,
                output_schema=spec.output_schema,
                risk_level=spec.risk_level,
                required_scopes=spec.required_scopes,
                approval_policy=spec.approval_policy,
                failure_policy=spec.failure_policy,
            )
            for spec in self._provider.list_tools()
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name not in {tool.name for tool in self.list_tools()}:
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown external tool: {request.tool_name}"},
                redaction="none",
            )
        result = await self._provider.execute(
            ExternalToolInvocation(
                tool_call_id=request.id,
                tool_name=request.tool_name,
                input=request.input,
                run_id=context.run_id,
                org_id=context.org_id,
                actor_user_id=context.actor_user_id,
                workspace_id=context.workspace_id,
                thread_id=context.thread_id,
                skill_id=context.skill_id,
            )
        )
        return AgentToolCallResult(
            status=result.status,
            output=result.output,
            error=result.error,
            redaction=result.redaction,
        )
