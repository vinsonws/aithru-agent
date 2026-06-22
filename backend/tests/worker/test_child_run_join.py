import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentApprovalPolicy, AgentRunSource, AgentRunStatus, AgentSkill
from aithru_agent.skills import InMemorySkillResolver
from pydantic_ai.models.test import TestModel


class ToolContext:
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = False


class JoiningRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal
        if deps.run.source == AgentRunSource.DELEGATED_TASK:
            return AgentRuntimeResult(content="Joined child output.")
        result = await PydanticAIToolBridge(deps=deps).call_tool(
            ToolContext("task_call_1"),
            "task",
            {
                "description": "Join a child run.",
                "prompt": "Produce child output.",
                "subagent_type": "child-researcher",
            },
        )
        return AgentRuntimeResult(content=f"Joined: {result['result']}")


def child_skill() -> AgentSkill:
    return AgentSkill(
        id="skill_child",
        org_id="org_1",
        key="child-researcher",
        name="Child Researcher",
        instructions="Handle delegated research tasks.",
        allowed_tools=[],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )


def child_writer_skill() -> AgentSkill:
    return AgentSkill(
        id="skill_child_writer",
        org_id="org_1",
        key="child-writer",
        name="Child Writer",
        instructions="Write a file after approval.",
        allowed_tools=["workspace.write_file"],
        allowed_subagents=[],
        approval_policy=AgentApprovalPolicy(require_approval_for_risk=["write"]),
        version="0.1.0",
        status="published",
    )


class ChildApprovalRuntime(AgentRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._child_runtime = AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="child done")
        )

    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        if deps.run.source == AgentRunSource.DELEGATED_TASK:
            return await self._child_runtime.run(goal, deps)
        result = await PydanticAIToolBridge(deps=deps).call_tool(
            ToolContext("task_call_1"),
            "task",
            {
                "description": "Ask a child writer for an approved write.",
                "prompt": "Write a file.",
                "subagent_type": "child-writer",
            },
        )
        return AgentRuntimeResult(content=f"Joined: {result['result']}")


@pytest.mark.asyncio
async def test_inline_child_run_join_marks_parent_waiting_then_resumes() -> None:
    runtime = create_agent_runtime(
        agent_runtime=JoiningRuntime(),
        skill_resolver=InMemorySkillResolver([child_skill()]),
    )

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Join child.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(parent.id)
    event_types = [event.type for event in events]
    paused = next(event for event in events if event.type == "run.paused")
    resumed = next(event for event in events if event.type == "run.resumed")

    assert parent.result is not None
    assert parent.result.content == "Joined: Joined child output."
    assert paused.payload["status"] == "waiting_subagent"
    assert resumed.payload["status"] == "running"
    assert event_types.index("run.paused") < event_types.index("subagent.completed")
    assert event_types.index("subagent.completed") < event_types.index("run.resumed")


@pytest.mark.asyncio
async def test_child_run_approval_pause_keeps_parent_waiting_for_subagent() -> None:
    runtime = create_agent_runtime(
        agent_runtime=ChildApprovalRuntime(),
        skill_resolver=InMemorySkillResolver([child_writer_skill()]),
    )

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Delegate a write.",
        scopes=["*"],
    )
    subagent_run = (await runtime.store.list_subagent_runs(parent_run_id=parent.id))[0]
    child = await runtime.store.get_run(subagent_run.child_run_id)
    parent_events = await runtime.event_store.list_by_run(parent.id)
    parent_event_types = [event.type for event in parent_events]

    assert parent.status == AgentRunStatus.WAITING_SUBAGENT
    assert child.status == AgentRunStatus.WAITING_APPROVAL
    assert subagent_run.status == "running"
    assert parent_event_types[-1] == "run.paused"
    assert "run.failed" not in parent_event_types
    assert "tool.failed" not in parent_event_types
