# Mem0 Cross-Thread Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Mem0-native cross-thread long-term memory so eligible runs search user memory before model execution and automatically add completed user/assistant turns to Mem0 without per-memory approval.

**Architecture:** Add a provider-neutral long-term memory interface under `aithru_agent.memory`, implement a Mem0 provider behind settings, wire Mem0 search into `AgentRunContextPacket`, and wire Mem0 add into a runtime processor. Existing `AgentMemoryEntry` and `AgentMemoryCandidate` remain local/pinned and compatibility mechanisms; Mem0 is the primary cross-thread memory engine when enabled.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Pydantic AI, Mem0 Python SDK (`mem0ai`), pytest, uv.

## Global Constraints

- Mem0 must not be exposed as an unrestricted model-callable tool.
- Mem0-native mode must not require per-memory approval by default.
- All real memory reads and writes must remain scoped by Aithru run scopes: `agent.memory.read`, `agent.memory.write`, or `*`.
- Tenant isolation must map `org_id` and `actor_user_id` into Mem0 identity values.
- Do not send secrets, credentials, service tokens, raw sensitive tool payloads, approval payloads, or unrestricted workspace content to Mem0.
- Mem0 results are context hints, not authority; current user input and repository files remain higher priority.
- Do not add Agent workflow graph, scheduler, WorkflowSpec, branch, or plan semantics.
- Preserve existing local memory APIs and candidate APIs for compatibility.
- Meaningful backend changes must run `cd backend && uv run pytest` and `cd backend && uv run python examples/file_report_agent.py` before completion.

---

## File Structure

- `backend/pyproject.toml` adds the Mem0 SDK dependency.
- `backend/src/aithru_agent/settings.py` owns Mem0 provider settings and env parsing.
- `backend/src/aithru_agent/memory/__init__.py` exports long-term memory interfaces.
- `backend/src/aithru_agent/memory/providers.py` defines provider-neutral dataclasses, protocols, identity mapping, no-op provider, and scope helpers.
- `backend/src/aithru_agent/memory/redaction.py` sanitizes outbound text before Mem0 writes.
- `backend/src/aithru_agent/memory/mem0.py` adapts Mem0 Platform or OSS clients to the provider protocol.
- `backend/src/aithru_agent/memory/factory.py` creates the configured long-term memory provider.
- `backend/src/aithru_agent/harness/context_packet.py` merges Mem0 search results with local pinned memory.
- `backend/src/aithru_agent/worker/runner.py` passes the configured provider and event writer into the context packet builder.
- `backend/src/aithru_agent/runtime/processors/mem0_memory.py` sends completed run messages to Mem0.
- `backend/src/aithru_agent/application/runtime.py` wires the provider, runner, and processors.
- `backend/src/aithru_agent/api/routes/long_term_memory.py` provides provider-aware forget and health routes.
- `backend/src/aithru_agent/api/routes/__init__.py` registers the route group.
- `README.md` and `docs/00-agent-harness-design.md` record implemented settings and runtime behavior after code lands.

---

### Task 1: Settings And Provider Contracts

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/aithru_agent/settings.py`
- Create: `backend/src/aithru_agent/memory/__init__.py`
- Create: `backend/src/aithru_agent/memory/providers.py`
- Test: `backend/tests/unit/test_settings.py`
- Test: `backend/tests/unit/memory/test_providers.py`

**Interfaces:**
- Produces: `AgentLongTermMemorySettings`
- Produces: `LongTermMemoryProvider`
- Produces: `LongTermMemoryIdentity`
- Produces: `LongTermMemoryMessage`
- Produces: `LongTermMemorySearchResult`
- Produces: `LongTermMemoryAddResult`
- Produces: `LongTermMemoryDeleteResult`
- Produces: `NoopLongTermMemoryProvider`
- Produces: `can_read_long_term_memory(scopes: list[str]) -> bool`
- Produces: `can_write_long_term_memory(scopes: list[str]) -> bool`
- Produces: `identity_for_run(run: AgentRun, *, app_id: str, default_agent_id: str) -> LongTermMemoryIdentity`

- [ ] **Step 1: Write failing settings tests**

Append these tests to `backend/tests/unit/test_settings.py`:

```python
from aithru_agent.settings import AgentLongTermMemorySettings


def test_long_term_memory_settings_default_to_local_provider() -> None:
    settings = AgentSettings()

    assert isinstance(settings.long_term_memory, AgentLongTermMemorySettings)
    assert settings.long_term_memory.provider == "local"
    assert settings.long_term_memory.mem0_mode == "platform"
    assert settings.long_term_memory.mem0_app_id == "aithru-agent"
    assert settings.long_term_memory.mem0_default_agent_id == "aithru-agent"
    assert settings.long_term_memory.mem0_top_k == 8
    assert settings.long_term_memory.mem0_threshold is None
    assert settings.long_term_memory.mem0_add_on_run_complete is True
    assert settings.long_term_memory.mem0_add_on_compaction is True
    assert settings.long_term_memory.mem0_approval_required is False
    assert "do not remember" in settings.long_term_memory.mem0_no_memory_markers


def test_long_term_memory_settings_parse_mem0_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_LONG_TERM_MEMORY_PROVIDER", "mem0")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_MODE", "platform")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_API_KEY", "mem0-key")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_APP_ID", "prod:aithru-agent")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_DEFAULT_AGENT_ID", "research-agent")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_TOP_K", "5")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_THRESHOLD", "0.4")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_ADD_ON_RUN_COMPLETE", "false")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_ADD_ON_COMPACTION", "false")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_APPROVAL_REQUIRED", "true")
    monkeypatch.setenv("AITHRU_AGENT_MEM0_NO_MEMORY_MARKERS", "forget this,do not store")

    settings = AgentSettings.from_env()

    assert settings.long_term_memory.provider == "mem0"
    assert settings.long_term_memory.mem0_mode == "platform"
    assert settings.long_term_memory.mem0_api_key == "mem0-key"
    assert settings.long_term_memory.mem0_app_id == "prod:aithru-agent"
    assert settings.long_term_memory.mem0_default_agent_id == "research-agent"
    assert settings.long_term_memory.mem0_top_k == 5
    assert settings.long_term_memory.mem0_threshold == 0.4
    assert settings.long_term_memory.mem0_add_on_run_complete is False
    assert settings.long_term_memory.mem0_add_on_compaction is False
    assert settings.long_term_memory.mem0_approval_required is True
    assert settings.long_term_memory.mem0_no_memory_markers == ["forget this", "do not store"]
```

- [ ] **Step 2: Write failing provider contract tests**

Create `backend/tests/unit/memory/test_providers.py`:

```python
from aithru_agent.domain import AgentRun
from aithru_agent.memory import (
    LongTermMemoryMessage,
    NoopLongTermMemoryProvider,
    can_read_long_term_memory,
    can_write_long_term_memory,
    identity_for_run,
)


def run_fixture() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Remember my preference.",
        workspace_id="workspace_1",
        thread_id="thread_1",
        selected_skill_keys=["research"],
        scopes=["agent.memory.read", "agent.memory.write"],
        status="queued",
        started_at="2026-06-25T00:00:00Z",
    )


def test_memory_scope_helpers_require_memory_scopes() -> None:
    assert can_read_long_term_memory(["agent.memory.read"]) is True
    assert can_read_long_term_memory(["*"]) is True
    assert can_read_long_term_memory(["agent.workspace.read"]) is False
    assert can_write_long_term_memory(["agent.memory.write"]) is True
    assert can_write_long_term_memory(["*"]) is True
    assert can_write_long_term_memory(["agent.memory.read"]) is False


def test_identity_for_run_is_tenant_safe() -> None:
    identity = identity_for_run(
        run_fixture(),
        app_id="prod:aithru-agent",
        default_agent_id="aithru-agent",
    )

    assert identity.user_id == "org_1:user_1"
    assert identity.app_id == "prod:aithru-agent"
    assert identity.agent_id == "research"
    assert identity.run_id == "run_1"
    assert identity.metadata["org_id"] == "org_1"
    assert identity.metadata["actor_user_id"] == "user_1"
    assert identity.metadata["thread_id"] == "thread_1"
    assert identity.metadata["workspace_id"] == "workspace_1"
    assert identity.metadata["selected_skill_keys"] == ["research"]


async def test_noop_provider_returns_empty_results() -> None:
    provider = NoopLongTermMemoryProvider()

    assert await provider.search(run=run_fixture(), query="preference", limit=5) == []
    result = await provider.add_messages(
        run=run_fixture(),
        messages=[LongTermMemoryMessage(role="user", content="Remember this.")],
    )

    assert result.status == "skipped"
    assert result.event_id is None
    delete = await provider.delete_memory(memory_id="mem_1")
    assert delete.deleted is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/unit/test_settings.py::test_long_term_memory_settings_default_to_local_provider tests/unit/test_settings.py::test_long_term_memory_settings_parse_mem0_env tests/unit/memory/test_providers.py -q
```

Expected: FAIL because `AgentLongTermMemorySettings` and `aithru_agent.memory` do not exist yet.

- [ ] **Step 4: Add Mem0 dependency**

Modify `backend/pyproject.toml` dependencies:

```toml
dependencies = [
  "cryptography>=49.0.0",
  "fastapi>=0.116.0",
  "httpx>=0.28.0",
  "jsonschema>=4.26.0",
  "mem0ai>=2.0.0,<3.0.0",
  "pydantic>=2.11.0",
  "pydantic-ai>=0.8.0",
  "pydantic-ai-harness>=0.3.0",
  "uvicorn>=0.35.0",
]
```

- [ ] **Step 5: Add settings model**

In `backend/src/aithru_agent/settings.py`, add these type aliases near the existing settings aliases:

```python
AgentLongTermMemoryProviderKind = Literal["local", "mem0"]
AgentMem0Mode = Literal["platform", "oss"]
```

Add this model after `AgentProcessorSettings`:

```python
class AgentLongTermMemorySettings(AithruBaseModel):
    provider: AgentLongTermMemoryProviderKind = "local"
    mem0_mode: AgentMem0Mode = "platform"
    mem0_api_key: str | None = None
    mem0_app_id: str = "aithru-agent"
    mem0_default_agent_id: str = "aithru-agent"
    mem0_top_k: int = Field(default=8, ge=1, le=100)
    mem0_threshold: float | None = Field(default=None, ge=0, le=1)
    mem0_add_on_run_complete: bool = True
    mem0_add_on_compaction: bool = True
    mem0_approval_required: bool = False
    mem0_no_memory_markers: list[str] = Field(
        default_factory=lambda: ["do not remember", "don't remember"]
    )

    @field_validator("mem0_api_key", "mem0_app_id", "mem0_default_agent_id")
    @classmethod
    def _optional_strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("long-term memory settings cannot contain blank strings")
        return stripped

    @field_validator("mem0_no_memory_markers")
    @classmethod
    def _markers_must_be_unique(cls, value: list[str]) -> list[str]:
        markers = [marker.strip().lower() for marker in value if marker.strip()]
        if len(set(markers)) != len(markers):
            raise ValueError("mem0 no-memory markers must be unique")
        return markers

    @model_validator(mode="after")
    def _validate_mem0_platform_settings(self) -> "AgentLongTermMemorySettings":
        if self.provider == "mem0" and self.mem0_mode == "platform" and not self.mem0_api_key:
            raise ValueError("mem0_api_key is required for platform Mem0 provider")
        return self
```

Add this field to `AgentSettings`:

```python
long_term_memory: AgentLongTermMemorySettings = Field(
    default_factory=AgentLongTermMemorySettings
)
```

Add this to `AgentSettings.from_env()`:

```python
long_term_memory=AgentLongTermMemorySettings(
    provider=os.getenv("AITHRU_AGENT_LONG_TERM_MEMORY_PROVIDER", "local"),
    mem0_mode=os.getenv("AITHRU_AGENT_MEM0_MODE", "platform"),
    mem0_api_key=os.getenv("AITHRU_AGENT_MEM0_API_KEY"),
    mem0_app_id=os.getenv("AITHRU_AGENT_MEM0_APP_ID", "aithru-agent"),
    mem0_default_agent_id=os.getenv(
        "AITHRU_AGENT_MEM0_DEFAULT_AGENT_ID",
        "aithru-agent",
    ),
    mem0_top_k=_env_int(
        os.getenv("AITHRU_AGENT_MEM0_TOP_K"),
        default=8,
        name="AITHRU_AGENT_MEM0_TOP_K",
    ),
    mem0_threshold=_env_float_optional(
        os.getenv("AITHRU_AGENT_MEM0_THRESHOLD"),
        name="AITHRU_AGENT_MEM0_THRESHOLD",
    ),
    mem0_add_on_run_complete=_env_bool_default(
        os.getenv("AITHRU_AGENT_MEM0_ADD_ON_RUN_COMPLETE"),
        default=True,
        name="AITHRU_AGENT_MEM0_ADD_ON_RUN_COMPLETE",
    ),
    mem0_add_on_compaction=_env_bool_default(
        os.getenv("AITHRU_AGENT_MEM0_ADD_ON_COMPACTION"),
        default=True,
        name="AITHRU_AGENT_MEM0_ADD_ON_COMPACTION",
    ),
    mem0_approval_required=_env_bool_default(
        os.getenv("AITHRU_AGENT_MEM0_APPROVAL_REQUIRED"),
        default=False,
        name="AITHRU_AGENT_MEM0_APPROVAL_REQUIRED",
    ),
    mem0_no_memory_markers=_split_csv(
        os.getenv("AITHRU_AGENT_MEM0_NO_MEMORY_MARKERS"),
        name="AITHRU_AGENT_MEM0_NO_MEMORY_MARKERS",
    )
    or ["do not remember", "don't remember"],
),
```

Add this helper near `_env_int`:

```python
def _env_float_optional(raw: str | None, *, name: str) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
```

- [ ] **Step 6: Add provider contracts**

Create `backend/src/aithru_agent/memory/providers.py`:

```python
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
    if run.selected_skill_keys:
        metadata["selected_skill_keys"] = run.selected_skill_keys
    return LongTermMemoryIdentity(
        user_id=f"{run.org_id}:{run.actor_user_id}",
        app_id=app_id,
        agent_id=(run.selected_skill_keys[0] if run.selected_skill_keys else default_agent_id),
        run_id=run.id,
        metadata=metadata,
    )


def can_read_long_term_memory(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.memory.read" in scopes


def can_write_long_term_memory(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.memory.write" in scopes
```

Create `backend/src/aithru_agent/memory/__init__.py`:

```python
from .providers import (
    LongTermMemoryAddResult,
    LongTermMemoryDeleteResult,
    LongTermMemoryIdentity,
    LongTermMemoryMessage,
    LongTermMemoryProvider,
    LongTermMemorySearchResult,
    NoopLongTermMemoryProvider,
    can_read_long_term_memory,
    can_write_long_term_memory,
    identity_for_run,
)

__all__ = [
    "LongTermMemoryAddResult",
    "LongTermMemoryDeleteResult",
    "LongTermMemoryIdentity",
    "LongTermMemoryMessage",
    "LongTermMemoryProvider",
    "LongTermMemorySearchResult",
    "NoopLongTermMemoryProvider",
    "can_read_long_term_memory",
    "can_write_long_term_memory",
    "identity_for_run",
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
cd backend
uv run pytest tests/unit/test_settings.py::test_long_term_memory_settings_default_to_local_provider tests/unit/test_settings.py::test_long_term_memory_settings_parse_mem0_env tests/unit/memory/test_providers.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/src/aithru_agent/settings.py backend/src/aithru_agent/memory/__init__.py backend/src/aithru_agent/memory/providers.py backend/tests/unit/test_settings.py backend/tests/unit/memory/test_providers.py
git commit -m "feat: add long-term memory provider contracts"
```

---

### Task 2: Mem0 Provider Adapter

**Files:**
- Create: `backend/src/aithru_agent/memory/mem0.py`
- Create: `backend/src/aithru_agent/memory/factory.py`
- Modify: `backend/src/aithru_agent/memory/__init__.py`
- Test: `backend/tests/unit/memory/test_mem0_provider.py`
- Test: `backend/tests/unit/memory/test_factory.py`

**Interfaces:**
- Consumes: `AgentLongTermMemorySettings`
- Consumes: `LongTermMemoryProvider`
- Consumes: `identity_for_run`
- Produces: `Mem0LongTermMemoryProvider`
- Produces: `create_long_term_memory_provider(settings: AgentSettings) -> LongTermMemoryProvider`

- [ ] **Step 1: Write failing Mem0 adapter tests**

Create `backend/tests/unit/memory/test_mem0_provider.py`:

```python
from aithru_agent.domain import AgentRun
from aithru_agent.memory import LongTermMemoryMessage
from aithru_agent.memory.mem0 import Mem0LongTermMemoryProvider
from aithru_agent.settings import AgentLongTermMemorySettings


class FakeMem0Client:
    def __init__(self) -> None:
        self.add_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []
        self.delete_calls: list[str] = []

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


def run_fixture() -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Use my preferences.",
        workspace_id="workspace_1",
        thread_id="thread_1",
        selected_skill_keys=["research"],
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


async def test_mem0_provider_deletes_by_memory_id() -> None:
    client = FakeMem0Client()
    provider = Mem0LongTermMemoryProvider(
        client=client,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )

    result = await provider.delete_memory(memory_id="mem_1")

    assert result.memory_id == "mem_1"
    assert result.deleted is True
    assert client.delete_calls == ["mem_1"]
```

- [ ] **Step 2: Write failing factory tests**

Create `backend/tests/unit/memory/test_factory.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/unit/memory/test_mem0_provider.py tests/unit/memory/test_factory.py -q
```

Expected: FAIL because `aithru_agent.memory.mem0` and `factory` do not exist.

- [ ] **Step 4: Implement Mem0 provider**

Create `backend/src/aithru_agent/memory/mem0.py`:

```python
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
        raw = await self._client.search(query, **kwargs)  # type: ignore[attr-defined]
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
        raw = await self._client.add(  # type: ignore[attr-defined]
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
        raw = await self._client.delete(memory_id=memory_id)  # type: ignore[attr-defined]
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
```

- [ ] **Step 5: Implement provider factory**

Create `backend/src/aithru_agent/memory/factory.py`:

```python
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
```

Update `backend/src/aithru_agent/memory/__init__.py`:

```python
from .factory import create_long_term_memory_provider
from .mem0 import Mem0LongTermMemoryProvider
from .providers import (
    LongTermMemoryAddResult,
    LongTermMemoryDeleteResult,
    LongTermMemoryIdentity,
    LongTermMemoryMessage,
    LongTermMemoryProvider,
    LongTermMemorySearchResult,
    NoopLongTermMemoryProvider,
    can_read_long_term_memory,
    can_write_long_term_memory,
    identity_for_run,
)

__all__ = [
    "LongTermMemoryAddResult",
    "LongTermMemoryDeleteResult",
    "LongTermMemoryIdentity",
    "LongTermMemoryMessage",
    "LongTermMemoryProvider",
    "LongTermMemorySearchResult",
    "Mem0LongTermMemoryProvider",
    "NoopLongTermMemoryProvider",
    "can_read_long_term_memory",
    "can_write_long_term_memory",
    "create_long_term_memory_provider",
    "identity_for_run",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
cd backend
uv run pytest tests/unit/memory/test_mem0_provider.py tests/unit/memory/test_factory.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/memory backend/tests/unit/memory
git commit -m "feat: add mem0 long-term memory provider"
```

---

### Task 3: Mem0 Search In Context Packet

**Files:**
- Modify: `backend/src/aithru_agent/harness/context_packet.py`
- Modify: `backend/src/aithru_agent/worker/runner.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Test: `backend/tests/unit/harness/test_context_packet.py`
- Test: `backend/tests/integration/test_pydantic_driver.py`

**Interfaces:**
- Consumes: `LongTermMemoryProvider.search`
- Produces: `memory.search.started`, `memory.search.completed`, `memory.search.skipped`, and `memory.search.failed` debug events.
- Produces: Mem0 search results as `AgentMemoryRecallItem(source="mem0")`.

- [ ] **Step 1: Write failing context packet test**

Append to `backend/tests/unit/harness/test_context_packet.py`:

```python
from aithru_agent.domain import AgentRun
from aithru_agent.harness import ContextPacketBuilder
from aithru_agent.memory import LongTermMemorySearchResult
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class FakeSearchProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, *, run: AgentRun, query: str, limit: int):
        del run, limit
        self.queries.append(query)
        return [
            LongTermMemorySearchResult(
                id="mem0_1",
                memory="User prefers concise Chinese summaries.",
                score=0.91,
                metadata={"org_id": "org_1"},
                created_at="2026-06-25T00:00:00Z",
                updated_at="2026-06-25T00:00:00Z",
            )
        ]

    async def add_messages(self, *, run, messages):
        raise AssertionError("search test must not add messages")

    async def delete_memory(self, *, memory_id: str):
        raise AssertionError("search test must not delete memory")


async def test_context_packet_includes_mem0_recall_items() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    event_writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Please use my preferences.",
        workspace_id=workspace.id,
        scopes=["agent.memory.read"],
        thread_id="thread_1",
    )
    provider = FakeSearchProvider()
    builder = ContextPacketBuilder(long_term_memory_provider=provider)

    packet = await builder.build(
        run,
        store,
        event_store=event_store,
        event_writer=event_writer,
    )

    assert packet.memory is not None
    assert packet.memory.items[0].memory_id == "mem0:mem0_1"
    assert packet.memory.items[0].source == "mem0"
    assert packet.memory.items[0].value == "User prefers concise Chinese summaries."
    assert "Please use my preferences." in provider.queries[0]
    events = await event_store.list_by_run(run.id)
    assert [event.type for event in events] == [
        "memory.search.started",
        "memory.search.completed",
    ]


async def test_context_packet_skips_mem0_without_read_scope() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    event_writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Please use my preferences.",
        workspace_id=workspace.id,
        scopes=["agent.workspace.read"],
        thread_id="thread_1",
    )
    provider = FakeSearchProvider()
    builder = ContextPacketBuilder(long_term_memory_provider=provider)

    packet = await builder.build(
        run,
        store,
        event_store=event_store,
        event_writer=event_writer,
    )

    assert packet.memory is None
    assert provider.queries == []
```

- [ ] **Step 2: Write failing integration test**

Append to `backend/tests/integration/test_pydantic_driver.py`:

```python
from aithru_agent.memory import LongTermMemorySearchResult


class SearchOnlyProvider:
    async def search(self, *, run, query: str, limit: int):
        del run, query, limit
        return [
            LongTermMemorySearchResult(
                id="mem0_pref",
                memory="User prefers concise Chinese summaries.",
                score=0.9,
                metadata={},
                created_at="2026-06-25T00:00:00Z",
                updated_at="2026-06-25T00:00:00Z",
            )
        ]

    async def add_messages(self, *, run, messages):
        raise AssertionError("integration search test must not add messages")

    async def delete_memory(self, *, memory_id: str):
        raise AssertionError("integration search test must not delete memory")


async def test_pydantic_ai_runtime_injects_mem0_context() -> None:
    app = create_agent_runtime(
        settings=AgentSettings(model="test"),
        long_term_memory_provider=SearchOnlyProvider(),
    )
    workspace = await app.store.create_workspace(org_id="org_1")
    run = await app.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Answer with my style preferences.",
        workspace_id=workspace.id,
        scopes=["agent.memory.read"],
        thread_id="thread_1",
    )

    completed = await app.runner.run_once(run.id)

    assert completed.status == "completed"
    events = await app.event_store.list_by_run(run.id)
    context_events = [event for event in events if event.type == "context.packet.built"]
    assert context_events
    memory_events = [event for event in events if event.type == "memory.search.completed"]
    assert memory_events
    assert memory_events[0].payload["retained_count"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/unit/harness/test_context_packet.py::test_context_packet_includes_mem0_recall_items tests/unit/harness/test_context_packet.py::test_context_packet_skips_mem0_without_read_scope tests/integration/test_pydantic_driver.py::test_pydantic_ai_runtime_injects_mem0_context -q
```

Expected: FAIL because `ContextPacketBuilder` and `create_agent_runtime` do not accept a long-term memory provider.

- [ ] **Step 4: Modify context packet builder**

In `backend/src/aithru_agent/harness/context_packet.py`, import provider types:

```python
from aithru_agent.memory import (
    LongTermMemoryProvider,
    LongTermMemorySearchResult,
    can_read_long_term_memory,
)
from aithru_agent.stream import AgentEventWriter, AgentStreamEvent
```

Add this field to `ContextPacketBuilder`:

```python
long_term_memory_provider: LongTermMemoryProvider | None = None
```

Change `build` signature:

```python
async def build(
    self,
    run: AgentRun,
    store: AgentStore,
    *,
    event_store: AgentEventStore | None = None,
    event_writer: AgentEventWriter | None = None,
) -> AgentRunContextPacket:
```

Move `_latest_context_summary(...)` before `_memory_recall(...)`, then call memory recall with query context:

```python
latest_context_summary = await self._latest_context_summary(
    run,
    store,
    dropped_thread_messages=dropped_thread_messages,
)
memory, dropped_memory = await self._memory_recall(
    run,
    store,
    thread_messages=thread_messages,
    latest_context_summary=latest_context_summary,
    event_writer=event_writer,
)
```

Replace `_memory_recall` with:

```python
async def _memory_recall(
    self,
    run: AgentRun,
    store: AgentStore,
    *,
    thread_messages: list[AgentRunContextMessage],
    latest_context_summary: AgentContextSummary | None,
    event_writer: AgentEventWriter | None,
) -> tuple[AgentMemoryRecall | None, int]:
    recall = await self.build_memory_recall(run, store)
    mem0_items = await self._long_term_memory_recall(
        run,
        thread_messages=thread_messages,
        latest_context_summary=latest_context_summary,
        event_writer=event_writer,
        existing_count=len(recall.items),
    )
    merged_items = _dedupe_memory_items([*recall.items, *mem0_items])
    dropped = max(0, len(merged_items) - self.max_memory_entries)
    retained = merged_items[: self.max_memory_entries]
    if not retained and not dropped:
        return None, 0
    return (
        AgentMemoryRecall(
            run_id=run.id,
            items=retained,
            count=len(retained),
            dropped=dropped,
        ),
        dropped,
    )
```

Add helper methods to the class:

```python
async def _long_term_memory_recall(
    self,
    run: AgentRun,
    *,
    thread_messages: list[AgentRunContextMessage],
    latest_context_summary: AgentContextSummary | None,
    event_writer: AgentEventWriter | None,
    existing_count: int,
) -> list[AgentMemoryRecallItem]:
    provider = self.long_term_memory_provider
    if provider is None or not can_read_long_term_memory(run.scopes):
        return []
    remaining = max(0, self.max_memory_entries - existing_count)
    if remaining <= 0:
        return []
    query = _long_term_memory_query(
        run,
        thread_messages=thread_messages,
        latest_context_summary=latest_context_summary,
    )
    if event_writer is not None:
        await event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="memory.search.started",
            source={"kind": "harness"},
            visibility="debug",
            payload={"provider": "mem0", "limit": remaining},
        )
    try:
        results = await provider.search(run=run, query=query, limit=remaining)
    except Exception as exc:
        if event_writer is not None:
            await event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="memory.search.failed",
                source={"kind": "harness"},
                visibility="debug",
                payload={"provider": "mem0", "error": {"message": str(exc)}},
            )
        return []
    items = [
        _mem0_recall_item(result, max_value_chars=self.max_content_chars)
        for result in results
        if result.memory.strip()
    ]
    if event_writer is not None:
        await event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="memory.search.completed",
            source={"kind": "harness"},
            visibility="debug",
            payload={
                "provider": "mem0",
                "result_count": len(results),
                "retained_count": len(items),
            },
        )
    return items
```

Add module helpers:

```python
def _long_term_memory_query(
    run: AgentRun,
    *,
    thread_messages: list[AgentRunContextMessage],
    latest_context_summary: AgentContextSummary | None,
) -> str:
    parts = [run.task_msg]
    if thread_messages:
        parts.append(thread_messages[-1].content)
    if latest_context_summary is not None:
        parts.append(latest_context_summary.summary)
    return "\n\n".join(part for part in parts if part.strip())[:2_000]


def _mem0_recall_item(
    result: LongTermMemorySearchResult,
    *,
    max_value_chars: int,
) -> AgentMemoryRecallItem:
    value, truncated, original_length = _bounded_text(result.memory, max_chars=max_value_chars)
    timestamp = result.updated_at or result.created_at or "1970-01-01T00:00:00Z"
    return AgentMemoryRecallItem(
        memory_id=f"mem0:{result.id}",
        scope="user",
        scope_id=None,
        key=f"mem0:{result.id}",
        value=value,
        source="mem0",
        confidence=result.score,
        visibility="private",
        reason="Mem0 returned this cross-thread memory for the current user query.",
        created_at=result.created_at or timestamp,
        updated_at=timestamp,
        truncated=truncated,
        original_length=original_length,
    )


def _dedupe_memory_items(items: list[AgentMemoryRecallItem]) -> list[AgentMemoryRecallItem]:
    seen: set[str] = set()
    retained: list[AgentMemoryRecallItem] = []
    for item in items:
        key = item.memory_id if item.memory_id.startswith("mem0:") else f"{item.key}:{item.value}"
        if key in seen:
            continue
        seen.add(key)
        retained.append(item)
    return retained
```

- [ ] **Step 5: Wire provider through runtime and worker**

In `backend/src/aithru_agent/worker/runner.py`, import `LongTermMemoryProvider`, add constructor parameter, and pass it into the builder:

```python
from aithru_agent.memory import LongTermMemoryProvider
```

```python
long_term_memory_provider: LongTermMemoryProvider | None = None,
```

```python
self._context_packet_builder = ContextPacketBuilder(
    long_term_memory_provider=long_term_memory_provider,
)
```

In `_build_deps`, pass the event writer:

```python
context_packet = await self._context_packet_builder.build(
    run,
    self._store,
    event_store=self._event_store,
    event_writer=self._event_writer,
)
```

In `backend/src/aithru_agent/application/runtime.py`, import `LongTermMemoryProvider` and `create_long_term_memory_provider`, add the field and factory injection:

```python
from aithru_agent.memory import LongTermMemoryProvider, create_long_term_memory_provider
```

Add to `AgentApplication`:

```python
long_term_memory_provider: LongTermMemoryProvider
```

Add parameter to `create_agent_application`:

```python
long_term_memory_provider: LongTermMemoryProvider | None = None,
```

Resolve before runner construction:

```python
resolved_long_term_memory_provider = (
    long_term_memory_provider
    or create_long_term_memory_provider(resolved_settings)
)
```

Pass into `AgentWorkerRunner`:

```python
long_term_memory_provider=resolved_long_term_memory_provider,
```

Return it from `AgentApplication`:

```python
long_term_memory_provider=resolved_long_term_memory_provider,
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
cd backend
uv run pytest tests/unit/harness/test_context_packet.py::test_context_packet_includes_mem0_recall_items tests/unit/harness/test_context_packet.py::test_context_packet_skips_mem0_without_read_scope tests/integration/test_pydantic_driver.py::test_pydantic_ai_runtime_injects_mem0_context -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/harness/context_packet.py backend/src/aithru_agent/worker/runner.py backend/src/aithru_agent/application/runtime.py backend/tests/unit/harness/test_context_packet.py backend/tests/integration/test_pydantic_driver.py
git commit -m "feat: recall mem0 memory in context packets"
```

---

### Task 4: Mem0 Automatic Write Processor

**Files:**
- Create: `backend/src/aithru_agent/memory/redaction.py`
- Create: `backend/src/aithru_agent/runtime/processors/mem0_memory.py`
- Modify: `backend/src/aithru_agent/runtime/processors/__init__.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Test: `backend/tests/unit/memory/test_redaction.py`
- Test: `backend/tests/unit/runtime/processors/test_mem0_memory_processor.py`
- Test: `backend/tests/integration/test_runtime_processors.py`

**Interfaces:**
- Consumes: `LongTermMemoryProvider.add_messages`
- Produces: `Mem0MemoryProcessor`
- Produces: `memory.add.started`, `memory.add.completed`, `memory.add.skipped`, and `memory.add.failed` audit/debug events.
- Produces: `sanitize_memory_text(value: str) -> str`
- Produces: `contains_no_memory_marker(value: str, markers: list[str]) -> bool`

- [ ] **Step 1: Write failing redaction tests**

Create `backend/tests/unit/memory/test_redaction.py`:

```python
from aithru_agent.memory.redaction import contains_no_memory_marker, sanitize_memory_text


def test_sanitize_memory_text_redacts_secret_like_values() -> None:
    value = (
        "Use api_key=sk-secret and password: hunter2. "
        "Authorization: Bearer abc.def.ghi should not be stored."
    )

    sanitized = sanitize_memory_text(value)

    assert "sk-secret" not in sanitized
    assert "hunter2" not in sanitized
    assert "abc.def.ghi" not in sanitized
    assert "[REDACTED]" in sanitized


def test_contains_no_memory_marker_is_case_insensitive() -> None:
    assert contains_no_memory_marker(
        "Please DO NOT REMEMBER this.",
        ["do not remember"],
    )
    assert not contains_no_memory_marker(
        "Please remember this preference.",
        ["do not remember"],
    )
```

- [ ] **Step 2: Write failing processor tests**

Create `backend/tests/unit/runtime/processors/test_mem0_memory_processor.py`:

```python
from aithru_agent.domain import AgentRunStatus
from aithru_agent.memory import LongTermMemoryAddResult
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.base import AgentRuntimeProcessorContext
from aithru_agent.runtime.processors.mem0_memory import Mem0MemoryProcessor
from aithru_agent.settings import AgentLongTermMemorySettings
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class FakeAddProvider:
    def __init__(self) -> None:
        self.messages = []

    async def search(self, *, run, query: str, limit: int):
        raise AssertionError("write processor must not search")

    async def add_messages(self, *, run, messages):
        del run
        self.messages.append(list(messages))
        return LongTermMemoryAddResult(status="PENDING", event_id="evt_1")

    async def delete_memory(self, *, memory_id: str):
        raise AssertionError("write processor must not delete memory")


async def context_fixture(scopes: list[str]):
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    event_writer = AgentEventWriter(event_store)
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Remember that I prefer concise Chinese summaries.",
        workspace_id=workspace.id,
        scopes=scopes,
        thread_id=thread.id,
    )
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Remember that I prefer concise Chinese summaries.",
        run_id=run.id,
    )
    await store.append_message(
        thread_id=thread.id,
        role="assistant",
        content="I will keep that in mind.",
        run_id=run.id,
    )
    completed = await store.update_run(
        run.id,
        status=AgentRunStatus.COMPLETED,
        result={"content": "I will keep that in mind."},
    )
    return AgentRuntimeProcessorContext(
        run=completed,
        store=store,
        event_writer=event_writer,
        event_store=event_store,
        terminal_status=AgentRunStatus.COMPLETED,
    )


async def test_mem0_processor_adds_completed_run_messages() -> None:
    provider = FakeAddProvider()
    processor = Mem0MemoryProcessor(
        provider=provider,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )
    context = await context_fixture(["agent.memory.write"])

    await processor.after_terminal(context)

    assert len(provider.messages) == 1
    assert [message.role for message in provider.messages[0]] == ["user", "assistant"]
    events = await context.event_store.list_by_run(context.run.id)
    assert [event.type for event in events] == [
        "memory.add.started",
        "memory.add.completed",
    ]
    assert events[-1].payload["event_id"] == "evt_1"


async def test_mem0_processor_skips_without_write_scope() -> None:
    provider = FakeAddProvider()
    processor = Mem0MemoryProcessor(
        provider=provider,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )
    context = await context_fixture(["agent.memory.read"])

    await processor.after_terminal(context)

    assert provider.messages == []
    events = await context.event_store.list_by_run(context.run.id)
    assert events[-1].type == "memory.add.skipped"
    assert events[-1].payload["reason"] == "missing_memory_write_scope"


async def test_mem0_processor_respects_no_memory_marker() -> None:
    provider = FakeAddProvider()
    processor = Mem0MemoryProcessor(
        provider=provider,
        settings=AgentLongTermMemorySettings(provider="mem0", mem0_api_key="mem0-key"),
    )
    context = await context_fixture(["agent.memory.write"])
    run = await context.store.update_run(
        context.run.id,
        task_msg="Do not remember this preference.",
    )
    context = AgentRuntimeProcessorContext(
        run=run,
        store=context.store,
        event_writer=context.event_writer,
        event_store=context.event_store,
        terminal_status=AgentRunStatus.COMPLETED,
    )

    await processor.after_terminal(context)

    assert provider.messages == []
    events = await context.event_store.list_by_run(context.run.id)
    assert events[-1].type == "memory.add.skipped"
    assert events[-1].payload["reason"] == "no_memory_marker"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/unit/memory/test_redaction.py tests/unit/runtime/processors/test_mem0_memory_processor.py -q
```

Expected: FAIL because redaction helpers and `Mem0MemoryProcessor` do not exist.

- [ ] **Step 4: Implement redaction helpers**

Create `backend/src/aithru_agent/memory/redaction.py`:

```python
from __future__ import annotations

import re


REDACTED_VALUE = "[REDACTED]"
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|token|password|passwd|secret|authorization)\s*[:=]\s*([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]+")


def sanitize_memory_text(value: str) -> str:
    redacted = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}={REDACTED_VALUE}", value)
    redacted = _BEARER_TOKEN.sub(f"Bearer {REDACTED_VALUE}", redacted)
    return redacted


def contains_no_memory_marker(value: str, markers: list[str]) -> bool:
    normalized = value.lower()
    return any(marker.lower() in normalized for marker in markers)
```

- [ ] **Step 5: Implement Mem0 write processor**

Create `backend/src/aithru_agent/runtime/processors/mem0_memory.py`:

```python
from __future__ import annotations

from aithru_agent.domain import AgentRunStatus
from aithru_agent.memory import (
    LongTermMemoryMessage,
    LongTermMemoryProvider,
    can_write_long_term_memory,
)
from aithru_agent.memory.redaction import contains_no_memory_marker, sanitize_memory_text
from aithru_agent.settings import AgentLongTermMemorySettings

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class Mem0MemoryProcessor(AgentRuntimeProcessor):
    name = "mem0_memory"

    def __init__(
        self,
        *,
        provider: LongTermMemoryProvider,
        settings: AgentLongTermMemorySettings,
    ) -> None:
        self._provider = provider
        self._settings = settings

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        terminal_status = context.terminal_status or context.run.status
        if terminal_status != AgentRunStatus.COMPLETED:
            return AgentRuntimeProcessorDecision()
        if not self._settings.mem0_add_on_run_complete:
            await self._write_skip(context, "disabled")
            return AgentRuntimeProcessorDecision()
        if not can_write_long_term_memory(context.run.scopes):
            await self._write_skip(context, "missing_memory_write_scope")
            return AgentRuntimeProcessorDecision()
        marker_source = context.run.task_msg
        if contains_no_memory_marker(marker_source, self._settings.mem0_no_memory_markers):
            await self._write_skip(context, "no_memory_marker")
            return AgentRuntimeProcessorDecision()
        messages = await _messages_for_run(context)
        if not messages:
            await self._write_skip(context, "no_messages")
            return AgentRuntimeProcessorDecision()
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.add.started",
            source={"kind": "harness"},
            visibility="debug",
            payload={"provider": "mem0", "message_count": len(messages)},
        )
        try:
            result = await self._provider.add_messages(run=context.run, messages=messages)
        except Exception as exc:
            await context.event_writer.write(
                run_id=context.run.id,
                thread_id=context.run.thread_id,
                type="memory.add.failed",
                source={"kind": "harness"},
                visibility="debug",
                payload={"provider": "mem0", "error": {"message": str(exc)}},
            )
            return AgentRuntimeProcessorDecision()
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.add.completed",
            source={"kind": "harness"},
            visibility="debug",
            payload={
                "provider": "mem0",
                "status": result.status,
                "event_id": result.event_id,
                "message_count": len(messages),
            },
        )
        return AgentRuntimeProcessorDecision()

    async def _write_skip(
        self,
        context: AgentRuntimeProcessorContext,
        reason: str,
    ) -> None:
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.add.skipped",
            source={"kind": "harness"},
            visibility="debug",
            payload={"provider": "mem0", "reason": reason},
        )


async def _messages_for_run(
    context: AgentRuntimeProcessorContext,
) -> list[LongTermMemoryMessage]:
    messages: list[LongTermMemoryMessage] = []
    if context.run.thread_id:
        thread_messages = await context.store.list_messages(context.run.thread_id)
        for message in thread_messages:
            if message.run_id != context.run.id:
                continue
            if message.role not in {"user", "assistant"}:
                continue
            content = sanitize_memory_text(message.content.strip())
            if content:
                messages.append(LongTermMemoryMessage(role=message.role, content=content))
    if messages:
        return messages
    if context.run.result and context.run.result.content.strip():
        return [
            LongTermMemoryMessage(
                role="user",
                content=sanitize_memory_text(context.run.task_msg.strip()),
            ),
            LongTermMemoryMessage(
                role="assistant",
                content=sanitize_memory_text(context.run.result.content.strip()),
            ),
        ]
    return []
```

Update `backend/src/aithru_agent/runtime/processors/__init__.py` to export `Mem0MemoryProcessor`.

- [ ] **Step 6: Wire processor in application runtime**

In `backend/src/aithru_agent/application/runtime.py`, import:

```python
from aithru_agent.runtime.processors.mem0_memory import Mem0MemoryProcessor
```

Change `_create_processor_runner` signature:

```python
def _create_processor_runner(
    settings: AgentSettings,
    *,
    model_profile_registry: AgentModelProfileRegistry | None = None,
    secret_store: AgentSecretStore | None = None,
    long_term_memory_provider: LongTermMemoryProvider | None = None,
) -> AgentRuntimeProcessorRunner:
```

Pass the provider from `create_agent_application`:

```python
processor_runner = _create_processor_runner(
    resolved_settings,
    model_profile_registry=model_profile_registry,
    secret_store=secret_store,
    long_term_memory_provider=resolved_long_term_memory_provider,
)
```

Replace the memory extraction block with:

```python
if settings.long_term_memory.provider == "mem0":
    if (
        settings.long_term_memory.mem0_add_on_run_complete
        and long_term_memory_provider is not None
    ):
        processors.append(
            Mem0MemoryProcessor(
                provider=long_term_memory_provider,
                settings=settings.long_term_memory,
            )
        )
elif settings.processors.memory_extraction_enabled:
    processors.append(MemoryExtractionProcessor())
```

- [ ] **Step 7: Add integration test for app wiring**

Append to `backend/tests/integration/test_runtime_processors.py`:

```python
from aithru_agent.memory import LongTermMemoryAddResult
from aithru_agent.runtime.processors.mem0_memory import Mem0MemoryProcessor
from aithru_agent.settings import AgentLongTermMemorySettings


class AppWiringMem0Provider:
    async def search(self, *, run, query: str, limit: int):
        return []

    async def add_messages(self, *, run, messages):
        return LongTermMemoryAddResult(status="PENDING", event_id="evt_app")

    async def delete_memory(self, *, memory_id: str):
        raise AssertionError("app wiring test must not delete memory")


def test_mem0_provider_mode_registers_mem0_processor_instead_of_candidate_processor() -> None:
    app = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            long_term_memory=AgentLongTermMemorySettings(
                provider="mem0",
                mem0_api_key="mem0-key",
            ),
        ),
        long_term_memory_provider=AppWiringMem0Provider(),
    )

    processor_names = [
        processor.__class__.__name__
        for processor in app.processor_runner.processors
    ]

    assert "Mem0MemoryProcessor" in processor_names
    assert "MemoryExtractionProcessor" not in processor_names
```

- [ ] **Step 8: Run tests to verify they pass**

Run:

```bash
cd backend
uv run pytest tests/unit/memory/test_redaction.py tests/unit/runtime/processors/test_mem0_memory_processor.py tests/integration/test_runtime_processors.py::test_mem0_provider_mode_registers_mem0_processor_instead_of_candidate_processor -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/src/aithru_agent/memory/redaction.py backend/src/aithru_agent/runtime/processors backend/src/aithru_agent/application/runtime.py backend/tests/unit/memory/test_redaction.py backend/tests/unit/runtime/processors/test_mem0_memory_processor.py backend/tests/integration/test_runtime_processors.py
git commit -m "feat: add completed runs to mem0 memory"
```

---

### Task 5: Provider Control Routes And Final Verification

**Files:**
- Create: `backend/src/aithru_agent/api/routes/long_term_memory.py`
- Modify: `backend/src/aithru_agent/api/routes/__init__.py`
- Modify: `README.md`
- Modify: `docs/00-agent-harness-design.md`
- Test: `backend/tests/integration/test_long_term_memory_api.py`

**Interfaces:**
- Consumes: `AgentApplication.long_term_memory_provider`
- Produces: `GET /api/long-term-memory/health`
- Produces: `DELETE /api/long-term-memory/{memory_id}`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/integration/test_long_term_memory_api.py`:

```python
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
    assert response.json() == {"memory_id": "mem0_1", "deleted": True}
    assert provider.deleted == ["mem0_1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
uv run pytest tests/integration/test_long_term_memory_api.py -q
```

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement routes**

Create `backend/src/aithru_agent/api/routes/long_term_memory.py`:

```python
"""Long-term memory provider routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aithru_agent.api.dependencies import ApiDependencies, api_deps
from aithru_agent.memory import LongTermMemoryDeleteResult, NoopLongTermMemoryProvider


router = APIRouter()


class LongTermMemoryHealth(BaseModel):
    provider: str
    enabled: bool


@router.get("/api/long-term-memory/health", response_model=LongTermMemoryHealth)
async def long_term_memory_health(
    deps: ApiDependencies = Depends(api_deps),
) -> LongTermMemoryHealth:
    provider = deps.runtime.settings.long_term_memory.provider
    return LongTermMemoryHealth(
        provider=provider,
        enabled=provider == "mem0",
    )


@router.delete(
    "/api/long-term-memory/{memory_id}",
    response_model=LongTermMemoryDeleteResult,
)
async def delete_long_term_memory(
    memory_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> LongTermMemoryDeleteResult:
    provider = deps.runtime.long_term_memory_provider
    if isinstance(provider, NoopLongTermMemoryProvider):
        return LongTermMemoryDeleteResult(memory_id=memory_id, deleted=False)
    return await provider.delete_memory(memory_id=memory_id)
```

Update `backend/src/aithru_agent/api/routes/__init__.py`:

```python
from aithru_agent.api.routes import (
    approvals,
    artifacts,
    events,
    external_tools,
    health,
    long_term_memory,
    memory,
    memory_candidates,
    messages,
    model_profiles,
    runs,
    skills,
    subagents,
    threads,
    workspaces,
)
```

Add `long_term_memory.router` before `memory.router` in the route list.

- [ ] **Step 4: Run API tests to verify they pass**

Run:

```bash
cd backend
uv run pytest tests/integration/test_long_term_memory_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Update docs with implemented configuration**

In `README.md`, add the following concrete environment variable block near the
memory section:

Mem0-native long-term memory can be enabled with:

```bash
AITHRU_AGENT_LONG_TERM_MEMORY_PROVIDER=mem0
AITHRU_AGENT_MEM0_MODE=platform
AITHRU_AGENT_MEM0_API_KEY=...
AITHRU_AGENT_MEM0_APP_ID=aithru-agent
AITHRU_AGENT_MEM0_TOP_K=8
```

When enabled, run context searches Mem0 before model execution and completed
runs add bounded user/assistant turns to Mem0 after completion. Mem0 writes are
automatic by default; local memory candidates remain available only in local
provider mode or an explicit compliance configuration.

In `docs/00-agent-harness-design.md`, update the Mem0 target paragraph from target language to implemented behavior after the tests pass.

- [ ] **Step 6: Run full verification**

Run:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/src/aithru_agent/api/routes/long_term_memory.py backend/src/aithru_agent/api/routes/__init__.py backend/tests/integration/test_long_term_memory_api.py README.md docs/00-agent-harness-design.md
git commit -m "feat: add long-term memory provider controls"
```

---

## Self-Review Checklist

- Spec coverage:
  - Mem0-native search is covered by Task 3.
  - Mem0-native automatic add is covered by Task 4.
  - Identity mapping is covered by Task 1 and Task 2.
  - No per-memory approval default is covered by Task 4 app wiring.
  - Local memory compatibility is preserved because `MemoryExtractionProcessor` remains active in local provider mode.
  - User control is covered by no-memory markers and provider delete route.
  - Provider events are covered by Task 3 and Task 4.
  - Workflow boundaries are preserved by keeping Mem0 behind harness providers and routes.
- Placeholder scan:
  - The plan contains no placeholder markers or unnamed implementation steps.
  - Each task has explicit files, interfaces, tests, commands, expected outcomes, and commit commands.
- Type consistency:
  - `LongTermMemoryProvider` methods are consumed consistently by Mem0 provider, context packet search, write processor, and routes.
  - `AgentLongTermMemorySettings` field names match the env parsing and task snippets.
  - Event names match the design spec: `memory.search.*`, `memory.add.*`, and provider delete behavior.

## Execution Options

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review each task before moving to the next, and keep commits small.
2. **Inline Execution** - Execute tasks in this session using executing-plans with checkpoints after each task.
