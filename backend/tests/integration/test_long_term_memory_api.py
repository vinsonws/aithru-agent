from fastapi.testclient import TestClient

from aithru_agent.api.main import create_app
from aithru_agent.application import create_agent_runtime
from aithru_agent.memory import LongTermMemoryDeleteResult, NoopLongTermMemoryProvider
from aithru_agent.settings import AgentSettings

_IDENTITY_HEADERS = {
    "X-Aithru-Org-Id": "org_1",
    "X-Aithru-User-Id": "user_1",
}


class DeleteProvider(NoopLongTermMemoryProvider):
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete_memory(self, *, memory_id: str) -> LongTermMemoryDeleteResult:
        self.deleted.append(memory_id)
        return LongTermMemoryDeleteResult(memory_id=memory_id, deleted=True)


def test_long_term_memory_health_reports_provider() -> None:
    app_runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime=app_runtime)
    client = TestClient(app)

    response = client.get("/api/long-term-memory/health")

    assert response.status_code == 200
    assert response.json() == {"provider": "local", "enabled": False}


def test_long_term_memory_delete_delegates_to_provider() -> None:
    provider = DeleteProvider()
    app_runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        long_term_memory_provider=provider,
    )
    app = create_app(runtime=app_runtime)
    client = TestClient(app)

    response = client.delete("/api/long-term-memory/mem0_1", headers=_IDENTITY_HEADERS)

    assert response.status_code == 200
    assert response.json()["memory_id"] == "mem0_1"
    assert response.json()["deleted"] is True
    assert provider.deleted == ["mem0_1"]


def test_long_term_memory_delete_rejects_anonymous_requests() -> None:
    app_runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime=app_runtime)
    client = TestClient(app)

    response = client.delete("/api/long-term-memory/mem0_1")

    assert response.status_code == 403
