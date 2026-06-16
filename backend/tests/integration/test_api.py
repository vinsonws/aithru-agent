import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import ToolPolicy
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep


def file_report_driver() -> ScriptedHarnessDriver:
    return ScriptedHarnessDriver(
        [
            ScriptedStep.message("I will write the report.\n"),
            ScriptedStep.tool("todo.create", {"title": "Write report", "status": "running"}),
            ScriptedStep.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\nDone.\n", "media_type": "text/markdown"},
            ),
            ScriptedStep.tool(
                "artifact.create",
                {
                    "type": "report",
                    "name": "Report",
                    "uri": "/reports/report.md",
                    "content": {"path": "/reports/report.md"},
                },
            ),
            ScriptedStep.finish(),
        ]
    )


@pytest.mark.asyncio
async def test_agent_api_threads_runs_events_stream_workspace_and_artifacts() -> None:
    runtime = create_agent_runtime(driver=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/api/agent/health")
        thread_response = await client.post(
            "/api/agent/threads",
            json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Work"},
        )
        thread = thread_response.json()
        message_response = await client.post(
            f"/api/agent/threads/{thread['id']}/messages",
            json={"role": "user", "content": "Please write a report"},
        )
        run_response = await client.post(
            "/api/agent/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "thread_id": thread["id"],
                "goal": "Write report",
                "scopes": ["*"],
            },
        )
        run = run_response.json()
        run_detail = (await client.get(f"/api/agent/runs/{run['id']}")).json()
        events = (await client.get(f"/api/agent/runs/{run['id']}/events")).json()
        stream = await client.get(f"/api/agent/runs/{run['id']}/stream")
        files = (await client.get(f"/api/agent/workspaces/{run['workspace_id']}/files")).json()
        file_content = (
            await client.get(f"/api/agent/workspaces/{run['workspace_id']}/files/reports/report.md")
        ).json()
        artifacts = (await client.get("/api/agent/artifacts", params={"run_id": run["id"]})).json()

    assert health.json() == {"ok": True, "service": "aithru-agent-backend"}
    assert thread_response.status_code == 201
    assert message_response.status_code == 201
    assert run_response.status_code == 201
    assert run_detail["status"] == "completed"
    assert [event["type"] for event in events][-1] == "run.completed"
    assert "event: run.completed" in stream.text
    assert files[0]["path"] == "/reports/report.md"
    assert file_content["content"] == "# Report\nDone.\n"
    assert artifacts[0]["type"] == "report"


@pytest.mark.asyncio
async def test_agent_api_resolves_approval_and_resumes_run() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run_response = await client.post(
            "/api/agent/runs",
            json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Write report", "scopes": ["*"]},
        )
        run = run_response.json()
        approvals = (await client.get("/api/agent/approvals")).json()
        resolved = await client.post(
            f"/api/agent/approvals/{approvals[0]['id']}/resolve",
            json={"decision": "approved", "comment": "ok"},
        )
        run_detail = (await client.get(f"/api/agent/runs/{run['id']}")).json()

    assert run["status"] == "waiting_approval"
    assert approvals[0]["status"] == "pending"
    assert resolved.status_code == 200
    assert run_detail["status"] == "completed"
