from __future__ import annotations

from collections.abc import Callable

from aithru_agent.settings import AgentSettings

from .mem0 import Mem0LongTermMemoryProvider
from .providers import LongTermMemoryProvider, NoopLongTermMemoryProvider


def create_long_term_memory_provider(
    settings: AgentSettings,
    *,
    client: object | None = None,
    client_factory: Callable[[str, str | None], object] | None = None,
) -> LongTermMemoryProvider:
    if settings.long_term_memory.provider == "local":
        return NoopLongTermMemoryProvider()
    resolved_client = client
    if resolved_client is None:
        factory = client_factory or _create_mem0_client
        try:
            resolved_client = factory(
                settings.long_term_memory.mem0_mode,
                settings.long_term_memory.mem0_api_key,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Mem0 long-term memory requires the mem0ai package. "
                "Install backend dependencies with uv sync."
            ) from exc
    return Mem0LongTermMemoryProvider(
        client=resolved_client,
        settings=settings.long_term_memory,
    )


def _create_mem0_client(mode: str, api_key: str | None) -> object:
    if mode == "platform":
        from mem0 import AsyncMemoryClient

        return AsyncMemoryClient(api_key=api_key)
    from mem0 import AsyncMemory

    return AsyncMemory()
