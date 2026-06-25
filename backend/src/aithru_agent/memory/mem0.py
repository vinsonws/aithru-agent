from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aithru_agent.domain import AgentRun
from aithru_agent.settings import AgentLongTermMemorySettings

from .providers import (
    LongTermMemoryAddResult,
    LongTermMemoryDeleteResult,
    LongTermMemoryMessage,
    LongTermMemorySearchResult,
    identity_for_run,
)


class Mem0LongTermMemoryProvider:
    def __init__(
        self,
        *,
        client: object,
        settings: AgentLongTermMemorySettings,
    ) -> None:
        self._client = client
        self._settings = settings

    async def search(
        self,
        *,
        run: AgentRun,
        query: str,
        limit: int,
    ) -> list[LongTermMemorySearchResult]:
        identity = identity_for_run(
            run,
            app_id=self._settings.mem0_app_id,
            default_agent_id=self._settings.mem0_default_agent_id,
        )
        kwargs: dict[str, object] = {
            "filters": {
                "AND": [
                    {"user_id": identity.user_id},
                    {"app_id": identity.app_id},
                ]
            },
            "top_k": min(limit, self._settings.mem0_top_k),
        }
        if self._settings.mem0_threshold is not None:
            kwargs["threshold"] = self._settings.mem0_threshold
        raw = await self._client.search(query, **kwargs)
        return [_search_result(item) for item in _result_items(raw)]

    async def add_messages(
        self,
        *,
        run: AgentRun,
        messages: Sequence[LongTermMemoryMessage],
    ) -> LongTermMemoryAddResult:
        identity = identity_for_run(
            run,
            app_id=self._settings.mem0_app_id,
            default_agent_id=self._settings.mem0_default_agent_id,
        )
        raw = await self._client.add(
            messages=[
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            user_id=identity.user_id,
            app_id=identity.app_id,
            agent_id=identity.agent_id,
            run_id=identity.run_id,
            metadata=identity.metadata,
            infer=True,
        )
        payload = _mapping(raw)
        status = str(payload.get("status", "completed"))
        event_id = payload.get("event_id")
        return LongTermMemoryAddResult(
            status=status,
            event_id=str(event_id) if event_id is not None else None,
            raw=payload,
        )

    async def delete_memory(self, *, memory_id: str) -> LongTermMemoryDeleteResult:
        raw = await self._client.delete(memory_id=memory_id)
        payload = _mapping(raw)
        deleted = bool(payload.get("deleted", True))
        return LongTermMemoryDeleteResult(
            memory_id=memory_id,
            deleted=deleted,
            raw=payload,
        )


def _result_items(raw: object) -> list[Mapping[str, object]]:
    if isinstance(raw, list):
        return [_mapping(item) for item in raw]
    payload = _mapping(raw)
    results = payload.get("results", [])
    if isinstance(results, list):
        return [_mapping(item) for item in results]
    return []


def _search_result(item: Mapping[str, object]) -> LongTermMemorySearchResult:
    memory_id = item.get("id") or item.get("memory_id")
    memory = item.get("memory") or item.get("text") or item.get("content")
    score = item.get("score")
    metadata = item.get("metadata")
    return LongTermMemorySearchResult(
        id=str(memory_id),
        memory=str(memory),
        score=float(score) if isinstance(score, int | float) else None,
        metadata=_mapping(metadata),
        created_at=_optional_str(item.get("created_at")),
        updated_at=_optional_str(item.get("updated_at")),
    )


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
