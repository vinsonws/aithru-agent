"""Tests for skill policy composition and effective run context."""

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.skill_policy import active_skill_keys, compose_skill_run_context, effective_run_context
from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentSkillConfiguration
from aithru_agent.skills import BuiltinPackageResolver
from aithru_agent.skills.packages import SkillPackage, parse_skill_package
from aithru_agent.domain import AgentSkillRegistrySource


def _package(
    key: str,
    allowed_tools: list[str] | None = None,
    denied_tools: list[str] | None = None,
) -> SkillPackage:
    return parse_skill_package(
        key=key,
        org_id="org_1",
        owner_user_id=None,
        source=AgentSkillRegistrySource.USER,
        skill_md=f"""---
name: {key.capitalize()}
description: {key} description.
---

{key} body.
""",
        policy=AgentSkillConfiguration(
            instructions="",
            allowed_tools=allowed_tools or [],
            denied_tools=denied_tools or [],
            allowed_subagents=[],
        ),
    )


def test_active_skill_keys_from_explicit_only() -> None:
    deps = _deps(explicit_skill_key="file-report")
    ctx = RunContext(deps=deps, model=TestModel(), usage=RunUsage(), loaded_capability_ids=set())

    keys = active_skill_keys(ctx)

    assert keys == ["file-report"]


def test_active_skill_keys_from_loaded_capabilities() -> None:
    deps = _deps()
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper", "skill:file-report"},
    )

    keys = active_skill_keys(ctx)

    assert "report-helper" in keys
    assert "file-report" in keys


def test_active_skill_keys_explicit_plus_loaded() -> None:
    deps = _deps(explicit_skill_key="deep-research")
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper"},
    )

    keys = active_skill_keys(ctx)

    assert "deep-research" in keys
    assert "report-helper" in keys


def test_compose_skill_run_context_no_packages() -> None:
    base = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        allowed_tools=["workspace.read_file", "workspace.write_file"],
    )
    result = compose_skill_run_context(base, [])

    assert result.allowed_tools == base.allowed_tools


def test_compose_skill_run_context_intersects_allowed_tools() -> None:
    base = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        allowed_tools=None,
    )
    packages = [
        _package("skill-a", allowed_tools=["workspace.read_file", "artifact.create"]),
        _package("skill-b", allowed_tools=["workspace.read_file"]),
    ]
    result = compose_skill_run_context(base, packages)

    assert result.allowed_tools == ["workspace.read_file"]


def test_compose_skill_run_context_denied_tools_removed() -> None:
    base = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        allowed_tools=None,
    )
    packages = [
        _package(
            "skill-a",
            allowed_tools=["workspace.read_file", "workspace.write_file"],
            denied_tools=["workspace.write_file"],
        ),
    ]
    result = compose_skill_run_context(base, packages)

    assert result.allowed_tools == ["workspace.read_file"]


def test_compose_skill_run_context_carries_denied_tools_without_allowlist() -> None:
    base = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        allowed_tools=None,
    )
    packages = [
        _package(
            "skill-a",
            denied_tools=["workspace.write_file"],
        ),
    ]
    result = compose_skill_run_context(base, packages)

    assert result.allowed_tools is None
    assert "workspace.write_file" in result.denied_tools


def test_compose_skill_run_context_deny_wins_over_allow() -> None:
    base = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        allowed_tools=None,
    )
    packages = [
        _package(
            "skill-a",
            allowed_tools=["workspace.read_file", "workspace.write_file"],
        ),
        _package(
            "skill-b",
            allowed_tools=["workspace.read_file"],
            denied_tools=["workspace.read_file"],
        ),
    ]
    result = compose_skill_run_context(base, packages)

    assert result.allowed_tools == []


def test_builtin_surprise_frontend_policy_allows_html_entrypoint() -> None:
    resolver = BuiltinPackageResolver()
    packages = [
        package
        for key in ("surprise-me", "frontend-design")
        if (package := resolver.get_package(key)) is not None
    ]
    assert {package.key for package in packages} == {"surprise-me", "frontend-design"}
    base = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
    )

    result = compose_skill_run_context(base, packages)

    assert result.workspace_allowed_paths is not None
    assert "/index.html" in result.workspace_allowed_paths


from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentToolApprovalPolicy, AgentToolDescriptor, AgentToolKind, AgentToolRiskLevel


def _desc(name: str) -> AgentToolDescriptor:
    return AgentToolDescriptor(
        name=name,
        kind=AgentToolKind.LOCAL_TOOL,
        description=f"Tool {name}.",
        input_schema={},
        output_schema={},
        risk_level=AgentToolRiskLevel.SAFE,
        required_scopes=[],
        approval_policy=AgentToolApprovalPolicy.NEVER,
    )


async def _fake_list_tools(self, ctx: object) -> list[AgentToolDescriptor]:
    allowed = None
    denied: set[str] = set()
    if isinstance(ctx, AgentRunContext) and ctx.allowed_tools is not None:
        allowed = set(ctx.allowed_tools)
    if isinstance(ctx, AgentRunContext):
        denied = set(ctx.denied_tools)
    all_tools = [
        _desc("workspace.list_files"),
        _desc("workspace.write_file"),
        _desc("artifact.create"),
        _desc("sandbox.run_python"),
    ]
    if allowed is not None:
        all_tools = [t for t in all_tools if t.name in allowed]
    return [t for t in all_tools if t.name not in denied]


async def _fake_requires_approval(self, name: str, ctx: object) -> bool:
    return False


def _deps(
    explicit_skill_key: str | None = None,
    visible_packages: dict[str, SkillPackage] | None = None,
) -> PydanticAgentDeps:
    from datetime import UTC, datetime

    from aithru_agent.domain import AgentRun, AgentRunStatus
    from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    store = type("FakeStore", (), {"get_run": lambda self, rid: None})()
    run = AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="test",
        workspace_id="ws_1",
        scopes=["*"],
        status=AgentRunStatus.QUEUED,
        started_at=now,
    )
    return PydanticAgentDeps(
        run=run,
        run_context=AgentRunContext(
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="ws_1",
        ),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=type("FakeRouter", (), {"list_tools": _fake_list_tools, "requires_approval_for_tool": _fake_requires_approval})(),
        store=store,  # type: ignore[arg-type]
        visible_skill_packages=visible_packages or {},
        explicit_skill_key=explicit_skill_key,
    )


@pytest.mark.asyncio
async def test_loaded_skill_policy_filters_aithru_toolset() -> None:
    from aithru_agent.agent.capabilities.toolset import AithruToolset

    deps = _deps(
        visible_packages={"report-helper": _package("report-helper", allowed_tools=["workspace.list_files"])},
    )
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper"},
    )

    tools = await AithruToolset().get_tools(ctx)

    assert list(tools) == ["workspace.list_files"]


@pytest.mark.asyncio
async def test_loaded_deny_only_skill_policy_filters_aithru_toolset() -> None:
    from aithru_agent.agent.capabilities.toolset import AithruToolset

    deps = _deps(
        visible_packages={"report-helper": _package("report-helper", denied_tools=["workspace.write_file"])},
    )
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper"},
    )

    tools = await AithruToolset().get_tools(ctx)

    assert "workspace.write_file" not in tools
    assert "workspace.list_files" in tools
    assert "artifact.create" in tools


@pytest.mark.asyncio
async def test_loaded_skill_without_sandbox_policy_hides_sandbox_tools() -> None:
    from aithru_agent.agent.capabilities.toolset import AithruToolset

    deps = _deps(
        visible_packages={"report-helper": _package("report-helper")},
    )
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper"},
    )

    tools = await AithruToolset().get_tools(ctx)

    assert "sandbox.run_python" not in tools
