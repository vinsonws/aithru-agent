import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentApprovalPolicy, AgentRunStatus, AgentSkill
from aithru_agent.harness.engine import HarnessRunDeps, HarnessStep
from aithru_agent.harness.drivers.pydantic_ai import PydanticAIHarnessDriver
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.skills.resolver import InMemorySkillResolver
from pydantic_ai.models.test import TestModel


class RecordingDriver:
    def __init__(self) -> None:
        self.seen_skill_instructions: str | None = None

    async def run(self, goal: str | None = None, deps: HarnessRunDeps | None = None) -> list[HarnessStep]:
        del goal
        self.seen_skill_instructions = deps.skill.instructions if deps and deps.skill else None
        return [HarnessStep(type="finish")]


def file_report_skill(allowed_tools: list[str]) -> AgentSkill:
    return AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Only use the allowed file report tools.",
        allowed_tools=allowed_tools,
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )


def write_approval_skill() -> AgentSkill:
    return AgentSkill(
        id="skill_approval",
        org_id="org_1",
        key="approval-file-report",
        name="Approval File Report",
        instructions="Write only after approval.",
        allowed_tools=["workspace.write_file"],
        allowed_subagents=[],
        approval_policy=AgentApprovalPolicy(require_approval_for_risk=["write"]),
        version="0.1.0",
        status="published",
    )


@pytest.mark.asyncio
async def test_worker_denies_scripted_tool_not_allowed_by_skill() -> None:
    runtime = create_agent_runtime(
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool("workspace.write_file", {"path": "/x.md", "content": "x"}),
                ScriptedStep.finish(),
            ]
        ),
        skill_resolver=InMemorySkillResolver([file_report_skill(["workspace.read_file"])]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Try write",
        scopes=["*"],
        skill_id="file-report",
    )
    events = await runtime.event_store.list_by_run(run.id)

    assert "tool.denied" in [event.type for event in events]
    assert await runtime.store.list_workspace_files(run.workspace_id) == []


@pytest.mark.asyncio
async def test_worker_uses_skill_approval_policy_for_risky_tools() -> None:
    runtime = create_agent_runtime(
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool("workspace.write_file", {"path": "/x.md", "content": "x"}),
                ScriptedStep.finish(),
            ]
        ),
        skill_resolver=InMemorySkillResolver([write_approval_skill()]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write with approval",
        scopes=["*"],
        skill_id="approval-file-report",
    )
    events = await runtime.event_store.list_by_run(run.id)
    approvals = await runtime.store.list_approvals()

    assert run.status == AgentRunStatus.WAITING_APPROVAL
    assert [event.type for event in events][-2:] == ["approval.requested", "run.paused"]
    assert len(approvals) == 1
    assert await runtime.store.list_workspace_files(run.workspace_id) == []


@pytest.mark.asyncio
async def test_pydantic_driver_exposes_only_skill_allowed_tools() -> None:
    runtime = create_agent_runtime(
        driver=PydanticAIHarnessDriver(
            model=TestModel(call_tools=["workspace.list_files"], custom_output_text="done")
        ),
        skill_resolver=InMemorySkillResolver([file_report_skill(["workspace.list_files"])]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Read file",
        scopes=["*"],
        skill_id="file-report",
    )
    events = await runtime.event_store.list_by_run(run.id)

    assert "tool.proposed" in [event.type for event in events]
    assert all(
        event.payload.get("tool_name") != "workspace.write_file"
        for event in events
        if isinstance(event.payload, dict)
    )


@pytest.mark.asyncio
async def test_worker_passes_resolved_skill_to_harness_driver() -> None:
    driver = RecordingDriver()
    runtime = create_agent_runtime(
        driver=driver,
        skill_resolver=InMemorySkillResolver([file_report_skill(["workspace.list_files"])]),
    )

    await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Use skill",
        scopes=["*"],
        skill_id="file-report",
    )

    assert driver.seen_skill_instructions == "Only use the allowed file report tools."


@pytest.mark.asyncio
async def test_worker_fails_queued_run_with_unresolvable_skill_before_tools_execute() -> None:
    runtime = create_agent_runtime(
        driver=ScriptedHarnessDriver(
            [
                ScriptedStep.tool("workspace.write_file", {"path": "/x.md", "content": "x"}),
                ScriptedStep.finish(),
            ]
        )
    )
    workspace = await runtime.store.create_workspace(org_id="org_1")
    queued = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Use missing skill",
        workspace_id=workspace.id,
        scopes=["*"],
        skill_id="missing-skill",
    )

    run = await runtime.worker.work_once()
    events = await runtime.event_store.list_by_run(queued.id)
    files = await runtime.store.list_workspace_files(workspace.id)

    assert run is not None
    assert run.status == AgentRunStatus.FAILED
    assert run.error["message"] == "Skill not found: missing-skill"
    assert "tool.proposed" not in [event.type for event in events]
    assert files == []
