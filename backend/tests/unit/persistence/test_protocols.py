from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream import InMemoryAgentEventStore


def test_memory_stores_satisfy_persistence_protocols() -> None:
    assert isinstance(InMemoryAgentStore(), AgentStore)
    assert isinstance(InMemoryAgentEventStore(), AgentEventStore)
