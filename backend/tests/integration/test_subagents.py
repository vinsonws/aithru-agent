import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus, AgentSkill, AgentSubagentRunStatus
from aithru_agent.harness import HarnessRunDeps, HarnessStep
from aithru_agent.harness.drivers.scripted.driver import ScriptedStep
from aithru_agent.skills import InMemorySkillResolver
from aithru_agent.trace import project_trace_spans


class SequencedDriver:
    def __init__(self, runs: list[list[ScriptedStep]]) -> None:
        self._runs = runs
        self._index = 0

    async def run(self, goal: str | None = None, deps: HarnessRunDeps | None = None) -> list[HarnessStep]:
        del goal, deps
        index = min(self._index, len(self._runs) - 1)
        self._index += 1
        return [step.step for step in self._runs[index]]


def subagent_skill() -> AgentSkill:
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
async def test_subagent_delegate_creates_child_run_and_parent_events() -> None:
    driver = SequencedDriver(
        [
            [
                ScriptedStep.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace.",
                    },
                ),
                ScriptedStep.finish(),
            ],
            [ScriptedStep.message("Subtask done."), ScriptedStep.finish()],
        ]
    )
    runtime = create_agent_runtime(driver=driver)

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Delegate research",
        scopes=["*"],
    )
    subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)
    child = await runtime.store.get_run(subagent_runs[0].child_run_id)
    parent_events = await runtime.event_store.list_by_run(parent.id)
    parent_event_types = [event.type for event in parent_events]

    assert parent.status == AgentRunStatus.COMPLETED
    assert len(subagent_runs) == 1
    assert subagent_runs[0].status == AgentSubagentRunStatus.RUNNING
    assert child is not None
    assert child.status == AgentRunStatus.QUEUED
    assert child.source == "delegated_task"
    assert parent_event_types[-1] == "run.completed"
    assert parent_event_types.index("subagent.started") < parent_event_types.index("tool.completed")

    completed_child = await runtime.worker.work_once()
    completed_subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)
    updated_parent_events = await runtime.event_store.list_by_run(parent.id)

    assert completed_child is not None
    assert completed_child.id == child.id
    assert completed_subagent_runs[0].status == AgentSubagentRunStatus.COMPLETED
    assert "subagent.completed" in [event.type for event in updated_parent_events]


@pytest.mark.asyncio
async def test_cancelled_child_run_updates_parent_subagent_state() -> None:
    driver = SequencedDriver(
        [
            [
                ScriptedStep.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace.",
                    },
                ),
                ScriptedStep.finish(),
            ],
            [ScriptedStep.message("This child should not run."), ScriptedStep.finish()],
        ]
    )
    runtime = create_agent_runtime(driver=driver)

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Delegate research",
        scopes=["*"],
    )
    subagent_run = (await runtime.store.list_subagent_runs(parent_run_id=parent.id))[0]

    child_cancelled = await runtime.runner.cancel_run(subagent_run.child_run_id)
    updated_subagent_run = (await runtime.store.list_subagent_runs(parent_run_id=parent.id))[0]
    parent_events = await runtime.event_store.list_by_run(parent.id)
    parent_event_types = [event.type for event in parent_events]
    parent_trace = project_trace_spans(parent_events)
    subagent_span = next(span for span in parent_trace if span.kind == "subagent")

    assert child_cancelled.status == AgentRunStatus.CANCELLED
    assert updated_subagent_run.status == AgentSubagentRunStatus.CANCELLED
    assert "subagent.failed" in parent_event_types
    assert parent_events[-1].payload["status"] == "cancelled"
    assert subagent_span.status == "cancelled"


@pytest.mark.asyncio
async def test_subagent_api_creates_specs_and_lists_run_delegations() -> None:
    driver = SequencedDriver(
        [
            [
                ScriptedStep.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace.",
                        "spec_key": "researcher",
                    },
                ),
                ScriptedStep.finish(),
            ]
        ]
    )
    runtime = create_agent_runtime(driver=driver)
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (
            await client.post(
                "/api/agent/subagents",
                json={
                    "org_id": "org_1",
                    "key": "researcher",
                    "name": "Researcher",
                    "instructions": "Use workspace evidence.",
                    "allowed_tools": ["workspace.read_file"],
                },
            )
        )
        listed = await client.get("/api/agent/subagents?org_id=org_1")
        parent = (
            await client.post(
                "/api/agent/runs",
                json={
                    "goal": "Delegate research",
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "scopes": ["*"],
                    "wait_for_completion": True,
                },
            )
        ).json()
        delegations = await client.get(f"/api/agent/runs/{parent['id']}/subagents")

    assert created.status_code == 201
    assert created.json()["key"] == "researcher"
    assert listed.status_code == 200
    assert listed.json()[0]["allowed_tools"] == ["workspace.read_file"]
    assert delegations.status_code == 200
    assert delegations.json()[0]["parent_run_id"] == parent["id"]
    assert delegations.json()[0]["spec_key"] == "researcher"


@pytest.mark.asyncio
async def test_subagent_delegate_rejects_unknown_child_skill() -> None:
    driver = SequencedDriver(
        [
            [
                ScriptedStep.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace.",
                        "skill_id": "missing-skill",
                    },
                ),
                ScriptedStep.finish(),
            ]
        ]
    )
    runtime = create_agent_runtime(driver=driver)

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Delegate research",
        scopes=["*"],
    )
    subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)
    events = await runtime.event_store.list_by_run(parent.id)
    tool_failed = next(event for event in events if event.type == "tool.failed")

    assert parent.status == AgentRunStatus.FAILED
    assert subagent_runs == []
    assert "Skill not found" in tool_failed.payload["error"]["message"]


@pytest.mark.asyncio
async def test_subagent_delegate_cannot_expand_child_scopes() -> None:
    driver = SequencedDriver(
        [
            [
                ScriptedStep.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace.",
                        "skill_id": "child-researcher",
                        "scopes": ["*"],
                    },
                ),
                ScriptedStep.finish(),
            ]
        ]
    )
    runtime = create_agent_runtime(
        driver=driver,
        skill_resolver=InMemorySkillResolver([subagent_skill()]),
    )

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Delegate research",
        scopes=["agent.subagent.write"],
    )
    subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)
    events = await runtime.event_store.list_by_run(parent.id)
    tool_failed = next(event for event in events if event.type == "tool.failed")

    assert parent.status == AgentRunStatus.FAILED
    assert subagent_runs == []
    assert "Child scopes must be a subset of parent scopes" in tool_failed.payload["error"]["message"]
