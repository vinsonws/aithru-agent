import pytest

from aithru_agent.memory import NoopLongTermMemoryProvider
from aithru_agent.memory.factory import create_long_term_memory_provider
from aithru_agent.memory.mem0 import Mem0LongTermMemoryProvider
from aithru_agent.settings import AgentLongTermMemorySettings, AgentSettings


def test_factory_returns_noop_for_local_provider() -> None:
    provider = create_long_term_memory_provider(AgentSettings())

    assert isinstance(provider, NoopLongTermMemoryProvider)


def test_factory_requires_client_for_mem0_in_tests() -> None:
    settings = AgentSettings(
        long_term_memory=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key")
    )

    provider = create_long_term_memory_provider(settings, client=object())

    assert isinstance(provider, Mem0LongTermMemoryProvider)


def test_factory_raises_clear_error_when_mem0_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AgentSettings(
        long_term_memory=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key")
    )

    def fail_import(mode: str, api_key: str | None):
        del mode, api_key
        raise ImportError("No module named mem0")

    with pytest.raises(RuntimeError, match="mem0ai"):
        create_long_term_memory_provider(settings, client_factory=fail_import)
