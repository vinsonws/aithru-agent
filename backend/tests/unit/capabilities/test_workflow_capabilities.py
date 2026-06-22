import pytest
from pydantic import ValidationError

from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter
from aithru_agent.capabilities.workflow import (
    WorkflowCapabilityAdapter,
    WorkflowCapabilityInvocation,
    WorkflowCapabilityResult,
    WorkflowCapabilitySpec,
)
from aithru_agent.domain import AgentExternalRunRef, AgentToolCallRequest, AgentToolKind


class FakeWorkflowProvider:
    def __init__(self) -> None:
        self.invocations: list[WorkflowCapabilityInvocation] = []

    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return [
            WorkflowCapabilitySpec(
                key="report_review",
                tool_name="workflow.report_review",
                description="Run the Workbench report review capability.",
                input_schema={
                    "type": "object",
                    "properties": {"artifact_id": {"type": "string"}},
                    "required": ["artifact_id"],
                },
                output_schema={"type": "object"},
                risk_level="write",
                required_scopes=["workflow.capability.report_review.invoke"],
                approval_policy="on_risk",
                metadata={"owner": "workbench"},
            )
        ]

    async def invoke(self, invocation: WorkflowCapabilityInvocation) -> WorkflowCapabilityResult:
        self.invocations.append(invocation)
        return WorkflowCapabilityResult(
            status="completed",
            output={
                "accepted": True,
                "artifact_id": invocation.input["artifact_id"],
            },
            redaction="partial",
            external_run=AgentExternalRunRef(
                kind="workflow_capability",
                capability_key=invocation.capability_key,
                capability_run_id="caprun_1",
                status="completed",
                correlation_id=invocation.correlation_id,
            ),
        )


def test_workflow_capability_spec_is_pydantic_validated_contract() -> None:
    spec = WorkflowCapabilitySpec(
        key="report_review",
        tool_name="workflow.report_review",
        description="Run review.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level="write",
        required_scopes=["workflow.capability.report_review.invoke"],
        approval_policy="on_risk",
        metadata={"owner": "workbench"},
    )

    assert spec.model_dump(mode="json") == {
        "key": "report_review",
        "tool_name": "workflow.report_review",
        "description": "Run review.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "risk_level": "write",
        "required_scopes": ["workflow.capability.report_review.invoke"],
        "approval_policy": "on_risk",
        "failure_policy": "fail_run",
        "metadata": {"owner": "workbench"},
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "key": " ",
            "tool_name": "workflow.report_review",
            "input_schema": {"type": "object"},
            "required_scopes": ["workflow.capability.report_review.invoke"],
        },
        {
            "key": "report review",
            "tool_name": "workflow.report_review",
            "input_schema": {"type": "object"},
            "required_scopes": ["workflow.capability.report_review.invoke"],
        },
        {
            "key": "report_review",
            "tool_name": " ",
            "input_schema": {"type": "object"},
            "required_scopes": ["workflow.capability.report_review.invoke"],
        },
        {
            "key": "report_review",
            "tool_name": "workflow.report_review",
            "input_schema": {"type": "array"},
            "required_scopes": ["workflow.capability.report_review.invoke"],
        },
        {
            "key": "report_review",
            "tool_name": "workflow.report_review",
            "input_schema": {"type": "object"},
            "required_scopes": [" "],
        },
    ],
)
def test_workflow_capability_spec_rejects_invalid_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        WorkflowCapabilitySpec(
            description="Run review.",
            output_schema={"type": "object"},
            risk_level="write",
            approval_policy="on_risk",
            **kwargs,
        )


@pytest.mark.asyncio
async def test_workflow_capability_adapter_lists_and_invokes_provider_runs() -> None:
    provider = FakeWorkflowProvider()
    adapter = WorkflowCapabilityAdapter(provider)
    router = AithruCapabilityRouter(adapters=[adapter])
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        thread_id="thread_1",
        skill_id="skill_1",
        scopes=["workflow.capability.report_review.invoke"],
    )

    tools = await router.list_tools(context)
    result = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="workflow.report_review",
            input={"artifact_id": "artifact_1"},
            requested_by="model",
        ),
        context,
    )

    assert tools[0].kind is AgentToolKind.WORKFLOW_CAPABILITY
    assert tools[0].name == "workflow.report_review"
    assert tools[0].required_scopes == ["workflow.capability.report_review.invoke"]
    assert tools[0].failure_policy == "fail_run"
    assert result.status == "completed"
    assert result.output == {"accepted": True, "artifact_id": "artifact_1"}
    assert result.redaction == "partial"
    assert result.external_run == AgentExternalRunRef(
        kind="workflow_capability",
        capability_key="report_review",
        capability_run_id="caprun_1",
        status="completed",
        correlation_id="run_1:toolcall_1",
    )
    assert provider.invocations == [
        WorkflowCapabilityInvocation(
            tool_call_id="toolcall_1",
            tool_name="workflow.report_review",
            capability_key="report_review",
            input={"artifact_id": "artifact_1"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
            thread_id="thread_1",
            skill_id="skill_1",
            correlation_id="run_1:toolcall_1",
        )
    ]


@pytest.mark.asyncio
async def test_workflow_capability_adapter_respects_scopes_and_allowed_tools() -> None:
    adapter = WorkflowCapabilityAdapter(FakeWorkflowProvider())
    router = AithruCapabilityRouter(adapters=[adapter])
    base_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=[],
    )
    scoped_context = base_context.model_copy(
        update={"scopes": ["workflow.capability.report_review.invoke"]}
    )
    disallowed_context = base_context.model_copy(
        update={
            "scopes": ["workflow.capability.report_review.invoke"],
            "allowed_tools": ["workspace.read_file"],
        }
    )

    denied = await router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="workflow.report_review",
            input={"artifact_id": "artifact_1"},
            requested_by="model",
        ),
        base_context,
    )

    assert await router.list_tools(base_context) == []
    assert [tool.name for tool in await router.list_tools(scoped_context)] == [
        "workflow.report_review"
    ]
    assert await router.list_tools(disallowed_context) == []
    assert denied.status == "denied"
    assert denied.error == {
        "message": "Missing required scope: workflow.capability.report_review.invoke"
    }
