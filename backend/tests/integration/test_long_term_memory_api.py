from fastapi.testclient import TestClient

from aithru_agent.api.main import create_app
from aithru_agent.application import create_agent_runtime
from aithru_agent.memory import LongTermMemoryDeleteResult, NoopLongTermMemoryProvider
from aithru_agent.settings import AgentSettings


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

    response = client.delete("/api/long-term-memory/mem0_1")

    assert response.status_code == 200
    assert response.json()["memory_id"] == "mem0_1"
    assert response.json()["deleted"] is True
    assert provider.deleted == ["mem0_1"]
