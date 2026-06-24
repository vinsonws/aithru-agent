import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus, AgentSkill, AgentWorkspacePolicy
from aithru_agent.domain.errors import AgentError
from tests.utils.step_runtime import Step, StepAgentRuntime
from aithru_agent.skills import InMemorySkillResolver


@pytest.mark.asyncio
async def test_workspace_tool_rejects_paths_outside_skill_allowed_paths() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="restricted-workspace",
        name="Restricted Workspace",
        instructions="Only write under /allowed.",
        allowed_tools=["workspace.write_file"],
        allowed_subagents=[],
        workspace_policy=AgentWorkspacePolicy(read=True, write=True, allowed_paths=["/allowed"]),
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "workspace.write_file",
                    {"path": "/secret.txt", "content": "nope"},
                ),
                Step.finish(),
            ]
        ),
        skill_resolver=InMemorySkillResolver([skill]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write outside allowed paths.",
        scopes=["*"],
        skill_id="restricted-workspace",
    )
    events = await runtime.event_store.list_by_run(run.id)
    tool_failed = next(event for event in events if event.type == "tool.failed")

    assert run.status == AgentRunStatus.FAILED
    assert "outside allowed workspace paths" in tool_failed.payload["error"]["message"]
    with pytest.raises(AgentError):
        await runtime.store.read_workspace_file(run.workspace_id, "/secret.txt")


@pytest.mark.asyncio
async def test_workspace_tool_allows_paths_inside_skill_allowed_paths() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="restricted-workspace",
        name="Restricted Workspace",
        instructions="Only write under /allowed.",
        allowed_tools=["workspace.write_file"],
        allowed_subagents=[],
        workspace_policy=AgentWorkspacePolicy(read=True, write=True, allowed_paths=["/allowed"]),
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "workspace.write_file",
                    {"path": "/allowed/report.md", "content": "ok"},
                ),
                Step.finish(),
            ]
        ),
        skill_resolver=InMemorySkillResolver([skill]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write inside allowed paths.",
        scopes=["*"],
        skill_id="restricted-workspace",
    )
    file = await runtime.store.read_workspace_file(run.workspace_id, "/allowed/report.md")

    assert run.status == AgentRunStatus.COMPLETED
    assert file.content == "ok"
