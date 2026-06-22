from typing import Literal, Protocol

from pydantic import Field, field_validator

from aithru_agent.domain import (
    AgentExternalRunRef,
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


class WorkflowCapabilitySpec(AithruBaseModel):
    key: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    risk_level: AgentToolRiskLevel
    required_scopes: list[str]
    approval_policy: AgentToolApprovalPolicy | Literal["never", "on_risk", "always"]
    failure_policy: AgentToolFailurePolicy | Literal["fail_run", "return_recoverable"] = (
        AgentToolFailurePolicy.FAIL_RUN
    )
    metadata: dict | None = None

    @field_validator("key")
    @classmethod
    def _key_must_be_slug(cls, value: str) -> str:
        return _slug(value, label="workflow capability key")

    @field_validator("tool_name")
    @classmethod
    def _tool_name_must_be_dotted_slug(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("workflow capability tool name cannot be blank")
        parts = name.split(".")
        if any(not _is_slug(part) for part in parts):
            raise ValueError(
                "workflow capability tool name must contain only dotted slug parts"
            )
        return name

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _schema_must_be_object(cls, value: dict) -> dict:
        if value.get("type") != "object":
            raise ValueError("workflow capability schemas must be JSON object schemas")
        return value

    @field_validator("required_scopes")
    @classmethod
    def _scopes_must_not_be_blank(cls, value: list[str]) -> list[str]:
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("workflow capability scopes cannot contain blank values")
        return scopes


class WorkflowCapabilityInvocation(AithruBaseModel):
    tool_call_id: str
    tool_name: str
    capability_key: str
    input: object
    run_id: str
    org_id: str
    actor_user_id: str
    workspace_id: str
    thread_id: str | None = None
    skill_id: str | None = None
    correlation_id: str


class WorkflowCapabilityResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied", "waiting_approval", "running"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"] = "none"
    external_run: AgentExternalRunRef | None = None


class WorkflowCapabilityProvider(Protocol):
    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        ...

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        ...


class WorkflowCapabilityAdapter:
    def __init__(self, provider: WorkflowCapabilityProvider) -> None:
        self._provider = provider

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name=spec.tool_name,
                kind=AgentToolKind.WORKFLOW_CAPABILITY,
                description=spec.description,
                input_schema=spec.input_schema,
                output_schema=spec.output_schema,
                risk_level=spec.risk_level,
                required_scopes=spec.required_scopes,
                approval_policy=spec.approval_policy,
                failure_policy=spec.failure_policy,
            )
            for spec in self._provider.list_capabilities()
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        capabilities = {
            capability.tool_name: capability
            for capability in self._provider.list_capabilities()
        }
        capability = capabilities.get(request.tool_name)
        if capability is None:
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown workflow capability tool: {request.tool_name}"},
                redaction="none",
            )

        result = await self._provider.invoke(
            WorkflowCapabilityInvocation(
                tool_call_id=request.id,
                tool_name=request.tool_name,
                capability_key=capability.key,
                input=request.input,
                run_id=context.run_id,
                org_id=context.org_id,
                actor_user_id=context.actor_user_id,
                workspace_id=context.workspace_id,
                thread_id=context.thread_id,
                skill_id=context.skill_id,
                correlation_id=f"{context.run_id}:{request.id}",
            )
        )
        return AgentToolCallResult(
            status=result.status,
            output=result.output,
            error=result.error,
            redaction=result.redaction,
            external_run=result.external_run,
        )


def _slug(value: str, *, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} cannot be blank")
    if not _is_slug(stripped):
        raise ValueError(
            f"{label} must contain only letters, numbers, underscores, or hyphens"
        )
    return stripped


def _is_slug(value: str) -> bool:
    return bool(value) and all(char.isalnum() or char in {"_", "-"} for char in value)
