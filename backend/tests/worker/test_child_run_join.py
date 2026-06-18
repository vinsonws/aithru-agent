import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunSource, AgentSkill
from aithru_agent.skills import InMemorySkillResolver


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
