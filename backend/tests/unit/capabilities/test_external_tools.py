import pytest
from pydantic import ValidationError

from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.external import (
    ExternalToolAdapter,
    ExternalToolInvocation,
    ExternalToolProvider,
    ExternalToolResult,
    ExternalToolSpec,
)
from aithru_agent.domain import AgentToolCallRequest, AgentToolKind


class FakeExternalProvider:
    def __init__(self) -> None:
        self.invocations: list[ExternalToolInvocation] = []

    def list_tools(self) -> list[ExternalToolSpec]:
        return [
            ExternalToolSpec(
                name="external.echo",
                description="Echo input through a fake external provider.",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                output_schema={"type": "object"},
                risk_level="read",
                required_scopes=["agent.external.echo"],
                approval_policy="never",
                provider="fake",
            )
        ]

    async def execute(self, invocation: ExternalToolInvocation) -> ExternalToolResult:
        self.invocations.append(invocation)
        return ExternalToolResult(
            status="completed",
            output={"echo": invocation.input["text"], "run_id": invocation.run_id},
            redaction="none",
        )


def test_external_tool_spec_is_pydantic_validated_contract() -> None:
    spec = ExternalToolSpec(
        name="external.echo",
        description="Echo input.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level="read",
        required_scopes=["agent.external.echo"],
        approval_policy="never",
        provider="fake",
    )

    assert spec.model_dump(mode="json") == {
        "name": "external.echo",
        "description": "Echo input.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "risk_level": "read",
        "required_scopes": ["agent.external.echo"],
        "approval_policy": "never",
        "failure_policy": "fail_run",
        "provider": "fake",
        "metadata": None,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": " ", "description": "x", "input_schema": {"type": "object"}, "provider": "fake"},
        {"name": "external.echo", "description": "x", "input_schema": {"type": "array"}, "provider": "fake"},
        {"name": "external.echo", "description": "x", "input_schema": {"type": "object"}, "provider": " "},
        {"name": "external.echo", "description": "x", "input_schema": {"type": "object"}, "provider": "fake", "required_scopes": [" "]},
    ],
)
def test_external_tool_spec_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ExternalToolSpec(output_schema={"type": "object"}, risk_level="read", approval_policy="never", **kwargs)


@pytest.mark.asyncio
async def test_external_tool_adapter_lists_and_executes_provider_tools() -> None:
    provider = FakeExternalProvider()
    adapter = ExternalToolAdapter(provider)
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        thread_id="thread_1",
        skill_id="skill_1",
        scopes=["agent.external.echo"],
    )
    router = AithruCapabilityRouter(adapters=[adapter])

    tools = await router.list_tools(context)
    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="external.echo",
            input={"text": "hello"},
            requested_by="model",
        ),
        context,
    )

    assert tools[0].kind is AgentToolKind.EXTERNAL_TOOL
    assert tools[0].name == "external.echo"
    assert tools[0].failure_policy == "fail_run"
    assert result.status == "completed"
    assert result.output == {"echo": "hello", "run_id": "run_1"}
    assert provider.invocations == [
        ExternalToolInvocation(
            tool_call_id="toolcall_1",
            tool_name="external.echo",
            input={"text": "hello"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
            thread_id="thread_1",
            skill_id="skill_1",
        )
    ]


@pytest.mark.asyncio
async def test_external_tool_adapter_respects_scope_skill_and_approval_policy() -> None:
    provider = FakeExternalProvider()
    adapter = ExternalToolAdapter(provider)
    scoped_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=[],
    )
    allowed_context = scoped_context.model_copy(
        update={
            "scopes": ["agent.external.echo"],
            "allowed_tools": ["external.echo"],
        }
    )
    denied_by_skill = scoped_context.model_copy(
        update={
            "scopes": ["agent.external.echo"],
            "allowed_tools": ["workspace.read_file"],
        }
    )
    approval_router = AithruCapabilityRouter(
        adapters=[adapter],
        policy=ToolPolicy(require_approval_for_risk=["read"]),
    )

    assert await AithruCapabilityRouter(adapters=[adapter]).list_tools(scoped_context) == []
    assert await AithruCapabilityRouter(adapters=[adapter]).list_tools(denied_by_skill) == []
    assert [tool.name for tool in await AithruCapabilityRouter(adapters=[adapter]).list_tools(allowed_context)] == [
        "external.echo"
    ]
    prepared = await approval_router.prepare_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="external.echo",
            input={"text": "hello"},
            requested_by="model",
        ),
        allowed_context,
    )

    assert prepared.status == "waiting_approval"
