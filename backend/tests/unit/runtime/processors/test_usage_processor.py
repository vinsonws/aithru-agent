import pytest

from aithru_agent.domain import AgentRunBudgetPolicy, AgentRunHarnessOptions, AgentRunSource
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.usage import (
    build_run_tree_usage_snapshot,
    build_run_usage_summary,
)
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_model_usage_events_project_into_direct_run_summary() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        goal="Track usage",
        workspace_id=workspace.id,
    )
    await writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="message.created",
        source={"kind": "harness"},
        payload={"ignored": True},
    )
    await writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={
            "requests": 1,
            "input_tokens": 12,
            "output_tokens": 3,
            "total_tokens": 15,
        },
    )

    summary = await build_run_usage_summary(run, event_store)

    assert summary.run_id == run.id
    assert summary.own_requests == 1
    assert summary.own_input_tokens == 12
    assert summary.own_output_tokens == 3
    assert summary.own_total_tokens == 15
    assert summary.descendant_requests == 0
    assert summary.total_requests == 1
    assert summary.total_tokens == 15


@pytest.mark.asyncio
async def test_subagent_child_run_usage_rolls_up_into_root_descendant_counters() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    root = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        goal="Root task",
        workspace_id=workspace.id,
    )
    child = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.DELEGATED_TASK,
        goal="Child task",
        workspace_id=workspace.id,
    )
    await store.create_subagent_run(
        org_id="org_1",
        parent_run_id=root.id,
        child_run_id=child.id,
        name="Researcher",
        task="Research",
    )
    await writer.write(
        run_id=root.id,
        thread_id=root.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 1, "input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
    )
    await writer.write(
        run_id=child.id,
        thread_id=child.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 2, "input_tokens": 20, "output_tokens": 4, "total_tokens": 24},
    )

    snapshot = await build_run_tree_usage_snapshot(root, store, event_store)
    root_summary = next(summary for summary in snapshot.runs if summary.run_id == root.id)
    child_summary = next(summary for summary in snapshot.runs if summary.run_id == child.id)

    assert [summary.run_id for summary in snapshot.runs] == [root.id, child.id]
    assert root_summary.own_requests == 1
    assert root_summary.descendant_requests == 2
    assert root_summary.descendant_input_tokens == 20
    assert root_summary.descendant_output_tokens == 4
    assert root_summary.descendant_total_tokens == 24
    assert root_summary.total_requests == 3
    assert root_summary.total_tokens == 32
    assert child_summary.descendant_requests == 0
    assert snapshot.total_requests == 3
    assert snapshot.total_tokens == 32


@pytest.mark.asyncio
async def test_tree_budget_status_chooses_worst_status() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    root = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        goal="Root task",
        workspace_id=workspace.id,
        harness_options=AgentRunHarnessOptions(
            budget_policy=AgentRunBudgetPolicy(max_total_tokens=30)
        ),
    )
    child = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.DELEGATED_TASK,
        goal="Child task",
        workspace_id=workspace.id,
        harness_options=AgentRunHarnessOptions(
            budget_policy=AgentRunBudgetPolicy(max_total_tokens=40)
        ),
    )
    await store.create_subagent_run(
        org_id="org_1",
        parent_run_id=root.id,
        child_run_id=child.id,
        name="Researcher",
        task="Research",
    )
    await writer.write(
        run_id=root.id,
        thread_id=root.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 1, "total_tokens": 8},
    )
    await writer.write(
        run_id=child.id,
        thread_id=child.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 1, "total_tokens": 35},
    )

    snapshot = await build_run_tree_usage_snapshot(root, store, event_store)
    root_summary = next(summary for summary in snapshot.runs if summary.run_id == root.id)
    child_summary = next(summary for summary in snapshot.runs if summary.run_id == child.id)

    assert root_summary.budget_status == "exceeded"
    assert root_summary.warnings == ["total_tokens_exceeded"]
    assert child_summary.budget_status == "warning"
    assert child_summary.warnings == ["total_tokens_near_limit"]
    assert snapshot.budget_status == "exceeded"
    assert snapshot.warnings == ["total_tokens_exceeded", "total_tokens_near_limit"]
