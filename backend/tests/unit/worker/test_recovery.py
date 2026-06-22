from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifact,
    AgentRunResult,
    AgentRun,
    AgentRunStatus,
    AgentSubagentRun,
    AgentSubagentRunStatus,
)
from aithru_agent.stream.events import AgentStreamEvent
from aithru_agent.worker.recovery import decide_run_recovery


def ev(sequence: int, event_type: str, payload: dict) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"run_1:{sequence}",
        run_id="run_1",
        sequence=sequence,
        timestamp="2026-06-18T00:00:00Z",
        type=event_type,
        source={"kind": "harness"},
        payload=payload,
    )


def run(status: AgentRunStatus, *, current_approval_id: str | None = None) -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue work.",
        workspace_id="workspace_1",
        status=status,
        current_approval_id=current_approval_id,
        started_at="2026-06-18T00:00:00Z",
    )


def approval(
    *,
    status: AgentApprovalStatus,
    decision: AgentApprovalDecision | None = None,
) -> AgentApproval:
    return AgentApproval(
        id="approval_1",
        run_id="run_1",
        tool_call_id="toolcall_1",
        tool_name="workspace.write_file",
        status=status,
        decision=decision,
        metadata={"pydantic_message_history": "[]"},
        created_at="2026-06-18T00:00:00Z",
    )


def subagent(status: AgentSubagentRunStatus) -> AgentSubagentRun:
    return AgentSubagentRun(
        id="subagent_run_1",
        org_id="org_1",
        parent_run_id="run_1",
        child_run_id="run_child",
        name="Researcher",
        task="Research.",
        status=status,
        created_at="2026-06-18T00:00:00Z",
    )


def child(status: AgentRunStatus, *, result: AgentRunResult | None = None) -> AgentRun:
    return AgentRun(
        id="run_child",
        org_id="org_1",
        actor_user_id="user_1",
        source="delegated_task",
        goal="Child work.",
        workspace_id="workspace_1",
        status=status,
        result=result,
        started_at="2026-06-18T00:00:00Z",
    )


def artifact() -> AgentArtifact:
    return AgentArtifact(
        id="artifact_1",
        org_id="org_1",
        workspace_id="workspace_1",
        run_id="run_child",
        type="report",
        name="Child Report",
        media_type="text/markdown",
        uri="/reports/child.md",
        content="# Child Report\nImportant findings.",
        created_at="2026-06-18T00:00:00Z",
    )


def test_recovery_decision_resumes_waiting_input_after_received_event() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_INPUT),
        events=[
            ev(4, "run.paused", {"status": "waiting_input", "input_request_id": "toolcall_input"}),
            ev(5, "input.received", {"message_id": "msg_1", "content": "Use APAC."}),
        ],
        approvals=[],
        subagents=[],
        child_runs=[],
    )

    assert decision.action == "resume_input"
    assert decision.reason == "input_received"
    assert decision.input_message_id == "msg_1"
    assert decision.pause_sequence == 4


def test_recovery_decision_does_not_resume_waiting_input_without_reply() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_INPUT),
        events=[ev(4, "run.paused", {"status": "waiting_input", "input_request_id": "toolcall_input"})],
        approvals=[],
        subagents=[],
        child_runs=[],
    )

    assert decision.action == "none"
    assert decision.reason == "waiting_for_input"


def test_recovery_decision_resumes_resolved_approval() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_APPROVAL, current_approval_id="approval_1"),
        events=[
            ev(3, "approval.requested", {"approval_id": "approval_1"}),
            ev(4, "run.paused", {"status": "waiting_approval", "approval_id": "approval_1"}),
        ],
        approvals=[approval(status=AgentApprovalStatus.RESOLVED, decision=AgentApprovalDecision.APPROVED)],
        subagents=[],
        child_runs=[],
    )

    assert decision.action == "resume_approval"
    assert decision.reason == "approval_resolved"
    assert decision.approval_id == "approval_1"
    assert decision.approval_decision == "approved"


def test_recovery_decision_keeps_pending_approval_waiting() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_APPROVAL, current_approval_id="approval_1"),
        events=[
            ev(3, "approval.requested", {"approval_id": "approval_1"}),
            ev(4, "run.paused", {"status": "waiting_approval", "approval_id": "approval_1"}),
        ],
        approvals=[approval(status=AgentApprovalStatus.PENDING)],
        subagents=[],
        child_runs=[],
    )

    assert decision.action == "none"
    assert decision.reason == "waiting_for_approval"


def test_recovery_decision_fails_parent_when_child_failed() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_SUBAGENT),
        events=[
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_subagent",
                    "subagent_run_id": "subagent_run_1",
                    "child_run_id": "run_child",
                },
            )
        ],
        approvals=[],
        subagents=[subagent(AgentSubagentRunStatus.FAILED)],
        child_runs=[child(AgentRunStatus.FAILED)],
    )

    assert decision.action == "fail_subagent"
    assert decision.reason == "subagent_failed"
    assert decision.subagent_run_id == "subagent_run_1"
    assert decision.child_run_id == "run_child"


def test_recovery_decision_resumes_completed_subagent_child_with_text_result() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_SUBAGENT),
        events=[
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_subagent",
                    "subagent_run_id": "subagent_run_1",
                    "child_run_id": "run_child",
                },
            )
        ],
        approvals=[],
        subagents=[subagent(AgentSubagentRunStatus.COMPLETED)],
        child_runs=[
            child(
                AgentRunStatus.COMPLETED,
                result=AgentRunResult(content="Child result."),
            )
        ],
    )

    assert decision.action == "resume_subagent"
    assert decision.reason == "subagent_completed"
    assert decision.subagent_run_id == "subagent_run_1"
    assert decision.child_run_id == "run_child"
    assert decision.child_result == "Child result."
    assert decision.child_result_summary is not None
    assert decision.child_result_summary.content == "Child result."
    assert decision.child_result_summary.has_output is True


def test_recovery_decision_does_not_auto_resume_completed_subagent_child_without_text_result() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_SUBAGENT),
        events=[
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_subagent",
                    "subagent_run_id": "subagent_run_1",
                    "child_run_id": "run_child",
                },
            )
        ],
        approvals=[],
        subagents=[subagent(AgentSubagentRunStatus.COMPLETED)],
        child_runs=[child(AgentRunStatus.COMPLETED)],
    )

    assert decision.action == "none"
    assert decision.reason == "subagent_completed_requires_model_continuation"


def test_recovery_decision_resumes_completed_subagent_child_with_artifact_summary() -> None:
    decision = decide_run_recovery(
        run=run(AgentRunStatus.WAITING_SUBAGENT),
        events=[
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_subagent",
                    "subagent_run_id": "subagent_run_1",
                    "child_run_id": "run_child",
                },
            )
        ],
        approvals=[],
        subagents=[subagent(AgentSubagentRunStatus.COMPLETED)],
        child_runs=[
            child(
                AgentRunStatus.COMPLETED,
                result=AgentRunResult(artifact_ids=["artifact_1"]),
            )
        ],
        child_artifacts=[artifact()],
    )

    assert decision.action == "resume_subagent"
    assert decision.reason == "subagent_completed"
    assert decision.child_result is None
    assert len(decision.child_artifacts) == 1
    assert decision.child_artifacts[0].id == "artifact_1"
    assert decision.child_artifacts[0].name == "Child Report"
    assert decision.child_artifacts[0].summary == "# Child Report\nImportant findings."
    assert decision.child_result_summary is not None
    assert decision.child_result_summary.artifact_ids == ["artifact_1"]
    assert decision.child_result_summary.artifact_count == 1
