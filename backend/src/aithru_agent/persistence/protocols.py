from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifact,
    AgentMessage,
    AgentMessageRole,
    AgentRun,
    AgentRunSource,
    AgentThread,
    AgentTodo,
    AgentTodoCreatorType,
    AgentTodoStatus,
    AgentWorkspace,
    AgentWorkspaceFile,
)
from aithru_agent.domain.artifact import AgentArtifactType

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

    async def append_message(
        self,
        *,
        thread_id: str,
        role: AgentMessageRole,
        content: str,
        run_id: str | None = None,
        artifact_ids: list[str] | None = None,
    ) -> AgentMessage:
        ...

    async def list_messages(self, thread_id: str) -> list[AgentMessage]:
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
        goal: str,
        workspace_id: str,
        scopes: list[str] | None = None,
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
    ) -> AgentArtifact:
        ...

    async def get_artifact(self, artifact_id: str) -> AgentArtifact | None:
        ...

    async def list_artifacts(self, *, run_id: str | None = None) -> list[AgentArtifact]:
        ...

    async def finalize_artifact(self, artifact_id: str) -> AgentArtifact:
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
