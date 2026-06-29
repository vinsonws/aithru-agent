import pytest

from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import AgentRunStatus
from aithru_agent.domain.errors import AgentError
from tests.utils.step_runtime import Step, StepAgentRuntime
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.trace import project_trace_spans
from aithru_agent.worker.runner import AgentWorkerRunner


def make_runner(driver: StepAgentRuntime) -> tuple[AgentWorkerRunner, InMemoryAgentStore, InMemoryAgentEventStore]:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    router = AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(store),
            TodoLocalTool(store),
        ],
        policy=ToolPolicy(require_approval_for_risk=[]),
    )
    return AgentWorkerRunner(store=store, event_writer=writer, capability_router=router, agent_runtime=driver), store, event_store


@pytest.mark.asyncio
async def test_scripted_worker_executes_tools_writes_events_and_completes_run() -> None:
    driver = StepAgentRuntime(
        [
            Step.message("I will inspect the workspace.\n"),
            Step.tool("todo.create", {"title": "Read files", "status": "running"}),
            Step.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\nDone.\n", "media_type": "text/markdown"},
            ),
            Step.message("Report complete."),
            Step.finish(),
        ]
    )
    runner, store, event_store = make_runner(driver)

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write a report",
        scopes=["*"],
    )

    stored_run = await store.get_run(run.id)
    file = await store.read_workspace_file(run.workspace_id, "/reports/report.md")
    events = await event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    assert stored_run.status == AgentRunStatus.COMPLETED
    assert stored_run.result is not None
    assert stored_run.result.content == "I will inspect the workspace.\nReport complete."
    assert file.content == "# Report\nDone.\n"
    assert stored_run.result.workspace_paths == ["/reports/report.md"]
    assert event_types == [
        "run.created",
        "run.started",
        "model.started",
        "message.created",
        "message.delta",
        "tool.proposed",
        "tool.started",
        "todo.created",
        "tool.completed",
        "tool.proposed",
        "tool.started",
        "workspace.file.created",
        "tool.completed",
        "message.delta",
        "model.completed",
        "message.completed",
        "run.completed",
    ]
    assert events[-1].payload["result"] == stored_run.result.model_dump(mode="json")
@pytest.mark.asyncio
async def test_worker_can_cancel_a_stored_run() -> None:
    driver = StepAgentRuntime([])
    runner, store, event_store = make_runner(driver)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Cancel me",
        workspace_id=workspace.id,
    )

    cancelled = await runner.cancel_run(run.id)
    events = await event_store.list_by_run(run.id)

    assert cancelled.status == AgentRunStatus.CANCELLED
    assert events[-1].type == "run.cancelled"


@pytest.mark.asyncio
async def test_worker_rejects_cancelling_terminal_run() -> None:
    runner, store, event_store = make_runner(StepAgentRuntime([Step.finish()]))
    completed = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Already done",
        scopes=["*"],
    )

    with pytest.raises(AgentError) as exc_info:
        await runner.cancel_run(completed.id)

    stored = await store.get_run(completed.id)
    events = await event_store.list_by_run(completed.id)

    assert exc_info.value.code == "BAD_REQUEST"
    assert stored.status == AgentRunStatus.COMPLETED
    assert [event.type for event in events][-1] == "run.completed"
