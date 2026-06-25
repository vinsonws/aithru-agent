from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from aithru_agent.domain import AgentRun


LongTermMemoryRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class LongTermMemoryIdentity:
    user_id: str
    app_id: str
    agent_id: str
    run_id: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class LongTermMemoryMessage:
    role: LongTermMemoryRole
    content: str


@dataclass(frozen=True)
class LongTermMemorySearchResult:
    id: str
    memory: str
    score: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class LongTermMemoryAddResult:
    status: str
    event_id: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LongTermMemoryDeleteResult:
    memory_id: str
    deleted: bool
    raw: Mapping[str, object] = field(default_factory=dict)


@runtime_checkable
class LongTermMemoryProvider(Protocol):
    async def search(
        self,
        *,
        run: AgentRun,
        query: str,
        limit: int,
    ) -> list[LongTermMemorySearchResult]:
        ...

    async def add_messages(
        self,
        *,
        run: AgentRun,
        messages: Sequence[LongTermMemoryMessage],
    ) -> LongTermMemoryAddResult:
        ...

    async def delete_memory(self, *, memory_id: str) -> LongTermMemoryDeleteResult:
        ...


class NoopLongTermMemoryProvider:
    async def search(
        self,
        *,
        run: AgentRun,
        query: str,
        limit: int,
    ) -> list[LongTermMemorySearchResult]:
        del run, query, limit
        return []

    async def add_messages(
        self,
        *,
        run: AgentRun,
        messages: Sequence[LongTermMemoryMessage],
    ) -> LongTermMemoryAddResult:
        del run, messages
        return LongTermMemoryAddResult(status="skipped")

    async def delete_memory(self, *, memory_id: str) -> LongTermMemoryDeleteResult:
        return LongTermMemoryDeleteResult(memory_id=memory_id, deleted=False)


def identity_for_run(
    run: AgentRun,
    *,
    app_id: str,
    default_agent_id: str,
) -> LongTermMemoryIdentity:
    metadata = {
        "org_id": run.org_id,
        "actor_user_id": run.actor_user_id,
        "workspace_id": run.workspace_id,
        "run_id": run.id,
        "source": str(run.source),
        "created_by": "aithru-agent",
    }
    if run.thread_id:
        metadata["thread_id"] = run.thread_id
    if run.skill_id:
        metadata["skill_id"] = run.skill_id
    return LongTermMemoryIdentity(
        user_id=f"{run.org_id}:{run.actor_user_id}",
        app_id=app_id,
        agent_id=run.skill_id or default_agent_id,
        run_id=run.id,
        metadata=metadata,
    )


def can_read_long_term_memory(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.memory.read" in scopes


def can_write_long_term_memory(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.memory.write" in scopes
