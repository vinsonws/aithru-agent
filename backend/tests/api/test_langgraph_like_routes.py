import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.api.main import create_app
from aithru_agent.api.routes.runs import _run_live_stream_response
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from tests.utils.step_runtime import Step, StepAgentRuntime


def file_report_driver() -> StepAgentRuntime:
    return StepAgentRuntime(
        [
            Step.message("I will write the report.\n"),
            Step.tool(
                "workspace.write_file",
                {
                    "path": "/reports/report.md",
                    "content": "# Report\nDone.\n",
                    "media_type": "text/markdown",
                },
            ),
            Step.finish(),
        ]
    )


class SlowStreamingRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": "msg_1", "role": "assistant"},
        )
        await asyncio.sleep(0.2)
        return AgentRuntimeResult(content="slow done")


@pytest.mark.asyncio
async def test_threads_runs_join_stream_routes() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread_response = await client.post(
            "/api/threads",
            json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Work"},
        )
        assert thread_response.status_code == 201
        thread = thread_response.json()
        message_response = await client.post(
            f"/api/threads/{thread['id']}/messages",
            json={"role": "user", "content": "Please write a report"},
        )
        run_response = await client.post(
            f"/api/threads/{thread['id']}/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "goal": "Write the report draft",
                "scopes": ["*"],
            },
        )
        run = run_response.json()

        assert message_response.status_code == 201
        assert run_response.status_code == 201
        assert run["thread_id"] == thread["id"]
        assert run["status"] == "queued"

        await runtime.worker.drain()

        thread_runs = (await client.get(f"/api/threads/{thread['id']}/runs")).json()
        run_detail = (await client.get(f"/api/threads/{thread['id']}/runs/{run['id']}")).json()
        events = (await client.get(f"/api/threads/{thread['id']}/runs/{run['id']}/events")).json()
        stream = await client.get(f"/api/threads/{thread['id']}/runs/{run['id']}/stream")
        joined = (await client.get(f"/api/threads/{thread['id']}/runs/{run['id']}/join")).json()

    assert [item["id"] for item in thread_runs] == [run["id"]]
    assert thread_runs[0]["summary"]["health"] == "completed"
    assert run_detail["status"] == "completed"
    assert run_detail["summary"]["health"] == "completed"
    assert run_detail["summary"]["needs_attention"] is False
    assert joined["status"] == "completed"
    assert joined["result"]["content"] == "I will write the report.\n"
    assert events[-1]["type"] == "run.completed"
    assert "event: run.completed" in stream.text


@pytest.mark.asyncio
async def test_thread_runs_support_status_and_summary_filters() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Work"},
            )
        ).json()
        completed_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Complete the report draft",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        queued_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Queued report",
                    "scopes": ["*"],
                },
            )
        ).json()

        completed = (
            await client.get(
                f"/api/threads/{thread['id']}/runs",
                params={"status": "completed", "health": "completed", "needs_attention": False},
            )
        ).json()
        queued = (
            await client.get(
                f"/api/threads/{thread['id']}/runs",
                params={"status": "queued"},
            )
        ).json()

    assert [run["id"] for run in completed] == [completed_run["id"]]
    assert completed[0]["summary"]["needs_attention"] is False
    assert [run["id"] for run in queued] == [queued_run["id"]]


@pytest.mark.asyncio
async def test_thread_runs_support_pagination_and_ordering() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Work"},
            )
        ).json()
        first = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "First"},
            )
        ).json()
        second = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Second"},
            )
        ).json()
        third = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Third"},
            )
        ).json()

        page = (
            await client.get(
                f"/api/threads/{thread['id']}/runs",
                params={
                    "order_by": "started_at",
                    "order_direction": "desc",
                    "offset": 1,
                    "limit": 2,
                },
            )
        ).json()

    assert [run["id"] for run in page] == [second["id"], first["id"]]
    assert third["id"] not in [run["id"] for run in page]


@pytest.mark.asyncio
async def test_thread_runs_can_include_pagination_metadata() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Work"},
            )
        ).json()
        first = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "First"},
            )
        ).json()
        second = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Second"},
            )
        ).json()

        page = (
            await client.get(
                f"/api/threads/{thread['id']}/runs",
                params={
                    "include_meta": True,
                    "order_by": "started_at",
                    "order_direction": "desc",
                    "limit": 1,
                },
            )
        ).json()

    assert [run["id"] for run in page["items"]] == [second["id"]]
    assert page["total"] == 2
    assert page["count"] == 1
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert first["id"] not in [run["id"] for run in page["items"]]


@pytest.mark.asyncio
async def test_runs_reject_invalid_pagination_params() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        invalid_limit = await client.get("/api/runs", params={"limit": 0})
        invalid_order = await client.get("/api/runs", params={"order_by": "goal"})

    assert invalid_limit.status_code == 422
    assert invalid_order.status_code == 422


@pytest.mark.asyncio
async def test_app_does_not_register_legacy_agent_routes() -> None:
    app = create_app(create_agent_runtime(agent_runtime=file_report_driver()))

    registered_paths = {
        path
        for route in app.routes
        for path in (getattr(route, "path", None), getattr(route, "path_format", None))
        if path is not None
    }

    legacy_prefix = "/api/" + "agent"

    assert all(not path.startswith(legacy_prefix) for path in registered_paths)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"{legacy_prefix}/health")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_runs_stream_creates_and_streams_completed_run() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stream = await client.post(
            "/api/runs/stream",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "goal": "Write report",
                "scopes": ["*"],
            },
        )
        runs = (await client.get("/api/runs")).json()

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: run.created" in stream.text
    assert "event: run.completed" in stream.text
    assert runs[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_runs_stream_emits_events_while_run_is_still_active() -> None:
    runtime = create_agent_runtime(agent_runtime=SlowStreamingRuntime())
    app = create_app(runtime)
    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Slow stream",
        scopes=["*"],
    )
    response = _run_live_stream_response(queued.id, app.state.aithru_api)
    iterator = response.body_iterator.__aiter__()

    early_chunks: list[str] = []
    while "event: run.started" not in "".join(early_chunks):
        chunk = await asyncio.wait_for(iterator.__anext__(), timeout=0.1)
        early_chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    running = await runtime.store.get_run(queued.id)
    remaining_chunks: list[str] = []
    while True:
        try:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=1)
        except StopAsyncIteration:
            break
        remaining_chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    early_text = "".join(early_chunks)
    full_text = early_text + "".join(remaining_chunks)

    assert response.media_type == "text/event-stream"
    assert running.status == AgentRunStatus.RUNNING
    assert "event: run.created" in early_text
    assert "event: run.started" in early_text
    assert "event: run.completed" not in early_text
    assert "event: run.completed" in full_text
