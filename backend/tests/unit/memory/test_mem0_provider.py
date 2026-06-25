from aithru_agent.domain import AgentRun
from aithru_agent.memory import LongTermMemoryMessage
from aithru_agent.memory.mem0 import Mem0LongTermMemoryProvider
from aithru_agent.settings import AgentLongTermMemorySettings


class FakeMem0Client:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []
        self.delete_calls: list[str] = []
        self.get_calls: list[str] = []
        self.get_payload = {
            "id": "mem_1",
            "user_id": "org_1:user_1",
            "metadata": {"org_id": "org_1", "actor_user_id": "user_1"},
        }

    async def add(self, messages, **kwargs):
        self.add_calls.append({"messages": messages, **kwargs})
        return {"status": "PENDING", "event_id": "evt_1"}

    async def search(self, query, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        return {
            "results": [
                {
                    "id": "mem_1",
                    "memory": "User prefers concise Chinese summaries.",
                    "score": 0.91,
                    "metadata": {"org_id": "org_1"},
                    "created_at": "2026-06-25T00:00:00Z",
                    "updated_at": "2026-06-25T00:00:00Z",
                }
            ]
        }

    async def delete(self, memory_id: str):
        self.delete_calls.append(memory_id)
        return {"deleted": True}

    async def get(self, memory_id: str):
        self.get_calls.append(memory_id)
        return self.get_payload


def run_fixture() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Use my preferences.",
        workspace_id="workspace_1",
        thread_id="thread_1",
        skill_id="research",
        scopes=["agent.memory.read", "agent.memory.write"],
        status="queued",
        started_at="2026-06-25T00:00:00Z",
    )


async def test_mem0_provider_adds_messages_with_identity_and_metadata() -> None:
    client = FakeMem0Client()
    provider = Mem0LongTermMemoryProvider(
        client=client,
        settings=AgentLongTermMemorySettings(
            provider="mem0",
            mem0_api_key="mem0-key",
            mem0_app_id="prod:aithru-agent",
            mem0_default_agent_id="aithru-agent",
        ),
    )

    result = await provider.add_messages(
        run=run_fixture(),
        messages=[
            LongTermMemoryMessage(role="user", content="I prefer concise Chinese summaries."),
            LongTermMemoryMessage(role="assistant", content="I will remember that."),
        ],
    )

    assert result.status == "PENDING"
    assert result.event_id == "evt_1"
    call = client.add_calls[0]
    assert call["user_id"] == "org_1:user_1"
    assert call["app_id"] == "prod:aithru-agent"
    assert call["agent_id"] == "research"
    assert call["run_id"] == "run_1"
    assert call["infer"] is True
    assert call["metadata"]["org_id"] == "org_1"
    assert call["metadata"]["thread_id"] == "thread_1"


async def test_mem0_provider_searches_with_entity_filters() -> None:
    client = FakeMem0Client()
    provider = Mem0LongTermMemoryProvider(
        client=client,
        settings=AgentLongTermMemorySettings(
            provider="mem0",
            mem0_api_key="mem0-key",
            mem0_app_id="prod:aithru-agent",
            mem0_top_k=3,
            mem0_threshold=0.35,
        ),
    )

    results = await provider.search(run=run_fixture(), query="What should I remember?", limit=2)

    assert results[0].id == "mem_1"
    assert results[0].memory == "User prefers concise Chinese summaries."
    call = client.search_calls[0]
    assert call["query"] == "What should I remember?"
    assert call["top_k"] == 2
    assert call["threshold"] == 0.35
    assert call["filters"] == {
        "AND": [
            {"user_id": "org_1:user_1"},
            {"app_id": "prod:aithru-agent"},
        ]
    }


async def test_mem0_provider_deletes_by_memory_id_after_identity_check() -> None:
    client = FakeMem0Client()
    provider = Mem0LongTermMemoryProvider(
        client=client,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )

    result = await provider.delete_memory(
        memory_id="mem_1",
        org_id="org_1",
        actor_user_id="user_1",
    )

    assert result.memory_id == "mem_1"
    assert result.deleted is True
    assert client.get_calls == ["mem_1"]
    assert client.delete_calls == ["mem_1"]


async def test_mem0_provider_rejects_delete_for_wrong_identity() -> None:
    from aithru_agent.memory import LongTermMemoryAccessDenied

    client = FakeMem0Client()
    provider = Mem0LongTermMemoryProvider(
        client=client,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )

    try:
        await provider.delete_memory(
            memory_id="mem_1",
            org_id="org_2",
            actor_user_id="user_2",
        )
    except LongTermMemoryAccessDenied:
        pass
    else:
        raise AssertionError("Expected delete to reject mismatched Mem0 memory identity")

    assert client.get_calls == ["mem_1"]
    assert client.delete_calls == []
