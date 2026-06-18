import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ApprovalRequired
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RunUsage

from aithru_agent.agent.capabilities import AithruBoundaryCapability, AithruToolset
from aithru_agent.domain import AgentToolDescriptor


def _ctx(*, approved: bool = False) -> RunContext[object]:
    return RunContext(
        deps=object(),
        model=TestModel(),
        usage=RunUsage(),
        tool_call_id="tc_1",
        tool_call_approved=approved,
    )


def _tool_def(*, requires_approval: bool) -> ToolDefinition:
    return ToolDefinition(
        name="workspace.write_file",
        description="Write a workspace file.",
        parameters_json_schema={"type": "object"},
        metadata={
            "aithru.requires_approval": requires_approval,
            "aithru.tool_name": "workspace.write_file",
        },
    )


def test_boundary_capability_provides_aithru_toolset() -> None:
    toolset = AithruToolset(tool_specs=[], tool_callback=None)
    capability = AithruBoundaryCapability(toolset=toolset)

    assert capability.get_toolset() is toolset


@pytest.mark.asyncio
async def test_boundary_capability_marks_tools_as_aithru_boundary_tools() -> None:
    capability = AithruBoundaryCapability()
    tool_def = _tool_def(requires_approval=False)

    prepared = await capability.prepare_tools(_ctx(), [tool_def])

    assert prepared[0].metadata == {
        "aithru.boundary": "capability_router",
        "aithru.requires_approval": False,
        "aithru.tool_name": "workspace.write_file",
    }


@pytest.mark.asyncio
async def test_boundary_capability_defers_unapproved_approval_required_tools() -> None:
    capability = AithruBoundaryCapability()
    call = ToolCallPart(
        tool_name="workspace.write_file",
        args={"path": "/notes.md", "content": "hello"},
        tool_call_id="tc_1",
    )
    tool_def = _tool_def(requires_approval=True)

    with pytest.raises(ApprovalRequired):
        await capability.before_tool_execute(
            _ctx(approved=False),
            call=call,
            tool_def=tool_def,
            args={"path": "/notes.md", "content": "hello"},
        )

    approved_args = await capability.before_tool_execute(
        _ctx(approved=True),
        call=call,
        tool_def=tool_def,
        args={"path": "/notes.md", "content": "hello"},
    )

    assert approved_args == {"path": "/notes.md", "content": "hello"}


@pytest.mark.asyncio
async def test_boundary_capability_prevents_execution_until_pydantic_approval() -> None:
    calls: list[str] = []

    async def call_tool(ctx: RunContext[object], tool_name: str, tool_input: dict) -> object:
        del ctx, tool_input
        calls.append(tool_name)
        return {"status": "executed"}

    descriptor = AgentToolDescriptor(
        name="workspace.write_file",
        kind="local_tool",
        description="Write a workspace file.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        output_schema={"type": "object"},
        risk_level="write",
        required_scopes=[],
        approval_policy="always",
    )
    capability = AithruBoundaryCapability(
        toolset=AithruToolset(
            tool_specs=[(descriptor, True)],
            tool_callback=call_tool,
        ),
    )
    agent = Agent(
        TestModel(call_tools=["workspace.write_file"], custom_output_text="done"),
        deps_type=object,
        output_type=str | DeferredToolRequests,
        capabilities=[capability],
    )

    final_output: object | None = None
    async with agent.run_stream_events("Write a file.", deps=object()) as stream:
        async for event in stream:
            if isinstance(event, AgentRunResultEvent):
                final_output = event.result.output

    assert isinstance(final_output, DeferredToolRequests)
    assert [call.tool_name for call in final_output.approvals] == ["workspace.write_file"]
    assert calls == []
