from typing import Any

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aithru_agent.agent.capabilities import AithruToolset
from aithru_agent.domain import AgentToolDescriptor


def _descriptor(*, name: str = "compat.echo") -> AgentToolDescriptor:
    return AgentToolDescriptor(
        name=name,
        kind="local_tool",
        description="Echo a value from the descriptor schema.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level="safe",
        required_scopes=[],
        approval_policy="never",
    )


def _ctx(deps: object = object()) -> RunContext[object]:
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage(), tool_call_id="tc_1")


@pytest.mark.asyncio
async def test_aithru_toolset_exposes_descriptors_as_pydantic_tools() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(ctx: RunContext[object], tool_name: str, tool_input: dict[str, Any]) -> object:
        del ctx
        calls.append((tool_name, tool_input))
        return {"ok": True, "input": tool_input}

    toolset = AithruToolset(
        tool_specs=[(_descriptor(), True)],
        tool_callback=call_tool,
    )
    ctx = _ctx()

    tools = await toolset.get_tools(ctx)
    tool = tools["compat.echo"]
    validated_args = tool.args_validator.validate_python({"value": "hello"})
    result = await toolset.call_tool("compat.echo", validated_args, ctx, tool)

    assert tool.tool_def.description == "Echo a value from the descriptor schema."
    assert tool.tool_def.parameters_json_schema["properties"]["value"]["type"] == "string"
    assert tool.tool_def.metadata == {
        "aithru.boundary": "capability_router",
        "aithru.requires_approval": True,
        "aithru.risk_level": "safe",
        "aithru.tool_kind": "local_tool",
        "aithru.tool_name": "compat.echo",
    }
    assert result == {"ok": True, "input": {"value": "hello"}}
    assert calls == [("compat.echo", {"value": "hello"})]


@pytest.mark.asyncio
async def test_pydantic_ai_agent_can_receive_tools_from_aithru_toolset() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(ctx: RunContext[object], tool_name: str, tool_input: dict[str, Any]) -> object:
        del ctx
        calls.append((tool_name, tool_input))
        return tool_input

    toolset = AithruToolset(
        tool_specs=[(_descriptor(), False)],
        tool_callback=call_tool,
    )
    agent = Agent(
        TestModel(call_tools=["compat.echo"], custom_output_text="done"),
        deps_type=object,
        output_type=str,
        toolsets=[toolset],
    )

    result = await agent.run("Call the tool.", deps=object())

    assert result.output == "done"
    assert calls == [("compat.echo", {"value": "a"})]
