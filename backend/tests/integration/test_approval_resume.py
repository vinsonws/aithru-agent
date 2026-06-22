import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.domain import (
    AgentApprovalDecision,
    AgentExternalApprovalRef,
    AgentExternalRunWaitRef,
    AgentRunStatus,
)
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
    agent_runtime = AgentRuntime(
        model=TestModel(call_tools=["workspace.write_file"], custom_output_text="Report written.")
    )
    return (
        AgentWorkerRunner(
            store=store,
            event_writer=writer,
            capability_router=router,
            agent_runtime=agent_runtime,
        ),
        store,
        event_store,
    )


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
    file = await store.read_workspace_file(run.workspace_id, "/a")
    all_types = [event.type for event in await event_store.list_by_run(run.id)]

    assert completed_run.status == AgentRunStatus.COMPLETED
    assert file.content == "a"
    assert all_types.index("tool.completed") < all_types.index("message.delta")
    assert all_types[-3:] == ["model.completed", "message.completed", "run.completed"]


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


@pytest.mark.asyncio
async def test_approval_resume_fails_run_with_unresolvable_skill_before_tool_executes() -> None:
    runner, store, event_store = make_approval_runner()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Resume with missing skill",
        workspace_id=workspace.id,
        scopes=["*"],
        skill_id="missing-skill",
    )
    approval = await store.create_approval(
        run_id=run.id,
        tool_call_id="toolcall_1",
        tool_name="workspace.write_file",
        tool_input={"path": "/reports/report.md", "content": "# Report\n", "media_type": "text/markdown"},
    )
    running = await store.claim_run(run.id)
    assert running is not None
    await store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_APPROVAL,
        current_approval_id=approval.id,
    )

    resumed = await runner.resume_run(
        run.id,
        approval_id=approval.id,
        decision=AgentApprovalDecision.APPROVED,
        comment="approved",
    )
    events = await event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    files = await store.list_workspace_files(workspace.id)

    assert resumed.status == AgentRunStatus.FAILED
    assert resumed.error["message"] == "Skill not found: missing-skill"
    assert "tool.started" not in event_types
    assert files == []


@pytest.mark.asyncio
async def test_workflow_owned_external_approval_resume_requeues_without_agent_approval() -> None:
    runner, store, event_store = make_approval_runner()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Wait for workflow-owned approval",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await store.claim_run(run.id)
    assert running is not None
    paused = await store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_APPROVAL,
        current_external_approval=AgentExternalApprovalRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            approval_id="capapproval_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="pending",
        ),
    )

    resumed = await runner.resume_after_external_approval(
        paused.id,
        approval_id="capapproval_1",
        capability_run_id="caprun_1",
        decision=AgentApprovalDecision.APPROVED,
        comment="approved in Workbench",
    )
    events = await event_store.list_by_run(run.id)

    assert resumed.status == AgentRunStatus.QUEUED
    assert resumed.current_approval_id is None
    assert resumed.current_external_approval is None
    assert await store.list_approvals() == []
    assert [event.type for event in events] == [
        "external_approval.resolved",
        "run.resumed",
    ]
    assert events[0].payload == {
        "kind": "workflow_capability",
        "capability_key": "report_review",
        "capability_run_id": "caprun_1",
        "approval_id": "capapproval_1",
        "tool_call_id": "tc_workflow",
        "tool_name": "workflow.report_review",
        "decision": "approved",
        "comment": "approved in Workbench",
    }


@pytest.mark.asyncio
async def test_rejected_workflow_owned_external_approval_fails_run() -> None:
    runner, store, event_store = make_approval_runner()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Wait for workflow-owned approval",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await store.claim_run(run.id)
    assert running is not None
    paused = await store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_APPROVAL,
        current_external_approval=AgentExternalApprovalRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            approval_id="capapproval_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="pending",
        ),
    )

    failed = await runner.resume_after_external_approval(
        paused.id,
        approval_id="capapproval_1",
        capability_run_id="caprun_1",
        decision=AgentApprovalDecision.REJECTED,
        comment="rejected in Workbench",
    )
    events = await event_store.list_by_run(run.id)

    assert failed.status == AgentRunStatus.FAILED
    assert failed.current_external_approval is None
    assert [event.type for event in events] == [
        "external_approval.resolved",
        "external_run.failed",
        "run.failed",
    ]
    assert failed.error == {"message": "External workflow approval rejected"}


@pytest.mark.asyncio
async def test_external_run_resume_requeues_after_completion() -> None:
    runner, store, event_store = make_approval_runner()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await store.claim_run(run.id)
    assert running is not None
    paused = await store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )

    resumed = await runner.resume_after_external_run(
        paused.id,
        capability_run_id="caprun_1",
        status="completed",
        output={"review_status": "accepted"},
        comment="completed in Workbench",
    )
    events = await event_store.list_by_run(run.id)

    assert resumed.status == AgentRunStatus.QUEUED
    assert resumed.current_external_run is None
    assert resumed.current_external_approval is None
    assert await store.list_approvals() == []
    assert [event.type for event in events] == [
        "external_run.completed",
        "run.resumed",
    ]
    assert events[0].payload == {
        "kind": "workflow_capability",
        "capability_key": "report_review",
        "capability_run_id": "caprun_1",
        "tool_call_id": "tc_workflow",
        "tool_name": "workflow.report_review",
        "status": "completed",
        "correlation_id": "run_1:tc_workflow",
        "output": {"review_status": "accepted"},
        "comment": "completed in Workbench",
    }
    assert events[1].payload == {"status": "queued", "resume_reason": "external_run_completed"}


@pytest.mark.asyncio
async def test_failed_external_run_fails_waiting_run() -> None:
    runner, store, event_store = make_approval_runner()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await store.claim_run(run.id)
    assert running is not None
    paused = await store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )

    failed = await runner.resume_after_external_run(
        paused.id,
        capability_run_id="caprun_1",
        status="failed",
        error={"message": "Workflow capability failed"},
        comment="failed in Workbench",
    )
    events = await event_store.list_by_run(run.id)

    assert failed.status == AgentRunStatus.FAILED
    assert failed.current_external_run is None
    assert failed.error == {"message": "Workflow capability failed"}
    assert [event.type for event in events] == [
        "external_run.failed",
        "run.failed",
    ]
    assert events[0].payload["status"] == "failed"
    assert events[0].payload["error"] == {"message": "Workflow capability failed"}
