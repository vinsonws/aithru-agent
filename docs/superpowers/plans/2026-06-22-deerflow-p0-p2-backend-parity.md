# DeerFlow P0-P2 Backend Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the P0-P2 capability gaps from `docs/01-deerflow-benchmark.md` while preserving Aithru Agent as a controlled AI harness, not a workflow graph runtime.

**Architecture:** Add a lightweight runtime processor layer for platform-state processors, then hang usage aggregation, summarization, clarification, title generation, and memory extraction from explicit run lifecycle hooks. P2 adds typed product contracts and controlled capability/configuration surfaces for images, file conversion, skill management, external tools, and model profiles without exposing raw local execution, unrestricted network access, or Agent-owned `WorkflowSpec` semantics.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, Pydantic AI as internal harness driver, existing in-memory and SQLite stores, pytest, uv.

---

## Priority Map

| Priority | Benchmark gap | Deliverable |
| --- | --- | --- |
| P0 | Runtime Processor layer | `aithru_agent.runtime.processors` package with ordered before/after run lifecycle hooks. |
| P0 | Run-tree usage / budget aggregation | Read-only usage projections for one run and run tree, plus explicit budget policy checks from `harness_options`. |
| P0 | Context semantic summarization | Durable thread/run summaries that feed back into `AgentRunContextPacket.compressed_context`. |
| P1 | Clarification preflight | Before-model processor that can pause underspecified threaded runs through existing `waiting_input` semantics. |
| P1 | Auto title generation | Processor that generates a short title for untitled threads and emits traceable events. |
| P1 | Async memory extraction | Post-run memory candidates with approve/reject API; approved candidates write normal scoped memory entries. |
| P2 | Vision / view image | Message/workspace attachment model plus controlled `media.view_image` capability with provider and model-profile checks. |
| P2 | File conversion | Upload conversion processor that writes managed markdown/text derivatives for supported document types. |
| P2 | Skill management UI/API | Skill configuration and registry APIs for enabled state, version metadata, and policy overlays. |
| P2 | MCP/external tool config | Product API for external tool server configuration with secret references, allowlists, validation, and audit events. |
| P2 | Multi-model config | Model profile registry and per-run profile selection guarded by platform scopes and budget policy. |

## File Structure

Create these new backend modules:

- `backend/src/aithru_agent/runtime/__init__.py`: Runtime composition package exports.
- `backend/src/aithru_agent/runtime/processors/__init__.py`: Processor package exports.
- `backend/src/aithru_agent/runtime/processors/base.py`: Processor context, decision, and hook interfaces.
- `backend/src/aithru_agent/runtime/processors/runner.py`: Ordered processor runner.
- `backend/src/aithru_agent/runtime/processors/usage.py`: Usage aggregation and budget check processor.
- `backend/src/aithru_agent/runtime/processors/summarization.py`: Context summary processor and summary provider interface.
- `backend/src/aithru_agent/runtime/processors/clarification.py`: Clarification preflight processor.
- `backend/src/aithru_agent/runtime/processors/title.py`: Thread title processor.
- `backend/src/aithru_agent/runtime/processors/memory_extraction.py`: Memory candidate extraction processor.
- `backend/src/aithru_agent/runtime/processors/file_conversion.py`: Workspace upload conversion processor.
- `backend/src/aithru_agent/domain/usage.py`: Usage counters, budget policy, and run-tree usage contracts.
- `backend/src/aithru_agent/domain/summary.py`: Durable context summary contracts.
- `backend/src/aithru_agent/domain/memory_candidate.py`: Memory candidate contracts and approval result.
- `backend/src/aithru_agent/domain/media.py`: Message attachment, image view request/result, and media policy contracts.
- `backend/src/aithru_agent/domain/file_conversion.py`: File conversion job/result contracts.
- `backend/src/aithru_agent/domain/model_profile.py`: Model profile and capability contracts.
- `backend/src/aithru_agent/domain/external_tool_config.py`: External tool configuration contracts.
- `backend/src/aithru_agent/api/routes/model_profiles.py`: Model profile API.
- `backend/src/aithru_agent/api/routes/external_tool_configs.py`: External tool configuration API.
- `backend/src/aithru_agent/api/routes/media.py`: Controlled media inspection API.
- `backend/src/aithru_agent/api/routes/memory_candidates.py`: Memory candidate review API.

Modify these existing backend modules:

- `backend/src/aithru_agent/domain/__init__.py`: Export new Pydantic contracts.
- `backend/src/aithru_agent/domain/run.py`: Add budget policy and model profile fields to `AgentRunHarnessOptions`.
- `backend/src/aithru_agent/domain/message.py`: Add `attachments: list[AgentMessageAttachment]`.
- `backend/src/aithru_agent/persistence/protocols.py`: Add processor state, summary, memory candidate, model profile, and external tool config store methods.
- `backend/src/aithru_agent/persistence/memory/store.py`: Implement new store methods for tests and local development.
- `backend/src/aithru_agent/persistence/sqlite/store.py`: Persist new contracts in the existing `agent_documents` JSON document table.
- `backend/src/aithru_agent/application/runtime.py`: Construct default processors and pass them into `AgentWorkerRunner`.
- `backend/src/aithru_agent/worker/runner.py`: Call processor hooks before model execution and after terminal completion/failure.
- `backend/src/aithru_agent/harness/context_packet.py`: Load durable summaries and image/text conversion references into bounded context.
- `backend/src/aithru_agent/api/dependencies.py`: Add request models and visibility helpers for new routes.
- `backend/src/aithru_agent/api/routes/__init__.py`: Register new route groups.
- `backend/src/aithru_agent/api/routes/runs.py`: Add usage endpoints and expose budget state in run detail/snapshot paths.
- `backend/src/aithru_agent/api/routes/threads.py`: Surface generated titles and latest summary metadata in thread workbench/dashboard projections.
- `backend/src/aithru_agent/api/routes/workspaces.py`: Trigger file conversion after uploads and expose conversion status.
- `backend/src/aithru_agent/api/routes/skills.py`: Add skill configuration and version endpoints.
- `backend/src/aithru_agent/capabilities/local_tools/__init__.py`: Export media local tool.
- `backend/src/aithru_agent/capabilities/local_tools/media.py`: Controlled `media.view_image` tool.
- `backend/src/aithru_agent/settings.py`: Add processor, conversion, external config, and model profile settings.
- `docs/00-agent-harness-design.md`: Document processor layer and P0-P2 boundaries.
- `docs/01-deerflow-benchmark.md`: Mark completed roadmap rows as implemented when tasks land.
- `README.md`: Update backend positioning only when public API or setup changes.

## Task 1: P0 Runtime Processor Layer

**Files:**
- Create: `backend/src/aithru_agent/runtime/__init__.py`
- Create: `backend/src/aithru_agent/runtime/processors/__init__.py`
- Create: `backend/src/aithru_agent/runtime/processors/base.py`
- Create: `backend/src/aithru_agent/runtime/processors/runner.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Modify: `backend/src/aithru_agent/worker/runner.py`
- Test: `backend/tests/unit/runtime/test_processors.py`
- Test: `backend/tests/integration/test_runtime_processors.py`

- [ ] **Step 1: Write the failing ordered-hook unit test**

```python
import pytest

from aithru_agent.domain import AgentRun, AgentRunSource, AgentRunStatus
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
    AgentRuntimeProcessorRunner,
)
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


class RecordingProcessor(AgentRuntimeProcessor):
    def __init__(self, name: str, sink: list[str]) -> None:
        self.name = name
        self._sink = sink

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        self._sink.append(f"before:{self.name}:{context.run.id}")
        return AgentRuntimeProcessorDecision()

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        self._sink.append(f"after:{self.name}:{context.run.id}:{context.terminal_status}")
        return AgentRuntimeProcessorDecision()


@pytest.mark.asyncio
async def test_processor_runner_invokes_hooks_in_order() -> None:
    store = InMemoryAgentStore()
    events = InMemoryAgentEventStore()
    writer = AgentEventWriter(events)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.API,
        goal="Summarize the workspace",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    sink: list[str] = []
    runner = AgentRuntimeProcessorRunner(
        processors=[
            RecordingProcessor("first", sink),
            RecordingProcessor("second", sink),
        ]
    )

    await runner.before_model(
        run=run,
        store=store,
        event_writer=writer,
        event_store=events,
        skill=None,
    )
    completed = run.model_copy(update={"status": AgentRunStatus.COMPLETED})
    await runner.after_terminal(
        run=completed,
        store=store,
        event_writer=writer,
        event_store=events,
        skill=None,
        terminal_status=AgentRunStatus.COMPLETED,
    )

    assert sink == [
        "before:first:run_1",
        "before:second:run_1",
        "after:first:run_1:completed",
        "after:second:run_1:completed",
    ]
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/test_processors.py -q
```

Expected: FAIL with an import error for `aithru_agent.runtime.processors`.

- [ ] **Step 3: Add the processor base contracts**

Add this implementation to `backend/src/aithru_agent/runtime/processors/base.py`:

```python
from dataclasses import dataclass

from aithru_agent.domain import AgentRun, AgentRunStatus, AgentSkill
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream import AgentEventWriter


@dataclass(frozen=True)
class AgentRuntimeProcessorContext:
    run: AgentRun
    store: AgentStore
    event_writer: AgentEventWriter
    event_store: AgentEventStore | None = None
    skill: AgentSkill | None = None
    terminal_status: AgentRunStatus | None = None


@dataclass(frozen=True)
class AgentRuntimeProcessorDecision:
    paused_run: AgentRun | None = None
    replaced_run: AgentRun | None = None

    @property
    def should_stop(self) -> bool:
        return self.paused_run is not None or self.replaced_run is not None


class AgentRuntimeProcessor:
    name: str = "runtime_processor"

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        return AgentRuntimeProcessorDecision()

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        return AgentRuntimeProcessorDecision()
```

- [ ] **Step 4: Add the ordered runner and package exports**

Add this implementation to `backend/src/aithru_agent/runtime/processors/runner.py`:

```python
from collections.abc import Sequence

from aithru_agent.domain import AgentRun, AgentRunStatus, AgentSkill
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream import AgentEventWriter

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class AgentRuntimeProcessorRunner:
    def __init__(self, processors: Sequence[AgentRuntimeProcessor] | None = None) -> None:
        self._processors = list(processors or [])

    @property
    def processors(self) -> list[AgentRuntimeProcessor]:
        return list(self._processors)

    async def before_model(
        self,
        *,
        run: AgentRun,
        store: AgentStore,
        event_writer: AgentEventWriter,
        event_store: AgentEventStore | None,
        skill: AgentSkill | None,
    ) -> AgentRuntimeProcessorDecision:
        context = AgentRuntimeProcessorContext(
            run=run,
            store=store,
            event_writer=event_writer,
            event_store=event_store,
            skill=skill,
        )
        for processor in self._processors:
            decision = await processor.before_model(context)
            if decision.should_stop:
                return decision
        return AgentRuntimeProcessorDecision()

    async def after_terminal(
        self,
        *,
        run: AgentRun,
        store: AgentStore,
        event_writer: AgentEventWriter,
        event_store: AgentEventStore | None,
        skill: AgentSkill | None,
        terminal_status: AgentRunStatus,
    ) -> AgentRuntimeProcessorDecision:
        context = AgentRuntimeProcessorContext(
            run=run,
            store=store,
            event_writer=event_writer,
            event_store=event_store,
            skill=skill,
            terminal_status=terminal_status,
        )
        latest_decision = AgentRuntimeProcessorDecision()
        for processor in self._processors:
            latest_decision = await processor.after_terminal(context)
        return latest_decision
```

Add exports to `backend/src/aithru_agent/runtime/processors/__init__.py`:

```python
from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)
from .runner import AgentRuntimeProcessorRunner

__all__ = [
    "AgentRuntimeProcessor",
    "AgentRuntimeProcessorContext",
    "AgentRuntimeProcessorDecision",
    "AgentRuntimeProcessorRunner",
]
```

Add exports to `backend/src/aithru_agent/runtime/__init__.py`:

```python
from .processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
    AgentRuntimeProcessorRunner,
)

__all__ = [
    "AgentRuntimeProcessor",
    "AgentRuntimeProcessorContext",
    "AgentRuntimeProcessorDecision",
    "AgentRuntimeProcessorRunner",
]
```

- [ ] **Step 5: Inject the processor runner into `AgentWorkerRunner`**

Modify `backend/src/aithru_agent/worker/runner.py` so the constructor accepts `processor_runner: AgentRuntimeProcessorRunner | None = None`, stores it as `self._processor_runner`, and uses `AgentRuntimeProcessorRunner()` as the default.

Before `model.started`, add this hook:

```python
        processor_decision = await self._processor_runner.before_model(
            run=run,
            store=self._store,
            event_writer=self._event_writer,
            event_store=self._event_store,
            skill=skill,
        )
        if processor_decision.paused_run is not None:
            return processor_decision.paused_run
        if processor_decision.replaced_run is not None:
            run = processor_decision.replaced_run
```

At the end of `_complete_run`, `_fail_run`, and cancellation paths, call `after_terminal` with the terminal run returned by the store. Keep those hooks after terminal events have been persisted so processors can project from the event log.

- [ ] **Step 6: Wire default processors through application assembly**

Modify `backend/src/aithru_agent/application/runtime.py` to construct a processor runner and pass it into `AgentWorkerRunner`:

```python
from aithru_agent.runtime import AgentRuntimeProcessorRunner


def _create_processor_runner(settings: AgentSettings) -> AgentRuntimeProcessorRunner:
    return AgentRuntimeProcessorRunner(processors=[])
```

Then:

```python
    processor_runner = _create_processor_runner(resolved_settings)
    runner = AgentWorkerRunner(
        store=resolved_store,
        event_writer=event_writer,
        capability_router=capability_router,
        event_store=resolved_event_store,
        agent_runtime=resolved_agent_runtime,
        skill_resolver=resolved_skill_resolver,
        processor_runner=processor_runner,
    )
```

- [ ] **Step 7: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/test_processors.py tests/integration/test_runtime_processors.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/runtime backend/src/aithru_agent/application/runtime.py backend/src/aithru_agent/worker/runner.py backend/tests/unit/runtime/test_processors.py backend/tests/integration/test_runtime_processors.py
git commit -m "feat: add runtime processor hooks"
```

## Task 2: P0 Run-Tree Usage And Budget Aggregation

**Files:**
- Create: `backend/src/aithru_agent/domain/usage.py`
- Create: `backend/src/aithru_agent/runtime/processors/usage.py`
- Modify: `backend/src/aithru_agent/domain/run.py`
- Modify: `backend/src/aithru_agent/domain/__init__.py`
- Modify: `backend/src/aithru_agent/api/routes/runs.py`
- Test: `backend/tests/unit/domain/test_usage.py`
- Test: `backend/tests/unit/runtime/processors/test_usage_processor.py`
- Test: `backend/tests/integration/test_run_usage_api.py`

- [ ] **Step 1: Write failing domain tests for event aggregation**

```python
from aithru_agent.domain.usage import (
    AgentRunBudgetPolicy,
    AgentRunUsageSummary,
    aggregate_model_usage_payloads,
)


def test_aggregate_model_usage_payloads_sums_requests_and_tokens() -> None:
    summary = aggregate_model_usage_payloads(
        run_id="run_1",
        payloads=[
            {"requests": 1, "input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
            {"requests": 2, "input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
        ],
    )

    assert summary == AgentRunUsageSummary(
        run_id="run_1",
        own_requests=3,
        own_input_tokens=27,
        own_output_tokens=8,
        own_total_tokens=35,
        descendant_requests=0,
        descendant_input_tokens=0,
        descendant_output_tokens=0,
        descendant_total_tokens=0,
        external_requests=0,
        external_total_tokens=0,
        budget_policy=None,
        budget_status="ok",
        warnings=[],
    )


def test_budget_policy_warns_and_exceeds_on_total_tokens() -> None:
    summary = AgentRunUsageSummary(
        run_id="run_1",
        own_requests=1,
        own_input_tokens=80,
        own_output_tokens=20,
        own_total_tokens=100,
        budget_policy=AgentRunBudgetPolicy(max_total_tokens=90, warn_at_ratio=0.75),
    )

    assert summary.budget_status == "exceeded"
    assert summary.warnings == ["total_tokens_exceeded"]
```

- [ ] **Step 2: Run the failing domain test**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_usage.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'aithru_agent.domain.usage'`.

- [ ] **Step 3: Add usage contracts and budget policy**

Add this implementation to `backend/src/aithru_agent/domain/usage.py`:

```python
from typing import Literal

from pydantic import Field, computed_field, field_validator

from .base import AithruBaseModel


AgentRunBudgetStatus = Literal["ok", "warning", "exceeded"]


class AgentRunBudgetPolicy(AithruBaseModel):
    max_requests: int | None = Field(default=None, ge=1)
    max_total_tokens: int | None = Field(default=None, ge=1)
    warn_at_ratio: float = Field(default=0.8, gt=0, le=1)


class AgentUsageCounters(AithruBaseModel):
    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    def add(self, other: "AgentUsageCounters") -> "AgentUsageCounters":
        return AgentUsageCounters(
            requests=self.requests + other.requests,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class AgentRunUsageSummary(AithruBaseModel):
    run_id: str
    own_requests: int = Field(default=0, ge=0)
    own_input_tokens: int = Field(default=0, ge=0)
    own_output_tokens: int = Field(default=0, ge=0)
    own_total_tokens: int = Field(default=0, ge=0)
    descendant_requests: int = Field(default=0, ge=0)
    descendant_input_tokens: int = Field(default=0, ge=0)
    descendant_output_tokens: int = Field(default=0, ge=0)
    descendant_total_tokens: int = Field(default=0, ge=0)
    external_requests: int = Field(default=0, ge=0)
    external_total_tokens: int = Field(default=0, ge=0)
    budget_policy: AgentRunBudgetPolicy | None = None
    budget_status: AgentRunBudgetStatus = "ok"
    warnings: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def total_requests(self) -> int:
        return self.own_requests + self.descendant_requests + self.external_requests

    @computed_field
    @property
    def total_tokens(self) -> int:
        return self.own_total_tokens + self.descendant_total_tokens + self.external_total_tokens


class AgentRunTreeUsageSnapshot(AithruBaseModel):
    root_run_id: str
    runs: list[AgentRunUsageSummary]
    total_requests: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    budget_status: AgentRunBudgetStatus
    warnings: list[str] = Field(default_factory=list)


def aggregate_model_usage_payloads(
    *,
    run_id: str,
    payloads: list[dict],
    budget_policy: AgentRunBudgetPolicy | None = None,
) -> AgentRunUsageSummary:
    counters = AgentUsageCounters()
    for payload in payloads:
        counters = counters.add(
            AgentUsageCounters(
                requests=_int_payload(payload, "requests"),
                input_tokens=_int_payload(payload, "input_tokens"),
                output_tokens=_int_payload(payload, "output_tokens"),
                total_tokens=_int_payload(payload, "total_tokens"),
            )
        )
    status, warnings = _budget_status(
        total_requests=counters.requests,
        total_tokens=counters.total_tokens,
        budget_policy=budget_policy,
    )
    return AgentRunUsageSummary(
        run_id=run_id,
        own_requests=counters.requests,
        own_input_tokens=counters.input_tokens,
        own_output_tokens=counters.output_tokens,
        own_total_tokens=counters.total_tokens,
        budget_policy=budget_policy,
        budget_status=status,
        warnings=warnings,
    )


def _budget_status(
    *,
    total_requests: int,
    total_tokens: int,
    budget_policy: AgentRunBudgetPolicy | None,
) -> tuple[AgentRunBudgetStatus, list[str]]:
    if budget_policy is None:
        return "ok", []
    warnings: list[str] = []
    exceeded = False
    if budget_policy.max_requests is not None:
        if total_requests > budget_policy.max_requests:
            warnings.append("requests_exceeded")
            exceeded = True
        elif total_requests >= int(budget_policy.max_requests * budget_policy.warn_at_ratio):
            warnings.append("requests_near_limit")
    if budget_policy.max_total_tokens is not None:
        if total_tokens > budget_policy.max_total_tokens:
            warnings.append("total_tokens_exceeded")
            exceeded = True
        elif total_tokens >= int(budget_policy.max_total_tokens * budget_policy.warn_at_ratio):
            warnings.append("total_tokens_near_limit")
    if exceeded:
        return "exceeded", warnings
    if warnings:
        return "warning", warnings
    return "ok", []


def _int_payload(payload: dict, key: str) -> int:
    value = payload.get(key, 0)
    return value if isinstance(value, int) and value > 0 else 0
```

Modify `AgentRunHarnessOptions` in `backend/src/aithru_agent/domain/run.py`:

```python
from .usage import AgentRunBudgetPolicy


class AgentRunHarnessOptions(AithruBaseModel):
    model: str | None = None
    model_profile_id: str | None = None
    instructions: str | None = None
    budget_policy: AgentRunBudgetPolicy | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    research_continuation: AgentRunResearchContinuationOptions | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    operator_follow_up: AgentRunOperatorFollowUpOptions | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
```

- [ ] **Step 4: Add usage projection helpers and API routes**

In `backend/src/aithru_agent/runtime/processors/usage.py`, add helpers that read `model.usage` events and child runs:

```python
from aithru_agent.domain import AgentRun
from aithru_agent.domain.usage import (
    AgentRunTreeUsageSnapshot,
    AgentRunUsageSummary,
    aggregate_model_usage_payloads,
)
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore


async def build_run_usage_summary(
    *,
    run: AgentRun,
    store: AgentStore,
    event_store: AgentEventStore,
) -> AgentRunUsageSummary:
    events = await event_store.list_by_run(run.id)
    payloads = [
        event.payload
        for event in events
        if event.type == "model.usage" and isinstance(event.payload, dict)
    ]
    return aggregate_model_usage_payloads(
        run_id=run.id,
        payloads=payloads,
        budget_policy=run.harness_options.budget_policy if run.harness_options else None,
    )
```

Add `GET /api/runs/{run_id}/usage` and `GET /api/runs/{run_id}/tree/usage` in `backend/src/aithru_agent/api/routes/runs.py`. The first endpoint returns `AgentRunUsageSummary`; the second returns `AgentRunTreeUsageSnapshot`. Use existing run visibility checks and existing child-run relationships from subagent and follow-up lineage events.

- [ ] **Step 5: Add integration tests for run usage API**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application import create_agent_runtime
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.stream import InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_run_usage_endpoint_projects_model_usage_events() -> None:
    store = InMemoryAgentStore()
    events = InMemoryAgentEventStore()
    runtime = create_agent_runtime(store=store, event_store=events)
    app = create_app(runtime)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Track usage",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=None,
        type="model.usage",
        source={"kind": "model"},
        visibility="debug",
        payload={"requests": 1, "input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{run.id}/usage")

    assert response.status_code == 200
    assert response.json()["own_total_tokens"] == 18
    assert response.json()["budget_status"] == "ok"
```

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_usage.py tests/unit/runtime/processors/test_usage_processor.py tests/integration/test_run_usage_api.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain backend/src/aithru_agent/runtime/processors/usage.py backend/src/aithru_agent/api/routes/runs.py backend/tests/unit/domain/test_usage.py backend/tests/unit/runtime/processors/test_usage_processor.py backend/tests/integration/test_run_usage_api.py
git commit -m "feat: add run usage projections"
```

## Task 3: P0 Durable Context Semantic Summarization

**Files:**
- Create: `backend/src/aithru_agent/domain/summary.py`
- Create: `backend/src/aithru_agent/runtime/processors/summarization.py`
- Modify: `backend/src/aithru_agent/domain/context.py`
- Modify: `backend/src/aithru_agent/harness/context_packet.py`
- Modify: `backend/src/aithru_agent/persistence/protocols.py`
- Modify: `backend/src/aithru_agent/persistence/memory/store.py`
- Modify: `backend/src/aithru_agent/persistence/sqlite/store.py`
- Test: `backend/tests/unit/runtime/processors/test_summarization_processor.py`
- Test: `backend/tests/unit/harness/test_context_packet_builder.py`

- [ ] **Step 1: Write failing tests for persisted summary reuse**

```python
import pytest

from aithru_agent.domain import AgentMessageRole
from aithru_agent.domain.summary import AgentContextSummary
from aithru_agent.harness import ContextPacketBuilder
from aithru_agent.persistence.memory import InMemoryAgentStore


@pytest.mark.asyncio
async def test_context_packet_uses_latest_thread_summary_when_messages_are_dropped() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue the investigation",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["*"],
    )
    for index in range(5):
        await store.append_message(
            thread_id=thread.id,
            role=AgentMessageRole.USER,
            content=f"Earlier detail {index}",
        )
    await store.create_context_summary(
        AgentContextSummary(
            id="summary_1",
            org_id="org_1",
            thread_id=thread.id,
            run_id=run.id,
            summary="The user is investigating Aithru Agent run resilience.",
            source="semantic_processor",
            source_sequence=5,
            message_count=5,
            created_at="2026-06-22T00:00:00Z",
        )
    )

    packet = await ContextPacketBuilder(max_thread_messages=2).build(run, store)

    assert packet.compressed_context is not None
    assert "run resilience" in packet.compressed_context.summary
    assert packet.budget is not None
    assert packet.budget.dropped_thread_messages == 3
```

- [ ] **Step 2: Run the failing summary tests**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_summarization_processor.py tests/unit/harness/test_context_packet_builder.py -q
```

Expected: FAIL because `AgentContextSummary` and summary store methods are missing.

- [ ] **Step 3: Add durable summary contracts**

Add this implementation to `backend/src/aithru_agent/domain/summary.py`:

```python
from typing import Literal

from pydantic import Field, field_validator

from .base import AithruBaseModel


AgentContextSummarySource = Literal["semantic_processor", "manual", "import"]


class AgentContextSummary(AithruBaseModel):
    id: str
    org_id: str
    thread_id: str | None = None
    run_id: str | None = None
    summary: str = Field(min_length=1)
    source: AgentContextSummarySource
    source_sequence: int | None = Field(default=None, ge=0)
    message_count: int = Field(default=0, ge=0)
    token_estimate: int | None = Field(default=None, ge=0)
    created_at: str

    @field_validator("id", "org_id", "summary", "created_at")
    @classmethod
    def _required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("summary strings cannot be blank")
        return stripped
```

Add store protocol methods:

```python
async def create_context_summary(self, summary: AgentContextSummary) -> AgentContextSummary:
    raise NotImplementedError

async def list_context_summaries(
    self,
    *,
    org_id: str,
    thread_id: str | None = None,
    run_id: str | None = None,
) -> list[AgentContextSummary]:
    raise NotImplementedError
```

Implement both in memory and SQLite stores using existing id counters for production-created summaries and JSON document storage for SQLite.

- [ ] **Step 4: Add semantic summary processor**

Add a `SemanticSummaryProvider` and processor to `backend/src/aithru_agent/runtime/processors/summarization.py`:

```python
from dataclasses import dataclass

from aithru_agent.domain import AgentMessage
from aithru_agent.domain.summary import AgentContextSummary
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class SemanticSummaryProvider:
    async def summarize_messages(self, messages: list[AgentMessage]) -> str:
        joined = " ".join(message.content.strip() for message in messages if message.content.strip())
        return joined[:600] if joined else "No thread context was available."


@dataclass
class ContextSummarizationProcessor(AgentRuntimeProcessor):
    provider: SemanticSummaryProvider
    min_message_count: int = 6
    name: str = "context_summarization"

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()
        messages = await context.store.list_messages(context.run.thread_id)
        if len(messages) < self.min_message_count:
            return AgentRuntimeProcessorDecision()
        summary_text = await self.provider.summarize_messages(messages)
        summary = AgentContextSummary(
            id=f"summary_{context.run.id}",
            org_id=context.run.org_id,
            thread_id=context.run.thread_id,
            run_id=context.run.id,
            summary=summary_text,
            source="semantic_processor",
            source_sequence=None,
            message_count=len(messages),
            created_at=_utc_now(),
        )
        await context.store.create_context_summary(summary)
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="context.summary.created",
            source={"kind": "harness"},
            visibility="debug",
            payload=summary.model_dump(mode="json"),
        )
        return AgentRuntimeProcessorDecision()
```

Use the same `utc_now()` helper pattern as the stores.

- [ ] **Step 5: Feed summaries into context packets**

Modify `ContextPacketBuilder.build()` in `backend/src/aithru_agent/harness/context_packet.py` so when `dropped_thread_messages > 0`, it loads the latest summary for the run thread and prefixes the compressed context summary with the durable summary text:

```python
        latest_summary = await self._latest_thread_summary(run, store)
        compressed_context = _compressed_context(
            dropped_thread_messages=dropped_thread_messages,
            dropped_todos=dropped_todos,
            dropped_artifacts=dropped_artifacts,
            dropped_tool_results=dropped_tool_results,
            dropped_memory=dropped_memory,
            dropped_research_evidence=dropped_research_evidence,
            durable_summary=latest_summary.summary if latest_summary else None,
        )
```

Add `_latest_thread_summary()` to return the most recent `AgentContextSummary` for the run org and thread.

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_summarization_processor.py tests/unit/harness/test_context_packet_builder.py tests/unit/persistence/test_memory_store.py tests/unit/persistence/test_sqlite_store.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain backend/src/aithru_agent/runtime/processors/summarization.py backend/src/aithru_agent/harness/context_packet.py backend/src/aithru_agent/persistence backend/tests/unit/runtime/processors/test_summarization_processor.py backend/tests/unit/harness/test_context_packet_builder.py backend/tests/unit/persistence
git commit -m "feat: persist semantic context summaries"
```

## Task 4: P1 Clarification Preflight

**Files:**
- Create: `backend/src/aithru_agent/runtime/processors/clarification.py`
- Modify: `backend/src/aithru_agent/settings.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Test: `backend/tests/unit/runtime/processors/test_clarification_processor.py`
- Test: `backend/tests/integration/test_clarification_preflight.py`

- [ ] **Step 1: Write failing integration test for `waiting_input` preflight**

```python
import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.application import create_agent_runtime
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.stream import InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_clarification_preflight_pauses_before_model_for_short_thread_goal() -> None:
    store = InMemoryAgentStore()
    events = InMemoryAgentEventStore()
    runtime = create_agent_runtime(
        store=store,
        event_store=events,
        agent_runtime=AgentRuntime(model=TestModel(custom_output_text="model should not run")),
    )
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Fix it",
        scopes=["agent.input.write"],
        thread_id=thread.id,
    )

    result = await runtime.runner.execute_run(run.id)

    assert result.status == "waiting_input"
    event_types = [event.type for event in await events.list_by_run(run.id)]
    assert "input.requested" in event_types
    assert "model.started" not in event_types
```

- [ ] **Step 2: Run the failing clarification test**

Run:

```bash
cd backend
uv run pytest tests/integration/test_clarification_preflight.py -q
```

Expected: FAIL because no clarification processor exists.

- [ ] **Step 3: Add clarification policy and processor**

Add settings:

```python
class AgentProcessorSettings(AithruBaseModel):
    clarification_enabled: bool = True
    clarification_min_goal_words: int = Field(default=4, ge=1, le=20)
```

Add processor implementation:

```python
from dataclasses import dataclass

from aithru_agent.domain import AgentRunStatus
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


@dataclass
class ClarificationPreflightProcessor(AgentRuntimeProcessor):
    min_goal_words: int = 4
    name: str = "clarification_preflight"

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()
        if "agent.input.write" not in context.run.scopes and "*" not in context.run.scopes:
            return AgentRuntimeProcessorDecision()
        words = [word for word in context.run.goal.strip().split() if word]
        if len(words) >= self.min_goal_words:
            return AgentRuntimeProcessorDecision()
        payload = {
            "input_request_id": f"clarify_{context.run.id}",
            "tool_call_id": f"clarify_{context.run.id}",
            "prompt": "What should the agent focus on, and what result should it produce?",
            "reason": "The run goal is too short to execute safely.",
        }
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="input.requested",
            source={"kind": "harness"},
            payload=payload,
        )
        paused = await context.store.update_run(
            context.run.id,
            status=AgentRunStatus.WAITING_INPUT,
        )
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={"status": "waiting_input", **payload},
        )
        return AgentRuntimeProcessorDecision(paused_run=paused)
```

- [ ] **Step 4: Wire the processor through application assembly**

In `_create_processor_runner(settings)`, include `ClarificationPreflightProcessor` when enabled. Keep it before model, before title and summary processors:

```python
processors = []
if settings.processors.clarification_enabled:
    processors.append(
        ClarificationPreflightProcessor(
            min_goal_words=settings.processors.clarification_min_goal_words
        )
    )
return AgentRuntimeProcessorRunner(processors=processors)
```

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_clarification_processor.py tests/integration/test_clarification_preflight.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/runtime/processors/clarification.py backend/src/aithru_agent/settings.py backend/src/aithru_agent/application/runtime.py backend/tests/unit/runtime/processors/test_clarification_processor.py backend/tests/integration/test_clarification_preflight.py
git commit -m "feat: add clarification preflight processor"
```

## Task 5: P1 Auto Thread Title Generation

**Files:**
- Create: `backend/src/aithru_agent/runtime/processors/title.py`
- Modify: `backend/src/aithru_agent/settings.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Modify: `backend/src/aithru_agent/api/routes/threads.py`
- Test: `backend/tests/unit/runtime/processors/test_title_processor.py`
- Test: `backend/tests/integration/test_thread_title_generation.py`

- [ ] **Step 1: Write failing title processor test**

```python
import pytest

from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.runtime.processors.title import ThreadTitleProcessor
from aithru_agent.runtime.processors import AgentRuntimeProcessorContext
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_title_processor_generates_title_for_untitled_thread() -> None:
    store = InMemoryAgentStore()
    events = InMemoryAgentEventStore()
    writer = AgentEventWriter(events)
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Compare Aithru Agent with DeerFlow for long running research tasks",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["*"],
    )

    await ThreadTitleProcessor().before_model(
        AgentRuntimeProcessorContext(
            run=run,
            store=store,
            event_writer=writer,
            event_store=events,
        )
    )

    updated = await store.get_thread(thread.id)
    assert updated is not None
    assert updated.title == "Compare Aithru Agent With DeerFlow"
```

- [ ] **Step 2: Run the failing title test**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_title_processor.py -q
```

Expected: FAIL because `ThreadTitleProcessor` is missing.

- [ ] **Step 3: Add deterministic title generator**

Add this implementation to `backend/src/aithru_agent/runtime/processors/title.py`:

```python
from dataclasses import dataclass

from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


@dataclass
class ThreadTitleProcessor(AgentRuntimeProcessor):
    max_words: int = 6
    name: str = "thread_title"

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()
        thread = await context.store.get_thread(context.run.thread_id)
        if thread is None or thread.title:
            return AgentRuntimeProcessorDecision()
        title = _title_from_goal(context.run.goal, max_words=self.max_words)
        updated = await context.store.update_thread(thread.id, title=title)
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=thread.id,
            type="thread.title.generated",
            source={"kind": "harness"},
            visibility="debug",
            payload={"thread_id": updated.id, "title": updated.title},
        )
        return AgentRuntimeProcessorDecision()


def _title_from_goal(goal: str, *, max_words: int) -> str:
    words = [
        word.strip(".,:;!?()[]{}").capitalize()
        for word in goal.split()
        if word.strip(".,:;!?()[]{}")
    ]
    title_words = words[:max_words]
    return " ".join(title_words) or "New Agent Thread"
```

- [ ] **Step 4: Wire title processor after clarification**

Add `ThreadTitleProcessor()` after `ClarificationPreflightProcessor` in `_create_processor_runner(settings)`. If clarification pauses, title generation will not run until the resumed run has enough context.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_title_processor.py tests/integration/test_thread_title_generation.py tests/api/test_langgraph_like_routes.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/runtime/processors/title.py backend/src/aithru_agent/settings.py backend/src/aithru_agent/application/runtime.py backend/src/aithru_agent/api/routes/threads.py backend/tests/unit/runtime/processors/test_title_processor.py backend/tests/integration/test_thread_title_generation.py
git commit -m "feat: generate thread titles from run goals"
```

## Task 6: P1 Async Memory Extraction Candidates

**Files:**
- Create: `backend/src/aithru_agent/domain/memory_candidate.py`
- Create: `backend/src/aithru_agent/runtime/processors/memory_extraction.py`
- Create: `backend/src/aithru_agent/api/routes/memory_candidates.py`
- Modify: `backend/src/aithru_agent/persistence/protocols.py`
- Modify: `backend/src/aithru_agent/persistence/memory/store.py`
- Modify: `backend/src/aithru_agent/persistence/sqlite/store.py`
- Modify: `backend/src/aithru_agent/api/routes/__init__.py`
- Test: `backend/tests/unit/runtime/processors/test_memory_extraction_processor.py`
- Test: `backend/tests/integration/test_memory_candidates_api.py`

- [ ] **Step 1: Write failing candidate API test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application import create_agent_runtime
from aithru_agent.domain.memory_candidate import AgentMemoryCandidate
from aithru_agent.persistence.memory import InMemoryAgentStore


@pytest.mark.asyncio
async def test_memory_candidate_can_be_approved_into_memory() -> None:
    store = InMemoryAgentStore()
    runtime = create_agent_runtime(store=store)
    app = create_app(runtime)
    candidate = AgentMemoryCandidate(
        id="memcand_1",
        org_id="org_1",
        run_id="run_1",
        scope="user",
        scope_id="user_1",
        key="preferred_report_style",
        value="Prefers concise reports with evidence tables.",
        confidence=0.82,
        status="pending",
        created_at="2026-06-22T00:00:00Z",
    )
    await store.create_memory_candidate(candidate)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/memory-candidates/memcand_1/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["candidate"]["status"] == "approved"
    assert body["memory_entry"]["key"] == "preferred_report_style"
```

- [ ] **Step 2: Add candidate contracts and store methods**

Add `AgentMemoryCandidate` and `AgentMemoryCandidateApprovalResult`:

```python
from typing import Literal

from pydantic import Field

from .base import AithruBaseModel
from .memory import AgentMemoryEntry, AgentMemoryRetentionPolicy


AgentMemoryCandidateStatus = Literal["pending", "approved", "rejected"]


class AgentMemoryCandidate(AithruBaseModel):
    id: str
    org_id: str
    run_id: str
    scope: str
    scope_id: str | None = None
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    status: AgentMemoryCandidateStatus = "pending"
    retention: AgentMemoryRetentionPolicy | None = None
    created_at: str
    resolved_at: str | None = None


class AgentMemoryCandidateApprovalResult(AithruBaseModel):
    candidate: AgentMemoryCandidate
    memory_entry: AgentMemoryEntry
```

Add store protocol methods:

```python
async def create_memory_candidate(
    self,
    candidate: AgentMemoryCandidate,
) -> AgentMemoryCandidate:
    raise NotImplementedError

async def get_memory_candidate(
    self,
    candidate_id: str,
) -> AgentMemoryCandidate | None:
    raise NotImplementedError

async def list_memory_candidates(
    self,
    *,
    org_id: str,
    status: str | None = None,
) -> list[AgentMemoryCandidate]:
    raise NotImplementedError

async def update_memory_candidate(
    self,
    candidate_id: str,
    **updates: object,
) -> AgentMemoryCandidate:
    raise NotImplementedError
```

- [ ] **Step 3: Add memory extraction processor**

Add a conservative processor that creates candidates only after completed runs and only for runs with `agent.memory.write` or `*` scope:

```python
from dataclasses import dataclass

from aithru_agent.domain import AgentRunStatus
from aithru_agent.domain.memory_candidate import AgentMemoryCandidate
from aithru_agent.runtime.processors import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


@dataclass
class MemoryExtractionProcessor(AgentRuntimeProcessor):
    name: str = "memory_extraction"

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.terminal_status != AgentRunStatus.COMPLETED:
            return AgentRuntimeProcessorDecision()
        if "agent.memory.write" not in context.run.scopes and "*" not in context.run.scopes:
            return AgentRuntimeProcessorDecision()
        if context.run.result is None or not context.run.result.content:
            return AgentRuntimeProcessorDecision()
        candidate = AgentMemoryCandidate(
            id=f"memcand_{context.run.id}",
            org_id=context.run.org_id,
            run_id=context.run.id,
            scope="thread" if context.run.thread_id else "user",
            scope_id=context.run.thread_id or context.run.actor_user_id,
            key=f"run_{context.run.id}_outcome",
            value=context.run.result.content[:800],
            confidence=0.6,
            status="pending",
            created_at=_utc_now(),
        )
        await context.store.create_memory_candidate(candidate)
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.candidate.created",
            source={"kind": "harness"},
            visibility="audit",
            payload=candidate.model_dump(mode="json"),
        )
        return AgentRuntimeProcessorDecision()
```

- [ ] **Step 4: Add candidate review routes**

Create `backend/src/aithru_agent/api/routes/memory_candidates.py` with:

- `GET /api/memory-candidates`
- `POST /api/memory-candidates/{candidate_id}/approve`
- `POST /api/memory-candidates/{candidate_id}/reject`

Approval writes a normal `AgentMemoryEntry` through `create_memory_entry`, updates candidate status, and emits no raw sensitive payload beyond the existing memory entry contract.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_memory_extraction_processor.py tests/integration/test_memory_candidates_api.py tests/integration/test_memory_events.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain/memory_candidate.py backend/src/aithru_agent/runtime/processors/memory_extraction.py backend/src/aithru_agent/api/routes/memory_candidates.py backend/src/aithru_agent/api/routes/__init__.py backend/src/aithru_agent/persistence backend/tests/unit/runtime/processors/test_memory_extraction_processor.py backend/tests/integration/test_memory_candidates_api.py
git commit -m "feat: add memory extraction candidates"
```

## Task 7: P2 Vision And Controlled View Image

**Files:**
- Create: `backend/src/aithru_agent/domain/media.py`
- Create: `backend/src/aithru_agent/capabilities/local_tools/media.py`
- Create: `backend/src/aithru_agent/api/routes/media.py`
- Modify: `backend/src/aithru_agent/domain/message.py`
- Modify: `backend/src/aithru_agent/api/dependencies.py`
- Modify: `backend/src/aithru_agent/api/routes/messages.py`
- Modify: `backend/src/aithru_agent/api/routes/__init__.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Test: `backend/tests/unit/domain/test_media.py`
- Test: `backend/tests/unit/capabilities/test_media_tools.py`
- Test: `backend/tests/integration/test_message_attachments.py`

- [ ] **Step 1: Write failing message attachment test**

```python
import pytest

from aithru_agent.domain import AgentMessageRole
from aithru_agent.domain.media import AgentMessageAttachment
from aithru_agent.persistence.memory import InMemoryAgentStore


@pytest.mark.asyncio
async def test_message_can_persist_workspace_image_attachment() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    attachment = AgentMessageAttachment(
        kind="workspace_file",
        workspace_id="ws_1",
        path="/uploads/chart.png",
        media_type="image/png",
    )

    message = await store.append_message(
        thread_id=thread.id,
        role=AgentMessageRole.USER,
        content="What does this chart show?",
        attachments=[attachment],
    )

    assert message.attachments == [attachment]
```

- [ ] **Step 2: Add media contracts**

Add to `backend/src/aithru_agent/domain/media.py`:

```python
from typing import Literal

from pydantic import Field, field_validator

from .base import AithruBaseModel


AgentMessageAttachmentKind = Literal["workspace_file", "artifact"]


class AgentMessageAttachment(AithruBaseModel):
    kind: AgentMessageAttachmentKind
    workspace_id: str | None = None
    artifact_id: str | None = None
    path: str | None = None
    media_type: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def _path_must_be_absolute(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = "/" + value.lstrip("/")
        return normalized


class AgentImageViewRequest(AithruBaseModel):
    workspace_id: str
    path: str
    prompt: str | None = None


class AgentImageViewResult(AithruBaseModel):
    workspace_id: str
    path: str
    media_type: str
    description: str
    provider: str
    bytes_read: int = Field(ge=0)
```

Modify `AgentMessage` to include:

```python
attachments: list[AgentMessageAttachment] = []
```

Modify `append_message()` protocol and both stores to accept `attachments: list[AgentMessageAttachment] | None = None`.

- [ ] **Step 3: Add controlled media tool**

Add `MediaLocalTool` with one descriptor:

```python
class MediaLocalTool:
    def __init__(self, store: AgentStore, provider: ImageViewProvider) -> None:
        self._store = store
        self._provider = provider

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="media.view_image",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Describe an image file from the current Agent Workspace.",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read", "agent.media.view"],
                approval_policy="never",
            )
        ]
```

Execution must read only the current run workspace, reject non-image media types, apply workspace path policy through the router context, and return `AgentImageViewResult`. The default provider returns a clear unavailable error until a configured vision-capable provider is injected.

- [ ] **Step 4: Add API and route registration**

Create `POST /api/workspaces/{workspace_id}/media/view-image` in `api/routes/media.py`. It uses `deps.require_workspace`, reads the workspace file, validates `image/*`, and calls the same provider interface as `media.view_image`.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_media.py tests/unit/capabilities/test_media_tools.py tests/integration/test_message_attachments.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain/media.py backend/src/aithru_agent/capabilities/local_tools/media.py backend/src/aithru_agent/api/routes/media.py backend/src/aithru_agent/domain/message.py backend/src/aithru_agent/api backend/src/aithru_agent/application/runtime.py backend/tests/unit/domain/test_media.py backend/tests/unit/capabilities/test_media_tools.py backend/tests/integration/test_message_attachments.py
git commit -m "feat: add controlled image attachment support"
```

## Task 8: P2 File Conversion Processor

**Files:**
- Create: `backend/src/aithru_agent/domain/file_conversion.py`
- Create: `backend/src/aithru_agent/runtime/processors/file_conversion.py`
- Modify: `backend/src/aithru_agent/api/routes/workspaces.py`
- Modify: `backend/src/aithru_agent/settings.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/unit/runtime/processors/test_file_conversion_processor.py`
- Test: `backend/tests/integration/test_workspace_upload_conversion.py`

- [ ] **Step 1: Add conversion dependencies**

Modify `backend/pyproject.toml` dependencies:

```toml
dependencies = [
  "fastapi>=0.116.0",
  "httpx>=0.28.0",
  "openpyxl>=3.1.0",
  "pydantic>=2.11.0",
  "pydantic-ai>=0.8.0",
  "pydantic-ai-harness>=0.3.0",
  "pypdf>=5.0.0",
  "python-docx>=1.1.0",
  "python-pptx>=1.0.0",
  "uvicorn>=0.35.0",
]
```

- [ ] **Step 2: Write failing upload conversion test**

```python
import base64
import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application import create_agent_runtime
from aithru_agent.persistence.memory import InMemoryAgentStore


@pytest.mark.asyncio
async def test_text_upload_creates_markdown_conversion_file() -> None:
    store = InMemoryAgentStore()
    runtime = create_agent_runtime(store=store)
    app = create_app(runtime)
    workspace = await store.create_workspace(org_id="org_1")
    payload = base64.b64encode(b"alpha,beta\n1,2\n").decode("ascii")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/workspaces/{workspace.id}/uploads",
            json={
                "path": "/uploads/data.csv",
                "content_base64": payload,
                "media_type": "text/csv",
            },
        )

    assert response.status_code == 201
    files = await store.list_workspace_files(workspace.id)
    paths = {file.path for file in files}
    assert "/workspace/converted/uploads/data.csv.md" in paths
```

- [ ] **Step 3: Add conversion contracts**

```python
from typing import Literal

from pydantic import Field

from .base import AithruBaseModel


AgentFileConversionStatus = Literal["converted", "unsupported", "failed"]


class AgentFileConversionResult(AithruBaseModel):
    workspace_id: str
    source_path: str
    source_media_type: str | None = None
    status: AgentFileConversionStatus
    output_path: str | None = None
    output_media_type: str | None = None
    error: dict | None = None
    created_at: str


class AgentFileConversionPolicy(AithruBaseModel):
    enabled: bool = True
    output_prefix: str = "/workspace/converted"
    max_input_bytes: int = Field(default=10_000_000, ge=1)
```

- [ ] **Step 4: Add upload conversion processor**

The processor should accept `workspace_id`, `source_path`, and file content from the upload route. It writes markdown derivatives under `/workspace/converted/<source-path>.md`, emits `workspace.file.converted`, and returns `AgentFileConversionResult`.

Supported first pass:

- `text/plain`, `text/csv`, `application/json`: decode UTF-8 and wrap in markdown fenced text.
- `application/pdf`: use `pypdf.PdfReader` text extraction.
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`: use `python-docx`.
- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`: use `openpyxl` and render sheet rows as markdown tables.
- `application/vnd.openxmlformats-officedocument.presentationml.presentation`: use `python-pptx` text frames.

- [ ] **Step 5: Call conversion from upload route**

After `write_workspace_file()` in `upload_workspace_file`, call the conversion processor only when settings enable conversion. Return the existing `AgentWorkspaceUploadResult` shape and add conversion metadata to the response model only in a backward-compatible optional field:

```python
conversion: AgentFileConversionResult | None = None
```

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/runtime/processors/test_file_conversion_processor.py tests/integration/test_workspace_upload_conversion.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/pyproject.toml backend/src/aithru_agent/domain/file_conversion.py backend/src/aithru_agent/runtime/processors/file_conversion.py backend/src/aithru_agent/api/routes/workspaces.py backend/src/aithru_agent/settings.py backend/tests/unit/runtime/processors/test_file_conversion_processor.py backend/tests/integration/test_workspace_upload_conversion.py
git commit -m "feat: convert uploaded files for model context"
```

## Task 9: P2 Skill Management API

**Files:**
- Modify: `backend/src/aithru_agent/domain/skill.py`
- Modify: `backend/src/aithru_agent/skills/resolver.py`
- Modify: `backend/src/aithru_agent/persistence/protocols.py`
- Modify: `backend/src/aithru_agent/persistence/memory/store.py`
- Modify: `backend/src/aithru_agent/persistence/sqlite/store.py`
- Modify: `backend/src/aithru_agent/api/routes/skills.py`
- Test: `backend/tests/unit/skills/test_skill_config.py`
- Test: `backend/tests/integration/test_skill_management_api.py`

- [ ] **Step 1: Write failing skill configuration API test**

```python
import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application import create_agent_runtime


@pytest.mark.asyncio
async def test_skill_can_be_disabled_through_config_api() -> None:
    runtime = create_agent_runtime()
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/skills/deep-research/config",
            json={"enabled": False},
        )
        listed = await client.get("/api/skills")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert all(skill["key"] != "deep-research" for skill in listed.json())
```

- [ ] **Step 2: Add skill configuration contracts**

Add:

```python
class AgentSkillConfig(AithruBaseModel):
    org_id: str
    skill_key: str
    enabled: bool | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    allowed_subagents: list[str] | None = None
    updated_at: str
```

Add a helper on `AgentSkill`:

```python
def with_config(self, config: AgentSkillConfig | None) -> "AgentSkill":
    if config is None:
        return self
    updates = {
        field: getattr(config, field)
        for field in ("enabled", "allowed_tools", "denied_tools", "allowed_subagents")
        if getattr(config, field) is not None
    }
    return self.model_copy(update=updates)
```

- [ ] **Step 3: Add store-backed config overlay**

Add store methods `get_skill_config`, `upsert_skill_config`, and `list_skill_configs`. Update the resolver path used by `api/routes/skills.py` so listing and resolving apply org-scoped config overlays after loading built-in/file skills.

- [ ] **Step 4: Add management routes**

Add to `api/routes/skills.py`:

- `GET /api/skills/{skill_key_or_ref}/versions`
- `GET /api/skills/{skill_key_or_ref}/config`
- `PATCH /api/skills/{skill_key_or_ref}/config`

Patch request:

```python
class UpdateSkillConfigRequest(BaseModel):
    enabled: bool | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    allowed_subagents: list[str] | None = None
```

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/skills/test_skill_config.py tests/integration/test_skill_management_api.py tests/skills/test_builtin_skills.py tests/skills/test_skill_package_loader.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain/skill.py backend/src/aithru_agent/skills backend/src/aithru_agent/persistence backend/src/aithru_agent/api/routes/skills.py backend/tests/unit/skills/test_skill_config.py backend/tests/integration/test_skill_management_api.py
git commit -m "feat: add skill management configuration"
```

## Task 10: P2 External Tool Configuration API

**Files:**
- Create: `backend/src/aithru_agent/domain/external_tool_config.py`
- Create: `backend/src/aithru_agent/api/routes/external_tool_configs.py`
- Modify: `backend/src/aithru_agent/settings.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Modify: `backend/src/aithru_agent/api/routes/__init__.py`
- Modify: `backend/src/aithru_agent/persistence/protocols.py`
- Modify: `backend/src/aithru_agent/persistence/memory/store.py`
- Modify: `backend/src/aithru_agent/persistence/sqlite/store.py`
- Test: `backend/tests/unit/domain/test_external_tool_config.py`
- Test: `backend/tests/integration/test_external_tool_config_api.py`

- [ ] **Step 1: Write failing config validation test**

```python
import pytest
from pydantic import ValidationError

from aithru_agent.domain.external_tool_config import AgentExternalToolConfig


def test_external_tool_config_rejects_secret_values() -> None:
    with pytest.raises(ValidationError):
        AgentExternalToolConfig(
            id="ext_1",
            org_id="org_1",
            kind="mcp_http_json",
            key="github",
            enabled=True,
            allowed_hosts=["api.github.com"],
            endpoint_url="https://api.github.com/mcp",
            secret_ref="plain-token-value",
            created_at="2026-06-22T00:00:00Z",
            updated_at="2026-06-22T00:00:00Z",
        )
```

- [ ] **Step 2: Add external config contracts**

```python
from typing import Literal

from pydantic import Field, field_validator

from .base import AithruBaseModel


AgentExternalToolConfigKind = Literal["mcp_http_json", "web_search_http_json"]


class AgentExternalToolConfig(AithruBaseModel):
    id: str
    org_id: str
    kind: AgentExternalToolConfigKind
    key: str = Field(min_length=1)
    enabled: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)
    endpoint_url: str | None = None
    secret_ref: str | None = None
    metadata: dict | None = None
    created_at: str
    updated_at: str

    @field_validator("secret_ref")
    @classmethod
    def _secret_ref_must_be_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped.startswith("secret://"):
            raise ValueError("external tool secret_ref must be a secret reference")
        return stripped
```

- [ ] **Step 3: Add product API**

Create routes:

- `GET /api/external-tools/configs`
- `POST /api/external-tools/configs`
- `PATCH /api/external-tools/configs/{config_id}`
- `DELETE /api/external-tools/configs/{config_id}`

Responses return secret references, never secret values. Create/update writes `external_tool.config.created` or `external_tool.config.updated` audit events only when called in run context; otherwise the route returns the config without creating a run event.

- [ ] **Step 4: Merge settings and store-backed configs at application creation**

In `application/runtime.py`, convert enabled `AgentExternalToolConfig` records into `MCPServerSpec` or controlled web settings. Validate allowed hosts before constructing providers. Keep env settings as server defaults and store configs as org/product overlays.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_external_tool_config.py tests/integration/test_external_tool_config_api.py tests/unit/capabilities/test_mcp_tools.py tests/unit/capabilities/test_web_tools.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain/external_tool_config.py backend/src/aithru_agent/api/routes/external_tool_configs.py backend/src/aithru_agent/settings.py backend/src/aithru_agent/application/runtime.py backend/src/aithru_agent/api/routes/__init__.py backend/src/aithru_agent/persistence backend/tests/unit/domain/test_external_tool_config.py backend/tests/integration/test_external_tool_config_api.py
git commit -m "feat: add external tool configuration API"
```

## Task 11: P2 Model Profile Registry And Per-Run Selection

**Files:**
- Create: `backend/src/aithru_agent/domain/model_profile.py`
- Create: `backend/src/aithru_agent/api/routes/model_profiles.py`
- Modify: `backend/src/aithru_agent/domain/run.py`
- Modify: `backend/src/aithru_agent/agent/runtime.py`
- Modify: `backend/src/aithru_agent/application/runtime.py`
- Modify: `backend/src/aithru_agent/api/routes/__init__.py`
- Modify: `backend/src/aithru_agent/persistence/protocols.py`
- Modify: `backend/src/aithru_agent/persistence/memory/store.py`
- Modify: `backend/src/aithru_agent/persistence/sqlite/store.py`
- Test: `backend/tests/unit/domain/test_model_profile.py`
- Test: `backend/tests/integration/test_model_profile_api.py`
- Test: `backend/tests/integration/test_pydantic_driver.py`

- [ ] **Step 1: Write failing model profile selection test**

```python
import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.domain.model_profile import AgentModelProfile
from aithru_agent.persistence.memory import InMemoryAgentStore


@pytest.mark.asyncio
async def test_runtime_uses_model_profile_id_before_raw_model_name() -> None:
    store = InMemoryAgentStore()
    await store.upsert_model_profile(
        AgentModelProfile(
            id="profile_test_fast",
            org_id="org_1",
            name="Test Fast",
            provider="test",
            model_name="test",
            enabled=True,
            capabilities=["text"],
            created_at="2026-06-22T00:00:00Z",
            updated_at="2026-06-22T00:00:00Z",
        )
    )
    runtime = AgentRuntime(
        model="fallback",
        model_factory=lambda model_name: TestModel(custom_output_text=f"model:{model_name}"),
    )

    assert runtime.model_for_profile("profile_test_fast", store=store) == "test"
```

- [ ] **Step 2: Add model profile contracts**

```python
from typing import Literal

from pydantic import Field

from .base import AithruBaseModel
from .usage import AgentRunBudgetPolicy


AgentModelCapability = Literal["text", "vision", "tool_use", "thinking"]


class AgentModelProfile(AithruBaseModel):
    id: str
    org_id: str
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    enabled: bool = True
    capabilities: list[AgentModelCapability] = Field(default_factory=lambda: ["text"])
    default_budget_policy: AgentRunBudgetPolicy | None = None
    created_at: str
    updated_at: str
```

- [ ] **Step 3: Add store methods and profile API**

Store methods:

- `upsert_model_profile(profile: AgentModelProfile) -> AgentModelProfile`
- `get_model_profile(profile_id: str) -> AgentModelProfile | None`
- `list_model_profiles(org_id: str) -> list[AgentModelProfile]`

Routes:

- `GET /api/model-profiles`
- `POST /api/model-profiles`
- `PATCH /api/model-profiles/{profile_id}`

- [ ] **Step 4: Resolve model profile during runtime**

Modify `_model_for_run()` in `backend/src/aithru_agent/agent/runtime.py` to prefer `run.harness_options.model_profile_id` when present. The worker dependency build path should resolve the profile using the store, reject disabled/missing profiles with `AgentError("MODEL_PROFILE_NOT_FOUND", "Model profile not found or disabled")`, and apply the profile default budget policy when the run did not provide an explicit budget policy.

- [ ] **Step 5: Enforce vision capability for `media.view_image`**

When a run calls `media.view_image`, require the active model profile to include `vision`. If the run uses a raw model name with no profile, the tool returns a denied result with `{"message": "Image viewing requires a vision-capable model profile"}`.

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
cd backend
uv run pytest tests/unit/domain/test_model_profile.py tests/integration/test_model_profile_api.py tests/integration/test_pydantic_driver.py tests/unit/capabilities/test_media_tools.py -q
```

Expected: PASS.

Commit:

```bash
git add backend/src/aithru_agent/domain/model_profile.py backend/src/aithru_agent/api/routes/model_profiles.py backend/src/aithru_agent/domain/run.py backend/src/aithru_agent/agent/runtime.py backend/src/aithru_agent/application/runtime.py backend/src/aithru_agent/api/routes/__init__.py backend/src/aithru_agent/persistence backend/tests/unit/domain/test_model_profile.py backend/tests/integration/test_model_profile_api.py backend/tests/integration/test_pydantic_driver.py
git commit -m "feat: add governed model profiles"
```

## Task 12: Documentation And Full Verification

**Files:**
- Modify: `docs/00-agent-harness-design.md`
- Modify: `docs/01-deerflow-benchmark.md`
- Modify: `README.md`
- Test: existing backend suite and examples

- [ ] **Step 1: Update design docs**

In `docs/00-agent-harness-design.md`, add a "Runtime Processors" section under the harness runtime discussion:

```markdown
### Runtime Processors

Runtime processors are harness lifecycle components for platform-state work
such as title generation, context summarization, clarification preflight,
usage aggregation, upload conversion, and memory candidate extraction.

Processors may update Agent Thread, Agent Run, Agent Workspace, Agent Memory,
and Agent stream/audit state through explicit store and capability APIs. They
must not define workflow nodes, graph branches, WorkflowSpec persistence,
provider scheduling, or model-visible bypasses around the capability router.
```

In `docs/01-deerflow-benchmark.md`, update the P0-P2 roadmap rows from gap text to implementation notes as each task lands.

- [ ] **Step 2: Update README only for public surface changes**

Add a short backend paragraph listing new APIs:

```markdown
The backend also exposes runtime processor projections for usage, context
summaries, clarification pauses, memory candidates, model profiles, external
tool configuration, media inspection, and upload conversion. These are harness
control-plane surfaces, not WorkflowSpec authoring or scheduling APIs.
```

- [ ] **Step 3: Run the required backend verification**

Run:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

Expected: both commands complete successfully.

- [ ] **Step 4: Check boundary language**

Run:

```bash
rg -n "Agent workflow|workflow graph|sub-workflow|save AgentPlan as workflow|WorkflowSpec" docs backend/src backend/tests
```

Expected: any `WorkflowSpec` matches are boundary explanations; no new Agent-owned workflow semantics were introduced.

- [ ] **Step 5: Final commit**

```bash
git add docs/00-agent-harness-design.md docs/01-deerflow-benchmark.md README.md
git commit -m "docs: update DeerFlow P0-P2 parity status"
```

## Self-Review

Spec coverage:

- P0 Runtime Processor layer is covered by Task 1.
- P0 Run-tree usage / budget aggregation is covered by Task 2.
- P0 Context semantic summarization is covered by Task 3.
- P1 Clarification preflight is covered by Task 4.
- P1 Auto title generation is covered by Task 5.
- P1 Async memory extraction is covered by Task 6.
- P2 Vision / view image is covered by Task 7.
- P2 File conversion is covered by Task 8.
- P2 Skill management UI/API is covered by Task 9.
- P2 MCP/external tool config is covered by Task 10.
- P2 Multi-model config is covered by Task 11.

Boundary check:

- Runtime processors remain harness lifecycle state processors.
- Todos, summaries, titles, conversions, memory candidates, and usage projections are not workflow definitions.
- External tools and media inspection remain capability-router or control-plane actions.
- Workbench integration remains explicit and narrow.
- P3 frontend, production AIO sandbox, IM channels, observability exporters, and full browser automation are outside this P0-P2 backend parity plan.

Execution order:

1. Finish P0 Tasks 1-3 first; do not start P1 until processor hooks, usage, and summaries pass.
2. Finish P1 Tasks 4-6 next; each is independently testable through processor hooks.
3. Finish P2 Tasks 7-11 in any order after Task 11's model profile capability checks are coordinated with Task 7's media tool.
4. Finish Task 12 after all code tasks pass.
