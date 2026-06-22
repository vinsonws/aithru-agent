import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunSource, AgentRunStatus, AgentSkill, AgentSubagentRunStatus
from aithru_agent.skills import InMemorySkillRegistry, InMemorySkillResolver


class ToolContext:
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = False


class TaskCallingRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal
        if deps.run.source == AgentRunSource.DELEGATED_TASK:
            return AgentRuntimeResult(content="Child result.")

        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": "msg_1", "role": "assistant"},
        )
        task_result = await PydanticAIToolBridge(deps=deps).call_tool(
            ToolContext("task_call_1"),
            "task",
            {
                "description": "Ask a child researcher for a short answer.",
                "prompt": "Return the child result.",
                "subagent_type": "child-researcher",
            },
        )
        content = f"Parent saw: {task_result['result']}"
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.delta",
            source={"kind": "model"},
            payload={"message_id": "msg_1", "delta": content},
        )
        return AgentRuntimeResult(content=content)


def child_skill(
    *,
    id: str = "skill_child",
    org_id: str = "org_1",
    name: str = "Child Researcher",
) -> AgentSkill:
    return AgentSkill(
        id=id,
        org_id=org_id,
        key="child-researcher",
        name=name,
        instructions="Handle delegated research tasks.",
        allowed_tools=[],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )


@pytest.mark.asyncio
async def test_task_tool_creates_visible_child_run_and_returns_joined_result() -> None:
    runtime = create_agent_runtime(
        agent_runtime=TaskCallingRuntime(),
        skill_resolver=InMemorySkillResolver([child_skill()]),
    )

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Delegate with task.",
        scopes=["*"],
    )
    subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)
    child = await runtime.store.get_run(subagent_runs[0].child_run_id)
    parent_events = await runtime.event_store.list_by_run(parent.id)
    event_types = [event.type for event in parent_events]

    assert parent.status == AgentRunStatus.COMPLETED
    assert parent.result is not None
    assert parent.result.content == "Parent saw: Child result."
    assert len(subagent_runs) == 1
    assert subagent_runs[0].status == AgentSubagentRunStatus.COMPLETED
    assert subagent_runs[0].result == "Child result."
    assert child is not None
    assert child.status == AgentRunStatus.COMPLETED
    assert child.source == AgentRunSource.DELEGATED_TASK
    assert child.skill_id == "child-researcher"
    assert event_types.index("subagent.started") < event_types.index("subagent.completed")
    assert event_types.index("subagent.completed") < event_types.index("tool.completed")


@pytest.mark.asyncio
async def test_task_tool_resolves_duplicate_child_skill_key_within_parent_org() -> None:
    runtime = create_agent_runtime(
        agent_runtime=TaskCallingRuntime(),
        skill_resolver=InMemorySkillRegistry(
            seed_skills=[
                child_skill(id="skill_child_org_1", org_id="org_1", name="Org 1 Child"),
                child_skill(id="skill_child_org_2", org_id="org_2", name="Org 2 Child"),
            ],
        ),
    )

    parent = await runtime.runner.start_run(
        org_id="org_2",
        actor_user_id="user_2",
        goal="Delegate with org-scoped task.",
        scopes=["*"],
    )
    subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)

    assert parent.status == AgentRunStatus.COMPLETED
    assert parent.result is not None
    assert parent.result.content == "Parent saw: Child result."
    assert len(subagent_runs) == 1
    child = await runtime.store.get_run(subagent_runs[0].child_run_id)
    assert subagent_runs[0].name == "Org 2 Child"
    assert child is not None
    assert child.org_id == "org_2"
    assert child.skill_id == "child-researcher"
