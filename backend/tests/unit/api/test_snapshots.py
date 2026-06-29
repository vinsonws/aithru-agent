from aithru_agent.api.snapshots import build_run_inspection_summary, build_run_resume_snapshot
from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalStatus,
    AgentExternalRunWaitRef,
    AgentRun,
    AgentRunStatus,
    AgentSubagentRun,
    AgentSubagentRunStatus,
)
from aithru_agent.stream.events import AgentStreamEvent


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


def run(status: AgentRunStatus) -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Continue work.",
        workspace_id="workspace_1",
        status=status,
        started_at="2026-06-18T00:00:00Z",
    )


def test_resume_snapshot_describes_active_input_pause() -> None:
    snapshot = build_run_resume_snapshot(
        run=run(AgentRunStatus.WAITING_INPUT),
        events=[
            ev(
                3,
                "input.requested",
                {
                    "input_request_id": "toolcall_input",
                    "tool_call_id": "toolcall_input",
                    "prompt": "Which region?",
                    "reason": "Need scope.",
                },
            ),
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_input",
                    "input_request_id": "toolcall_input",
                    "tool_call_id": "toolcall_input",
                    "prompt": "Which region?",
                    "reason": "Need scope.",
                },
            ),
        ],
        approvals=[],
        subagents=[],
    )

    assert snapshot.model_dump(mode="json") == {
        "kind": "input",
        "run_status": "waiting_input",
        "resumable": True,
        "reason": "Need scope.",
        "paused_event_sequence": 4,
        "resumed_event_sequence": None,
        "approval_id": None,
        "approval_status": None,
        "tool_call_id": "toolcall_input",
        "tool_name": None,
        "has_persisted_message_history": False,
        "input_request_id": "toolcall_input",
        "input_prompt": "Which region?",
        "input_received": False,
        "input_message_id": None,
        "subagent_run_id": None,
        "child_run_id": None,
        "subagent_status": None,
        "audit_event_types": ["input.requested", "run.paused"],
    }


def test_resume_snapshot_keeps_input_resume_audit_after_completion() -> None:
    snapshot = build_run_resume_snapshot(
        run=run(AgentRunStatus.COMPLETED),
        events=[
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_input",
                    "input_request_id": "toolcall_input",
                    "tool_call_id": "toolcall_input",
                    "prompt": "Which region?",
                },
            ),
            ev(5, "input.received", {"message_id": "msg_1", "content": "Use APAC."}),
            ev(6, "run.resumed", {"status": "queued", "resume_reason": "input_received"}),
            ev(10, "run.completed", {"status": "completed"}),
        ],
        approvals=[],
        subagents=[],
    )

    assert snapshot.kind == "input"
    assert snapshot.resumable is False
    assert snapshot.input_received is True
    assert snapshot.input_message_id == "msg_1"
    assert snapshot.resumed_event_sequence == 6
    assert snapshot.audit_event_types == ["run.paused", "input.received", "run.resumed"]


def test_resume_snapshot_describes_active_approval_pause_with_persisted_history() -> None:
    approval = AgentApproval(
        id="approval_1",
        run_id="run_1",
        tool_call_id="toolcall_1",
        tool_name="workspace.write_file",
        status=AgentApprovalStatus.PENDING,
        metadata={"pydantic_message_history": "[]"},
        created_at="2026-06-18T00:00:00Z",
    )

    snapshot = build_run_resume_snapshot(
        run=run(AgentRunStatus.WAITING_APPROVAL),
        events=[
            ev(3, "approval.requested", {"approval_id": "approval_1"}),
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_approval",
                    "approval_id": "approval_1",
                    "tool_call_id": "toolcall_1",
                    "tool_name": "workspace.write_file",
                },
            ),
        ],
        approvals=[approval],
        subagents=[],
    )

    assert snapshot.kind == "approval"
    assert snapshot.resumable is True
    assert snapshot.approval_id == "approval_1"
    assert snapshot.approval_status == "pending"
    assert snapshot.has_persisted_message_history is True
    assert snapshot.tool_name == "workspace.write_file"


def test_resume_snapshot_describes_active_external_approval_pause() -> None:
    snapshot = build_run_resume_snapshot(
        run=run(AgentRunStatus.WAITING_APPROVAL),
        events=[
            ev(
                3,
                "external_approval.requested",
                {
                    "kind": "workflow_capability",
                    "capability_run_id": "caprun_1",
                    "approval_id": "capapproval_1",
                },
            ),
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_approval",
                    "approval_kind": "external",
                    "current_external_approval": {
                        "kind": "workflow_capability",
                        "capability_key": "report_review",
                        "capability_run_id": "caprun_1",
                        "approval_id": "capapproval_1",
                        "tool_call_id": "tc_workflow",
                        "tool_name": "workflow.report_review",
                        "correlation_id": "run_1:tc_workflow",
                        "status": "pending",
                    },
                },
            ),
        ],
        approvals=[],
        subagents=[],
    )

    assert snapshot.kind == "external_approval"
    assert snapshot.resumable is True
    assert snapshot.approval_id == "capapproval_1"
    assert snapshot.approval_status is None
    assert snapshot.external_approval_id == "capapproval_1"
    assert snapshot.external_capability_key == "report_review"
    assert snapshot.external_capability_run_id == "caprun_1"
    assert snapshot.tool_call_id == "tc_workflow"
    assert snapshot.tool_name == "workflow.report_review"
    assert snapshot.reason == "Waiting for external workflow approval to run workflow.report_review."
    assert snapshot.audit_event_types == ["external_approval.requested", "run.paused"]


def test_resume_snapshot_describes_active_external_run_pause() -> None:
    snapshot = build_run_resume_snapshot(
        run=run(AgentRunStatus.WAITING_EXTERNAL_RUN),
        events=[
            ev(
                3,
                "external_run.created",
                {
                    "kind": "workflow_capability",
                    "tool_call_id": "tc_workflow",
                    "tool_name": "workflow.report_review",
                    "capability_key": "report_review",
                    "capability_run_id": "caprun_1",
                    "status": "running",
                    "correlation_id": "run_1:tc_workflow",
                    "approval_id": None,
                },
            ),
            ev(
                4,
                "run.paused",
                {
                    "status": "waiting_external_run",
                    "current_external_run": {
                        "kind": "workflow_capability",
                        "capability_key": "report_review",
                        "capability_run_id": "caprun_1",
                        "tool_call_id": "tc_workflow",
                        "tool_name": "workflow.report_review",
                        "correlation_id": "run_1:tc_workflow",
                        "status": "running",
                    },
                },
            ),
        ],
        approvals=[],
        subagents=[],
    )

    assert snapshot.kind == "external_run"
    assert snapshot.resumable is True
    assert snapshot.approval_id is None
    assert snapshot.external_capability_key == "report_review"
    assert snapshot.external_capability_run_id == "caprun_1"
    assert snapshot.tool_call_id == "tc_workflow"
    assert snapshot.tool_name == "workflow.report_review"
    assert snapshot.reason == "Waiting for external workflow capability run caprun_1."
    assert snapshot.audit_event_types == ["external_run.created", "run.paused"]


def test_resume_snapshot_describes_active_subagent_pause() -> None:
    subagent = AgentSubagentRun(
        id="subagent_run_1",
        org_id="org_1",
        parent_run_id="run_1",
        child_run_id="run_child",
        name="Researcher",
        task="Research.",
        status=AgentSubagentRunStatus.RUNNING,
        created_at="2026-06-18T00:00:00Z",
    )

    snapshot = build_run_resume_snapshot(
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
        subagents=[subagent],
    )

    assert snapshot.kind == "subagent"
    assert snapshot.resumable is True
    assert snapshot.subagent_run_id == "subagent_run_1"
    assert snapshot.child_run_id == "run_child"
    assert snapshot.subagent_status == "running"


def test_inspection_summary_exposes_external_run_diagnostics() -> None:
    summary = build_run_inspection_summary(
        run=run(AgentRunStatus.FAILED),
        events=[
            ev(
                3,
                "external_run.failed",
                {
                    "kind": "workflow_capability",
                    "capability_key": "report_review",
                    "capability_run_id": "caprun_failed",
                    "tool_call_id": "tc_failed",
                    "tool_name": "workflow.report_review",
                    "status": "failed",
                    "correlation_id": "run_1:tc_failed",
                    "error": {"message": "Workflow capability failed"},
                    "comment": "failed in Workbench",
                },
            ),
            ev(
                4,
                "external_run.cancelled",
                {
                    "kind": "workflow_capability",
                    "capability_key": "report_publish",
                    "capability_run_id": "caprun_cancelled",
                    "tool_call_id": "tc_cancelled",
                    "tool_name": "workflow.report_publish",
                    "status": "cancelled",
                    "correlation_id": "run_1:tc_cancelled",
                    "comment": "cancelled in Workbench",
                },
            ),
        ],
        todos=[],
        workspace_files=[],
        approvals=[],
        trace=[],
    )

    assert summary.external_run_count == 2
    assert summary.failed_external_run_count == 1
    assert summary.cancelled_external_run_count == 1
    assert summary.external_runs[0].capability_run_id == "caprun_failed"
    assert summary.external_runs[0].capability_key == "report_review"
    assert summary.external_runs[0].tool_name == "workflow.report_review"
    assert summary.external_runs[0].status == "failed"
    assert summary.external_runs[0].error == {"message": "Workflow capability failed"}
    assert summary.external_runs[0].comment == "failed in Workbench"
    assert summary.external_runs[0].source_event_sequence == 3


def test_inspection_summary_exposes_sandbox_diagnostics() -> None:
    completed_diagnostics = {
        "sandbox_run_id": "sandbox_toolcall_1",
        "status": "completed",
        "language": "python",
        "execution": {
            "language": "python",
            "timeout_ms": 1000,
            "exit_code": 0,
            "stdout_chars": 3,
            "stderr_chars": 0,
            "stdout_truncated": False,
            "stderr_truncated": False,
            "result_type": "str",
            "error_code": None,
            "timed_out": False,
        },
        "workspace_effects": {
            "declared_count": 1,
            "persisted_count": 1,
            "paths": ["/reports/summary.md"],
            "persistence_error": None,
        },
        "error_code": None,
        "timed_out": False,
    }
    failed_diagnostics = {
        "sandbox_run_id": "sandbox_toolcall_2",
        "status": "failed",
        "language": "python",
        "execution": {
            "language": "python",
            "timeout_ms": 1000,
            "exit_code": 0,
            "stdout_chars": 0,
            "stderr_chars": 0,
            "stdout_truncated": False,
            "stderr_truncated": False,
            "result_type": None,
            "error_code": None,
            "timed_out": False,
        },
        "workspace_effects": {
            "declared_count": 1,
            "persisted_count": 0,
            "paths": [],
            "persistence_error": {"message": "Path is outside allowed workspace paths"},
        },
        "error_code": None,
        "timed_out": False,
    }

    summary = build_run_inspection_summary(
        run=run(AgentRunStatus.FAILED),
        events=[
            ev(
                3,
                "sandbox.completed",
                {
                    "sandbox_run_id": "sandbox_toolcall_1",
                    "status": "completed",
                    "diagnostics": completed_diagnostics,
                },
            ),
            ev(
                4,
                "sandbox.failed",
                {
                    "sandbox_run_id": "sandbox_toolcall_2",
                    "status": "failed",
                    "diagnostics": failed_diagnostics,
                    "error": {"message": "Path is outside allowed workspace paths"},
                },
            ),
        ],
        todos=[],
        workspace_files=[],
        approvals=[],
        trace=[],
    )

    assert summary.sandbox_run_count == 2
    assert summary.needs_attention is True
    assert summary.attention_reasons == [
        "health_failed",
        "sandbox_failed",
        "sandbox_workspace_side_effect",
        "sandbox_persistence_error",
    ]
    assert summary.failed_sandbox_run_count == 1
    assert summary.sandbox_workspace_file_count == 1
    assert summary.sandbox_persistence_error_count == 1
    assert summary.sandbox_operator_action_count == 4
    assert [action.kind for action in summary.sandbox_operator_actions] == [
        "inspect_workspace_file",
        "inspect_sandbox_error",
        "review_workspace_policy",
        "retry_sandbox_run",
    ]
    assert (
        summary.sandbox_operator_actions[0].path
        == "/api/workspaces/workspace_1/files/reports/summary.md"
    )
    assert summary.sandbox_operator_actions[-1].path == "/api/runs"
    completed_actions = summary.sandbox_runs[0].operator_actions
    assert [action.kind for action in completed_actions] == [
        "inspect_workspace_file",
    ]
    assert completed_actions[0].method == "GET"
    assert completed_actions[0].path == "/api/workspaces/workspace_1/files/reports/summary.md"
    assert completed_actions[0].workspace_path == "/reports/summary.md"
    assert summary.sandbox_runs[0].sandbox_run_id == "sandbox_toolcall_1"
    assert summary.sandbox_runs[0].source_event_sequence == 3
    assert summary.sandbox_runs[0].workspace_effects.paths == ["/reports/summary.md"]
    failed_actions = summary.sandbox_runs[1].operator_actions
    assert [action.kind for action in failed_actions] == [
        "inspect_sandbox_error",
        "review_workspace_policy",
        "retry_sandbox_run",
    ]
    assert failed_actions[0].method == "GET"
    assert failed_actions[0].path == "/api/runs/run_1/summary"
    assert failed_actions[1].workspace_path is None
    assert failed_actions[2].method == "POST"
    assert failed_actions[2].path == "/api/runs"
    assert summary.sandbox_runs[1].sandbox_run_id == "sandbox_toolcall_2"
    assert summary.sandbox_runs[1].status == "failed"
    assert summary.sandbox_runs[1].source_event_sequence == 4
    assert summary.sandbox_runs[1].error == {
        "message": "Path is outside allowed workspace paths"
    }


def test_inspection_summary_exposes_active_external_run_staleness() -> None:
    waiting = run(AgentRunStatus.WAITING_EXTERNAL_RUN).model_copy(
        update={
            "current_external_run": AgentExternalRunWaitRef(
                kind="workflow_capability",
                capability_key="report_review",
                capability_run_id="caprun_waiting",
                tool_call_id="tc_workflow",
                tool_name="workflow.report_review",
                correlation_id="run_1:tc_workflow",
                status="running",
            )
        }
    )

    summary = build_run_inspection_summary(
        run=waiting,
        events=[
            ev(
                2,
                "external_run.created",
                {
                    "kind": "workflow_capability",
                    "capability_key": "report_review",
                    "capability_run_id": "caprun_waiting",
                    "tool_call_id": "tc_workflow",
                    "tool_name": "workflow.report_review",
                    "status": "running",
                    "correlation_id": "run_1:tc_workflow",
                },
            )
        ],
        todos=[],
        workspace_files=[],
        approvals=[],
        trace=[],
        reference_time="2026-06-18T01:00:01Z",
        external_run_stale_after_seconds=3600,
    )

    assert summary.external_run_stale is True
    assert summary.active_external_run is not None
    assert summary.active_external_run.capability_run_id == "caprun_waiting"
    assert summary.active_external_run.capability_key == "report_review"
    assert summary.active_external_run.tool_call_id == "tc_workflow"
    assert summary.active_external_run.tool_name == "workflow.report_review"
    assert summary.active_external_run.source_event_sequence == 2
    assert summary.active_external_run.waited_seconds == 3601
    assert summary.active_external_run.stale_after_seconds == 3600
    assert summary.active_external_run.stale is True
    actions = summary.active_external_run.operator_actions
    assert [action.kind for action in actions] == [
        "check_provider_status",
        "redeliver_completed_callback",
        "mark_failed",
        "mark_cancelled",
    ]
    assert actions[1].method == "POST"
    assert actions[1].path == "/api/runs/run_1/external-run/resolve"
    assert actions[2].status == "failed"
    assert actions[3].status == "cancelled"
