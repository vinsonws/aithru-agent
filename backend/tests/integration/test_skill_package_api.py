import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings


@pytest.mark.asyncio
async def test_user_skill_package_api_surfaces_created_skill_and_runs_with_it() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/skill-registry/user",
            json={
                "key": "file-report",
                "name": "File Report",
                "description": "Use for concise workspace reports.",
                "body": "# File Report\n\nWrite reports from workspace evidence.",
                "allowed_tools": ["workspace.list_files"],
                "denied_tools": [],
                "allowed_subagents": [],
            },
        )
        registry_response = await client.get("/api/skill-registry")
        runtime_detail_response = await client.get("/api/skills/file-report")
        run_response = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Use file report",
                "scopes": ["*"],
                "skill_id": "file-report",
            },
        )

    assert created_response.status_code == 201
    assert created_response.json()["source"] == "user"
    assert "file-report" in [entry["key"] for entry in registry_response.json()]
    assert runtime_detail_response.status_code == 200
    assert runtime_detail_response.json()["key"] == "file-report"
    assert run_response.status_code == 201


@pytest.mark.asyncio
async def test_user_skill_package_patch_updates_content_and_policy() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/skill-registry/user",
            json={
                "key": "file-report",
                "name": "File Report",
                "description": "Use for reports.",
                "body": "# File Report\n\nOld body.",
                "allowed_tools": ["workspace.list_files"],
                "denied_tools": [],
                "allowed_subagents": [],
            },
        )
        patched_response = await client.patch(
            "/api/skill-registry/user/file-report",
            json={
                "name": "Artifact Report",
                "description": "Create artifact-only reports.",
                "body": "# Artifact Report\n\nNew body.",
                "allowed_tools": ["artifact.create"],
                "denied_tools": ["workspace.write_file"],
                "allowed_subagents": [],
            },
        )
        runtime_detail_response = await client.get("/api/skills/file-report")

    patched = patched_response.json()
    runtime_detail = runtime_detail_response.json()
    assert patched_response.status_code == 200
    assert patched["name"] == "Artifact Report"
    assert patched["configuration"]["allowed_tools"] == ["artifact.create"]
    assert patched["configuration"]["denied_tools"] == ["workspace.write_file"]
    assert runtime_detail["name"] == "Artifact Report"
    assert runtime_detail["instructions"] == "# Artifact Report\n\nNew body."
    assert runtime_detail["allowed_tools"] == ["artifact.create"]


@pytest.mark.asyncio
async def test_user_skill_package_builtin_key_conflict_returns_409() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/skill-registry/user",
            json={
                "key": "deep-research",
                "name": "Deep Research Override",
                "description": "Conflicts with built-in skill.",
                "body": "No override.",
            },
        )

    assert response.status_code == 409
