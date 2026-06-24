import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunSource, AgentRunStatus, AgentSkill, AgentSubagentRunStatus
from aithru_agent.skills import InMemorySkillResolver
from aithru_agent.stream.events import AgentStreamEvent, AgentStreamSource
from aithru_agent.trace import project_trace_spans
from tests.utils.step_runtime import Step, StepAgentRuntime


class SequencedRuntime(AgentRuntime):
    def __init__(self, runs: list[list[Step]]) -> None:
        super().__init__()
        self._runs = runs
        self._index = 0

    async def run(self, task_msg, deps):  # type: ignore[no-untyped-def]
        index = min(self._index, len(self._runs) - 1)
        self._index += 1
        return await StepAgentRuntime(self._runs[index]).run(task_msg, deps)


class ToolContext:
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = False


class DelegatingArtifactRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg
        if deps.run.source == AgentRunSource.DELEGATED_TASK:
            await deps.store.create_artifact(
                org_id=deps.run.org_id,
                workspace_id=deps.run.workspace_id,
                run_id=deps.run.id,
                type="report",
                name="Child Report",
                media_type="text/markdown",
                uri="/reports/child.md",
                content="# Child Report\nImportant findings.",
            )
            return AgentRuntimeResult(content="Child result.")

        await PydanticAIToolBridge(deps=deps).call_tool(
            ToolContext("delegate_call_1"),
            "subagent.delegate",
            {
                "name": "researcher",
                "task": "Summarize the workspace evidence now.",
                "spec_key": "researcher",
            },
        )
        return AgentRuntimeResult(content="Parent queued child.")


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
    driver = SequencedRuntime(
        [
            [
                Step.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace evidence now.",
                    },
                ),
                Step.finish(),
            ],
            [Step.message("Subtask done."), Step.finish()],
        ]
    )
    runtime = create_agent_runtime(agent_runtime=driver)

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Delegate research",
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
async def test_completed_subagent_persists_structured_result_summary() -> None:
    runtime = create_agent_runtime(agent_runtime=DelegatingArtifactRuntime())

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Delegate artifact research",
        scopes=["*"],
    )
    subagent_run = (await runtime.store.list_subagent_runs(parent_run_id=parent.id))[0]
    child = await runtime.store.get_run(subagent_run.child_run_id)
    assert child is not None

    await runtime.worker.work_once()
    completed = (await runtime.store.list_subagent_runs(parent_run_id=parent.id))[0]
    parent_events = await runtime.event_store.list_by_run(parent.id)
    completed_event = next(event for event in parent_events if event.type == "subagent.completed")
    subagent_span = next(
        span
        for span in project_trace_spans(parent_events)
        if span.id == f"subagent:{completed.id}"
    )

    assert completed.status == AgentSubagentRunStatus.COMPLETED
    assert completed.result_summary is not None
    assert completed.result_summary.content == "Child result."
    assert completed.result_summary.artifact_count == 1
    assert completed.result_summary.artifacts[0].name == "Child Report"
    assert completed_event.payload["result_summary"]["content"] == "Child result."
    assert completed_event.payload["result_summary"]["artifacts"][0]["summary"] == (
        "# Child Report\nImportant findings."
    )
    assert subagent_span.refs["artifact_count"] == 1
    assert subagent_span.refs["result_content_length"] == len("Child result.")


@pytest.mark.asyncio
async def test_cancelled_child_run_updates_parent_subagent_state() -> None:
    driver = SequencedRuntime(
        [
            [
                Step.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace evidence now.",
                    },
                ),
                Step.finish(),
            ],
            [Step.message("This child should not run."), Step.finish()],
        ]
    )
    runtime = create_agent_runtime(agent_runtime=driver)

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Delegate research",
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
    driver = SequencedRuntime(
        [
            [
                Step.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace evidence now.",
                        "spec_key": "researcher",
                    },
                ),
                Step.finish(),
            ]
        ]
    )
    runtime = create_agent_runtime(agent_runtime=driver)
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (
            await client.post(
                "/api/subagents",
                json={
                    "org_id": "org_1",
                    "key": "researcher",
                    "name": "Researcher",
                    "instructions": "Use workspace evidence.",
                    "allowed_tools": ["workspace.read_file"],
                },
            )
        )
        listed = await client.get("/api/subagents?org_id=org_1")
        parent = (
            await client.post(
                "/api/runs",
                json={
                    "task_msg": "Delegate research task now",
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "scopes": ["*"],
                    "wait_for_completion": True,
                },
            )
        ).json()
        delegations = await client.get(f"/api/runs/{parent['id']}/subagents")

    assert created.status_code == 201
    assert created.json()["key"] == "researcher"
    assert listed.status_code == 200
    assert listed.json()[0]["allowed_tools"] == ["workspace.read_file"]
    assert delegations.status_code == 200
    assert delegations.json()[0]["parent_run_id"] == parent["id"]
    assert delegations.json()[0]["spec_key"] == "researcher"


@pytest.mark.asyncio
async def test_subagent_run_tree_api_projects_parent_child_inspection_view() -> None:
    driver = SequencedRuntime(
        [
            [
                Step.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace evidence now.",
                        "spec_key": "researcher",
                    },
                ),
                Step.finish(),
            ],
            [Step.message("Subtask done."), Step.finish()],
        ]
    )
    runtime = create_agent_runtime(agent_runtime=driver)
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Tree"},
            )
        ).json()
        parent = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "task_msg": "Delegate research task now",
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "scopes": ["*"],
                    "wait_for_completion": True,
                },
            )
        ).json()
        await runtime.worker.work_once()
        child_run_id = (
            await runtime.store.list_subagent_runs(parent_run_id=parent["id"])
        )[0].child_run_id
        await runtime.event_store.append(
            AgentStreamEvent(
                id="event_child_web_failure",
                run_id=child_run_id,
                thread_id=thread["id"],
                sequence=await runtime.event_store.next_sequence(child_run_id),
                timestamp="2026-06-18T00:00:00Z",
                type="web.fetch.failed",
                source=AgentStreamSource(kind="test"),
                payload={
                    "tool_call_id": "tool_1",
                    "url": "https://example.test",
                    "error": {"type": "timeout"},
                },
            )
        )
        tree = (await client.get(f"/api/runs/{parent['id']}/tree")).json()
        thread_tree = (
            await client.get(f"/api/threads/{thread['id']}/runs/{parent['id']}/tree")
        ).json()

    assert tree == thread_tree
    assert tree["root_run_id"] == parent["id"]
    assert tree["summary"]["total_runs"] == 2
    assert tree["summary"]["total_delegations"] == 1
    assert tree["summary"]["max_depth"] == 1
    assert tree["summary"]["attention_runs"] == 2
    assert tree["summary"]["degraded_runs"] == 1
    assert tree["summary"]["root_needs_attention"] is True
    assert [node["depth"] for node in tree["nodes"]] == [0, 1]
    assert tree["nodes"][0]["run_id"] == parent["id"]
    assert tree["nodes"][0]["child_count"] == 1
    assert tree["nodes"][0]["attention_reasons"] == ["descendant_degraded"]
    assert tree["nodes"][1]["source"] == "delegated_task"
    assert tree["nodes"][1]["research_degraded"] is True
    assert tree["nodes"][1]["attention_reasons"] == ["self_degraded"]
    assert tree["nodes"][1]["subagent_run_id"] == tree["delegations"][0]["subagent_run_id"]
    assert tree["delegations"][0]["parent_run_id"] == parent["id"]
    assert tree["delegations"][0]["name"] == "researcher"


@pytest.mark.asyncio
async def test_subagent_delegate_rejects_unknown_child_skill() -> None:
    driver = SequencedRuntime(
        [
            [
                Step.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace evidence now.",
                        "skill_id": "missing-skill",
                    },
                ),
                Step.finish(),
            ]
        ]
    )
    runtime = create_agent_runtime(agent_runtime=driver)

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Delegate research",
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
    driver = SequencedRuntime(
        [
            [
                Step.tool(
                    "subagent.delegate",
                    {
                        "name": "researcher",
                        "task": "Summarize the workspace evidence now.",
                        "skill_id": "child-researcher",
                        "scopes": ["*"],
                    },
                ),
                Step.finish(),
            ]
        ]
    )
    runtime = create_agent_runtime(
        agent_runtime=driver,
        skill_resolver=InMemorySkillResolver([subagent_skill()]),
    )

    parent = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Delegate research",
        scopes=["agent.subagent.write"],
    )
    subagent_runs = await runtime.store.list_subagent_runs(parent_run_id=parent.id)
    events = await runtime.event_store.list_by_run(parent.id)
    tool_failed = next(event for event in events if event.type == "tool.failed")

    assert parent.status == AgentRunStatus.FAILED
    assert subagent_runs == []
    assert "Child scopes must be a subset of parent scopes" in tool_failed.payload["error"]["message"]
