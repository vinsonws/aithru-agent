import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import ToolPolicy
from aithru_agent.domain import AgentSandboxPolicy, AgentSkill
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.settings import AgentSettings
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
async def test_agent_api_follow_stream_waits_for_new_run_events() -> None:
    runtime = create_agent_runtime(driver=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Write report", "scopes": ["*"]},
            )
        ).json()
        stream_task = asyncio.create_task(
            client.get(
                f"/api/agent/runs/{run['id']}/stream",
                params={
                    "after_sequence": 1,
                    "follow": True,
                    "poll_interval_seconds": 0.01,
                    "timeout_seconds": 2,
                },
            )
        )
        await asyncio.sleep(0.05)
        assert not stream_task.done()
        await runtime.worker.drain()
        stream = await stream_task

    assert stream.status_code == 200
    assert "event: run.started" in stream.text
    assert "event: run.completed" in stream.text


@pytest.mark.asyncio
async def test_agent_api_requires_bearer_token_when_configured() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/api/agent/health")
        missing = await client.post(
            "/api/agent/threads",
            json={"org_id": "org_1", "owner_user_id": "user_1"},
        )
        wrong = await client.post(
            "/api/agent/threads",
            headers={"Authorization": "Bearer wrong"},
            json={"org_id": "org_1", "owner_user_id": "user_1"},
        )
        authorized = await client.post(
            "/api/agent/threads",
            headers={"Authorization": "Bearer secret-token"},
            json={"org_id": "org_1", "owner_user_id": "user_1"},
        )

    assert health.status_code == 200
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"] == "Unauthorized"
    assert wrong.json()["detail"] == "Unauthorized"
    assert authorized.status_code == 201


@pytest.mark.asyncio
async def test_agent_api_binds_run_scopes_to_configured_token_scopes() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(
            api_token="secret-token",
            api_scopes=["agent.workspace.read"],
        ),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inherited = await client.post(
            "/api/agent/runs",
            headers={"Authorization": "Bearer secret-token"},
            json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Read only"},
        )
        escalated = await client.post(
            "/api/agent/runs",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "goal": "Escalate",
                "scopes": ["*"],
            },
        )
        runs = (await client.get(
            "/api/agent/runs",
            headers={"Authorization": "Bearer secret-token"},
        )).json()

    assert inherited.status_code == 201
    assert inherited.json()["scopes"] == ["agent.workspace.read"]
    assert escalated.status_code == 403
    assert escalated.json()["detail"] == "Requested scopes exceed API token scopes"
    assert [run["goal"] for run in runs] == ["Read only"]


@pytest.mark.asyncio
async def test_agent_api_binds_run_identity_to_trusted_headers() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_from_header",
        "X-Aithru-User-Id": "user_from_header",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inherited = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={"goal": "Use trusted identity"},
        )
        conflicting = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={
                "org_id": "org_from_body",
                "actor_user_id": "user_from_header",
                "goal": "Conflict",
            },
        )
        runs = (await client.get("/api/agent/runs", headers=headers)).json()

    assert inherited.status_code == 201
    assert inherited.json()["org_id"] == "org_from_header"
    assert inherited.json()["actor_user_id"] == "user_from_header"
    assert conflicting.status_code == 403
    assert conflicting.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [run["goal"] for run in runs] == ["Use trusted identity"]


@pytest.mark.asyncio
async def test_agent_api_binds_thread_identity_to_trusted_headers() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_from_header",
        "X-Aithru-User-Id": "user_from_header",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inherited = await client.post(
            "/api/agent/threads",
            headers=headers,
            json={"title": "Trusted"},
        )
        conflicting = await client.post(
            "/api/agent/threads",
            headers=headers,
            json={"org_id": "org_from_header", "owner_user_id": "user_from_body"},
        )
        threads = (await client.get("/api/agent/threads", headers=headers)).json()

    assert inherited.status_code == 201
    assert inherited.json()["org_id"] == "org_from_header"
    assert inherited.json()["owner_user_id"] == "user_from_header"
    assert conflicting.status_code == 403
    assert conflicting.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [thread["title"] for thread in threads] == ["Trusted"]


@pytest.mark.asyncio
async def test_agent_api_filters_threads_by_trusted_identity_headers() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_thread = (
            await client.post("/api/agent/threads", headers=user_a_headers, json={"title": "User A"})
        ).json()
        user_b_thread = (
            await client.post("/api/agent/threads", headers=user_b_headers, json={"title": "User B"})
        ).json()
        user_a_threads = (await client.get("/api/agent/threads", headers=user_a_headers)).json()
        hidden_thread = await client.get(f"/api/agent/threads/{user_b_thread['id']}", headers=user_a_headers)
        hidden_messages = await client.get(
            f"/api/agent/threads/{user_b_thread['id']}/messages",
            headers=user_a_headers,
        )
        hidden_append = await client.post(
            f"/api/agent/threads/{user_b_thread['id']}/messages",
            headers=user_a_headers,
            json={"role": "user", "content": "should not write"},
        )
        visible_thread = await client.get(f"/api/agent/threads/{user_a_thread['id']}", headers=user_a_headers)

    assert [thread["id"] for thread in user_a_threads] == [user_a_thread["id"]]
    assert hidden_thread.status_code == 404
    assert hidden_thread.json()["detail"] == "Thread not found"
    assert hidden_messages.status_code == 404
    assert hidden_messages.json()["detail"] == "Thread not found"
    assert hidden_append.status_code == 404
    assert hidden_append.json()["detail"] == "Thread not found"
    assert visible_thread.status_code == 200
    assert visible_thread.json()["id"] == user_a_thread["id"]


@pytest.mark.asyncio
async def test_agent_api_filters_runs_by_trusted_identity_headers() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/agent/runs", headers=user_a_headers, json={"goal": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/agent/runs", headers=user_b_headers, json={"goal": "User B"})
        ).json()
        user_a_runs = (await client.get("/api/agent/runs", headers=user_a_headers)).json()
        hidden_run = await client.get(f"/api/agent/runs/{user_b_run['id']}", headers=user_a_headers)
        hidden_events = await client.get(f"/api/agent/runs/{user_b_run['id']}/events", headers=user_a_headers)
        visible_run = await client.get(f"/api/agent/runs/{user_a_run['id']}", headers=user_a_headers)

    assert [run["id"] for run in user_a_runs] == [user_a_run["id"]]
    assert hidden_run.status_code == 404
    assert hidden_run.json()["detail"] == "Run not found"
    assert hidden_events.status_code == 404
    assert hidden_events.json()["detail"] == "Run not found"
    assert visible_run.status_code == 200
    assert visible_run.json()["id"] == user_a_run["id"]


@pytest.mark.asyncio
async def test_agent_api_rejects_run_with_thread_outside_trusted_identity() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_b_thread = (
            await client.post("/api/agent/threads", headers=user_b_headers, json={"title": "User B"})
        ).json()
        response = await client.post(
            "/api/agent/runs",
            headers=user_a_headers,
            json={"thread_id": user_b_thread["id"], "goal": "Attach elsewhere"},
        )
        runs = (await client.get("/api/agent/runs", headers=user_a_headers)).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_filters_approvals_by_trusted_run_identity() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/agent/runs", headers=user_a_headers, json={"goal": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/agent/runs", headers=user_b_headers, json={"goal": "User B"})
        ).json()
        await runtime.worker.drain()
        user_a_run = (await client.get(f"/api/agent/runs/{user_a_run['id']}", headers=user_a_headers)).json()
        user_b_run = (await client.get(f"/api/agent/runs/{user_b_run['id']}", headers=user_b_headers)).json()
        user_a_approvals = (await client.get("/api/agent/approvals", headers=user_a_headers)).json()
        visible_approval = await client.get(
            f"/api/agent/approvals/{user_a_run['current_approval_id']}",
            headers=user_a_headers,
        )
        hidden_approval = await client.get(
            f"/api/agent/approvals/{user_b_run['current_approval_id']}",
            headers=user_a_headers,
        )
        hidden_resolve = await client.post(
            f"/api/agent/approvals/{user_b_run['current_approval_id']}/resolve",
            headers=user_a_headers,
            json={"decision": "approved"},
        )

    assert [approval["id"] for approval in user_a_approvals] == [user_a_run["current_approval_id"]]
    assert visible_approval.status_code == 200
    assert visible_approval.json()["id"] == user_a_run["current_approval_id"]
    assert hidden_approval.status_code == 404
    assert hidden_approval.json()["detail"] == "Approval not found"
    assert hidden_resolve.status_code == 404
    assert hidden_resolve.json()["detail"] == "Approval not found"


@pytest.mark.asyncio
async def test_agent_api_filters_artifacts_by_trusted_run_identity() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/agent/runs", headers=user_a_headers, json={"goal": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/agent/runs", headers=user_b_headers, json={"goal": "User B"})
        ).json()
        await runtime.worker.drain()
        user_a_artifacts = (await client.get("/api/agent/artifacts", headers=user_a_headers)).json()
        user_b_artifacts = (
            await client.get(
                "/api/agent/artifacts",
                headers=user_b_headers,
                params={"run_id": user_b_run["id"]},
            )
        ).json()
        hidden_artifact = await client.get(
            f"/api/agent/artifacts/{user_b_artifacts[0]['id']}",
            headers=user_a_headers,
        )
        hidden_run_artifacts = await client.get(
            "/api/agent/artifacts",
            headers=user_a_headers,
            params={"run_id": user_b_run["id"]},
        )
        visible_artifact = await client.get(
            f"/api/agent/artifacts/{user_a_artifacts[0]['id']}",
            headers=user_a_headers,
        )

    assert [artifact["run_id"] for artifact in user_a_artifacts] == [user_a_run["id"]]
    assert hidden_artifact.status_code == 404
    assert hidden_artifact.json()["detail"] == "Artifact not found"
    assert hidden_run_artifacts.status_code == 404
    assert hidden_run_artifacts.json()["detail"] == "Run not found"
    assert visible_artifact.status_code == 200
    assert visible_artifact.json()["id"] == user_a_artifacts[0]["id"]


@pytest.mark.asyncio
async def test_agent_api_rejects_workspace_access_outside_trusted_identity() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        settings=AgentSettings(api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/agent/runs", headers=user_a_headers, json={"goal": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/agent/runs", headers=user_b_headers, json={"goal": "User B"})
        ).json()
        await runtime.worker.drain()
        visible_files = await client.get(
            f"/api/agent/workspaces/{user_a_run['workspace_id']}/files",
            headers=user_a_headers,
        )
        hidden_files = await client.get(
            f"/api/agent/workspaces/{user_b_run['workspace_id']}/files",
            headers=user_a_headers,
        )
        hidden_read = await client.get(
            f"/api/agent/workspaces/{user_b_run['workspace_id']}/files/reports/report.md",
            headers=user_a_headers,
        )
        hidden_write = await client.put(
            f"/api/agent/workspaces/{user_b_run['workspace_id']}/files/notes.md",
            headers=user_a_headers,
            json={"content": "nope", "media_type": "text/plain"},
        )
        hidden_delete = await client.delete(
            f"/api/agent/workspaces/{user_b_run['workspace_id']}/files/reports/report.md",
            headers=user_a_headers,
        )

    assert visible_files.status_code == 200
    assert hidden_files.status_code == 404
    assert hidden_files.json()["detail"] == "Workspace not found"
    assert hidden_read.status_code == 404
    assert hidden_read.json()["detail"] == "Workspace not found"
    assert hidden_write.status_code == 404
    assert hidden_write.json()["detail"] == "Workspace not found"
    assert hidden_delete.status_code == 404
    assert hidden_delete.json()["detail"] == "Workspace not found"


@pytest.mark.asyncio
async def test_agent_api_binds_memory_to_trusted_identity_headers() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(api_token="secret-token"))
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_memory = (
            await client.post(
                "/api/agent/memory",
                headers=user_a_headers,
                json={"scope": "user", "key": "preference.language", "value": "Chinese"},
            )
        ).json()
        await client.post(
            "/api/agent/memory",
            headers=user_b_headers,
            json={"scope": "user", "key": "preference.language", "value": "English"},
        )
        conflicting_org = await client.post(
            "/api/agent/memory",
            headers=user_a_headers,
            json={"org_id": "org_2", "scope": "user", "key": "bad", "value": "bad"},
        )
        conflicting_user_scope = await client.get(
            "/api/agent/memory",
            headers=user_a_headers,
            params={"scope": "user", "scope_id": "user_b"},
        )
        user_a_entries = (
            await client.get(
                "/api/agent/memory",
                headers=user_a_headers,
                params={"scope": "user"},
            )
        ).json()

    assert user_a_memory["org_id"] == "org_1"
    assert user_a_memory["scope_id"] == "user_a"
    assert conflicting_org.status_code == 403
    assert conflicting_org.json()["detail"] == "Request identity conflicts with authenticated context"
    assert conflicting_user_scope.status_code == 403
    assert conflicting_user_scope.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [entry["id"] for entry in user_a_entries] == [user_a_memory["id"]]


@pytest.mark.asyncio
async def test_agent_api_binds_subagent_specs_to_trusted_org_header() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(api_token="secret-token"))
    app = create_app(runtime)
    org_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    org_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        org_a_spec = (
            await client.post(
                "/api/agent/subagents",
                headers=org_a_headers,
                json={"key": "researcher", "name": "Researcher", "instructions": "Research carefully."},
            )
        ).json()
        await client.post(
            "/api/agent/subagents",
            headers=org_b_headers,
            json={"key": "writer", "name": "Writer", "instructions": "Write clearly."},
        )
        conflicting_create = await client.post(
            "/api/agent/subagents",
            headers=org_a_headers,
            json={
                "org_id": "org_b",
                "key": "bad",
                "name": "Bad",
                "instructions": "Wrong org.",
            },
        )
        conflicting_list = await client.get(
            "/api/agent/subagents",
            headers=org_a_headers,
            params={"org_id": "org_b"},
        )
        org_a_specs = (await client.get("/api/agent/subagents", headers=org_a_headers)).json()
        hidden_spec = await client.get("/api/agent/subagents/writer", headers=org_a_headers)
        visible_spec = await client.get("/api/agent/subagents/researcher", headers=org_a_headers)

    assert org_a_spec["org_id"] == "org_a"
    assert conflicting_create.status_code == 403
    assert conflicting_create.json()["detail"] == "Request identity conflicts with authenticated context"
    assert conflicting_list.status_code == 403
    assert conflicting_list.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [spec["key"] for spec in org_a_specs] == ["researcher"]
    assert hidden_spec.status_code == 404
    assert hidden_spec.json()["detail"] == "Subagent spec not found"
    assert visible_spec.status_code == 200
    assert visible_spec.json()["id"] == org_a_spec["id"]


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
async def test_agent_api_persists_completed_assistant_message_to_thread() -> None:
    runtime = create_agent_runtime(driver=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/agent/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Report"},
            )
        ).json()
        user_message = (
            await client.post(
                f"/api/agent/threads/{thread['id']}/messages",
                json={"role": "user", "content": "Please write a report"},
            )
        ).json()
        run = (
            await client.post(
                "/api/agent/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "goal": "Write report",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        messages = (await client.get(f"/api/agent/threads/{thread['id']}/messages")).json()

    assert messages[0] == user_message
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "I will write the report.\n"
    assert messages[1]["run_id"] == run["id"]


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
async def test_agent_api_accepts_user_input_for_paused_thread_run() -> None:
    runtime = create_agent_runtime(
        driver=file_report_driver(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/agent/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Report"},
            )
        ).json()
        run = (
            await client.post(
                "/api/agent/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "goal": "Write report",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.post(
            f"/api/agent/runs/{run['id']}/input",
            json={"content": "Please keep it brief."},
        )
        messages = (await client.get(f"/api/agent/threads/{thread['id']}/messages")).json()
        events = (await client.get(f"/api/agent/runs/{run['id']}/events")).json()

    created_message = response.json()

    assert response.status_code == 201
    assert created_message["role"] == "user"
    assert created_message["content"] == "Please keep it brief."
    assert created_message["run_id"] == run["id"]
    assert messages == [created_message]
    assert [event["type"] for event in events][-2:] == ["message.created", "message.completed"]
    assert events[-2]["payload"] == {"message_id": created_message["id"], "role": "user"}
    assert events[-1]["payload"] == {
        "message_id": created_message["id"],
        "content": "Please keep it brief.",
    }


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
async def test_agent_api_rejects_run_with_unknown_skill() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/agent/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "goal": "Use missing skill",
                "skill_id": "missing-skill",
                "scopes": ["*"],
            },
        )
        runs = (await client.get("/api/agent/runs")).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found: missing-skill"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_rejects_run_with_unknown_thread() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/agent/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "thread_id": "missing-thread",
                "goal": "Use missing thread",
                "scopes": ["*"],
            },
        )
        runs = (await client.get("/api/agent/runs")).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found: missing-thread"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_rejects_messages_for_unknown_thread() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/agent/threads/missing-thread/messages",
            json={"role": "user", "content": "hello"},
        )
        listed = await client.get("/api/agent/threads/missing-thread/messages")

    assert created.status_code == 404
    assert created.json()["detail"] == "Thread not found"
    assert listed.status_code == 404
    assert listed.json()["detail"] == "Thread not found"


@pytest.mark.asyncio
async def test_agent_api_rejects_file_operations_for_unknown_workspace() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/agent/workspaces/missing-workspace/files")
        read = await client.get("/api/agent/workspaces/missing-workspace/files/notes.md")
        written = await client.put(
            "/api/agent/workspaces/missing-workspace/files/notes.md",
            json={"content": "hello", "media_type": "text/plain"},
        )
        deleted = await client.delete("/api/agent/workspaces/missing-workspace/files/notes.md")

    assert listed.status_code == 404
    assert read.status_code == 404
    assert written.status_code == 404
    assert deleted.status_code == 404
    assert listed.json()["detail"] == "Workspace not found"
    assert read.json()["detail"] == "Workspace not found"
    assert written.json()["detail"] == "Workspace not found"
    assert deleted.json()["detail"] == "Workspace not found"


@pytest.mark.asyncio
async def test_agent_api_rejects_run_event_reads_for_unknown_run() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        events = await client.get("/api/agent/runs/missing-run/events")
        stream = await client.get("/api/agent/runs/missing-run/stream")

    assert events.status_code == 404
    assert stream.status_code == 404
    assert events.json()["detail"] == "Run not found"
    assert stream.json()["detail"] == "Run not found"


@pytest.mark.asyncio
async def test_agent_api_validates_workspace_file_content_as_text() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/agent/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "goal": "Prepare workspace"},
            )
        ).json()
        response = await client.put(
            f"/api/agent/workspaces/{run['workspace_id']}/files/data.json",
            json={"content": {"nested": True}, "media_type": "application/json"},
        )

    assert response.status_code == 422


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
