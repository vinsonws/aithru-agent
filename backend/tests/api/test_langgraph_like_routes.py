import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
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


@pytest.mark.asyncio
async def test_threads_runs_join_stream_routes_keep_agent_compatibility() -> None:
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
                "goal": "Write report",
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
        legacy = (await client.get(f"/api/agent/runs/{run['id']}")).json()

    assert [item["id"] for item in thread_runs] == [run["id"]]
    assert run_detail["status"] == "completed"
    assert joined["status"] == "completed"
    assert joined["result"]["content"] == "I will write the report.\n"
    assert events[-1]["type"] == "run.completed"
    assert "event: run.completed" in stream.text
    assert legacy["id"] == run["id"]


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
        runs = (await client.get("/api/agent/runs")).json()

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: run.created" in stream.text
    assert "event: run.completed" in stream.text
    assert runs[0]["status"] == "completed"
