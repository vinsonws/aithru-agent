"""Derived API snapshot projections."""

from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import quote

from pydantic import Field, model_validator

from aithru_agent.domain import (
    AgentApproval,
    AgentPresentation,
    AgentRun,
    AgentRunOperatorFollowUpOptions,
    AgentSubagentResultSummary,
    AgentSubagentRun,
    AgentTodo,
    AgentWorkspaceFile,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.stream.presentations import presentations_from_events
from aithru_agent.domain.research import (
    ResearchEvidence,
    ResearchEvidenceSectionSummary,
    ResearchLimitation,
    ResearchPlanPhase,
    ResearchPlanSection,
    ResearchPlanSectionPriority,
    ResearchQualitySummary,
    ResearchReport,
    ResearchReportStatus,
    ResearchSource,
)
from aithru_agent.sandbox import (
    SandboxExecutionStatus,
    SandboxExecutionSummary,
    SandboxRunDiagnostics,
    SandboxWorkspaceEffectsSummary,
)
from aithru_agent.stream.events import AgentStreamEvent
from aithru_agent.trace import AgentTraceSpan


ResearchSnapshotStatus = Literal["none", "complete", "partial", "insufficient_evidence"]
ResearchSnapshotWebToolName = Literal["web.search", "web.fetch"]
ResearchExecutionStatus = Literal["none", "planned", "running", "blocked", "completed", "degraded"]
ResearchExecutionStepStatus = Literal["pending", "running", "done", "blocked", "cancelled"]
ResearchReviewStatus = Literal["none", "pass", "warn", "fail"]
ResearchReviewFindingSeverity = Literal["info", "warning", "error"]
ResearchReviewFindingCode = Literal[
    "missing_report",
    "missing_report_file",
    "partial_report",
    "insufficient_evidence_report",
    "missing_evidence",
    "blocked_research_steps",
    "web_failures",
    "research_limitations",
    "low_quality_sources",
    "no_high_quality_sources",
    "weak_research_sections",
]
ResearchContinuationStatus = Literal["none", "ready", "needs_research", "needs_report"]
ResearchContinuationActionKind = Literal[
    "collect_more_sources",
    "retry_search",
    "retry_fetch",
    "improve_source_quality",
    "address_limitations",
    "regenerate_report",
]
ResearchContinuationActionPriority = Literal["high", "medium", "low"]
RunTreeAttentionReason = Literal[
    "self_failed",
    "self_cancelled",
    "self_waiting_approval",
    "self_waiting_external_run",
    "self_waiting_input",
    "self_degraded",
    "self_sandbox_failed",
    "self_sandbox_workspace_side_effect",
    "self_sandbox_persistence_error",
    "descendant_failed",
    "descendant_cancelled",
    "descendant_waiting_approval",
    "descendant_waiting_external_run",
    "descendant_waiting_input",
    "descendant_degraded",
    "descendant_sandbox_failed",
    "descendant_sandbox_workspace_side_effect",
    "descendant_sandbox_persistence_error",
]
RunInspectionHealth = Literal[
    "queued",
    "running",
    "waiting_approval",
    "waiting_subagent",
    "waiting_input",
    "waiting_external_run",
    "completed",
    "degraded",
    "failed",
    "cancelled",
]
RunInspectionAttentionReason = Literal[
    "health_degraded",
    "health_failed",
    "health_cancelled",
    "health_waiting_approval",
    "health_waiting_external_run",
    "health_waiting_input",
    "sandbox_failed",
    "sandbox_workspace_side_effect",
    "sandbox_persistence_error",
]
RunResumeKind = Literal["none", "input", "approval", "external_approval", "external_run", "subagent"]
RunExternalRunDiagnosticStatus = Literal[
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
]
RunActiveExternalRunOperatorActionKind = Literal[
    "check_provider_status",
    "redeliver_completed_callback",
    "mark_failed",
    "mark_cancelled",
]
RunActiveExternalRunOperatorActionMethod = Literal["POST"]
RunActiveExternalRunOperatorActionStatus = Literal["completed", "failed", "cancelled"]
RunSandboxOperatorActionKind = Literal[
    "inspect_sandbox_error",
    "inspect_workspace_file",
    "review_workspace_policy",
    "retry_sandbox_run",
]
RunSandboxOperatorActionMethod = Literal["GET", "POST"]

DEFAULT_EXTERNAL_RUN_STALE_AFTER_SECONDS = 1800


class RunTreeNode(AithruBaseModel):
    run_id: str
    parent_run_id: str | None = None
    depth: int = Field(ge=0)
    status: str
    source: str
    task_msg: str
    skill_id: str | None = None
    workspace_id: str
    subagent_run_id: str | None = None
    subagent_name: str | None = None
    subagent_status: str | None = None
    child_count: int = Field(default=0, ge=0)
    workspace_file_count: int = Field(default=0, ge=0)
    result_workspace_paths: list[str] = Field(default_factory=list)
    terminal: bool = False
    needs_attention: bool = False
    attention_reasons: list[RunTreeAttentionReason] = Field(default_factory=list)
    sandbox_run_count: int = Field(default=0, ge=0)
    failed_sandbox_run_count: int = Field(default=0, ge=0)
    sandbox_workspace_file_count: int = Field(default=0, ge=0)
    sandbox_persistence_error_count: int = Field(default=0, ge=0)
    sandbox_operator_action_count: int = Field(default=0, ge=0)
    research_status: ResearchSnapshotStatus = "none"
    research_degraded: bool = False
    descendant_attention_count: int = Field(default=0, ge=0)
    descendant_failed_count: int = Field(default=0, ge=0)
    descendant_cancelled_count: int = Field(default=0, ge=0)
    descendant_waiting_count: int = Field(default=0, ge=0)
    descendant_waiting_approval_count: int = Field(default=0, ge=0)
    descendant_waiting_external_run_count: int = Field(default=0, ge=0)
    descendant_waiting_input_count: int = Field(default=0, ge=0)
    descendant_degraded_count: int = Field(default=0, ge=0)
    descendant_failed_sandbox_run_count: int = Field(default=0, ge=0)
    descendant_sandbox_workspace_file_count: int = Field(default=0, ge=0)
    descendant_sandbox_persistence_error_count: int = Field(default=0, ge=0)
    descendant_sandbox_operator_action_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _attention_flag_must_match_reasons(self) -> "RunTreeNode":
        if self.needs_attention != bool(self.attention_reasons):
            raise ValueError("run tree needs_attention must match attention reasons")
        return self


class RunTreeDelegation(AithruBaseModel):
    subagent_run_id: str
    parent_run_id: str
    child_run_id: str
    name: str
    task: str
    spec_key: str | None = None
    status: str
    child_run_status: str | None = None
    result_summary: AgentSubagentResultSummary | None = None


class RunTreeSummary(AithruBaseModel):
    root_run_id: str
    total_runs: int = Field(ge=0)
    total_delegations: int = Field(ge=0)
    max_depth: int = Field(ge=0)
    active_runs: int = Field(ge=0)
    waiting_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    completed_runs: int = Field(ge=0)
    workspace_file_count: int = Field(ge=0)
    attention_runs: int = Field(ge=0)
    degraded_runs: int = Field(ge=0)
    sandbox_attention_runs: int = Field(default=0, ge=0)
    sandbox_run_count: int = Field(default=0, ge=0)
    failed_sandbox_run_count: int = Field(default=0, ge=0)
    sandbox_workspace_file_count: int = Field(default=0, ge=0)
    sandbox_persistence_error_count: int = Field(default=0, ge=0)
    sandbox_operator_action_count: int = Field(default=0, ge=0)
    root_needs_attention: bool = False


class RunTreeSnapshot(AithruBaseModel):
    root_run_id: str
    nodes: list[RunTreeNode] = Field(default_factory=list)
    delegations: list[RunTreeDelegation] = Field(default_factory=list)
    summary: RunTreeSummary


class ResearchSnapshotWebFailure(AithruBaseModel):
    tool_call_id: str
    tool_name: ResearchSnapshotWebToolName
    query: str | None = None
    url: str | None = None
    error: dict[str, Any] | None = None
    limitation: ResearchLimitation | None = None


class ResearchSnapshotTodo(AithruBaseModel):
    todo_id: str
    title: str
    status: str


class ResearchSnapshotReportFile(AithruBaseModel):
    path: str
    name: str
    uri: str | None = None
    report_status: ResearchReportStatus
    source_count: int | None = None
    evidence_count: int | None = None
    limitation_count: int | None = None
    quality_summary: dict[str, Any] | None = None


class ResearchSnapshotSummary(AithruBaseModel):
    status: ResearchSnapshotStatus = "none"
    degraded: bool = False
    failed_web_span_count: int = 0
    web_failures: list[ResearchSnapshotWebFailure] = Field(default_factory=list)
    blocked_todos: list[ResearchSnapshotTodo] = Field(default_factory=list)
    report_files: list[ResearchSnapshotReportFile] = Field(default_factory=list)
    limitations: list[ResearchLimitation] = Field(default_factory=list)


class ResearchExecutionPlanSection(AithruBaseModel):
    section_id: str
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    priority: ResearchPlanSectionPriority = "medium"


class ResearchExecutionPlan(AithruBaseModel):
    query: str | None = None
    objective: str | None = None
    sections: list[ResearchExecutionPlanSection] = Field(default_factory=list)
    source_event_sequence: int | None = Field(default=None, ge=0)


class ResearchExecutionStep(AithruBaseModel):
    phase: ResearchPlanPhase
    title: str = Field(min_length=1)
    description: str | None = None
    todo_id: str | None = None
    todo_order: int | None = Field(default=None, ge=1)
    status: ResearchExecutionStepStatus
    related_tool_names: list[str] = Field(default_factory=list)
    web_success_count: int = Field(default=0, ge=0)
    web_failure_count: int = Field(default=0, ge=0)
    report_workspace_paths: list[str] = Field(default_factory=list)
    limitation_codes: list[str] = Field(default_factory=list)
    attention: bool = False


class ResearchExecutionProgress(AithruBaseModel):
    total_steps: int = Field(ge=0)
    pending_steps: int = Field(ge=0)
    running_steps: int = Field(ge=0)
    done_steps: int = Field(ge=0)
    blocked_steps: int = Field(ge=0)
    cancelled_steps: int = Field(ge=0)
    terminal_steps: int = Field(ge=0)
    web_success_count: int = Field(ge=0)
    web_failure_count: int = Field(ge=0)
    report_file_count: int = Field(ge=0)
    limitation_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_must_match_steps(self) -> "ResearchExecutionProgress":
        counted_steps = (
            self.pending_steps
            + self.running_steps
            + self.done_steps
            + self.blocked_steps
            + self.cancelled_steps
        )
        if counted_steps != self.total_steps:
            raise ValueError("research execution step counts must equal total_steps")
        terminal_steps = self.done_steps + self.blocked_steps + self.cancelled_steps
        if terminal_steps != self.terminal_steps:
            raise ValueError("research execution terminal count must match terminal statuses")
        return self


class ResearchExecutionSnapshot(AithruBaseModel):
    run_id: str
    status: ResearchExecutionStatus
    degraded: bool = False
    plan: ResearchExecutionPlan | None = None
    steps: list[ResearchExecutionStep] = Field(default_factory=list)
    progress: ResearchExecutionProgress
    summary: ResearchSnapshotSummary


class ResearchEvidenceLedgerReportFile(AithruBaseModel):
    path: str
    name: str
    uri: str | None = None
    report_status: ResearchReportStatus
    source_count: int | None = None
    source_input_count: int | None = None
    duplicate_source_count: int | None = None
    evidence_count: int | None = None
    limitation_count: int | None = None
    section_count: int | None = None
    section_summary: list[ResearchEvidenceSectionSummary] = Field(default_factory=list)
    quality_summary: dict[str, Any] | None = None


class ResearchEvidenceLedgerCounts(AithruBaseModel):
    source_input_count: int = Field(default=0, ge=0)
    duplicate_source_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    limitation_count: int = Field(default=0, ge=0)
    section_count: int = Field(default=0, ge=0)
    missing_section_count: int = Field(default=0, ge=0)
    weak_section_count: int = Field(default=0, ge=0)
    report_file_count: int = Field(default=0, ge=0)


class ResearchEvidenceLedgerSection(AithruBaseModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str | None = None
    priority: ResearchPlanSectionPriority = "medium"
    source_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    covered: bool = False
    quality_summary: ResearchQualitySummary = Field(default_factory=ResearchQualitySummary)
    weak_quality: bool = False

    @model_validator(mode="after")
    def _covered_must_match_evidence_count(self) -> "ResearchEvidenceLedgerSection":
        if self.covered != (self.evidence_count > 0):
            raise ValueError("research ledger section coverage must match evidence count")
        expected_weak_quality = self.covered and self.quality_summary.high == 0
        if self.weak_quality != expected_weak_quality:
            raise ValueError("research ledger section weak-quality flag must match quality summary")
        return self


class ResearchEvidenceLedger(AithruBaseModel):
    run_id: str
    status: ResearchSnapshotStatus = "none"
    degraded: bool = False
    title: str | None = None
    query: str | None = None
    summary: str | None = None
    source_event_sequence: int | None = Field(default=None, ge=0)
    quality_summary: ResearchQualitySummary | None = None
    sources: list[ResearchSource] = Field(default_factory=list)
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    limitations: list[ResearchLimitation] = Field(default_factory=list)
    sections: list[ResearchEvidenceLedgerSection] = Field(default_factory=list)
    section_summary: list[ResearchEvidenceSectionSummary] = Field(default_factory=list)
    report_files: list[ResearchEvidenceLedgerReportFile] = Field(default_factory=list)
    counts: ResearchEvidenceLedgerCounts

    @model_validator(mode="after")
    def _section_counts_must_match_sections(self) -> "ResearchEvidenceLedger":
        if self.counts.section_count != len(self.sections):
            raise ValueError("research evidence ledger section count must match sections")
        missing = sum(1 for section in self.sections if not section.covered)
        if self.counts.missing_section_count != missing:
            raise ValueError("research evidence ledger missing-section count must match sections")
        weak = sum(1 for section in self.sections if section.weak_quality)
        if self.counts.weak_section_count != weak:
            raise ValueError("research evidence ledger weak-section count must match sections")
        return self


class ResearchReviewFinding(AithruBaseModel):
    code: ResearchReviewFindingCode
    severity: ResearchReviewFindingSeverity
    message: str = Field(min_length=1)


class ResearchReviewCounts(AithruBaseModel):
    source_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    limitation_count: int = Field(default=0, ge=0)
    report_file_count: int = Field(default=0, ge=0)
    blocked_step_count: int = Field(default=0, ge=0)
    web_failure_count: int = Field(default=0, ge=0)
    high_quality_source_count: int = Field(default=0, ge=0)
    low_quality_source_count: int = Field(default=0, ge=0)
    weak_section_count: int = Field(default=0, ge=0)
    finding_count: int = Field(default=0, ge=0)


class ResearchReviewSnapshot(AithruBaseModel):
    run_id: str
    status: ResearchReviewStatus
    score: int = Field(ge=0, le=100)
    ready_for_answer: bool = False
    report_status: ResearchSnapshotStatus = "none"
    reviewed_event_sequence: int | None = Field(default=None, ge=0)
    report_workspace_paths: list[str] = Field(default_factory=list)
    counts: ResearchReviewCounts
    findings: list[ResearchReviewFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _finding_count_must_match_findings(self) -> "ResearchReviewSnapshot":
        if self.counts.finding_count != len(self.findings):
            raise ValueError("research review finding count must match findings")
        return self


class ResearchContinuationAction(AithruBaseModel):
    action_id: str = Field(min_length=1)
    kind: ResearchContinuationActionKind
    priority: ResearchContinuationActionPriority
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    related_finding_codes: list[ResearchReviewFindingCode] = Field(default_factory=list)
    target_section_ids: list[str] = Field(default_factory=list)
    suggested_tool_names: list[str] = Field(default_factory=list)
    suggested_research_phases: list[ResearchPlanPhase] = Field(default_factory=list)


class ResearchContinuationCounts(AithruBaseModel):
    action_count: int = Field(default=0, ge=0)
    high_priority_action_count: int = Field(default=0, ge=0)
    suggested_tool_count: int = Field(default=0, ge=0)
    target_section_count: int = Field(default=0, ge=0)


class ResearchContinuationSnapshot(AithruBaseModel):
    run_id: str
    status: ResearchContinuationStatus
    ready_for_answer: bool = False
    review_status: ResearchReviewStatus
    report_status: ResearchSnapshotStatus = "none"
    query: str | None = None
    reviewed_event_sequence: int | None = Field(default=None, ge=0)
    actions: list[ResearchContinuationAction] = Field(default_factory=list)
    counts: ResearchContinuationCounts

    @model_validator(mode="after")
    def _counts_must_match_actions(self) -> "ResearchContinuationSnapshot":
        if self.counts.action_count != len(self.actions):
            raise ValueError("research continuation action count must match actions")
        high_priority_count = sum(1 for action in self.actions if action.priority == "high")
        if self.counts.high_priority_action_count != high_priority_count:
            raise ValueError("research continuation high-priority count must match actions")
        suggested_tools = {
            tool_name
            for action in self.actions
            for tool_name in action.suggested_tool_names
        }
        if self.counts.suggested_tool_count != len(suggested_tools):
            raise ValueError("research continuation suggested tool count must match actions")
        target_section_ids = {
            section_id
            for action in self.actions
            for section_id in action.target_section_ids
        }
        if self.counts.target_section_count != len(target_section_ids):
            raise ValueError("research continuation target section count must match actions")
        return self


class ResearchContinuationChildLink(AithruBaseModel):
    source_run_id: str
    child_run_id: str
    action_ids: list[str] = Field(default_factory=list)
    continuation_status: ResearchContinuationStatus | str | None = None
    query: str | None = None
    source_event_sequence: int = Field(ge=0)
    child_run_status: str | None = None
    child_run_task_msg: str | None = None


class ResearchContinuationSourceLink(AithruBaseModel):
    source_run_id: str
    child_run_id: str
    action_ids: list[str] = Field(default_factory=list)
    continuation_status: ResearchContinuationStatus | str | None = None
    query: str | None = None
    source_event_sequence: int = Field(ge=0)
    source_run_status: str | None = None
    source_run_task_msg: str | None = None


class ResearchContinuationLineageCounts(AithruBaseModel):
    source_count: int = Field(default=0, ge=0)
    child_count: int = Field(default=0, ge=0)


class ResearchContinuationLineageSnapshot(AithruBaseModel):
    run_id: str
    source: ResearchContinuationSourceLink | None = None
    children: list[ResearchContinuationChildLink] = Field(default_factory=list)
    counts: ResearchContinuationLineageCounts

    @model_validator(mode="after")
    def _counts_must_match_links(self) -> "ResearchContinuationLineageSnapshot":
        if self.counts.source_count != int(self.source is not None):
            raise ValueError("research continuation source count must match source link")
        if self.counts.child_count != len(self.children):
            raise ValueError("research continuation child count must match child links")
        return self


class RunExternalRunDiagnostic(AithruBaseModel):
    kind: str
    capability_key: str | None = Field(default=None, exclude_if=lambda value: value is None)
    capability_run_id: str
    tool_call_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    tool_name: str | None = Field(default=None, exclude_if=lambda value: value is None)
    status: RunExternalRunDiagnosticStatus
    source_event_sequence: int = Field(ge=0)
    correlation_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    approval_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    error: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)
    output_summary: str | None = Field(default=None, exclude_if=lambda value: value is None)
    comment: str | None = Field(default=None, exclude_if=lambda value: value is None)


class RunActiveExternalRunOperatorAction(AithruBaseModel):
    kind: RunActiveExternalRunOperatorActionKind
    label: str
    reason: str
    method: RunActiveExternalRunOperatorActionMethod | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    path: str | None = Field(default=None, exclude_if=lambda value: value is None)
    status: RunActiveExternalRunOperatorActionStatus | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class RunActiveExternalRunDiagnostic(AithruBaseModel):
    kind: str
    capability_key: str
    capability_run_id: str
    tool_call_id: str
    tool_name: str
    status: Literal["running"] = "running"
    source_event_sequence: int | None = Field(
        default=None,
        ge=0,
        exclude_if=lambda value: value is None,
    )
    correlation_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    waited_seconds: int = Field(ge=0)
    stale_after_seconds: int = Field(ge=1)
    stale: bool
    operator_actions: list[RunActiveExternalRunOperatorAction] = Field(default_factory=list)


class RunSandboxOperatorAction(AithruBaseModel):
    kind: RunSandboxOperatorActionKind
    label: str
    reason: str
    method: RunSandboxOperatorActionMethod | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    path: str | None = Field(default=None, exclude_if=lambda value: value is None)
    workspace_path: str | None = Field(default=None, exclude_if=lambda value: value is None)


class RunSandboxDiagnostic(AithruBaseModel):
    sandbox_run_id: str = Field(min_length=1)
    status: SandboxExecutionStatus
    source_event_sequence: int = Field(ge=0)
    language: Literal["python"] = "python"
    execution: SandboxExecutionSummary
    workspace_effects: SandboxWorkspaceEffectsSummary = Field(
        default_factory=SandboxWorkspaceEffectsSummary
    )
    error_code: str | None = None
    timed_out: bool = False
    error: dict[str, str] | None = Field(default=None, exclude_if=lambda value: value is None)
    operator_actions: list[RunSandboxOperatorAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def _matches_execution_summary(self) -> "RunSandboxDiagnostic":
        if self.language != self.execution.language:
            raise ValueError("sandbox diagnostic language must match execution language")
        if self.error_code != self.execution.error_code:
            raise ValueError("sandbox diagnostic error_code must match execution error_code")
        if self.timed_out != self.execution.timed_out:
            raise ValueError("sandbox diagnostic timed_out must match execution timed_out")
        if self.status == "completed" and self.error is not None:
            raise ValueError("completed sandbox diagnostics cannot carry error details")
        return self


class RunInspectionSummary(AithruBaseModel):
    health: RunInspectionHealth
    needs_attention: bool
    attention_reasons: list[RunInspectionAttentionReason] = Field(default_factory=list)
    event_count: int
    todo_count: int
    blocked_todo_count: int
    workspace_file_count: int
    approval_count: int
    failed_trace_count: int
    research_status: ResearchSnapshotStatus
    research_degraded: bool
    last_event_type: str | None = None
    external_runs: list[RunExternalRunDiagnostic] = Field(default_factory=list)
    external_run_count: int = Field(default=0, ge=0)
    failed_external_run_count: int = Field(default=0, ge=0)
    cancelled_external_run_count: int = Field(default=0, ge=0)
    active_external_run: RunActiveExternalRunDiagnostic | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    external_run_stale: bool = Field(default=False, exclude_if=lambda value: value is False)
    sandbox_runs: list[RunSandboxDiagnostic] = Field(default_factory=list)
    sandbox_run_count: int = Field(default=0, ge=0)
    failed_sandbox_run_count: int = Field(default=0, ge=0)
    sandbox_workspace_file_count: int = Field(default=0, ge=0)
    sandbox_persistence_error_count: int = Field(default=0, ge=0)
    sandbox_operator_actions: list[RunSandboxOperatorAction] = Field(default_factory=list)
    sandbox_operator_action_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _diagnostic_counts_must_match_runs(self) -> "RunInspectionSummary":
        if self.needs_attention != bool(self.attention_reasons):
            raise ValueError("needs_attention must match attention reasons")
        if len(self.attention_reasons) != len(set(self.attention_reasons)):
            raise ValueError("attention reasons must be unique")
        if self.external_run_count != len(self.external_runs):
            raise ValueError("external run count must match external runs")
        failed = sum(1 for run in self.external_runs if run.status == "failed")
        if self.failed_external_run_count != failed:
            raise ValueError("failed external run count must match external runs")
        cancelled = sum(1 for run in self.external_runs if run.status == "cancelled")
        if self.cancelled_external_run_count != cancelled:
            raise ValueError("cancelled external run count must match external runs")
        if self.active_external_run is None and self.external_run_stale:
            raise ValueError("external run stale requires an active external run")
        if (
            self.active_external_run is not None
            and self.external_run_stale != self.active_external_run.stale
        ):
            raise ValueError("external run stale must match active external run")
        if self.sandbox_run_count != len(self.sandbox_runs):
            raise ValueError("sandbox run count must match sandbox runs")
        failed_sandbox_runs = sum(1 for run in self.sandbox_runs if run.status == "failed")
        if self.failed_sandbox_run_count != failed_sandbox_runs:
            raise ValueError("failed sandbox run count must match sandbox runs")
        workspace_file_count = sum(
            run.workspace_effects.persisted_count for run in self.sandbox_runs
        )
        if self.sandbox_workspace_file_count != workspace_file_count:
            raise ValueError("sandbox workspace file count must match sandbox runs")
        persistence_error_count = sum(
            1 for run in self.sandbox_runs if run.workspace_effects.persistence_error is not None
        )
        if self.sandbox_persistence_error_count != persistence_error_count:
            raise ValueError("sandbox persistence error count must match sandbox runs")
        expected_actions = [
            action
            for sandbox_run in self.sandbox_runs
            for action in sandbox_run.operator_actions
        ]
        if self.sandbox_operator_actions != expected_actions:
            raise ValueError("sandbox operator actions must match sandbox runs")
        if self.sandbox_operator_action_count != len(expected_actions):
            raise ValueError("sandbox operator action count must match sandbox actions")
        return self


class OperatorFollowUpChildLink(AithruBaseModel):
    source_run_id: str
    child_run_id: str
    operator_follow_up: AgentRunOperatorFollowUpOptions
    source_event_sequence: int = Field(ge=0)
    child_run_status: str | None = None
    child_run_task_msg: str | None = None


class OperatorFollowUpSourceLink(AithruBaseModel):
    source_run_id: str
    child_run_id: str
    operator_follow_up: AgentRunOperatorFollowUpOptions
    source_event_sequence: int = Field(ge=0)
    source_run_status: str | None = None
    source_run_task_msg: str | None = None


class OperatorFollowUpLineageCounts(AithruBaseModel):
    source_count: int = Field(default=0, ge=0)
    child_count: int = Field(default=0, ge=0)


class OperatorFollowUpLineageSnapshot(AithruBaseModel):
    run_id: str
    source: OperatorFollowUpSourceLink | None = None
    children: list[OperatorFollowUpChildLink] = Field(default_factory=list)
    counts: OperatorFollowUpLineageCounts

    @model_validator(mode="after")
    def _counts_must_match_links(self) -> "OperatorFollowUpLineageSnapshot":
        if self.counts.source_count != int(self.source is not None):
            raise ValueError("operator follow-up source count must match source link")
        if self.counts.child_count != len(self.children):
            raise ValueError("operator follow-up child count must match child links")
        return self


class RunResumeSnapshot(AithruBaseModel):
    kind: RunResumeKind = "none"
    run_status: str
    resumable: bool = False
    reason: str | None = None
    paused_event_sequence: int | None = None
    resumed_event_sequence: int | None = None
    approval_id: str | None = None
    approval_status: str | None = None
    external_approval_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    external_capability_key: str | None = Field(default=None, exclude_if=lambda value: value is None)
    external_capability_run_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    external_run_status: str | None = Field(default=None, exclude_if=lambda value: value is None)
    tool_call_id: str | None = None
    tool_name: str | None = None
    has_persisted_message_history: bool = False
    input_request_id: str | None = None
    input_prompt: str | None = None
    input_received: bool = False
    input_message_id: str | None = None
    subagent_run_id: str | None = None
    child_run_id: str | None = None
    subagent_status: str | None = None
    audit_event_types: list[str] = Field(default_factory=list)


class RunSnapshotResponse(AithruBaseModel):
    run: AgentRun
    summary: RunInspectionSummary
    events: list[AgentStreamEvent] = Field(default_factory=list)
    trace: list[AgentTraceSpan] = Field(default_factory=list)
    todos: list[AgentTodo] = Field(default_factory=list)
    approvals: list[AgentApproval] = Field(default_factory=list)
    workspace_files: list[AgentWorkspaceFile] = Field(default_factory=list)
    research: ResearchSnapshotSummary
    research_execution: ResearchExecutionSnapshot
    research_evidence: ResearchEvidenceLedger
    research_review: ResearchReviewSnapshot
    research_continuation: ResearchContinuationSnapshot
    research_lineage: ResearchContinuationLineageSnapshot
    operator_follow_up_lineage: OperatorFollowUpLineageSnapshot
    resume: RunResumeSnapshot
    subagents: list[AgentSubagentRun] = Field(default_factory=list)
    presentations: list[AgentPresentation] = Field(default_factory=list)


def build_run_tree_snapshot(
    *,
    root_run: AgentRun,
    runs: list[AgentRun],
    subagents: list[AgentSubagentRun],
    workspace_files: list[AgentWorkspaceFile],
    events_by_run: dict[str, list[AgentStreamEvent]] | None = None,
    todos_by_run: dict[str, list[AgentTodo]] | None = None,
    trace_by_run: dict[str, list[AgentTraceSpan]] | None = None,
) -> RunTreeSnapshot:
    runs_by_id = {run.id: run for run in runs}
    subagents_by_parent: dict[str, list[AgentSubagentRun]] = {}
    for subagent in subagents:
        subagents_by_parent.setdefault(subagent.parent_run_id, []).append(subagent)
    for parent_id in subagents_by_parent:
        subagents_by_parent[parent_id].sort(key=lambda item: item.id)

    workspace_files_by_workspace: dict[str, list[AgentWorkspaceFile]] = {}
    for workspace_file in workspace_files:
        workspace_files_by_workspace.setdefault(workspace_file.workspace_id, []).append(workspace_file)

    nodes: list[RunTreeNode] = []
    delegations: list[RunTreeDelegation] = []
    visited: set[str] = set()
    queue: list[tuple[AgentRun, int, AgentSubagentRun | None]] = [(root_run, 0, None)]

    while queue:
        run, depth, inbound = queue.pop(0)
        if run.id in visited:
            continue
        visited.add(run.id)
        children = [
            subagent
            for subagent in subagents_by_parent.get(run.id, [])
            if subagent.child_run_id in runs_by_id
        ]
        nodes.append(
            _run_tree_node(
                run,
                depth=depth,
                inbound=inbound,
                child_count=len(children),
                workspace_file_count=len(workspace_files_by_workspace.get(run.workspace_id, [])),
                events=(events_by_run or {}).get(run.id, []),
                research=build_research_snapshot_summary(
                    events=(events_by_run or {}).get(run.id, []),
                    todos=(todos_by_run or {}).get(run.id, []),
                    workspace_files=workspace_files_by_workspace.get(run.workspace_id, []),
                    trace=(trace_by_run or {}).get(run.id, []),
                ),
            )
        )
        for subagent in children:
            child = runs_by_id[subagent.child_run_id]
            delegations.append(_run_tree_delegation(subagent, child))
            queue.append((child, depth + 1, subagent))

    _roll_up_run_tree_attention(nodes)
    summary = _run_tree_summary(
        root_run_id=root_run.id,
        nodes=nodes,
        delegations=delegations,
    )
    return RunTreeSnapshot(
        root_run_id=root_run.id,
        nodes=nodes,
        delegations=delegations,
        summary=summary,
    )


def build_run_resume_snapshot(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    approvals: list[AgentApproval],
    subagents: list[AgentSubagentRun],
) -> RunResumeSnapshot:
    run_status = _status_value(run.status)
    pause_event = _latest_pause_event(events)
    if pause_event is None:
        return RunResumeSnapshot(run_status=run_status)

    payload = _dict_value(pause_event.payload)
    pause_status = _string_value(payload.get("status"))
    kind = _resume_kind_for_status(pause_status, payload)
    if kind == "none":
        return RunResumeSnapshot(run_status=run_status)

    resumed_event = _first_event_after(events, pause_event.sequence, "run.resumed")
    audit_events = _resume_audit_events(events, pause_event.sequence)
    base = {
        "kind": kind,
        "run_status": run_status,
        "resumable": run_status == pause_status,
        "reason": _resume_reason(kind, payload),
        "paused_event_sequence": pause_event.sequence,
        "resumed_event_sequence": resumed_event.sequence if resumed_event else None,
        "tool_call_id": _string_value(payload.get("tool_call_id")),
        "tool_name": _string_value(payload.get("tool_name")),
        "audit_event_types": [event.type for event in audit_events],
    }
    if kind == "input":
        received = _first_event_after(events, pause_event.sequence, "input.received")
        received_payload = _dict_value(received.payload) if received else {}
        return RunResumeSnapshot(
            **base,
            input_request_id=_string_value(payload.get("input_request_id")),
            input_prompt=_string_value(payload.get("prompt")),
            input_received=received is not None,
            input_message_id=_string_value(received_payload.get("message_id")),
        )
    if kind == "approval":
        approval_id = _string_value(payload.get("approval_id"))
        approval = _approval_by_id(approvals, approval_id)
        return RunResumeSnapshot(
            **base,
            approval_id=approval_id,
            approval_status=_status_value(approval.status) if approval else None,
            has_persisted_message_history=_approval_has_pydantic_history(approval),
        )
    if kind == "external_approval":
        external = _dict_value(payload.get("current_external_approval"))
        return RunResumeSnapshot(
            **{
                **base,
                "tool_call_id": _string_value(external.get("tool_call_id")) or base["tool_call_id"],
                "tool_name": _string_value(external.get("tool_name")) or base["tool_name"],
            },
            approval_id=_string_value(external.get("approval_id")),
            external_approval_id=_string_value(external.get("approval_id")),
            external_capability_key=_string_value(external.get("capability_key")),
            external_capability_run_id=_string_value(external.get("capability_run_id")),
        )
    if kind == "external_run":
        external = _dict_value(payload.get("current_external_run"))
        return RunResumeSnapshot(
            **{
                **base,
                "tool_call_id": _string_value(external.get("tool_call_id")) or base["tool_call_id"],
                "tool_name": _string_value(external.get("tool_name")) or base["tool_name"],
            },
            external_capability_key=_string_value(external.get("capability_key")),
            external_capability_run_id=_string_value(external.get("capability_run_id")),
            external_run_status=_string_value(external.get("status")),
        )
    subagent_run_id = _string_value(payload.get("subagent_run_id"))
    subagent = _subagent_by_id(subagents, subagent_run_id)
    return RunResumeSnapshot(
        **base,
        subagent_run_id=subagent_run_id,
        child_run_id=_string_value(payload.get("child_run_id")),
        subagent_status=_status_value(subagent.status) if subagent else None,
    )


def _run_tree_node(
    run: AgentRun,
    *,
    depth: int,
    inbound: AgentSubagentRun | None,
    child_count: int,
    workspace_file_count: int,
    events: list[AgentStreamEvent],
    research: ResearchSnapshotSummary,
) -> RunTreeNode:
    status = _status_value(run.status)
    sandbox_runs = _sandbox_run_diagnostics(
        events,
        run_id=run.id,
        workspace_id=run.workspace_id,
    )
    failed_sandbox_run_count = sum(1 for item in sandbox_runs if item.status == "failed")
    sandbox_workspace_file_count = sum(
        item.workspace_effects.persisted_count for item in sandbox_runs
    )
    sandbox_persistence_error_count = sum(
        1
        for item in sandbox_runs
        if item.workspace_effects.persistence_error is not None
    )
    sandbox_operator_action_count = sum(len(item.operator_actions) for item in sandbox_runs)
    attention_reasons = _local_run_tree_attention_reasons(
        status,
        research,
        failed_sandbox_run_count=failed_sandbox_run_count,
        sandbox_workspace_file_count=sandbox_workspace_file_count,
        sandbox_persistence_error_count=sandbox_persistence_error_count,
    )
    return RunTreeNode(
        run_id=run.id,
        parent_run_id=inbound.parent_run_id if inbound else None,
        depth=depth,
        status=status,
        source=_status_value(run.source),
        task_msg=run.task_msg,
        skill_id=run.skill_id,
        workspace_id=run.workspace_id,
        subagent_run_id=inbound.id if inbound else None,
        subagent_name=inbound.name if inbound else None,
        subagent_status=_status_value(inbound.status) if inbound else None,
        child_count=child_count,
        workspace_file_count=workspace_file_count,
        result_workspace_paths=list(run.result.workspace_paths) if run.result else [],
        terminal=status in {"completed", "failed", "cancelled"},
        needs_attention=bool(attention_reasons),
        attention_reasons=attention_reasons,
        sandbox_run_count=len(sandbox_runs),
        failed_sandbox_run_count=failed_sandbox_run_count,
        sandbox_workspace_file_count=sandbox_workspace_file_count,
        sandbox_persistence_error_count=sandbox_persistence_error_count,
        sandbox_operator_action_count=sandbox_operator_action_count,
        research_status=research.status,
        research_degraded=research.degraded,
    )


def _local_run_tree_attention_reasons(
    status: str,
    research: ResearchSnapshotSummary,
    *,
    failed_sandbox_run_count: int,
    sandbox_workspace_file_count: int,
    sandbox_persistence_error_count: int,
) -> list[RunTreeAttentionReason]:
    reasons: list[RunTreeAttentionReason] = []
    if status == "failed":
        reasons.append("self_failed")
    elif status == "cancelled":
        reasons.append("self_cancelled")
    elif status == "waiting_approval":
        reasons.append("self_waiting_approval")
    elif status == "waiting_external_run":
        reasons.append("self_waiting_external_run")
    elif status == "waiting_input":
        reasons.append("self_waiting_input")
    if research.degraded:
        reasons.append("self_degraded")
    reasons.extend(
        _self_sandbox_run_tree_attention_reasons(
            failed_sandbox_run_count=failed_sandbox_run_count,
            sandbox_workspace_file_count=sandbox_workspace_file_count,
            sandbox_persistence_error_count=sandbox_persistence_error_count,
        )
    )
    return reasons


def _self_sandbox_run_tree_attention_reasons(
    *,
    failed_sandbox_run_count: int,
    sandbox_workspace_file_count: int,
    sandbox_persistence_error_count: int,
) -> list[RunTreeAttentionReason]:
    reasons: list[RunTreeAttentionReason] = []
    if failed_sandbox_run_count:
        reasons.append("self_sandbox_failed")
    if sandbox_workspace_file_count:
        reasons.append("self_sandbox_workspace_side_effect")
    if sandbox_persistence_error_count:
        reasons.append("self_sandbox_persistence_error")
    return reasons


def _roll_up_run_tree_attention(nodes: list[RunTreeNode]) -> None:
    children_by_parent: dict[str, list[RunTreeNode]] = {}
    for node in nodes:
        if node.parent_run_id is not None:
            children_by_parent.setdefault(node.parent_run_id, []).append(node)

    for node in sorted(nodes, key=lambda item: item.depth, reverse=True):
        for child in children_by_parent.get(node.run_id, []):
            node.descendant_attention_count += child.descendant_attention_count
            if child.needs_attention:
                node.descendant_attention_count += 1

            node.descendant_failed_count += child.descendant_failed_count
            if child.status == "failed":
                node.descendant_failed_count += 1

            node.descendant_cancelled_count += child.descendant_cancelled_count
            if child.status == "cancelled":
                node.descendant_cancelled_count += 1

            node.descendant_waiting_count += child.descendant_waiting_count
            node.descendant_waiting_approval_count += child.descendant_waiting_approval_count
            if child.status == "waiting_approval":
                node.descendant_waiting_count += 1
                node.descendant_waiting_approval_count += 1
            node.descendant_waiting_external_run_count += child.descendant_waiting_external_run_count
            if child.status == "waiting_external_run":
                node.descendant_waiting_count += 1
                node.descendant_waiting_external_run_count += 1
            node.descendant_waiting_input_count += child.descendant_waiting_input_count
            if child.status == "waiting_input":
                node.descendant_waiting_count += 1
                node.descendant_waiting_input_count += 1

            node.descendant_degraded_count += child.descendant_degraded_count
            if child.research_degraded:
                node.descendant_degraded_count += 1

            node.descendant_failed_sandbox_run_count += (
                child.descendant_failed_sandbox_run_count
                + child.failed_sandbox_run_count
            )
            node.descendant_sandbox_workspace_file_count += (
                child.descendant_sandbox_workspace_file_count
                + child.sandbox_workspace_file_count
            )
            node.descendant_sandbox_persistence_error_count += (
                child.descendant_sandbox_persistence_error_count
                + child.sandbox_persistence_error_count
            )
            node.descendant_sandbox_operator_action_count += (
                child.descendant_sandbox_operator_action_count
                + child.sandbox_operator_action_count
            )

        descendant_reasons = _descendant_run_tree_attention_reasons(node)
        if descendant_reasons:
            node.attention_reasons = _unique_run_tree_attention_reasons(
                [*node.attention_reasons, *descendant_reasons]
            )
            node.needs_attention = True


def _descendant_run_tree_attention_reasons(node: RunTreeNode) -> list[RunTreeAttentionReason]:
    reasons: list[RunTreeAttentionReason] = []
    if node.descendant_failed_count:
        reasons.append("descendant_failed")
    if node.descendant_cancelled_count:
        reasons.append("descendant_cancelled")
    if node.descendant_waiting_approval_count:
        reasons.append("descendant_waiting_approval")
    if node.descendant_waiting_external_run_count:
        reasons.append("descendant_waiting_external_run")
    if node.descendant_waiting_input_count:
        reasons.append("descendant_waiting_input")
    if node.descendant_degraded_count:
        reasons.append("descendant_degraded")
    if node.descendant_failed_sandbox_run_count:
        reasons.append("descendant_sandbox_failed")
    if node.descendant_sandbox_workspace_file_count:
        reasons.append("descendant_sandbox_workspace_side_effect")
    if node.descendant_sandbox_persistence_error_count:
        reasons.append("descendant_sandbox_persistence_error")
    return reasons


def _unique_run_tree_attention_reasons(
    reasons: list[RunTreeAttentionReason],
) -> list[RunTreeAttentionReason]:
    ordered: list[RunTreeAttentionReason] = []
    seen: set[RunTreeAttentionReason] = set()
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        ordered.append(reason)
    return ordered


def _run_tree_delegation(
    subagent: AgentSubagentRun,
    child: AgentRun,
) -> RunTreeDelegation:
    return RunTreeDelegation(
        subagent_run_id=subagent.id,
        parent_run_id=subagent.parent_run_id,
        child_run_id=subagent.child_run_id,
        name=subagent.name,
        task=subagent.task,
        spec_key=subagent.spec_key,
        status=_status_value(subagent.status),
        child_run_status=_status_value(child.status),
        result_summary=subagent.result_summary,
    )


def _run_tree_summary(
    *,
    root_run_id: str,
    nodes: list[RunTreeNode],
    delegations: list[RunTreeDelegation],
) -> RunTreeSummary:
    statuses = [node.status for node in nodes]
    root_node = next((node for node in nodes if node.run_id == root_run_id), None)
    sandbox_attention_runs = sum(
        1
        for node in nodes
        if node.failed_sandbox_run_count
        or node.sandbox_workspace_file_count
        or node.sandbox_persistence_error_count
    )
    return RunTreeSummary(
        root_run_id=root_run_id,
        total_runs=len(nodes),
        total_delegations=len(delegations),
        max_depth=max((node.depth for node in nodes), default=0),
        active_runs=sum(1 for status in statuses if status in {"queued", "running", "waiting_subagent"}),
        waiting_runs=sum(1 for status in statuses if status.startswith("waiting_")),
        failed_runs=sum(1 for status in statuses if status == "failed"),
        completed_runs=sum(1 for status in statuses if status == "completed"),
        workspace_file_count=sum(node.workspace_file_count for node in nodes),
        attention_runs=sum(1 for node in nodes if node.needs_attention),
        degraded_runs=sum(1 for node in nodes if node.research_degraded),
        sandbox_attention_runs=sandbox_attention_runs,
        sandbox_run_count=sum(node.sandbox_run_count for node in nodes),
        failed_sandbox_run_count=sum(node.failed_sandbox_run_count for node in nodes),
        sandbox_workspace_file_count=sum(
            node.sandbox_workspace_file_count for node in nodes
        ),
        sandbox_persistence_error_count=sum(
            node.sandbox_persistence_error_count for node in nodes
        ),
        sandbox_operator_action_count=sum(
            node.sandbox_operator_action_count for node in nodes
        ),
        root_needs_attention=bool(root_node and root_node.needs_attention),
    )


def build_run_inspection_summary(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    todos: list[AgentTodo],
    workspace_files: list[AgentWorkspaceFile],
    approvals: list[AgentApproval],
    trace: list[AgentTraceSpan],
    reference_time: str | None = None,
    external_run_stale_after_seconds: int = DEFAULT_EXTERNAL_RUN_STALE_AFTER_SECONDS,
) -> RunInspectionSummary:
    research = build_research_snapshot_summary(
        events=events,
        todos=todos,
        workspace_files=workspace_files,
        trace=trace,
    )
    health = _run_health(run, research)
    external_runs = _external_run_diagnostics(events)
    sandbox_runs = _sandbox_run_diagnostics(
        events,
        run_id=run.id,
        workspace_id=run.workspace_id,
    )
    failed_sandbox_run_count = sum(1 for item in sandbox_runs if item.status == "failed")
    sandbox_workspace_file_count = sum(
        item.workspace_effects.persisted_count for item in sandbox_runs
    )
    sandbox_persistence_error_count = sum(
        1
        for item in sandbox_runs
        if item.workspace_effects.persistence_error is not None
    )
    sandbox_operator_actions = _sandbox_operator_actions_from_runs(sandbox_runs)
    attention_reasons = _run_inspection_attention_reasons(
        health=health,
        failed_sandbox_run_count=failed_sandbox_run_count,
        sandbox_workspace_file_count=sandbox_workspace_file_count,
        sandbox_persistence_error_count=sandbox_persistence_error_count,
    )
    active_external_run = _active_external_run_diagnostic(
        run,
        events,
        reference_time=reference_time,
        stale_after_seconds=external_run_stale_after_seconds,
    )
    return RunInspectionSummary(
        health=health,
        needs_attention=bool(attention_reasons),
        attention_reasons=attention_reasons,
        event_count=len(events),
        todo_count=len(todos),
        blocked_todo_count=sum(1 for todo in todos if _todo_status(todo) == "blocked"),
        workspace_file_count=len(workspace_files),
        approval_count=len(approvals),
        failed_trace_count=sum(1 for span in trace if span.status == "failed"),
        research_status=research.status,
        research_degraded=research.degraded,
        last_event_type=events[-1].type if events else None,
        external_runs=external_runs,
        external_run_count=len(external_runs),
        failed_external_run_count=sum(1 for item in external_runs if item.status == "failed"),
        cancelled_external_run_count=sum(1 for item in external_runs if item.status == "cancelled"),
        active_external_run=active_external_run,
        external_run_stale=active_external_run.stale if active_external_run else False,
        sandbox_runs=sandbox_runs,
        sandbox_run_count=len(sandbox_runs),
        failed_sandbox_run_count=failed_sandbox_run_count,
        sandbox_workspace_file_count=sandbox_workspace_file_count,
        sandbox_persistence_error_count=sandbox_persistence_error_count,
        sandbox_operator_actions=sandbox_operator_actions,
        sandbox_operator_action_count=len(sandbox_operator_actions),
    )


def _sandbox_operator_actions_from_runs(
    sandbox_runs: list[RunSandboxDiagnostic],
) -> list[RunSandboxOperatorAction]:
    return [
        action
        for sandbox_run in sandbox_runs
        for action in sandbox_run.operator_actions
    ]


def _run_inspection_attention_reasons(
    *,
    health: RunInspectionHealth,
    failed_sandbox_run_count: int,
    sandbox_workspace_file_count: int,
    sandbox_persistence_error_count: int,
) -> list[RunInspectionAttentionReason]:
    reasons: list[RunInspectionAttentionReason] = []
    health_reason: dict[RunInspectionHealth, RunInspectionAttentionReason] = {
        "degraded": "health_degraded",
        "failed": "health_failed",
        "cancelled": "health_cancelled",
        "waiting_approval": "health_waiting_approval",
        "waiting_external_run": "health_waiting_external_run",
        "waiting_input": "health_waiting_input",
    }
    reason = health_reason.get(health)
    if reason is not None:
        reasons.append(reason)
    if failed_sandbox_run_count:
        reasons.append("sandbox_failed")
    if sandbox_workspace_file_count:
        reasons.append("sandbox_workspace_side_effect")
    if sandbox_persistence_error_count:
        reasons.append("sandbox_persistence_error")
    return reasons


def build_research_snapshot_summary(
    *,
    events: list[AgentStreamEvent],
    todos: list[AgentTodo],
    workspace_files: list[AgentWorkspaceFile],
    trace: list[AgentTraceSpan],
) -> ResearchSnapshotSummary:
    """Build a research-specific run summary from already persisted run facts."""
    web_failures = _web_failures_from_events(events)
    blocked_todos = _blocked_research_todos(todos)
    report_files = _research_report_files(events, workspace_files)
    limitations = _research_limitations(events, web_failures)
    status = _research_status(report_files)

    return ResearchSnapshotSummary(
        status=status,
        degraded=(
            status in {"partial", "insufficient_evidence"}
            or bool(web_failures)
            or bool(blocked_todos)
            or bool(limitations)
        ),
        failed_web_span_count=sum(
            1
            for span in trace
            if span.kind == "web" and span.status == "failed"
        ),
        web_failures=web_failures,
        blocked_todos=blocked_todos,
        report_files=report_files,
        limitations=limitations,
    )


def _external_run_diagnostics(events: list[AgentStreamEvent]) -> list[RunExternalRunDiagnostic]:
    by_run_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        if event.type not in {
            "external_run.created",
            "external_run.completed",
            "external_run.failed",
            "external_run.cancelled",
        }:
            continue
        payload = _dict_value(event.payload)
        capability_run_id = _string_value(payload.get("capability_run_id")) or f"external_run_{event.sequence}"
        if capability_run_id not in by_run_id:
            order.append(capability_run_id)
            by_run_id[capability_run_id] = {
                "kind": _string_value(payload.get("kind")) or "workflow_capability",
                "capability_run_id": capability_run_id,
                "status": _external_run_status(event.type, payload),
                "source_event_sequence": event.sequence,
            }
        current = by_run_id[capability_run_id]
        current["status"] = _external_run_status(event.type, payload)
        current["source_event_sequence"] = event.sequence
        _copy_nonblank(payload, current, "kind")
        _copy_nonblank(payload, current, "capability_key")
        _copy_nonblank(payload, current, "tool_call_id")
        _copy_nonblank(payload, current, "tool_name")
        _copy_nonblank(payload, current, "correlation_id")
        _copy_nonblank(payload, current, "approval_id")
        _copy_nonblank(payload, current, "comment")
        error = _dict_value_or_none(payload.get("error"))
        if error is not None:
            current["error"] = error
        output_summary = _external_run_output_summary(payload.get("output"))
        if output_summary is not None:
            current["output_summary"] = output_summary
    return [RunExternalRunDiagnostic.model_validate(by_run_id[run_id]) for run_id in order]


def _sandbox_run_diagnostics(
    events: list[AgentStreamEvent],
    *,
    run_id: str | None = None,
    workspace_id: str | None = None,
) -> list[RunSandboxDiagnostic]:
    diagnostics: list[RunSandboxDiagnostic] = []
    for event in events:
        if event.type not in {"sandbox.completed", "sandbox.failed"}:
            continue
        payload = _dict_value(event.payload)
        raw_diagnostics = _dict_value(payload.get("diagnostics"))
        if not raw_diagnostics:
            continue
        try:
            sandbox = SandboxRunDiagnostics.model_validate(raw_diagnostics)
        except ValueError:
            continue
        diagnostics.append(
            RunSandboxDiagnostic(
                sandbox_run_id=sandbox.sandbox_run_id,
                status=sandbox.status,
                source_event_sequence=event.sequence,
                language=sandbox.language,
                execution=sandbox.execution,
                workspace_effects=sandbox.workspace_effects,
                error_code=sandbox.error_code,
                timed_out=sandbox.timed_out,
                error=_sandbox_error(payload.get("error")),
                operator_actions=_sandbox_operator_actions(
                    sandbox=sandbox,
                    error=_sandbox_error(payload.get("error")),
                    run_id=run_id,
                    workspace_id=workspace_id,
                ),
            )
        )
    return diagnostics


def _sandbox_operator_actions(
    *,
    sandbox: SandboxRunDiagnostics,
    error: dict[str, str] | None,
    run_id: str | None,
    workspace_id: str | None,
) -> list[RunSandboxOperatorAction]:
    actions: list[RunSandboxOperatorAction] = []
    summary_path = f"/api/runs/{run_id}/summary" if run_id else None
    if sandbox.status == "failed":
        actions.append(
            RunSandboxOperatorAction(
                kind="inspect_sandbox_error",
                label="Inspect sandbox error",
                reason=_sandbox_error_action_reason(sandbox, error),
                method="GET" if summary_path else None,
                path=summary_path,
            )
        )
    for workspace_path in sandbox.workspace_effects.paths:
        actions.append(
            RunSandboxOperatorAction(
                kind="inspect_workspace_file",
                label="Inspect workspace file",
                reason=f"Review sandbox output file {workspace_path}.",
                method="GET" if workspace_id else None,
                path=_workspace_file_api_path(workspace_id, workspace_path),
                workspace_path=workspace_path,
            )
        )
    if sandbox.workspace_effects.persistence_error is not None:
        actions.append(
            RunSandboxOperatorAction(
                kind="review_workspace_policy",
                label="Review workspace policy",
                reason="A declared sandbox workspace output could not be persisted.",
            )
        )
    if sandbox.status == "failed":
        actions.append(
            RunSandboxOperatorAction(
                kind="retry_sandbox_run",
                label="Retry sandbox run",
                reason="Create an explicit follow-up Agent Run after adjusting sandbox inputs.",
                method="POST",
                path="/api/runs",
            )
        )
    return actions


def _sandbox_error_action_reason(
    sandbox: SandboxRunDiagnostics,
    error: dict[str, str] | None,
) -> str:
    message = error.get("message") if error else None
    if message:
        return f"Inspect sandbox failure: {message}"
    if sandbox.error_code:
        return f"Inspect sandbox failure code {sandbox.error_code}."
    return "Inspect sandbox failure details."


def _workspace_file_api_path(workspace_id: str | None, workspace_path: str) -> str | None:
    if workspace_id is None:
        return None
    path_suffix = quote(workspace_path.lstrip("/"), safe="/")
    return f"/api/workspaces/{quote(workspace_id, safe='')}/files/{path_suffix}"


def _sandbox_error(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    error = {
        str(key): str(error_value)
        for key, error_value in value.items()
        if isinstance(key, str) and error_value is not None
    }
    return error or None


def _active_external_run_diagnostic(
    run: AgentRun,
    events: list[AgentStreamEvent],
    *,
    reference_time: str | None,
    stale_after_seconds: int,
) -> RunActiveExternalRunDiagnostic | None:
    external = run.current_external_run
    if str(run.status) != "waiting_external_run" or external is None:
        return None
    source_event = _active_external_run_source_event(events, external.capability_run_id)
    started_at = (
        _parse_timestamp(source_event.timestamp)
        if source_event is not None
        else _parse_timestamp(run.started_at)
    )
    reference = _parse_timestamp(reference_time) if reference_time else datetime.now(UTC)
    waited_seconds = max(0, int((reference - started_at).total_seconds()))
    stale = waited_seconds > stale_after_seconds
    return RunActiveExternalRunDiagnostic(
        kind=external.kind,
        capability_key=external.capability_key,
        capability_run_id=external.capability_run_id,
        tool_call_id=external.tool_call_id,
        tool_name=external.tool_name,
        status=external.status,
        source_event_sequence=source_event.sequence if source_event else None,
        correlation_id=external.correlation_id,
        waited_seconds=waited_seconds,
        stale_after_seconds=stale_after_seconds,
        stale=stale,
        operator_actions=_active_external_run_operator_actions(
            run_id=run.id,
            capability_run_id=external.capability_run_id,
            stale=stale,
        ),
    )


def _active_external_run_source_event(
    events: list[AgentStreamEvent],
    capability_run_id: str,
) -> AgentStreamEvent | None:
    for event in reversed(events):
        if event.type != "external_run.created":
            continue
        payload = _dict_value(event.payload)
        if payload.get("capability_run_id") == capability_run_id:
            return event
    for event in reversed(events):
        if event.type != "run.paused":
            continue
        payload = _dict_value(event.payload)
        if payload.get("status") != "waiting_external_run":
            continue
        external = _dict_value(payload.get("current_external_run"))
        if external.get("capability_run_id") == capability_run_id:
            return event
    return None


def _active_external_run_operator_actions(
    *,
    run_id: str,
    capability_run_id: str,
    stale: bool,
) -> list[RunActiveExternalRunOperatorAction]:
    if not stale:
        return []
    resolve_path = f"/api/runs/{run_id}/external-run/resolve"
    return [
        RunActiveExternalRunOperatorAction(
            kind="check_provider_status",
            label="Check provider status",
            reason=f"Inspect provider-owned CapabilityRun {capability_run_id}.",
        ),
        RunActiveExternalRunOperatorAction(
            kind="redeliver_completed_callback",
            label="Redeliver completed callback",
            reason="Use this if the provider completed but the Agent callback was missed.",
            method="POST",
            path=resolve_path,
            status="completed",
        ),
        RunActiveExternalRunOperatorAction(
            kind="mark_failed",
            label="Mark external run failed",
            reason="Use this if the provider reports a terminal failure.",
            method="POST",
            path=resolve_path,
            status="failed",
        ),
        RunActiveExternalRunOperatorAction(
            kind="mark_cancelled",
            label="Mark external run cancelled",
            reason="Use this if the provider reports cancellation.",
            method="POST",
            path=resolve_path,
            status="cancelled",
        ),
    ]


def _external_run_status(
    event_type: str,
    payload: dict[str, Any],
) -> RunExternalRunDiagnosticStatus:
    status = _string_value(payload.get("status"))
    if status in {"running", "waiting_approval", "completed", "failed", "cancelled"}:
        return cast(RunExternalRunDiagnosticStatus, status)
    if event_type == "external_run.completed":
        return "completed"
    if event_type == "external_run.failed":
        return "failed"
    if event_type == "external_run.cancelled":
        return "cancelled"
    return "running"


def _copy_nonblank(source: dict[str, Any], target: dict[str, Any], key: str) -> None:
    value = _string_value(source.get(key))
    if value is not None:
        target[key] = value


def _external_run_output_summary(output: object) -> str | None:
    if output is None:
        return None
    if isinstance(output, str):
        return _bounded_summary(output)
    if isinstance(output, dict):
        parts = [
            f"{key}={value}"
            for key, value in output.items()
            if value is not None and not isinstance(value, (dict, list))
        ]
        if parts:
            return _bounded_summary("; ".join(parts))
    return _bounded_summary(str(output))


def _bounded_summary(value: str, *, max_chars: int = 500) -> str:
    return value if len(value) <= max_chars else value[:max_chars]


def build_research_execution_snapshot(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    todos: list[AgentTodo],
    workspace_files: list[AgentWorkspaceFile],
    trace: list[AgentTraceSpan],
) -> ResearchExecutionSnapshot:
    """Build a research execution projection without adding persisted plan state."""
    summary = build_research_snapshot_summary(
        events=events,
        todos=todos,
        workspace_files=workspace_files,
        trace=trace,
    )
    plan_output = _latest_research_plan_output(events)
    plan = _research_execution_plan(plan_output)
    steps = _research_execution_steps(
        plan_output=plan_output,
        todos=todos,
        events=events,
        summary=summary,
    )
    progress = _research_execution_progress(steps, summary)
    status = _research_execution_status(
        progress=progress,
        summary=summary,
        has_plan=plan is not None,
        has_research_events=_has_research_activity_events(events),
    )
    return ResearchExecutionSnapshot(
        run_id=run.id,
        status=status,
        degraded=summary.degraded or status in {"blocked", "degraded"},
        plan=plan,
        steps=steps,
        progress=progress,
        summary=summary,
    )


def build_research_evidence_ledger(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    workspace_files: list[AgentWorkspaceFile],
) -> ResearchEvidenceLedger:
    """Build a source/evidence ledger from structured research report events."""
    report_result = _latest_research_report(events)
    report_files = _research_evidence_ledger_report_files(events, workspace_files)
    if report_result is None:
        return ResearchEvidenceLedger(
            run_id=run.id,
            report_files=report_files,
            counts=ResearchEvidenceLedgerCounts(
                report_file_count=len(report_files),
            ),
        )

    report, sequence = report_result
    sections = _research_evidence_ledger_sections(report)
    return ResearchEvidenceLedger(
        run_id=run.id,
        status=report.status,
        degraded=report.status in {"partial", "insufficient_evidence"} or bool(report.limitations),
        title=report.title,
        query=report.query,
        summary=report.summary,
        source_event_sequence=sequence,
        quality_summary=report.quality_summary,
        sources=report.sources,
        evidence=report.evidence,
        limitations=report.limitations,
        sections=sections,
        section_summary=report.section_summary,
        report_files=report_files,
        counts=ResearchEvidenceLedgerCounts(
            source_input_count=report.source_input_count,
            duplicate_source_count=report.duplicate_source_count,
            source_count=len(report.sources),
            evidence_count=len(report.evidence),
            limitation_count=len(report.limitations),
            section_count=len(sections),
            missing_section_count=sum(1 for section in sections if not section.covered),
            weak_section_count=sum(1 for section in sections if section.weak_quality),
            report_file_count=len(report_files),
        ),
    )


def _research_evidence_ledger_sections(
    report: ResearchReport,
) -> list[ResearchEvidenceLedgerSection]:
    summary_by_id = {
        summary.section_id: summary
        for summary in report.section_summary
    }
    quality_by_id = _research_section_quality_summaries(report)
    sections: list[ResearchEvidenceLedgerSection] = []
    seen: set[str] = set()
    for section in report.sections:
        sections.append(
            _research_evidence_ledger_section_item(
                section=section,
                summary=summary_by_id.get(section.section_id),
                quality_summary=quality_by_id.get(section.section_id),
            )
        )
        seen.add(section.section_id)
    for summary in report.section_summary:
        if summary.section_id in seen:
            continue
        sections.append(
            _research_evidence_ledger_section_item(
                section=None,
                summary=summary,
                quality_summary=quality_by_id.get(summary.section_id),
            )
        )
    return sections


def _research_section_quality_summaries(
    report: ResearchReport,
) -> dict[str, ResearchQualitySummary]:
    counts_by_section: dict[str, dict[str, int]] = {}
    for evidence in report.evidence:
        if evidence.section_id is None:
            continue
        counts = counts_by_section.setdefault(
            evidence.section_id,
            {"high": 0, "medium": 0, "low": 0},
        )
        counts[evidence.quality.label] += 1
    return {
        section_id: ResearchQualitySummary(**counts)
        for section_id, counts in counts_by_section.items()
    }


def _research_evidence_ledger_section_item(
    *,
    section: ResearchPlanSection | None,
    summary: ResearchEvidenceSectionSummary | None,
    quality_summary: ResearchQualitySummary | None,
) -> ResearchEvidenceLedgerSection:
    section_id = section.section_id if section is not None else (summary.section_id if summary else "section")
    source_count = summary.source_count if summary is not None else 0
    evidence_count = summary.evidence_count if summary is not None else 0
    section_quality_summary = quality_summary or ResearchQualitySummary()
    return ResearchEvidenceLedgerSection(
        section_id=section_id,
        title=section.title if section is not None else section_id,
        question=section.question if section is not None else None,
        priority=section.priority if section is not None else "medium",
        source_count=source_count,
        evidence_count=evidence_count,
        covered=evidence_count > 0,
        quality_summary=section_quality_summary,
        weak_quality=evidence_count > 0 and section_quality_summary.high == 0,
    )


def build_research_review_snapshot(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    todos: list[AgentTodo],
    workspace_files: list[AgentWorkspaceFile],
    trace: list[AgentTraceSpan],
) -> ResearchReviewSnapshot:
    """Build a quality gate over existing research projections."""
    execution = build_research_execution_snapshot(
        run=run,
        events=events,
        todos=todos,
        workspace_files=workspace_files,
        trace=trace,
    )
    ledger = build_research_evidence_ledger(
        run=run,
        events=events,
        workspace_files=workspace_files,
    )
    findings = _research_review_findings(execution=execution, ledger=ledger)
    high_quality_source_count, low_quality_source_count = _research_review_quality_counts(ledger)
    counts = ResearchReviewCounts(
        source_count=ledger.counts.source_count,
        evidence_count=ledger.counts.evidence_count,
        limitation_count=ledger.counts.limitation_count,
        report_file_count=ledger.counts.report_file_count,
        blocked_step_count=execution.progress.blocked_steps,
        web_failure_count=execution.progress.web_failure_count,
        high_quality_source_count=high_quality_source_count,
        low_quality_source_count=low_quality_source_count,
        weak_section_count=ledger.counts.weak_section_count,
        finding_count=len(findings),
    )
    status = _research_review_status(
        execution=execution,
        ledger=ledger,
        findings=findings,
    )
    return ResearchReviewSnapshot(
        run_id=run.id,
        status=status,
        score=_research_review_score(status=status, findings=findings),
        ready_for_answer=status == "pass",
        report_status=ledger.status,
        reviewed_event_sequence=ledger.source_event_sequence,
        report_workspace_paths=[workspace_file.path for workspace_file in ledger.report_files],
        counts=counts,
        findings=findings,
    )


def build_research_continuation_snapshot(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    todos: list[AgentTodo],
    workspace_files: list[AgentWorkspaceFile],
    trace: list[AgentTraceSpan],
) -> ResearchContinuationSnapshot:
    """Build typed next-action suggestions from existing research review facts."""
    execution = build_research_execution_snapshot(
        run=run,
        events=events,
        todos=todos,
        workspace_files=workspace_files,
        trace=trace,
    )
    ledger = build_research_evidence_ledger(
        run=run,
        events=events,
        workspace_files=workspace_files,
    )
    review = build_research_review_snapshot(
        run=run,
        events=events,
        todos=todos,
        workspace_files=workspace_files,
        trace=trace,
    )
    actions = _research_continuation_actions(
        execution=execution,
        ledger=ledger,
        review=review,
    )
    return ResearchContinuationSnapshot(
        run_id=run.id,
        status=_research_continuation_status(review=review, actions=actions),
        ready_for_answer=review.ready_for_answer,
        review_status=review.status,
        report_status=review.report_status,
        query=ledger.query or (execution.plan.query if execution.plan else None),
        reviewed_event_sequence=review.reviewed_event_sequence,
        actions=actions,
        counts=ResearchContinuationCounts(
            action_count=len(actions),
            high_priority_action_count=sum(1 for action in actions if action.priority == "high"),
            suggested_tool_count=len(
                {
                    tool_name
                    for action in actions
                    for tool_name in action.suggested_tool_names
                }
            ),
            target_section_count=len(
                {
                    section_id
                    for action in actions
                    for section_id in action.target_section_ids
                }
            ),
        ),
    )


def build_research_continuation_lineage_snapshot(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    runs_by_id: dict[str, AgentRun] | None = None,
) -> ResearchContinuationLineageSnapshot:
    """Build continuation lineage from run stream audit events."""
    source = _research_continuation_source_link(
        run=run,
        events=events,
        runs_by_id=runs_by_id or {},
    )
    children = _research_continuation_child_links(
        run=run,
        events=events,
        runs_by_id=runs_by_id or {},
    )
    return ResearchContinuationLineageSnapshot(
        run_id=run.id,
        source=source,
        children=children,
        counts=ResearchContinuationLineageCounts(
            source_count=1 if source is not None else 0,
            child_count=len(children),
        ),
    )


def build_operator_follow_up_lineage_snapshot(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    runs_by_id: dict[str, AgentRun] | None = None,
) -> OperatorFollowUpLineageSnapshot:
    """Build operator follow-up lineage from run stream audit events."""
    source = _operator_follow_up_source_link(
        run=run,
        events=events,
        runs_by_id=runs_by_id or {},
    )
    children = _operator_follow_up_child_links(
        run=run,
        events=events,
        runs_by_id=runs_by_id or {},
    )
    return OperatorFollowUpLineageSnapshot(
        run_id=run.id,
        source=source,
        children=children,
        counts=OperatorFollowUpLineageCounts(
            source_count=1 if source is not None else 0,
            child_count=len(children),
        ),
    )


def _operator_follow_up_source_link(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    runs_by_id: dict[str, AgentRun],
) -> OperatorFollowUpSourceLink | None:
    for event in reversed(events):
        if event.type != "run.created":
            continue
        payload = _dict_value(event.payload)
        follow_up = _operator_follow_up_value(payload.get("operator_follow_up"))
        if follow_up is None:
            continue
        source_run = runs_by_id.get(follow_up.source_run_id)
        return OperatorFollowUpSourceLink(
            source_run_id=follow_up.source_run_id,
            child_run_id=_string_value(payload.get("child_run_id")) or run.id,
            operator_follow_up=follow_up,
            source_event_sequence=event.sequence,
            source_run_status=_status_value(source_run.status) if source_run else None,
            source_run_task_msg=source_run.task_msg if source_run else None,
        )
    return None


def _operator_follow_up_child_links(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    runs_by_id: dict[str, AgentRun],
) -> list[OperatorFollowUpChildLink]:
    children: list[OperatorFollowUpChildLink] = []
    seen: set[str] = set()
    for event in events:
        if event.type != "operator_action.follow_up.created":
            continue
        payload = _dict_value(event.payload)
        follow_up = _operator_follow_up_value(payload.get("operator_follow_up"))
        if follow_up is None:
            continue
        child_run_id = _string_value(payload.get("child_run_id"))
        if child_run_id is None or child_run_id in seen:
            continue
        seen.add(child_run_id)
        child_run = runs_by_id.get(child_run_id)
        children.append(
            OperatorFollowUpChildLink(
                source_run_id=_string_value(payload.get("source_run_id"))
                or follow_up.source_run_id
                or run.id,
                child_run_id=child_run_id,
                operator_follow_up=follow_up,
                source_event_sequence=event.sequence,
                child_run_status=_status_value(child_run.status) if child_run else None,
                child_run_task_msg=child_run.task_msg if child_run else None,
            )
        )
    return children


def _operator_follow_up_value(value: object) -> AgentRunOperatorFollowUpOptions | None:
    payload = _dict_value(value)
    if not payload:
        return None
    try:
        return AgentRunOperatorFollowUpOptions.model_validate(payload)
    except ValueError:
        return None


def _research_continuation_source_link(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    runs_by_id: dict[str, AgentRun],
) -> ResearchContinuationSourceLink | None:
    for event in reversed(events):
        if event.type != "run.created":
            continue
        payload = _dict_value(event.payload)
        continuation = _dict_value(payload.get("continuation"))
        if not continuation:
            continue
        source_run_id = _string_value(continuation.get("source_run_id"))
        if source_run_id is None:
            continue
        child_run_id = _string_value(continuation.get("child_run_id")) or run.id
        source_run = runs_by_id.get(source_run_id)
        return ResearchContinuationSourceLink(
            source_run_id=source_run_id,
            child_run_id=child_run_id,
            action_ids=_list_of_strings(continuation.get("action_ids")),
            continuation_status=_string_value(continuation.get("continuation_status")),
            query=_string_value(continuation.get("query")),
            source_event_sequence=event.sequence,
            source_run_status=_status_value(source_run.status) if source_run else None,
            source_run_task_msg=source_run.task_msg if source_run else None,
        )
    return None


def _research_continuation_child_links(
    *,
    run: AgentRun,
    events: list[AgentStreamEvent],
    runs_by_id: dict[str, AgentRun],
) -> list[ResearchContinuationChildLink]:
    children: list[ResearchContinuationChildLink] = []
    seen: set[str] = set()
    for event in events:
        if event.type != "research.continuation.created":
            continue
        continuation = _dict_value(event.payload)
        source_run_id = _string_value(continuation.get("source_run_id")) or run.id
        child_run_id = _string_value(continuation.get("child_run_id"))
        if child_run_id is None or child_run_id in seen:
            continue
        seen.add(child_run_id)
        child_run = runs_by_id.get(child_run_id)
        children.append(
            ResearchContinuationChildLink(
                source_run_id=source_run_id,
                child_run_id=child_run_id,
                action_ids=_list_of_strings(continuation.get("action_ids")),
                continuation_status=_string_value(continuation.get("continuation_status")),
                query=_string_value(continuation.get("query")),
                source_event_sequence=event.sequence,
                child_run_status=_status_value(child_run.status) if child_run else None,
                child_run_task_msg=child_run.task_msg if child_run else None,
            )
        )
    return children


def _research_continuation_actions(
    *,
    execution: ResearchExecutionSnapshot,
    ledger: ResearchEvidenceLedger,
    review: ResearchReviewSnapshot,
) -> list[ResearchContinuationAction]:
    if review.status in {"none", "pass"}:
        return []

    actions: list[ResearchContinuationAction] = []
    finding_codes = [finding.code for finding in review.findings]
    findings_by_code = {finding.code: finding for finding in review.findings}
    missing_section_ids = _research_missing_section_ids(ledger)
    weak_section_ids = _research_weak_section_ids(ledger)
    continuation_target_section_ids = _unique_strings(missing_section_ids + weak_section_ids)

    source_finding_codes = _ordered_finding_codes(
        finding_codes,
        ["insufficient_evidence_report", "missing_evidence", "partial_report"],
    )
    if source_finding_codes:
        actions.append(
            ResearchContinuationAction(
                action_id="collect_more_sources",
                kind="collect_more_sources",
                priority="high",
                title="Collect more evidence sources",
                reason=_research_continuation_reason_with_sections(
                    "The research report is not supported by enough usable citation evidence.",
                    missing_section_ids,
                ),
                related_finding_codes=source_finding_codes,
                target_section_ids=missing_section_ids,
                suggested_tool_names=["web.search", "web.fetch"],
                suggested_research_phases=["search", "fetch"],
            )
        )

    if _research_execution_phase_needs_retry(execution, "search"):
        actions.append(
            ResearchContinuationAction(
                action_id="retry_search",
                kind="retry_search",
                priority="high",
                title="Retry controlled web search",
                reason="Search did not complete cleanly, so the run may need fresh candidate sources.",
                related_finding_codes=_ordered_finding_codes(
                    finding_codes,
                    ["blocked_research_steps", "web_failures"],
                ),
                suggested_tool_names=["web.search"],
                suggested_research_phases=["search"],
            )
        )

    if _research_execution_phase_needs_retry(execution, "fetch"):
        actions.append(
            ResearchContinuationAction(
                action_id="retry_fetch",
                kind="retry_fetch",
                priority="high",
                title="Retry controlled web fetch",
                reason="Fetch did not complete cleanly, so cited sources may need fresh content.",
                related_finding_codes=_ordered_finding_codes(
                    finding_codes,
                    ["blocked_research_steps", "web_failures"],
                ),
                suggested_tool_names=["web.fetch"],
                suggested_research_phases=["fetch"],
            )
        )

    quality_finding_codes = _ordered_finding_codes(
        finding_codes,
        ["low_quality_sources", "no_high_quality_sources", "weak_research_sections"],
    )
    if quality_finding_codes:
        actions.append(
            ResearchContinuationAction(
                action_id="improve_source_quality",
                kind="improve_source_quality",
                priority="medium",
                title="Improve source quality",
                reason=_research_continuation_reason_with_sections(
                    "The report needs stronger sources before it should be treated as ready.",
                    weak_section_ids,
                    label="Weak sections",
                ),
                related_finding_codes=quality_finding_codes,
                target_section_ids=weak_section_ids,
                suggested_tool_names=["web.search", "web.fetch"],
                suggested_research_phases=["search", "fetch"],
            )
        )

    if "research_limitations" in finding_codes:
        limitation_finding = findings_by_code["research_limitations"]
        actions.append(
            ResearchContinuationAction(
                action_id="address_limitations",
                kind="address_limitations",
                priority="high" if limitation_finding.severity == "error" else "medium",
                title="Address research limitations",
                reason="The report records limitations that should be resolved or explained before final use.",
                related_finding_codes=["research_limitations"],
                suggested_tool_names=[],
                suggested_research_phases=["synthesize"],
            )
        )

    if _research_continuation_should_regenerate_report(review=review, ledger=ledger, actions=actions):
        actions.append(
            ResearchContinuationAction(
                action_id="regenerate_report",
                kind="regenerate_report",
                priority="medium",
                title="Regenerate the research report",
                reason="After evidence or limitation repairs, create a fresh report workspace_file and review it again.",
                related_finding_codes=_ordered_finding_codes(
                    finding_codes,
                    [
                        "missing_report",
                        "missing_report_file",
                        "partial_report",
                        "insufficient_evidence_report",
                        "missing_evidence",
                        "research_limitations",
                        "low_quality_sources",
                        "no_high_quality_sources",
                        "weak_research_sections",
                    ],
                ),
                target_section_ids=continuation_target_section_ids,
                suggested_tool_names=["research.create_report"],
                suggested_research_phases=["report"],
            )
        )

    return actions


def _research_missing_section_ids(ledger: ResearchEvidenceLedger) -> list[str]:
    return [section.section_id for section in ledger.sections if not section.covered]


def _research_weak_section_ids(ledger: ResearchEvidenceLedger) -> list[str]:
    return [section.section_id for section in ledger.sections if section.weak_quality]


def _research_continuation_reason_with_sections(
    reason: str,
    section_ids: list[str],
    *,
    label: str = "Missing sections",
) -> str:
    if not section_ids:
        return reason
    return f"{reason} {label}: {', '.join(section_ids)}."


def _research_execution_phase_needs_retry(
    execution: ResearchExecutionSnapshot,
    phase: ResearchPlanPhase,
) -> bool:
    return any(
        step.phase == phase
        and (
            step.status == "blocked"
            or step.web_failure_count > 0
            or step.attention
        )
        for step in execution.steps
    )


def _research_continuation_should_regenerate_report(
    *,
    review: ResearchReviewSnapshot,
    ledger: ResearchEvidenceLedger,
    actions: list[ResearchContinuationAction],
) -> bool:
    if review.status == "none":
        return False
    if "missing_report" in [finding.code for finding in review.findings]:
        return True
    if "missing_report_file" in [finding.code for finding in review.findings]:
        return True
    return ledger.status != "none" and bool(actions)


def _research_continuation_status(
    *,
    review: ResearchReviewSnapshot,
    actions: list[ResearchContinuationAction],
) -> ResearchContinuationStatus:
    if review.status == "none":
        return "none"
    if review.ready_for_answer:
        return "ready"
    research_action_kinds = {
        "collect_more_sources",
        "retry_search",
        "retry_fetch",
        "improve_source_quality",
        "address_limitations",
    }
    if any(action.kind in research_action_kinds for action in actions):
        return "needs_research"
    return "needs_report"


def _ordered_finding_codes(
    finding_codes: list[ResearchReviewFindingCode],
    order: list[ResearchReviewFindingCode],
) -> list[ResearchReviewFindingCode]:
    present = set(finding_codes)
    return [code for code in order if code in present]


def _research_review_findings(
    *,
    execution: ResearchExecutionSnapshot,
    ledger: ResearchEvidenceLedger,
) -> list[ResearchReviewFinding]:
    if not _has_research_review_facts(execution=execution, ledger=ledger):
        return []

    findings: list[ResearchReviewFinding] = []
    if ledger.status == "none":
        findings.append(
            ResearchReviewFinding(
                code="missing_report",
                severity="error",
                message="Research activity has no structured report output.",
            )
        )
    elif ledger.status == "insufficient_evidence":
        findings.append(
            ResearchReviewFinding(
                code="insufficient_evidence_report",
                severity="error",
                message="The latest research report marked the answer as insufficient evidence.",
            )
        )
    elif ledger.status == "partial":
        findings.append(
            ResearchReviewFinding(
                code="partial_report",
                severity="warning",
                message="The latest research report is partial.",
            )
        )

    if ledger.status != "none" and ledger.counts.evidence_count == 0:
        findings.append(
            ResearchReviewFinding(
                code="missing_evidence",
                severity="error",
                message="The latest research report has no citation evidence rows.",
            )
        )

    if ledger.status != "none" and ledger.counts.report_file_count == 0:
        findings.append(
            ResearchReviewFinding(
                code="missing_report_file",
                severity="warning",
                message="The latest research report has no persisted report workspace_file.",
            )
        )

    if execution.progress.blocked_steps:
        findings.append(
            ResearchReviewFinding(
                code="blocked_research_steps",
                severity="warning",
                message="One or more research execution steps are blocked.",
            )
        )

    if execution.progress.web_failure_count:
        findings.append(
            ResearchReviewFinding(
                code="web_failures",
                severity="warning",
                message="Controlled web tool failures affected the research run.",
            )
        )

    if ledger.counts.limitation_count:
        findings.append(
            ResearchReviewFinding(
                code="research_limitations",
                severity=_research_review_limitation_severity(ledger),
                message="The latest research report recorded limitations.",
            )
        )

    high_quality_source_count, low_quality_source_count = _research_review_quality_counts(ledger)
    if low_quality_source_count:
        findings.append(
            ResearchReviewFinding(
                code="low_quality_sources",
                severity="warning",
                message="The latest research report includes low-quality sources.",
            )
        )
    if ledger.counts.evidence_count and high_quality_source_count == 0:
        findings.append(
            ResearchReviewFinding(
                code="no_high_quality_sources",
                severity="warning",
                message="The latest research report has evidence but no high-quality sources.",
            )
        )
    weak_section_ids = _research_weak_section_ids(ledger)
    if weak_section_ids:
        findings.append(
            ResearchReviewFinding(
                code="weak_research_sections",
                severity="warning",
                message=(
                    "The latest research report has sections without high-quality evidence: "
                    + ", ".join(weak_section_ids)
                    + "."
                ),
            )
        )

    return findings


def _has_research_review_facts(
    *,
    execution: ResearchExecutionSnapshot,
    ledger: ResearchEvidenceLedger,
) -> bool:
    return (
        execution.status != "none"
        or ledger.status != "none"
        or ledger.counts.report_file_count > 0
        or ledger.counts.source_count > 0
        or ledger.counts.evidence_count > 0
    )


def _research_review_quality_counts(ledger: ResearchEvidenceLedger) -> tuple[int, int]:
    if ledger.quality_summary is not None:
        return ledger.quality_summary.high, ledger.quality_summary.low
    high = sum(1 for evidence in ledger.evidence if evidence.quality.label == "high")
    low = sum(1 for evidence in ledger.evidence if evidence.quality.label == "low")
    return high, low


def _research_review_limitation_severity(
    ledger: ResearchEvidenceLedger,
) -> ResearchReviewFindingSeverity:
    return "error" if any(limitation.severity == "error" for limitation in ledger.limitations) else "warning"


def _research_review_status(
    *,
    execution: ResearchExecutionSnapshot,
    ledger: ResearchEvidenceLedger,
    findings: list[ResearchReviewFinding],
) -> ResearchReviewStatus:
    if not _has_research_review_facts(execution=execution, ledger=ledger):
        return "none"
    if any(finding.severity == "error" for finding in findings):
        return "fail"
    if any(finding.severity == "warning" for finding in findings):
        return "warn"
    return "pass"


def _research_review_score(
    *,
    status: ResearchReviewStatus,
    findings: list[ResearchReviewFinding],
) -> int:
    if status == "none":
        return 0
    score = 100
    for finding in findings:
        score -= 50 if finding.severity == "error" else 20
    return max(0, score)


def _run_health(
    run: AgentRun,
    research: ResearchSnapshotSummary,
) -> RunInspectionHealth:
    status = str(run.status.value if hasattr(run.status, "value") else run.status)
    if status == "completed" and research.degraded:
        return "degraded"
    if status in {
        "queued",
        "running",
        "waiting_approval",
        "waiting_subagent",
        "waiting_input",
        "waiting_external_run",
        "completed",
        "failed",
        "cancelled",
    }:
        return status
    return "failed"


def _latest_research_plan_output(
    events: list[AgentStreamEvent],
) -> tuple[dict[str, Any], int] | None:
    for event in reversed(events):
        if event.type != "tool.completed":
            continue
        payload = _dict_value(event.payload)
        if payload.get("tool_name") != "research.create_plan":
            continue
        output = _dict_value(payload.get("output"))
        if output:
            return output, event.sequence
    return None


def _latest_research_report(
    events: list[AgentStreamEvent],
) -> tuple[ResearchReport, int] | None:
    for event in reversed(events):
        if event.type != "tool.completed":
            continue
        payload = _dict_value(event.payload)
        if payload.get("tool_name") != "research.create_report":
            continue
        output = _dict_value(payload.get("output"))
        report = _research_report_value(output.get("report"))
        if report is not None:
            return report, event.sequence
    return None


def _research_report_value(value: object) -> ResearchReport | None:
    if isinstance(value, ResearchReport):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return ResearchReport.model_validate(value)
    except ValueError:
        return None


def _research_evidence_ledger_report_files(
    events: list[AgentStreamEvent],
    workspace_files: list[AgentWorkspaceFile],
) -> list[ResearchEvidenceLedgerReportFile]:
    report_files: list[ResearchEvidenceLedgerReportFile] = []
    workspace_files_by_path = {file.path: file for file in workspace_files}
    for report, path in _research_report_file_outputs(events):
        workspace_file = workspace_files_by_path.get(path)
        report_files.append(
            ResearchEvidenceLedgerReportFile(
                path=path,
                name=_workspace_file_name(workspace_file, path),
                uri=path,
                report_status=report.status,
                source_count=len(report.sources),
                source_input_count=report.source_input_count,
                duplicate_source_count=report.duplicate_source_count,
                evidence_count=len(report.evidence),
                limitation_count=len(report.limitations),
                section_count=len(report.sections),
                section_summary=list(report.section_summary),
                quality_summary=report.quality_summary.model_dump(mode="json")
                if report.quality_summary is not None
                else None,
            )
        )
    return report_files


def _research_section_summary_values(value: object) -> list[ResearchEvidenceSectionSummary]:
    summaries: list[ResearchEvidenceSectionSummary] = []
    for raw_summary in _list_of_dicts(value):
        try:
            summaries.append(ResearchEvidenceSectionSummary.model_validate(raw_summary))
        except ValueError:
            continue
    return summaries


def _research_execution_plan(
    plan_output: tuple[dict[str, Any], int] | None,
) -> ResearchExecutionPlan | None:
    if plan_output is None:
        return None
    output, sequence = plan_output
    plan = _dict_value(output.get("plan"))
    if not plan:
        return None
    return ResearchExecutionPlan(
        query=_string_value(plan.get("query")),
        objective=_string_value(plan.get("objective")),
        sections=_research_execution_plan_sections(plan),
        source_event_sequence=sequence,
    )


def _research_execution_plan_sections(
    plan: dict[str, Any],
) -> list[ResearchExecutionPlanSection]:
    sections: list[ResearchExecutionPlanSection] = []
    for raw_section in _list_of_dicts(plan.get("sections")):
        section_id = _string_value(raw_section.get("section_id"))
        title = _string_value(raw_section.get("title"))
        question = _string_value(raw_section.get("question"))
        if section_id is None or title is None or question is None:
            continue
        sections.append(
            ResearchExecutionPlanSection(
                section_id=section_id,
                title=title,
                question=question,
                priority=_research_section_priority_value(raw_section.get("priority")),
            )
        )
    return sections


def _research_section_priority_value(value: object) -> ResearchPlanSectionPriority:
    if value in {"high", "medium", "low"}:
        return cast(ResearchPlanSectionPriority, value)
    return "medium"


def _research_execution_steps(
    *,
    plan_output: tuple[dict[str, Any], int] | None,
    todos: list[AgentTodo],
    events: list[AgentStreamEvent],
    summary: ResearchSnapshotSummary,
) -> list[ResearchExecutionStep]:
    steps: list[ResearchExecutionStep] = []
    current_todos_by_id = {todo.id: todo for todo in todos}
    current_todos_by_title = {todo.title: todo for todo in sorted(todos, key=lambda item: item.order)}

    if plan_output is not None:
        output, _sequence = plan_output
        plan = _dict_value(output.get("plan"))
        plan_steps = _list_of_dicts(plan.get("steps"))
        plan_todos = _list_of_dicts(output.get("todos"))
        for index, raw_step in enumerate(plan_steps):
            title = _string_value(raw_step.get("title"))
            if title is None:
                continue
            raw_todo = plan_todos[index] if index < len(plan_todos) else {}
            todo = _research_step_current_todo(
                raw_todo=raw_todo,
                title=title,
                current_todos_by_id=current_todos_by_id,
                current_todos_by_title=current_todos_by_title,
            )
            steps.append(
                _research_execution_step(
                    phase=_research_phase_value(raw_step.get("phase"), title),
                    title=title,
                    description=_string_value(raw_step.get("description"))
                    or (todo.description if todo else None),
                    todo=todo,
                    events=events,
                    summary=summary,
                )
            )

    if not steps:
        for todo in sorted(todos, key=lambda item: item.order):
            phase = _DEFAULT_RESEARCH_PHASE_BY_TITLE.get(todo.title)
            if phase is None:
                continue
            steps.append(
                _research_execution_step(
                    phase=phase,
                    title=todo.title,
                    description=todo.description,
                    todo=todo,
                    events=events,
                    summary=summary,
                )
            )

    if not steps and summary.report_files:
        steps.append(
            _research_execution_step(
                phase="report",
                title="Create research report",
                description=None,
                todo=None,
                events=events,
                summary=summary,
            )
        )

    return steps


def _research_execution_step(
    *,
    phase: ResearchPlanPhase,
    title: str,
    description: str | None,
    todo: AgentTodo | None,
    events: list[AgentStreamEvent],
    summary: ResearchSnapshotSummary,
) -> ResearchExecutionStep:
    web_success_count = _web_success_count_for_phase(events, phase)
    web_failure_count = _web_failure_count_for_phase(summary.web_failures, phase)
    report_workspace_paths = (
        [workspace_file.path for workspace_file in summary.report_files]
        if phase == "report"
        else []
    )
    limitation_codes = _limitation_codes_for_phase(
        limitations=summary.limitations,
        web_failures=summary.web_failures,
        phase=phase,
    )
    status = _research_execution_step_status(
        todo=todo,
        phase=phase,
        report_workspace_paths=report_workspace_paths,
        web_failure_count=web_failure_count,
    )
    return ResearchExecutionStep(
        phase=phase,
        title=title,
        description=description,
        todo_id=todo.id if todo else None,
        todo_order=todo.order if todo else None,
        status=status,
        related_tool_names=_research_related_tools_for_phase(phase),
        web_success_count=web_success_count,
        web_failure_count=web_failure_count,
        report_workspace_paths=report_workspace_paths,
        limitation_codes=limitation_codes,
        attention=(
            status in {"blocked", "cancelled"}
            or web_failure_count > 0
            or (phase == "report" and summary.degraded)
        ),
    )


def _research_step_current_todo(
    *,
    raw_todo: dict[str, Any],
    title: str,
    current_todos_by_id: dict[str, AgentTodo],
    current_todos_by_title: dict[str, AgentTodo],
) -> AgentTodo | None:
    todo_id = _string_value(raw_todo.get("id"))
    if todo_id and todo_id in current_todos_by_id:
        return current_todos_by_id[todo_id]
    return current_todos_by_title.get(title)


def _research_execution_step_status(
    *,
    todo: AgentTodo | None,
    phase: ResearchPlanPhase,
    report_workspace_paths: list[str],
    web_failure_count: int,
) -> ResearchExecutionStepStatus:
    if todo is not None:
        status = _todo_status(todo)
        if status in {"pending", "running", "done", "blocked", "cancelled"}:
            return cast(ResearchExecutionStepStatus, status)
    if phase == "report" and report_workspace_paths:
        return "done"
    if web_failure_count:
        return "blocked"
    return "pending"


def _research_execution_progress(
    steps: list[ResearchExecutionStep],
    summary: ResearchSnapshotSummary,
) -> ResearchExecutionProgress:
    return ResearchExecutionProgress(
        total_steps=len(steps),
        pending_steps=sum(1 for step in steps if step.status == "pending"),
        running_steps=sum(1 for step in steps if step.status == "running"),
        done_steps=sum(1 for step in steps if step.status == "done"),
        blocked_steps=sum(1 for step in steps if step.status == "blocked"),
        cancelled_steps=sum(1 for step in steps if step.status == "cancelled"),
        terminal_steps=sum(
            1
            for step in steps
            if step.status in {"done", "blocked", "cancelled"}
        ),
        web_success_count=sum(step.web_success_count for step in steps),
        web_failure_count=sum(step.web_failure_count for step in steps),
        report_file_count=len(summary.report_files),
        limitation_count=len(summary.limitations),
    )


def _research_execution_status(
    *,
    progress: ResearchExecutionProgress,
    summary: ResearchSnapshotSummary,
    has_plan: bool,
    has_research_events: bool,
) -> ResearchExecutionStatus:
    has_research_facts = (
        has_plan
        or has_research_events
        or progress.total_steps > 0
        or progress.report_file_count > 0
        or summary.status != "none"
    )
    if not has_research_facts:
        return "none"
    if progress.report_file_count:
        return "degraded" if summary.degraded else "completed"
    if progress.blocked_steps or progress.cancelled_steps or progress.web_failure_count:
        return "blocked"
    if progress.running_steps or progress.done_steps or progress.web_success_count:
        return "running"
    return "planned"


def _research_phase_value(value: object, title: str) -> ResearchPlanPhase:
    if value in {"search", "fetch", "synthesize", "report", "custom"}:
        return cast(ResearchPlanPhase, value)
    return _DEFAULT_RESEARCH_PHASE_BY_TITLE.get(title, "custom")


def _research_related_tools_for_phase(phase: ResearchPlanPhase) -> list[str]:
    match phase:
        case "search":
            return ["web.search"]
        case "fetch":
            return ["web.fetch"]
        case "synthesize" | "report":
            return ["research.create_report"]
        case _:
            return []


def _web_success_count_for_phase(
    events: list[AgentStreamEvent],
    phase: ResearchPlanPhase,
) -> int:
    event_type = _web_event_type_for_phase(phase, completed=True)
    if event_type is None:
        return 0
    return sum(1 for event in events if event.type == event_type)


def _web_failure_count_for_phase(
    failures: list[ResearchSnapshotWebFailure],
    phase: ResearchPlanPhase,
) -> int:
    tool_name = _web_tool_name_for_phase(phase)
    if tool_name is None:
        return 0
    return sum(1 for failure in failures if failure.tool_name == tool_name)


def _limitation_codes_for_phase(
    *,
    limitations: list[ResearchLimitation],
    web_failures: list[ResearchSnapshotWebFailure],
    phase: ResearchPlanPhase,
) -> list[str]:
    codes: list[str] = []
    tool_name = _web_tool_name_for_phase(phase)
    if tool_name is not None:
        for failure in web_failures:
            if failure.tool_name == tool_name and failure.limitation is not None:
                codes.append(failure.limitation.code)
    for limitation in limitations:
        if _limitation_matches_phase(limitation, phase):
            codes.append(limitation.code)
    return _unique_strings(codes)


def _limitation_matches_phase(
    limitation: ResearchLimitation,
    phase: ResearchPlanPhase,
) -> bool:
    match phase:
        case "search":
            return "search" in limitation.code
        case "fetch":
            return "fetch" in limitation.code
        case "synthesize" | "report":
            return True
        case _:
            return False


def _web_event_type_for_phase(
    phase: ResearchPlanPhase,
    *,
    completed: bool,
) -> str | None:
    suffix = "completed" if completed else "failed"
    match phase:
        case "search":
            return f"web.search.{suffix}"
        case "fetch":
            return f"web.fetch.{suffix}"
        case _:
            return None


def _web_tool_name_for_phase(
    phase: ResearchPlanPhase,
) -> ResearchSnapshotWebToolName | None:
    match phase:
        case "search":
            return "web.search"
        case "fetch":
            return "web.fetch"
        case _:
            return None


def _has_research_activity_events(events: list[AgentStreamEvent]) -> bool:
    research_event_types = {
        "web.search.completed",
        "web.search.failed",
        "web.fetch.completed",
        "web.fetch.failed",
    }
    for event in events:
        if event.type in research_event_types:
            return True
        if event.type != "tool.completed":
            continue
        payload = _dict_value(event.payload)
        if payload.get("tool_name") in {"research.create_plan", "research.create_report"}:
            return True
    return False


def _latest_pause_event(events: list[AgentStreamEvent]) -> AgentStreamEvent | None:
    for event in reversed(events):
        if event.type == "run.paused":
            return event
    return None


def _first_event_after(
    events: list[AgentStreamEvent],
    sequence: int,
    event_type: str,
) -> AgentStreamEvent | None:
    for event in events:
        if event.sequence > sequence and event.type == event_type:
            return event
    return None


def _resume_audit_events(
    events: list[AgentStreamEvent],
    sequence: int,
) -> list[AgentStreamEvent]:
    audit_types = {
        "run.paused",
        "run.resumed",
        "input.requested",
        "input.received",
        "approval.requested",
        "approval.resolved",
        "external_approval.requested",
        "external_approval.resolved",
        "external_run.created",
        "external_run.completed",
        "external_run.failed",
        "external_run.cancelled",
        "subagent.started",
        "subagent.completed",
        "subagent.failed",
    }
    start_sequence = 0
    for event in events:
        if event.sequence < sequence and event.type == "run.resumed":
            start_sequence = event.sequence
    return [
        event
        for event in events
        if event.sequence > start_sequence and event.type in audit_types
    ]


def _resume_kind_for_status(status: str | None, payload: dict[str, Any] | None = None) -> RunResumeKind:
    if status == "waiting_input":
        return "input"
    if status == "waiting_approval":
        if payload and _string_value(payload.get("approval_kind")) == "external":
            return "external_approval"
        return "approval"
    if status == "waiting_external_run":
        return "external_run"
    if status == "waiting_subagent":
        return "subagent"
    return "none"


def _resume_reason(kind: RunResumeKind, payload: dict[str, Any]) -> str | None:
    if kind == "input":
        return _string_value(payload.get("reason"))
    if kind == "approval":
        tool_name = _string_value(payload.get("tool_name"))
        return f"Waiting for approval to run {tool_name}." if tool_name else "Waiting for approval."
    if kind == "external_approval":
        external = _dict_value(payload.get("current_external_approval"))
        tool_name = _string_value(external.get("tool_name")) or _string_value(payload.get("tool_name"))
        return (
            f"Waiting for external workflow approval to run {tool_name}."
            if tool_name
            else "Waiting for external workflow approval."
        )
    if kind == "external_run":
        external = _dict_value(payload.get("current_external_run"))
        capability_run_id = _string_value(external.get("capability_run_id"))
        return (
            f"Waiting for external workflow capability run {capability_run_id}."
            if capability_run_id
            else "Waiting for external workflow capability run."
        )
    if kind == "subagent":
        return "Waiting for a subagent result."
    return None


def _approval_by_id(
    approvals: list[AgentApproval],
    approval_id: str | None,
) -> AgentApproval | None:
    if approval_id is None:
        return None
    return next((approval for approval in approvals if approval.id == approval_id), None)


def _subagent_by_id(
    subagents: list[AgentSubagentRun],
    subagent_run_id: str | None,
) -> AgentSubagentRun | None:
    if subagent_run_id is None:
        return None
    return next((subagent for subagent in subagents if subagent.id == subagent_run_id), None)


def _approval_has_pydantic_history(approval: AgentApproval | None) -> bool:
    if approval is None or not isinstance(approval.metadata, dict):
        return False
    return any(
        isinstance(approval.metadata.get(key), str) and bool(approval.metadata.get(key))
        for key in ("pydantic_message_history", "message_history_json")
    )


def _web_failures_from_events(events: list[AgentStreamEvent]) -> list[ResearchSnapshotWebFailure]:
    failures: list[ResearchSnapshotWebFailure] = []
    for event in events:
        if event.type not in {"web.search.failed", "web.fetch.failed"}:
            continue
        payload = _dict_value(event.payload)
        tool_name: ResearchSnapshotWebToolName = (
            "web.search" if event.type == "web.search.failed" else "web.fetch"
        )
        failures.append(
            ResearchSnapshotWebFailure(
                tool_call_id=_string_value(payload.get("tool_call_id")) or str(event.sequence),
                tool_name=tool_name,
                query=_string_value(payload.get("query")),
                url=_string_value(payload.get("url")),
                error=_dict_value_or_none(payload.get("error")),
                limitation=_limitation_value(payload.get("limitation")),
            )
        )
    return failures


def _blocked_research_todos(todos: list[AgentTodo]) -> list[ResearchSnapshotTodo]:
    return [
        ResearchSnapshotTodo(
            todo_id=todo.id,
            title=todo.title,
            status=str(todo.status.value if hasattr(todo.status, "value") else todo.status),
        )
        for todo in todos
        if _todo_status(todo) == "blocked"
    ]


def _research_report_files(
    events: list[AgentStreamEvent],
    workspace_files: list[AgentWorkspaceFile],
) -> list[ResearchSnapshotReportFile]:
    report_files: list[ResearchSnapshotReportFile] = []
    workspace_files_by_path = {file.path: file for file in workspace_files}
    for report, path in _research_report_file_outputs(events):
        workspace_file = workspace_files_by_path.get(path)
        report_files.append(
            ResearchSnapshotReportFile(
                path=path,
                name=_workspace_file_name(workspace_file, path),
                uri=path,
                report_status=report.status,
                source_count=len(report.sources),
                evidence_count=len(report.evidence),
                limitation_count=len(report.limitations),
                quality_summary=report.quality_summary.model_dump(mode="json")
                if report.quality_summary is not None
                else None,
            )
        )
    return report_files


def _research_report_file_outputs(events: list[AgentStreamEvent]) -> list[tuple[ResearchReport, str]]:
    outputs: list[tuple[ResearchReport, str]] = []
    for event in events:
        if event.type != "tool.completed":
            continue
        payload = _dict_value(event.payload)
        if payload.get("tool_name") != "research.create_report":
            continue
        output = _dict_value(payload.get("output"))
        report = _research_report_value(output.get("report"))
        if report is None:
            continue
        workspace_file = _dict_value(output.get("workspace_file"))
        path = _string_value(workspace_file.get("path")) or _string_value(output.get("path"))
        if path is None:
            continue
        outputs.append((report, path))
    return outputs


def _workspace_file_name(file: AgentWorkspaceFile | None, fallback_path: str) -> str:
    path = file.path if file is not None else fallback_path
    return path.rstrip("/").rsplit("/", 1)[-1] or path


def _research_limitations(
    events: list[AgentStreamEvent],
    web_failures: list[ResearchSnapshotWebFailure],
) -> list[ResearchLimitation]:
    limitations: list[ResearchLimitation] = []
    seen: set[tuple[str, str, str | None]] = set()

    for failure in web_failures:
        if failure.limitation is not None:
            _append_unique_limitation(limitations, seen, failure.limitation)

    for event in events:
        if event.type != "tool.completed":
            continue
        payload = _dict_value(event.payload)
        if payload.get("tool_name") != "research.create_report":
            continue
        output = _dict_value(payload.get("output"))
        report = _dict_value(output.get("report"))
        raw_limitations = report.get("limitations")
        if not isinstance(raw_limitations, list):
            continue
        for raw_limitation in raw_limitations:
            limitation = _limitation_value(raw_limitation)
            if limitation is not None:
                _append_unique_limitation(limitations, seen, limitation)

    return limitations


def _research_status(
    report_files: list[ResearchSnapshotReportFile],
) -> ResearchSnapshotStatus:
    if not report_files:
        return "none"
    return report_files[-1].report_status


def _append_unique_limitation(
    limitations: list[ResearchLimitation],
    seen: set[tuple[str, str, str | None]],
    limitation: ResearchLimitation,
) -> None:
    key = (limitation.code, limitation.message, limitation.source_url)
    if key in seen:
        return
    seen.add(key)
    limitations.append(limitation)


def _limitation_value(value: object) -> ResearchLimitation | None:
    if isinstance(value, ResearchLimitation):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return ResearchLimitation.model_validate(value)
    except ValueError:
        return None


def _report_status_value(value: object) -> ResearchReportStatus | None:
    if value in {"complete", "partial", "insufficient_evidence"}:
        return value
    return None


def _todo_status(todo: AgentTodo) -> str:
    return _status_value(todo.status)


def _status_value(status: object) -> str:
    return str(status.value if hasattr(status, "value") else status)


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _dict_value(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _dict_value_or_none(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


_DEFAULT_RESEARCH_PHASE_BY_TITLE: dict[str, ResearchPlanPhase] = {
    "Search sources": "search",
    "Fetch and review sources": "fetch",
    "Synthesize findings": "synthesize",
    "Create research report": "report",
}
