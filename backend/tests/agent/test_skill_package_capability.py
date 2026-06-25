"""Tests for AithruSkillCapability and AithruSkillActivationObserver."""

from unittest.mock import MagicMock

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aithru_agent.agent.capabilities.skill_package import (
    AithruSkillActivationObserver,
    AithruSkillCapability,
    skill_capability_id,
)
from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentSkillConfiguration, AgentSkillRegistrySource, AgentRunStatus
from aithru_agent.skills.packages import SkillPackage, parse_skill_package
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


def _package(key: str = "file-report") -> SkillPackage:
    name = key.replace("-", " ").title()
    return parse_skill_package(
        key=key,
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md=f"""---
name: {name}
description: Use for reports.
---

{key} body.
""",
        policy=AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]),
    )


def test_skill_package_capability_is_deferred_unless_explicit() -> None:
    package = _package(key="file-report")
    deferred = AithruSkillCapability(package=package)
    explicit = AithruSkillCapability(package=package, explicit=True)

    assert deferred.id == "skill:file-report"
    assert deferred.defer_loading is True
    assert deferred.description == "File Report: Use for reports."
    assert explicit.defer_loading is False


def test_skill_package_capability_get_instructions() -> None:
    capability = AithruSkillCapability(package=_package(key="report-helper"))

    instructions = capability.get_instructions()

    assert "## Aithru Skill: Report Helper" in instructions
    assert "report-helper body" in instructions


@pytest.mark.asyncio
async def test_activation_observer_emits_skill_activated_for_explicit() -> None:
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    deps = _deps(writer, explicit_skill_key="file-report")
    ctx = _ctx(deps)

    observer = AithruSkillActivationObserver()
    result = await observer.before_model_request(ctx, _fake_request_context())

    assert result is not None
    events = await event_store.list_by_run("run_1")
    activated = [e for e in events if e.type == "skill.activated"]
    assert len(activated) == 1
    assert activated[0].payload["skill_key"] == "file-report"
    assert activated[0].payload["trigger"] == "explicit"


@pytest.mark.asyncio
async def test_activation_observer_emits_skill_activated_for_loaded() -> None:
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    deps = _deps(writer)
    ctx = _ctx(deps, loaded_capability_ids={"skill:file-report"})

    observer = AithruSkillActivationObserver()
    result = await observer.before_model_request(ctx, _fake_request_context())

    assert result is not None
    events = await event_store.list_by_run("run_1")
    activated = [e for e in events if e.type == "skill.activated"]
    assert len(activated) == 1
    assert activated[0].payload["skill_key"] == "file-report"
    assert activated[0].payload["trigger"] == "pydantic_load_capability"


@pytest.mark.asyncio
async def test_activation_observer_does_not_duplicate_events() -> None:
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    deps = _deps(writer, explicit_skill_key="file-report")
    ctx = _ctx(deps)

    observer = AithruSkillActivationObserver()
    await observer.before_model_request(ctx, _fake_request_context())
    await observer.before_model_request(ctx, _fake_request_context())

    events = await event_store.list_by_run("run_1")
    activated = [e for e in events if e.type == "skill.activated"]
    assert len(activated) == 1


@pytest.mark.asyncio
async def test_activation_observer_payload_excludes_full_skill_md() -> None:
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    deps = _deps(writer, explicit_skill_key="file-report")
    ctx = _ctx(deps)

    observer = AithruSkillActivationObserver()
    await observer.before_model_request(ctx, _fake_request_context())

    events = await event_store.list_by_run("run_1")
    activated = [e for e in events if e.type == "skill.activated"]
    assert len(activated) == 1
    payload = activated[0].payload
    assert "file-report body" not in str(payload)


def _fake_request_context() -> MagicMock:
    return MagicMock()


def _deps(
    writer: AgentEventWriter,
    explicit_skill_key: str | None = None,
) -> PydanticAgentDeps:
    from datetime import UTC, datetime

    store = type("FakeStore", (), {"get_run": lambda self, rid: None})()
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    run = type(
        "FakeRun",
        (),
        {
            "id": "run_1",
            "org_id": "org_1",
            "actor_user_id": "user_1",
            "source": "api",
            "task_msg": "test",
            "workspace_id": "ws_1",
            "thread_id": None,
            "skill_id": explicit_skill_key,
            "scopes": ["*"],
            "status": AgentRunStatus.RUNNING,
            "started_at": now,
        },
    )
    return PydanticAgentDeps(
        run=run,  # type: ignore[arg-type]
        run_context=AgentRunContext(
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="ws_1",
        ),
        event_writer=writer,
        capability_router=type("FakeRouter", (), {})(),  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        visible_skill_packages={"file-report": _package(key="file-report")},
        explicit_skill_key=explicit_skill_key,
        emitted_skill_activation_keys=set(),
    )


def _ctx(
    deps: PydanticAgentDeps,
    loaded_capability_ids: set[str] | None = None,
) -> RunContext[PydanticAgentDeps]:
    return RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids=loaded_capability_ids or set(),
    )
