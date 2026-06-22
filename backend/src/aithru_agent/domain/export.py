from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .approval import AgentApproval
from .artifact import AgentArtifact
from .base import AithruBaseModel
from .run import AgentRun
from .todo import AgentTodo
from .workspace import AgentWorkspaceFile, AgentWorkspaceSnapshot


AgentRunExportSchemaVersion = Literal["run_export.v1"]


class AgentRunExportSummary(AithruBaseModel):
    run_id: str
    workspace_id: str
    status: str
    event_count: int = Field(ge=0)
    trace_span_count: int = Field(ge=0)
    todo_count: int = Field(ge=0)
    approval_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    workspace_file_count: int = Field(ge=0)


class AgentRunExportBundle(AithruBaseModel):
    schema_version: AgentRunExportSchemaVersion = "run_export.v1"
    exported_at: str
    run: AgentRun
    events: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    todos: list[AgentTodo] = Field(default_factory=list)
    approvals: list[AgentApproval] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    workspace_snapshot: AgentWorkspaceSnapshot
    summary: AgentRunExportSummary

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if self.summary.run_id != self.run.id:
            raise ValueError("export summary run_id must match run id")
        if self.summary.workspace_id != self.run.workspace_id:
            raise ValueError("export summary workspace_id must match run workspace_id")
        if self.summary.event_count != len(self.events):
            raise ValueError("export summary event_count must match events length")
        if self.summary.trace_span_count != len(self.trace):
            raise ValueError("export summary trace_span_count must match trace length")
        if self.summary.todo_count != len(self.todos):
            raise ValueError("export summary todo_count must match todos length")
        if self.summary.approval_count != len(self.approvals):
            raise ValueError("export summary approval_count must match approvals length")
        if self.summary.artifact_count != len(self.artifacts):
            raise ValueError("export summary artifact_count must match artifacts length")
        if self.summary.workspace_file_count != self.workspace_snapshot.file_count:
            raise ValueError("export summary workspace_file_count must match workspace snapshot")
        return self


class AgentRunExportArtifactResult(AithruBaseModel):
    artifact: AgentArtifact
    workspace_file: AgentWorkspaceFile
    export_summary: AgentRunExportSummary
    schema_version: AgentRunExportSchemaVersion = "run_export.v1"
    path: str

    @model_validator(mode="after")
    def validate_pointer(self) -> Self:
        if self.path != self.workspace_file.path:
            raise ValueError("export artifact path must match workspace file path")
        if self.artifact.uri != self.path:
            raise ValueError("export artifact uri must match result path")
        if self.artifact.workspace_id != self.export_summary.workspace_id:
            raise ValueError("export artifact workspace_id must match export summary")
        if self.workspace_file.workspace_id != self.export_summary.workspace_id:
            raise ValueError("workspace file workspace_id must match export summary")
        if self.artifact.run_id != self.export_summary.run_id:
            raise ValueError("export artifact run_id must match export summary")
        return self
