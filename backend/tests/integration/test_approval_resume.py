import pytest

from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import AgentApprovalDecision, AgentRunStatus
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker.runner import AgentWorkerRunner


def make_approval_runner() -> tuple[AgentWorkerRunner, InMemoryAgentStore, InMemoryAgentEventStore]:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    router = AithruCapabilityRouter(
        adapters=[WorkspaceLocalTool(store), TodoLocalTool(store), ArtifactLocalTool(store)],
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    driver = ScriptedHarnessDriver(
        [
            ScriptedStep.message("I need to write a report.\n"),
            ScriptedStep.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\n", "media_type": "text/markdown"},
            ),
            ScriptedStep.message("Report written."),
            ScriptedStep.finish(),
        ]
    )
    return AgentWorkerRunner(store=store, event_writer=writer, capability_router=router, driver=driver), store, event_store


@pytest.mark.asyncio
async def test_risky_tool_pauses_before_execution_and_resume_approval_completes() -> None:
    runner, store, event_store = make_approval_runner()

    run = await runner.start_run(org_id="org_1", actor_user_id="user_1", goal="Write report", scopes=["*"])
    phase1_events = await event_store.list_by_run(run.id)
    phase1_types = [event.type for event in phase1_events]
    paused_run = await store.get_run(run.id)
    approvals = await store.list_approvals()

    assert paused_run.status == AgentRunStatus.WAITING_APPROVAL
    assert phase1_types[-2:] == ["approval.requested", "run.paused"]
    assert "tool.started" not in phase1_types
    assert len(approvals) == 1

    await runner.resume_run(
        run.id,
        approval_id=approvals[0].id,
        decision=AgentApprovalDecision.APPROVED,
        comment="approved",
    )
    completed_run = await store.get_run(run.id)
    file = await store.read_workspace_file(run.workspace_id, "/reports/report.md")
    all_types = [event.type for event in await event_store.list_by_run(run.id)]

    assert completed_run.status == AgentRunStatus.COMPLETED
    assert file.content == "# Report\n"
    assert all_types[-9:] == [
        "approval.resolved",
        "run.resumed",
        "tool.started",
        "workspace.file.created",
        "tool.completed",
        "message.delta",
        "model.completed",
        "message.completed",
        "run.completed",
    ]


@pytest.mark.asyncio
async def test_rejected_approval_fails_run_without_executing_tool() -> None:
    runner, store, event_store = make_approval_runner()
    run = await runner.start_run(org_id="org_1", actor_user_id="user_1", goal="Write report", scopes=["*"])
    approval = (await store.list_approvals())[0]

    await runner.resume_run(
        run.id,
        approval_id=approval.id,
        decision=AgentApprovalDecision.REJECTED,
        comment="no",
    )
    failed_run = await store.get_run(run.id)
    events = await event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    assert failed_run.status == AgentRunStatus.FAILED
    assert "workspace.file.created" not in event_types
    assert event_types[-3:] == ["approval.resolved", "tool.denied", "run.failed"]
