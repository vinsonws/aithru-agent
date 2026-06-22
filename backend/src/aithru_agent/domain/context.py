import re
from typing import Literal

from pydantic import Field, computed_field, field_validator

from .artifact import AgentArtifact, AgentArtifactType
from .base import AithruBaseModel
from .memory import AgentMemoryRecall
from .message import AgentMessage, AgentMessageRole
from .research import (
    ResearchLimitation,
    ResearchPlanPhase,
    ResearchPlanSectionPriority,
    ResearchReportStatus,
    ResearchSourceQualityLabel,
)
from .run import AgentRun, AgentRunStatus
from .todo import AgentTodo, AgentTodoStatus


AgentRunResumeReason = Literal[
    "waiting_input",
    "waiting_approval",
    "waiting_external_run",
    "waiting_subagent",
    "input_received",
]


class AgentRunContextCounts(AithruBaseModel):
    thread_messages: int = Field(ge=0)
    todos: int = Field(ge=0)
    artifacts: int = Field(ge=0)
    tool_results: int = Field(default=0, ge=0)
    memory: int = Field(default=0, ge=0)
    research_evidence: int = Field(default=0, ge=0)


class AgentRunContextBudgetUsage(AithruBaseModel):
    max_chars: int = Field(gt=0)
    used_chars: int = Field(ge=0)
    dropped_thread_messages: int = Field(default=0, ge=0)
    dropped_todos: int = Field(default=0, ge=0)
    dropped_artifacts: int = Field(default=0, ge=0)
    dropped_tool_results: int = Field(default=0, ge=0)
    dropped_memory: int = Field(default=0, ge=0)
    dropped_research_evidence: int = Field(default=0, ge=0)
    truncated_items: int = Field(default=0, ge=0)

    @computed_field
    @property
    def remaining_chars(self) -> int:
        return max(0, self.max_chars - self.used_chars)


class AgentRunCompressedContext(AithruBaseModel):
    summary: str
    counts: AgentRunContextCounts
    truncated: bool = False
    original_length: int = Field(default=0, ge=0)


class AgentRunContextMessage(AithruBaseModel):
    id: str
    role: AgentMessageRole
    content: str
    run_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    created_at: str
    truncated: bool = False
    original_length: int = Field(default=0, ge=0)

    @classmethod
    def from_message(
        cls,
        message: AgentMessage,
        *,
        max_content_chars: int,
    ) -> "AgentRunContextMessage":
        content, truncated, original_length = _bounded_text(
            message.content,
            max_chars=max_content_chars,
        )
        return cls(
            id=message.id,
            role=message.role,
            content=content,
            run_id=message.run_id,
            artifact_ids=message.artifact_ids,
            created_at=message.created_at,
            truncated=truncated,
            original_length=original_length,
        )


class AgentRunContextTodo(AithruBaseModel):
    id: str
    title: str
    status: AgentTodoStatus
    order: int
    description: str | None = None
    truncated: bool = False

    @classmethod
    def from_todo(
        cls,
        todo: AgentTodo,
        *,
        max_content_chars: int,
    ) -> "AgentRunContextTodo":
        description, truncated, _ = _bounded_text(
            todo.description,
            max_chars=max_content_chars,
        )
        return cls(
            id=todo.id,
            title=todo.title,
            status=todo.status,
            order=todo.order,
            description=description,
            truncated=truncated,
        )


class AgentRunContextArtifact(AithruBaseModel):
    id: str
    type: AgentArtifactType
    name: str
    uri: str | None = None
    media_type: str | None = None
    summary: str | None = None
    truncated: bool = False
    created_at: str

    @classmethod
    def from_artifact(
        cls,
        artifact: AgentArtifact,
        *,
        summary: str | None,
        truncated: bool,
    ) -> "AgentRunContextArtifact":
        return cls(
            id=artifact.id,
            type=artifact.type,
            name=artifact.name,
            uri=artifact.uri,
            media_type=artifact.media_type,
            summary=summary,
            truncated=truncated,
            created_at=artifact.created_at,
        )


class AgentRunContextToolResult(AithruBaseModel):
    tool_call_id: str
    tool_name: str
    status: str
    summary: str
    source_sequence: int = Field(ge=0)
    source_type: Literal["tool", "external_run"] = "tool"
    capability_key: str | None = None
    capability_run_id: str | None = None
    truncated: bool = False
    original_length: int = Field(default=0, ge=0)


AgentRunResearchContinuationStatus = Literal[
    "none",
    "planned",
    "running",
    "blocked",
    "completed",
    "degraded",
]
AgentRunResearchActionKind = Literal[
    "collect_more_sources",
    "retry_search",
    "retry_fetch",
    "improve_source_quality",
    "address_limitations",
    "regenerate_report",
]
AgentRunResearchActionPriority = Literal["high", "medium", "low"]


class AgentRunResearchEvidenceContext(AithruBaseModel):
    citation_number: int = Field(ge=1)
    title: str = Field(min_length=1)
    url: str
    section_id: str | None = None
    quality_label: ResearchSourceQualityLabel | None = None
    snippet: str | None = None
    excerpt: str | None = None
    truncated: bool = False
    original_length: int = Field(default=0, ge=0)


class AgentRunResearchSectionContext(AithruBaseModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str | None = None
    priority: ResearchPlanSectionPriority = "medium"
    source_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    covered: bool = False
    truncated: bool = False
    original_length: int = Field(default=0, ge=0)


class AgentRunResearchActionContext(AithruBaseModel):
    kind: AgentRunResearchActionKind
    priority: AgentRunResearchActionPriority
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target_section_ids: list[str] = Field(default_factory=list)
    suggested_tool_names: list[str] = Field(default_factory=list)
    suggested_research_phases: list[ResearchPlanPhase] = Field(default_factory=list)

    @field_validator("target_section_ids")
    @classmethod
    def _target_section_ids_must_be_stable_slugs(cls, value: list[str]) -> list[str]:
        section_ids: list[str] = []
        seen: set[str] = set()
        for item in value:
            section_id = item.strip()
            if not section_id:
                raise ValueError("target research section id cannot be blank")
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", section_id):
                raise ValueError("target research section id must be a stable lowercase slug")
            if section_id in seen:
                continue
            section_ids.append(section_id)
            seen.add(section_id)
        return section_ids


class AgentRunResearchContinuationContext(AithruBaseModel):
    source_run_id: str | None = None
    query: str | None = None
    status: AgentRunResearchContinuationStatus = "none"
    report_status: ResearchReportStatus | None = None
    target_section_ids: list[str] = Field(default_factory=list)
    source_event_sequence: int | None = Field(default=None, ge=0)
    completed_steps: list[str] = Field(default_factory=list)
    pending_steps: list[str] = Field(default_factory=list)
    blocked_steps: list[str] = Field(default_factory=list)
    report_artifact_ids: list[str] = Field(default_factory=list)
    report_artifact_uris: list[str] = Field(default_factory=list)
    sections: list[AgentRunResearchSectionContext] = Field(default_factory=list)
    evidence: list[AgentRunResearchEvidenceContext] = Field(default_factory=list)
    limitations: list[ResearchLimitation] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    action_hints: list[AgentRunResearchActionContext] = Field(default_factory=list)
    dropped_evidence: int = Field(default=0, ge=0)

    @field_validator("source_run_id")
    @classmethod
    def _source_run_id_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("target_section_ids")
    @classmethod
    def _target_section_ids_must_be_stable_slugs(cls, value: list[str]) -> list[str]:
        section_ids: list[str] = []
        seen: set[str] = set()
        for item in value:
            section_id = item.strip()
            if not section_id:
                raise ValueError("target research section id cannot be blank")
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", section_id):
                raise ValueError("target research section id must be a stable lowercase slug")
            if section_id in seen:
                continue
            section_ids.append(section_id)
            seen.add(section_id)
        return section_ids

    @computed_field
    @property
    def has_truncated_content(self) -> bool:
        return any(item.truncated for item in self.evidence)

    @computed_field
    @property
    def has_dropped_context(self) -> bool:
        return self.dropped_evidence > 0

    def event_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "report_status": self.report_status,
            "evidence": len(self.evidence),
            "limitations": len(self.limitations),
            "sections": len(self.sections),
            "missing_sections": sum(1 for section in self.sections if not section.covered),
            "target_sections": len(self.target_section_ids),
            "action_hints": len(self.action_hints),
            "dropped_evidence": self.dropped_evidence,
        }
        if self.source_run_id is not None:
            payload["source_run_id"] = self.source_run_id
        return payload


class AgentRunResumeContext(AithruBaseModel):
    reason: AgentRunResumeReason
    detail: str

    @classmethod
    def from_run(
        cls,
        run: AgentRun,
        *,
        latest_message: AgentRunContextMessage | None = None,
    ) -> "AgentRunResumeContext | None":
        if run.status == AgentRunStatus.WAITING_INPUT:
            return cls(
                reason="waiting_input",
                detail="The run is paused waiting for user input.",
            )
        if run.status == AgentRunStatus.WAITING_APPROVAL:
            return cls(
                reason="waiting_approval",
                detail="The run is paused waiting for approval.",
            )
        if run.status == AgentRunStatus.WAITING_EXTERNAL_RUN:
            return cls(
                reason="waiting_external_run",
                detail="The run is paused waiting for an external workflow capability run.",
            )
        if run.status == AgentRunStatus.WAITING_SUBAGENT:
            return cls(
                reason="waiting_subagent",
                detail="The run is paused waiting for a subagent result.",
            )
        if latest_message and latest_message.role == "user" and latest_message.run_id == run.id:
            return cls(
                reason="input_received",
                detail="Latest user input is available.",
            )
        return None


class AgentRunContextPacket(AithruBaseModel):
    run_id: str
    thread_id: str | None = None
    skill_id: str | None = None
    goal: str
    status: AgentRunStatus
    resume: AgentRunResumeContext | None = None
    compressed_context: AgentRunCompressedContext | None = None
    budget: AgentRunContextBudgetUsage | None = None
    thread_messages: list[AgentRunContextMessage] = Field(default_factory=list)
    todos: list[AgentRunContextTodo] = Field(default_factory=list)
    artifacts: list[AgentRunContextArtifact] = Field(default_factory=list)
    tool_results: list[AgentRunContextToolResult] = Field(default_factory=list)
    research: AgentRunResearchContinuationContext | None = None
    memory: AgentMemoryRecall | None = None

    @computed_field
    @property
    def counts(self) -> AgentRunContextCounts:
        return AgentRunContextCounts(
            thread_messages=len(self.thread_messages),
            todos=len(self.todos),
            artifacts=len(self.artifacts),
            tool_results=len(self.tool_results),
            memory=self.memory.count if self.memory else 0,
            research_evidence=len(self.research.evidence) if self.research else 0,
        )

    @computed_field
    @property
    def has_context(self) -> bool:
        return bool(
            self.resume
            or self.compressed_context
            or self.thread_messages
            or self.todos
            or self.artifacts
            or self.tool_results
            or self.research
            or (self.memory and self.memory.items)
        )

    @computed_field
    @property
    def has_truncated_content(self) -> bool:
        truncated = any(message.truncated for message in self.thread_messages) or any(
            todo.truncated for todo in self.todos
        ) or any(artifact.truncated for artifact in self.artifacts) or bool(
            self.compressed_context and self.compressed_context.truncated
        ) or any(result.truncated for result in self.tool_results)
        if truncated:
            return True
        if self.research and self.research.has_truncated_content:
            return True
        return bool(self.memory and any(item.truncated for item in self.memory.items))

    @computed_field
    @property
    def has_dropped_context(self) -> bool:
        if not self.budget:
            return False
        return any(
            count > 0
            for count in (
                self.budget.dropped_thread_messages,
                self.budget.dropped_todos,
                self.budget.dropped_artifacts,
                self.budget.dropped_tool_results,
                self.budget.dropped_memory,
                self.budget.dropped_research_evidence,
            )
        )

    def event_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "thread_messages": self.counts.thread_messages,
            "todos": self.counts.todos,
            "artifacts": self.counts.artifacts,
            "tool_results": self.counts.tool_results,
            "memory": self.counts.memory,
            "research_evidence": self.counts.research_evidence,
            "has_truncated_content": self.has_truncated_content,
            "has_dropped_context": self.has_dropped_context,
        }
        if self.research is not None:
            payload["research"] = self.research.event_payload()
        if self.budget is not None:
            payload["budget"] = self.budget.model_dump(mode="json")
        return payload


def _bounded_text(value: str | None, *, max_chars: int) -> tuple[str | None, bool, int]:
    if value is None:
        return None, False, 0
    original_length = len(value)
    if original_length <= max_chars:
        return value, False, original_length
    return value[:max_chars], True, original_length
