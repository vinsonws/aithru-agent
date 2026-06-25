import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime, PydanticAgentDeps
from aithru_agent.agent.capabilities import AithruBoundaryCapability, AithruToolset
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import WorkspaceLocalTool
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


async def _deps() -> PydanticAgentDeps:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="List files.",
        workspace_id=workspace.id,
    )
    return PydanticAgentDeps(
        run=run,
        run_context=AgentRunContext(
            run_id=run.id,
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id=workspace.id,
            scopes=["*"],
        ),
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[WorkspaceLocalTool(store)],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        store=store,
    )


@pytest.mark.asyncio
async def test_runtime_builds_agent_with_aithru_boundary_toolset() -> None:
    runtime = AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done"))

    agent = await runtime.build_agent(await _deps())

    root_capabilities = getattr(getattr(agent, "_root_capability"), "capabilities")
    capability_toolsets = getattr(agent, "_cap_toolsets")
    direct_function_tools = getattr(agent, "_function_toolset").tools

    assert any(
        isinstance(capability, AithruBoundaryCapability)
        for capability in root_capabilities
    )
    assert any(_contains_aithru_toolset(toolset) for toolset in capability_toolsets)
    assert direct_function_tools == {}


def _contains_aithru_toolset(toolset: object) -> bool:
    if isinstance(toolset, AithruToolset):
        return True
    wrapped = getattr(toolset, "wrapped", None)
    if wrapped is not None and _contains_aithru_toolset(wrapped):
        return True
    return any(
        _contains_aithru_toolset(child)
        for child in getattr(toolset, "toolsets", [])
    )


def _aithru_toolsets(toolset: object) -> list[AithruToolset]:
    if isinstance(toolset, AithruToolset):
        return [toolset]
    wrapped = getattr(toolset, "wrapped", None)
    if wrapped is not None:
        return _aithru_toolsets(wrapped)
    found: list[AithruToolset] = []
    for child in getattr(toolset, "toolsets", []):
        found.extend(_aithru_toolsets(child))
    return found


@pytest.mark.asyncio
async def test_runtime_builds_dynamic_aithru_toolset_for_loaded_skill_policy() -> None:
    runtime = AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done"))

    agent = await runtime.build_agent(await _deps())

    capability_toolsets = getattr(agent, "_cap_toolsets")
    toolsets = [
        toolset
        for capability_toolset in capability_toolsets
        for toolset in _aithru_toolsets(capability_toolset)
    ]

    assert toolsets
    assert all(toolset.tool_specs is None for toolset in toolsets)
