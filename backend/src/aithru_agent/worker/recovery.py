from typing import Any, Literal

from pydantic import Field, model_validator

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentWorkspaceFile,
    AgentRun,
    AgentRunStatus,
    AgentSubagentResultSummary,
    AgentSubagentRun,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.stream import AgentStreamEvent
from aithru_agent.worker.subagent_result import build_subagent_result_summary


RunRecoveryAction = Literal[
    "none",
    "resume_input",
    "resume_approval",
    "resume_subagent",
    "fail_subagent",
]
RunRecoveryReason = Literal[
    "not_paused",
    "no_pause_event",
    "already_resumed",
    "waiting_for_input",
    "input_received",
    "waiting_for_approval",
    "waiting_for_external_run",
    "approval_resolved",
    "waiting_for_subagent",
    "subagent_completed",
    "subagent_failed",
    "subagent_completed_requires_model_continuation",
]


class RunRecoveryDecision(AithruBaseModel):
    run_id: str
    run_status: AgentRunStatus
    action: RunRecoveryAction = "none"
    reason: RunRecoveryReason
    detail: str
    pause_sequence: int | None = Field(default=None, ge=0)
    resumed_sequence: int | None = Field(default=None, ge=0)
    input_request_id: str | None = None
    input_message_id: str | None = None
    approval_id: str | None = None
    approval_decision: str | None = None
    subagent_run_id: str | None = None
    child_run_id: str | None = None
    child_status: str | None = None
    child_result: str | None = None
    child_workspace_files: list[AgentWorkspaceFile] = Field(default_factory=list)
    child_result_summary: AgentSubagentResultSummary | None = None

    @model_validator(mode="after")
    def _action_has_required_identifiers(self) -> "RunRecoveryDecision":
        if self.action == "resume_input" and self.input_message_id is None:
            raise ValueError("resume_input requires input_message_id")
        if self.action == "resume_approval" and (self.approval_id is None or self.approval_decision is None):
            raise ValueError("resume_approval requires approval_id and approval_decision")
        if self.action == "fail_subagent" and (self.subagent_run_id is None or self.child_run_id is None):
            raise ValueError("fail_subagent requires subagent_run_id and child_run_id")
        if self.action == "resume_subagent" and (
            self.subagent_run_id is None
            or self.child_run_id is None
            or (
                self.child_result is None
                and not self.child_workspace_files
                and not (self.child_result_summary and self.child_result_summary.has_output)
            )
        ):
            raise ValueError("resume_subagent requires subagent_run_id, child_run_id, and child output context")
        return self


def decide_run_recovery(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    approvals: list[AgentApproval],
    subagents: list[AgentSubagentRun],
    child_runs: list[AgentRun],
    child_workspace_files: list[AgentWorkspaceFile] | None = None,
) -> RunRecoveryDecision:
    if run.status not in {
        AgentRunStatus.WAITING_INPUT,
        AgentRunStatus.WAITING_APPROVAL,
        AgentRunStatus.WAITING_SUBAGENT,
        AgentRunStatus.WAITING_EXTERNAL_RUN,
    }:
        return _decision(run, reason="not_paused", detail="Run is not paused.")

    pause = _latest_pause_event(events)
    if pause is None:
        return _decision(run, reason="no_pause_event", detail="Paused run has no persisted pause event.")

    resumed = _first_event_after(events, pause.sequence, "run.resumed")
    if resumed is not None:
        return _decision(
            run,
            reason="already_resumed",
            detail="Run already has a resume event after the latest pause.",
            pause_sequence=pause.sequence,
            resumed_sequence=resumed.sequence,
        )

    if run.status == AgentRunStatus.WAITING_INPUT:
        return _input_decision(run, pause, events)
    if run.status == AgentRunStatus.WAITING_APPROVAL:
        return _approval_decision(run, pause, approvals)
    if run.status == AgentRunStatus.WAITING_EXTERNAL_RUN:
        return _decision(
            run,
            reason="waiting_for_external_run",
            detail="Run is waiting for an external workflow capability run to resolve.",
            pause_sequence=pause.sequence,
        )
    return _subagent_decision(run, pause, subagents, child_runs, child_workspace_files or [])


def _input_decision(
    run: AgentRun,
    pause: AgentStreamEvent,
    events: list[AgentStreamEvent],
) -> RunRecoveryDecision:
    received = _first_event_after(events, pause.sequence, "input.received")
    input_request_id = _string_payload(pause.payload, "input_request_id")
    if received is None:
        return _decision(
            run,
            reason="waiting_for_input",
            detail="Run is still waiting for user input.",
            pause_sequence=pause.sequence,
            input_request_id=input_request_id,
        )
    message_id = _string_payload(received.payload, "message_id")
    return _decision(
        run,
        action="resume_input",
        reason="input_received",
        detail="User input was received after the latest pause and the run can be requeued.",
        pause_sequence=pause.sequence,
        input_request_id=input_request_id,
        input_message_id=message_id,
    )


def _approval_decision(
    run: AgentRun,
    pause: AgentStreamEvent,
    approvals: list[AgentApproval],
) -> RunRecoveryDecision:
    approval_id = run.current_approval_id or _string_payload(pause.payload, "approval_id")
    approval = _approval_by_id(approvals, approval_id)
    if approval is None:
        return _decision(
            run,
            reason="waiting_for_approval",
            detail="Run is waiting for approval and no resolved approval decision is available.",
            pause_sequence=pause.sequence,
            approval_id=approval_id,
        )
    if approval.status != AgentApprovalStatus.RESOLVED or approval.decision is None:
        return _decision(
            run,
            reason="waiting_for_approval",
            detail="Run is still waiting for an approval decision.",
            pause_sequence=pause.sequence,
            approval_id=approval.id,
        )
    return _decision(
        run,
        action="resume_approval",
        reason="approval_resolved",
        detail="Approval was resolved after the run paused and can be applied.",
        pause_sequence=pause.sequence,
        approval_id=approval.id,
        approval_decision=_approval_decision_value(approval.decision),
    )


def _subagent_decision(
    run: AgentRun,
    pause: AgentStreamEvent,
    subagents: list[AgentSubagentRun],
    child_runs: list[AgentRun],
    child_workspace_files: list[AgentWorkspaceFile],
) -> RunRecoveryDecision:
    subagent_run_id = _string_payload(pause.payload, "subagent_run_id")
    child_run_id = _string_payload(pause.payload, "child_run_id")
    subagent = _subagent_by_id(subagents, subagent_run_id)
    child = _child_by_id(child_runs, child_run_id or (subagent.child_run_id if subagent else None))
    child_status = child.status.value if child else None
    if child and child.status in {AgentRunStatus.FAILED, AgentRunStatus.CANCELLED}:
        return _decision(
            run,
            action="fail_subagent",
            reason="subagent_failed",
            detail="Delegated child run reached a terminal failure state.",
            pause_sequence=pause.sequence,
            subagent_run_id=subagent_run_id or (subagent.id if subagent else None),
            child_run_id=child.id,
            child_status=child_status,
        )
    if child and child.status == AgentRunStatus.COMPLETED:
        result_summary = build_subagent_result_summary(child, child_workspace_files)
        if result_summary.has_output:
            return _decision(
                run,
                action="resume_subagent",
                reason="subagent_completed",
                detail="Delegated child run completed with recoverable output context and can continue the parent.",
                pause_sequence=pause.sequence,
                subagent_run_id=subagent_run_id or (subagent.id if subagent else None),
                child_run_id=child.id,
                child_status=child_status,
                child_result=result_summary.content,
                child_workspace_files=result_summary.workspace_files,
                child_result_summary=result_summary,
            )
        return _decision(
            run,
            reason="subagent_completed_requires_model_continuation",
            detail="Delegated child completed without a textual result for automatic parent continuation.",
            pause_sequence=pause.sequence,
            subagent_run_id=subagent_run_id or (subagent.id if subagent else None),
            child_run_id=child.id,
            child_status=child_status,
        )
    return _decision(
        run,
        reason="waiting_for_subagent",
        detail="Run is still waiting for a delegated child run.",
        pause_sequence=pause.sequence,
        subagent_run_id=subagent_run_id or (subagent.id if subagent else None),
        child_run_id=child_run_id,
        child_status=child_status,
    )


def _decision(
    run: AgentRun,
    *,
    reason: RunRecoveryReason,
    detail: str,
    action: RunRecoveryAction = "none",
    pause_sequence: int | None = None,
    resumed_sequence: int | None = None,
    input_request_id: str | None = None,
    input_message_id: str | None = None,
    approval_id: str | None = None,
    approval_decision: str | None = None,
    subagent_run_id: str | None = None,
    child_run_id: str | None = None,
    child_status: str | None = None,
    child_result: str | None = None,
    child_workspace_files: list[AgentWorkspaceFile] | None = None,
    child_result_summary: AgentSubagentResultSummary | None = None,
) -> RunRecoveryDecision:
    return RunRecoveryDecision(
        run_id=run.id,
        run_status=run.status,
        action=action,
        reason=reason,
        detail=detail,
        pause_sequence=pause_sequence,
        resumed_sequence=resumed_sequence,
        input_request_id=input_request_id,
        input_message_id=input_message_id,
        approval_id=approval_id,
        approval_decision=approval_decision,
        subagent_run_id=subagent_run_id,
        child_run_id=child_run_id,
        child_status=child_status,
        child_result=child_result,
        child_workspace_files=child_workspace_files or [],
        child_result_summary=child_result_summary,
    )


def _latest_pause_event(events: list[AgentStreamEvent]) -> AgentStreamEvent | None:
    pause_events = [event for event in events if event.type == "run.paused"]
    if not pause_events:
        return None
    return max(pause_events, key=lambda event: event.sequence)


def _first_event_after(
    events: list[AgentStreamEvent],
    sequence: int,
    event_type: str,
) -> AgentStreamEvent | None:
    later = [
        event
        for event in events
        if event.sequence > sequence and event.type == event_type
    ]
    if not later:
        return None
    return min(later, key=lambda event: event.sequence)


def _approval_by_id(approvals: list[AgentApproval], approval_id: str | None) -> AgentApproval | None:
    if approval_id is None:
        return None
    for approval in approvals:
        if approval.id == approval_id:
            return approval
    return None


def _subagent_by_id(subagents: list[AgentSubagentRun], subagent_run_id: str | None) -> AgentSubagentRun | None:
    if subagent_run_id is None:
        return None
    for subagent in subagents:
        if subagent.id == subagent_run_id:
            return subagent
    return None


def _child_by_id(child_runs: list[AgentRun], child_run_id: str | None) -> AgentRun | None:
    if child_run_id is None:
        return None
    for child in child_runs:
        if child.id == child_run_id:
            return child
    return None


def _string_payload(payload: Any, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _approval_decision_value(decision: AgentApprovalDecision | str) -> str:
    return decision.value if isinstance(decision, AgentApprovalDecision) else str(decision)
