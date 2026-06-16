import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import ToolPolicy
from aithru_agent.domain import AgentSandboxPolicy, AgentSkill
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.skills import InMemorySkillResolver


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

        assert run["status"] == "queued"
        await runtime.worker.drain()

        run_detail = (await client.get(f"/api/agent/runs/{run['id']}")).json()
        events = (await client.get(f"/api/agent/runs/{run['id']}/events")).json()
        trace = (await client.get(f"/api/agent/runs/{run['id']}/trace")).json()
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
    assert {span["kind"] for span in trace} >= {"run", "model", "tool", "workspace", "artifact"}
    assert next(span for span in trace if span["kind"] == "run")["status"] == "completed"
    assert "event: run.completed" in stream.text
    assert files[0]["path"] == "/reports/report.md"
    assert file_content["content"] == "# Report\nDone.\n"
    assert artifacts[0]["type"] == "report"


@pytest.mark.asyncio
async def test_agent_api_returns_run_snapshot_for_inspection() -> None:
    runtime = create_agent_runtime(driver=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Write report", "scopes": ["*"]},
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(f"/api/agent/runs/{run['id']}/snapshot")

    snapshot = response.json()

    assert response.status_code == 200
    assert snapshot["run"]["id"] == run["id"]
    assert snapshot["run"]["status"] == "completed"
    assert [event["type"] for event in snapshot["events"]][-1] == "run.completed"
    assert {span["kind"] for span in snapshot["trace"]} >= {
        "run",
        "message",
        "model",
        "tool",
        "todo",
        "workspace",
        "artifact",
    }
    assert snapshot["todos"][0]["title"] == "Write report"
    assert snapshot["artifacts"][0]["type"] == "report"
    assert snapshot["workspace_files"][0]["path"] == "/reports/report.md"
    assert snapshot["approvals"] == []
    assert snapshot["subagents"] == []


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
        await runtime.worker.drain()
        approvals = (await client.get("/api/agent/approvals")).json()
        resolved = await client.post(
            f"/api/agent/approvals/{approvals[0]['id']}/resolve",
            json={"decision": "approved", "comment": "ok"},
        )
        run_detail = (await client.get(f"/api/agent/runs/{run['id']}")).json()

    assert run["status"] == "queued"
    assert approvals[0]["status"] == "pending"
    assert resolved.status_code == 200
    assert run_detail["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_api_run_resume_uses_current_approval() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Write report", "scopes": ["*"]},
            )
        ).json()
        await runtime.worker.drain()
        paused = (await client.get(f"/api/agent/runs/{run['id']}")).json()
        resumed = await client.post(
            f"/api/agent/runs/{run['id']}/resume",
            json={"decision": "approved", "comment": "ok"},
        )
        run_detail = (await client.get(f"/api/agent/runs/{run['id']}")).json()

    assert paused["status"] == "waiting_approval"
    assert paused["current_approval_id"] is not None
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert run_detail["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_api_run_resume_rejects_run_without_current_approval() -> None:
    runtime = create_agent_runtime(driver=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Write report", "scopes": ["*"]},
            )
        ).json()
        response = await client.post(
            f"/api/agent/runs/{run['id']}/resume",
            json={"decision": "approved"},
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_agent_api_validates_create_run_body() -> None:
    app = create_app(create_agent_runtime(driver=file_report_driver()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/agent/runs", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_api_lists_and_gets_published_skills() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Read files and write a report.",
        allowed_tools=["workspace.read_file"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        skills = (await client.get("/api/agent/skills")).json()
        by_key = (await client.get("/api/agent/skills/file-report")).json()
        by_id = (await client.get("/api/agent/skills/skill_1")).json()
        missing = await client.get("/api/agent/skills/missing")

    assert skills == [skill.model_dump(mode="json")]
    assert by_key["id"] == "skill_1"
    assert by_id["key"] == "file-report"
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_agent_api_lists_run_tools_filtered_by_skill_policy() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Only list files.",
        allowed_tools=["workspace.list_files"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "List files",
                    "scopes": ["*"],
                    "skill_id": "file-report",
                },
            )
        ).json()
        tools_response = await client.get(f"/api/agent/runs/{run['id']}/tools")
        tools = tools_response.json()

    assert tools_response.status_code == 200
    assert [tool["name"] for tool in tools] == ["workspace.list_files"]
    assert tools[0]["kind"] == "local_tool"


@pytest.mark.asyncio
async def test_agent_api_hides_sandbox_tools_when_skill_disables_sandbox() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="no-sandbox",
        name="No Sandbox",
        instructions="Do not execute code.",
        allowed_tools=["sandbox.run_python"],
        allowed_subagents=[],
        sandbox_policy=AgentSandboxPolicy(enabled=False),
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Try code.",
                    "scopes": ["*"],
                    "skill_id": "no-sandbox",
                },
            )
        ).json()
        tools_response = await client.get(f"/api/agent/runs/{run['id']}/tools")

    assert tools_response.status_code == 200
    assert [tool["name"] for tool in tools_response.json()] == []


@pytest.mark.asyncio
async def test_agent_api_creates_and_lists_memory_entries() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/agent/memory",
            json={
                "org_id": "org_1",
                "scope": "user",
                "scope_id": "user_1",
                "key": "preference.language",
                "value": "Prefers Chinese summaries.",
            },
        )
        listed = (
            await client.get(
                "/api/agent/memory",
                params={"org_id": "org_1", "scope": "user", "query": "Chinese"},
            )
        ).json()

    created = created_response.json()

    assert created_response.status_code == 201
    assert created["key"] == "preference.language"
    assert [entry["id"] for entry in listed] == [created["id"]]
