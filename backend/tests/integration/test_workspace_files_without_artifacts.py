from httpx import ASGITransport, AsyncClient
import pytest

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings


@pytest.mark.asyncio
async def test_openapi_no_longer_exposes_artifact_routes_or_schemas() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    assert all(not path.startswith("/api/artifacts") for path in openapi["paths"])
    assert all("Artifact" not in name for name in openapi["components"]["schemas"])


@pytest.mark.asyncio
async def test_workspace_file_downloads_directly_without_artifact_promotion() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    workspace = await runtime.store.create_workspace(org_id="org_1")
    await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/report.md",
        content="# Report\nDone.\n",
        media_type="text/markdown",
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/workspaces/{workspace.id}/files/reports/report.md/download"
        )

    assert response.status_code == 200
    assert response.text == "# Report\nDone.\n"
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="report.md"'
