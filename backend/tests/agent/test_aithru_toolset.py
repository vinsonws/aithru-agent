from typing import Any
from types import SimpleNamespace
from datetime import UTC, datetime

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aithru_agent.agent.capabilities import AithruToolset
from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import WorkspaceLocalTool
from aithru_agent.domain import AgentRun, AgentRunStatus
from aithru_agent.domain import AgentToolDescriptor
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


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
async def test_aithru_toolset_can_expose_openai_compatible_tool_names() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(ctx: RunContext[object], tool_name: str, tool_input: dict[str, Any]) -> object:
        del ctx
        calls.append((tool_name, tool_input))
        return {"ok": True}

    deps = SimpleNamespace(tool_name_aliases={})
    toolset = AithruToolset(
        tool_specs=[(_descriptor(name="workspace.read_file"), False)],
        tool_callback=call_tool,
        expose_safe_tool_names=True,
    )
    ctx = _ctx(deps=deps)

    tools = await toolset.get_tools(ctx)
    tool = tools["workspace_read_file"]
    validated_args = tool.args_validator.validate_python({"value": "hello"})
    result = await toolset.call_tool("workspace_read_file", validated_args, ctx, tool)

    assert "workspace.read_file" not in tools
    assert tool.tool_def.name == "workspace_read_file"
    assert tool.tool_def.metadata["aithru.tool_name"] == "workspace.read_file"
    assert deps.tool_name_aliases == {"workspace_read_file": "workspace.read_file"}
    assert result == {"ok": True}
    assert calls == [("workspace.read_file", {"value": "hello"})]


@pytest.mark.asyncio
async def test_aithru_toolset_describes_workspace_allowed_paths() -> None:
    store = InMemoryAgentStore()
    run = AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="write html",
        workspace_id="ws_1",
        scopes=["*"],
        status=AgentRunStatus.RUNNING,
        started_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    deps = PydanticAgentDeps(
        run=run,
        run_context=AgentRunContext(
            run_id=run.id,
            org_id=run.org_id,
            actor_user_id=run.actor_user_id,
            workspace_id=run.workspace_id,
            scopes=["agent.workspace.write"],
            workspace_allowed_paths=["/workspace", "/outputs"],
        ),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=AithruCapabilityRouter(
            adapters=[WorkspaceLocalTool(store)],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        store=store,
    )
    toolset = AithruToolset()
    ctx = _ctx(deps=deps)

    tools = await toolset.get_tools(ctx)
    path_schema = tools["workspace.write_file"].tool_def.parameters_json_schema["properties"]["path"]

    assert "description" in path_schema
    assert "/workspace" in path_schema["description"]
    assert "/outputs" in path_schema["description"]


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
