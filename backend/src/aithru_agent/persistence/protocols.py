from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifact,
    AgentArtifactPromotionResult,
    AgentArtifactRetentionPolicy,
    AgentContextSummary,
    AgentMemoryCandidate,
    AgentMemoryCandidateApprovalResult,
    AgentMemoryCandidateStatus,
    AgentMemoryEntry,
    AgentMemoryForgetResult,
    AgentMemoryRetentionPolicy,
    AgentMessage,
    AgentMessageAttachment,
    AgentMessageRole,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunRetryPolicy,
    AgentRunSource,
    AgentSubagentRun,
    AgentSubagentSpec,
    AgentThread,
    AgentThreadStatus,
    AgentTodo,
    AgentTodoCreatorType,
    AgentTodoStatus,
    AgentWorkspace,
    AgentWorkspaceDiff,
    AgentWorkspaceFile,
    AgentWorkspaceFileVersion,
    AgentWorkspaceRestoreResult,
    AgentWorkspaceSnapshot,
)
from aithru_agent.domain.artifact import AgentArtifactRetentionMode, AgentArtifactType

if TYPE_CHECKING:
    from aithru_agent.stream.events import AgentStreamEvent


class WorkspaceFileContent(BaseModel):
    content: str | bytes
    media_type: str | None = None


StoreUpdate = dict[str, Any]


@runtime_checkable
class AgentStore(Protocol):
    async def create_thread(
        self,
        *,
        org_id: str,
        owner_user_id: str,
        title: str | None = None,
    ) -> AgentThread:
        ...

    async def get_thread(self, thread_id: str) -> AgentThread | None:
        ...

    async def list_threads(self) -> list[AgentThread]:
        ...

    async def update_thread(
        self,
        thread_id: str,
        **updates: AgentThreadStatus | str | object,
    ) -> AgentThread:
        ...

    async def append_message(
        self,
        *,
        thread_id: str,
        role: AgentMessageRole,
        content: str,
        run_id: str | None = None,
        artifact_ids: list[str] | None = None,
        attachments: list[AgentMessageAttachment] | None = None,
    ) -> AgentMessage:
        ...

    async def list_messages(self, thread_id: str) -> list[AgentMessage]:
        ...

    async def create_context_summary(
        self,
        summary: AgentContextSummary,
    ) -> AgentContextSummary:
        ...

    async def list_context_summaries(
        self,
        *,
        org_id: str,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> list[AgentContextSummary]:
        ...

    async def create_workspace(
        self,
        *,
        org_id: str,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> AgentWorkspace:
        ...

    async def get_workspace(self, workspace_id: str) -> AgentWorkspace | None:
        ...

    async def create_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        source: AgentRunSource | str,
        task_msg: str,
        workspace_id: str,
        scopes: list[str] | None = None,
        harness_options: AgentRunHarnessOptions | None = None,
        retry_policy: AgentRunRetryPolicy | None = None,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        ...

    async def get_run(self, run_id: str) -> AgentRun | None:
        ...

    async def list_runs(self) -> list[AgentRun]:
        ...

    async def update_run(self, run_id: str, **updates: object) -> AgentRun:
        ...

    async def claim_run(
        self,
        run_id: str,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        ...

    async def claim_next_queued_run(
        self,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        ...

    async def renew_run_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        heartbeat_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        ...

    async def create_todo(
        self,
        *,
        run_id: str,
        title: str,
        status: AgentTodoStatus | str = AgentTodoStatus.PENDING,
        description: str | None = None,
        created_by: AgentTodoCreatorType | Literal["agent", "user", "system"] = "agent",
    ) -> AgentTodo:
        ...

    async def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: AgentTodoStatus | str | None = None,
    ) -> AgentTodo:
        ...

    async def list_todos(self, run_id: str) -> list[AgentTodo]:
        ...

    async def create_approval(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_input: dict | None = None,
        metadata: dict | None = None,
    ) -> AgentApproval:
        ...

    async def get_approval(self, approval_id: str) -> AgentApproval | None:
        ...

    async def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | str | None = None,
    ) -> list[AgentApproval]:
        ...

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentApproval:
        ...

    async def write_workspace_file(
        self,
        *,
        workspace_id: str,
        path: str,
        content: str | bytes,
        media_type: str | None = None,
    ) -> AgentWorkspaceFile:
        ...

    async def read_workspace_file(self, workspace_id: str, path: str) -> WorkspaceFileContent:
        ...

    async def list_workspace_files(self, workspace_id: str) -> list[AgentWorkspaceFile]:
        ...

    async def list_workspace_file_versions(
        self,
        *,
        workspace_id: str,
        path: str | None = None,
    ) -> list[AgentWorkspaceFileVersion]:
        ...

    async def get_workspace_snapshot(
        self,
        workspace_id: str,
        *,
        version: int | None = None,
    ) -> AgentWorkspaceSnapshot:
        ...

    async def diff_workspace_snapshots(
        self,
        *,
        workspace_id: str,
        base_version: int | None = None,
        target_version: int | None = None,
    ) -> AgentWorkspaceDiff:
        ...

    async def restore_workspace_snapshot(
        self,
        workspace_id: str,
        *,
        version: int,
    ) -> AgentWorkspaceRestoreResult:
        ...

    async def delete_workspace_file(self, workspace_id: str, path: str) -> dict[str, str]:
        ...

    async def create_artifact(
        self,
        *,
        org_id: str,
        workspace_id: str,
        run_id: str | None,
        type: AgentArtifactType,
        name: str,
        media_type: str | None = None,
        uri: str | None = None,
        content: object | None = None,
        metadata: dict | None = None,
        retention: AgentArtifactRetentionPolicy | None = None,
    ) -> AgentArtifact:
        ...

    async def promote_workspace_file_to_artifact(
        self,
        *,
        org_id: str,
        workspace_id: str,
        path: str,
        name: str,
        type: AgentArtifactType = "file",
        run_id: str | None = None,
        retention: AgentArtifactRetentionPolicy | None = None,
        metadata: dict | None = None,
    ) -> AgentArtifactPromotionResult:
        ...

    async def get_artifact(self, artifact_id: str) -> AgentArtifact | None:
        ...

    async def list_artifacts(
        self,
        *,
        run_id: str | None = None,
        workspace_id: str | None = None,
        type: AgentArtifactType | None = None,
        retention_mode: AgentArtifactRetentionMode | None = None,
        finalized: bool | None = None,
    ) -> list[AgentArtifact]:
        ...

    async def finalize_artifact(self, artifact_id: str) -> AgentArtifact:
        ...

    async def create_memory_entry(
        self,
        *,
        org_id: str,
        scope: str,
        key: str,
        value: str,
        scope_id: str | None = None,
        owner: str | None = None,
        source: str | None = None,
        confidence: float | None = None,
        visibility: str | None = None,
        retention: AgentMemoryRetentionPolicy | dict[str, object] | str | None = None,
    ) -> AgentMemoryEntry:
        ...

    async def get_memory_entry(self, memory_id: str) -> AgentMemoryEntry | None:
        ...

    async def list_memory_entries(
        self,
        *,
        org_id: str,
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        include_expired: bool = False,
    ) -> list[AgentMemoryEntry]:
        ...

    async def delete_memory_entry(self, memory_id: str) -> AgentMemoryForgetResult:
        ...

    async def create_memory_candidate(
        self,
        candidate: AgentMemoryCandidate,
    ) -> AgentMemoryCandidate:
        ...

    async def get_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str | None = None,
    ) -> AgentMemoryCandidate | None:
        ...

    async def list_memory_candidates(
        self,
        *,
        org_id: str,
        status: AgentMemoryCandidateStatus | str | None = None,
        run_id: str | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
    ) -> list[AgentMemoryCandidate]:
        ...

    async def update_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str,
        status: AgentMemoryCandidateStatus | str | None = None,
        resolved_at: str | None = None,
        expected_status: AgentMemoryCandidateStatus | str | None = None,
    ) -> AgentMemoryCandidate:
        ...

    async def approve_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str,
        owner: str | None = None,
        resolved_at: str | None = None,
    ) -> AgentMemoryCandidateApprovalResult:
        ...

    async def create_subagent_spec(
        self,
        *,
        org_id: str,
        key: str,
        name: str,
        instructions: str,
        allowed_tools: list[str] | None = None,
    ) -> AgentSubagentSpec:
        ...

    async def get_subagent_spec(self, org_id: str, key: str) -> AgentSubagentSpec | None:
        ...

    async def list_subagent_specs(self, org_id: str) -> list[AgentSubagentSpec]:
        ...

    async def create_subagent_run(
        self,
        *,
        org_id: str,
        parent_run_id: str,
        child_run_id: str,
        name: str,
        task: str,
        spec_key: str | None = None,
    ) -> AgentSubagentRun:
        ...

    async def get_subagent_run(self, subagent_run_id: str) -> AgentSubagentRun | None:
        ...

    async def list_subagent_runs(
        self,
        *,
        parent_run_id: str | None = None,
        child_run_id: str | None = None,
    ) -> list[AgentSubagentRun]:
        ...

    async def update_subagent_run(
        self,
        subagent_run_id: str,
        **updates: object,
    ) -> AgentSubagentRun:
        ...


@runtime_checkable
class AgentEventStore(Protocol):
    async def append(self, event: AgentStreamEvent) -> None:
        ...

    async def list_by_run(self, run_id: str) -> list[AgentStreamEvent]:
        ...

    async def list_after_sequence(self, run_id: str, after_sequence: int) -> list[AgentStreamEvent]:
        ...

    async def next_sequence(self, run_id: str) -> int:
        ...
