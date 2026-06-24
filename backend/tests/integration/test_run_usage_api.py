import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunSource


@pytest.mark.asyncio
async def test_get_run_usage_projects_model_usage_events() -> None:
    runtime = create_agent_runtime()
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        task_msg="Track usage",
        workspace_id=workspace.id,
    )
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={
            "requests": 2,
            "input_tokens": 18,
            "output_tokens": 4,
            "total_tokens": 22,
        },
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{run.id}/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run.id
    assert payload["own_requests"] == 2
    assert payload["own_input_tokens"] == 18
    assert payload["own_output_tokens"] == 4
    assert payload["own_total_tokens"] == 22
    assert payload["total_requests"] == 2
    assert payload["total_tokens"] == 22


@pytest.mark.asyncio
async def test_thread_scoped_run_usage_route_enforces_thread_run_relationship() -> None:
    runtime = create_agent_runtime()
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Usage",
    )
    other_thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Other",
    )
    workspace = await runtime.store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        task_msg="Track usage",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 1, "total_tokens": 9},
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/threads/{thread.id}/runs/{run.id}/usage")
        wrong_thread_response = await client.get(
            f"/api/threads/{other_thread.id}/runs/{run.id}/usage"
        )

    assert response.status_code == 200
    assert response.json()["total_tokens"] == 9
    assert wrong_thread_response.status_code == 404


@pytest.mark.asyncio
async def test_tree_usage_route_includes_subagent_child_usage() -> None:
    runtime = create_agent_runtime()
    workspace = await runtime.store.create_workspace(org_id="org_1")
    root = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        task_msg="Root task",
        workspace_id=workspace.id,
    )
    child = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.DELEGATED_TASK,
        task_msg="Child task",
        workspace_id=workspace.id,
    )
    await runtime.store.create_subagent_run(
        org_id="org_1",
        parent_run_id=root.id,
        child_run_id=child.id,
        name="Researcher",
        task="Research",
    )
    await runtime.event_writer.write(
        run_id=root.id,
        thread_id=root.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 1, "total_tokens": 6},
    )
    await runtime.event_writer.write(
        run_id=child.id,
        thread_id=child.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 2, "total_tokens": 14},
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{root.id}/tree/usage")

    assert response.status_code == 200
    payload = response.json()
    root_usage = next(summary for summary in payload["runs"] if summary["run_id"] == root.id)
    child_usage = next(summary for summary in payload["runs"] if summary["run_id"] == child.id)
    assert [summary["run_id"] for summary in payload["runs"]] == [root.id, child.id]
    assert root_usage["own_requests"] == 1
    assert root_usage["descendant_requests"] == 2
    assert root_usage["total_requests"] == 3
    assert root_usage["total_tokens"] == 20
    assert child_usage["own_requests"] == 2
    assert payload["total_requests"] == 3
    assert payload["total_tokens"] == 20


@pytest.mark.asyncio
async def test_thread_scoped_tree_usage_route_enforces_thread_run_relationship() -> None:
    runtime = create_agent_runtime()
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Usage",
    )
    other_thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Other",
    )
    workspace = await runtime.store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        task_msg="Track usage",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=run.thread_id,
        type="model.usage",
        source={"kind": "model"},
        payload={"requests": 1, "total_tokens": 7},
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/threads/{thread.id}/runs/{run.id}/tree/usage")
        wrong_thread_response = await client.get(
            f"/api/threads/{other_thread.id}/runs/{run.id}/tree/usage"
        )

    assert response.status_code == 200
    assert response.json()["total_tokens"] == 7
    assert wrong_thread_response.status_code == 404
