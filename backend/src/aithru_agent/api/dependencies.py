"""Shared API request models and dependency helpers."""

import asyncio
import base64
import binascii
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from aithru_agent.application import AgentRuntime
from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentArtifact,
    AgentArtifactRetentionPolicy,
    AgentArtifactType,
    AgentMemoryEntry,
    AgentMemoryRetentionPolicy,
    AgentMemoryVisibilityPolicy,
    AgentMessageRole,
    AgentMessageAttachment,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunRetryPolicy,
    AgentThread,
    AgentThreadStatus,
    AgentWorkspace,
    AgentWorkspaceTextPatchEdit,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import ContextBuilder
from aithru_agent.skills.resolver import resolve_skill_for_org
from aithru_agent.stream import format_sse_event


class CreateThreadRequest(BaseModel):
    org_id: str = "org_1"
    owner_user_id: str = "user_1"
    title: str | None = None


class UpdateThreadRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    status: AgentThreadStatus = Field(default=None)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateThreadRequest":
        if not self.model_fields_set.intersection({"title", "status"}):
            raise ValueError("at least one thread field must be supplied")
        return self

    def store_updates(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in ("title", "status")
            if field in self.model_fields_set
        }


class AppendMessageRequest(BaseModel):
    role: AgentMessageRole
    content: str = Field(min_length=1)
    attachments: list[AgentMessageAttachment] = Field(default_factory=list)


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_msg: str = Field(min_length=1, validation_alias=AliasChoices("task_msg", "goal"))
    org_id: str = "org_1"
    actor_user_id: str = "user_1"
    scopes: list[str] | None = None
    harness_options: AgentRunHarnessOptions | None = None
    retry_policy: AgentRunRetryPolicy | None = None
    thread_id: str | None = None
    skill_id: str | None = None
    wait_for_completion: bool = False
    persist_task_msg_message: bool = Field(
        default=False,
        validation_alias=AliasChoices("persist_task_msg_message", "persist_goal_message"),
    )


class ResolveApprovalRequest(BaseModel):
    decision: AgentApprovalDecision
    approval_id: str | None = None
    comment: str | None = None


class ResolveExternalApprovalRequest(BaseModel):
    decision: AgentApprovalDecision
    approval_id: str | None = None
    capability_run_id: str | None = None
    comment: str | None = None


class ResolveExternalRunRequest(BaseModel):
    capability_run_id: str = Field(min_length=1)
    status: Literal["completed", "failed", "cancelled"]
    output: Any | None = None
    error: dict | None = None
    comment: str | None = None


class AppendRunInputRequest(BaseModel):
    content: str = Field(min_length=1)


class WriteWorkspaceFileRequest(BaseModel):
    content: str
    media_type: str | None = None


class PatchWorkspaceFileRequest(BaseModel):
    edits: list[AgentWorkspaceTextPatchEdit] = Field(min_length=1)
    media_type: str | None = None


class UploadWorkspaceFileRequest(BaseModel):
    path: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    media_type: str | None = None

    @field_validator("path")
    @classmethod
    def _path_must_be_under_uploads(cls, value: str) -> str:
        normalized = "/" + value.lstrip("/")
        if normalized == "/uploads" or not normalized.startswith("/uploads/"):
            raise ValueError("upload path must be under /uploads")
        return normalized

    @field_validator("content_base64")
    @classmethod
    def _content_must_be_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except binascii.Error as err:
            raise ValueError("content_base64 must be valid base64") from err
        return value

    def content_bytes(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class RestoreWorkspaceSnapshotRequest(BaseModel):
    version: int = Field(ge=0)


class PromoteWorkspaceFileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    type: AgentArtifactType = "file"
    run_id: str | None = None
    retention: AgentArtifactRetentionPolicy | None = None
    metadata: dict | None = None


class CreateRunExportArtifactRequest(BaseModel):
    path: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    retention: AgentArtifactRetentionPolicy | None = None
    metadata: dict | None = None


class CreateMemoryEntryRequest(BaseModel):
    org_id: str = "org_1"
    scope: str
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    scope_id: str | None = None
    owner: str | None = None
    source: str | None = None
    confidence: float | None = None
    visibility: str | None = None
    retention: AgentMemoryRetentionPolicy | None = None


class CreateSubagentSpecRequest(BaseModel):
    org_id: str = "org_1"
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)


class ApiDependencies:
    """Runtime-backed API helper methods shared by route groups."""

    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime
        self.context_builder = ContextBuilder()

    async def require_workspace(self, request: Request, workspace_id: str) -> AgentWorkspace:
        workspace = await self.runtime.store.get_workspace(workspace_id)
        if not workspace or not await self.workspace_visible(request, workspace):
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    async def require_thread(self, request: Request, thread_id: str) -> AgentThread:
        thread = await self.runtime.store.get_thread(thread_id)
        if not thread or not thread_visible(request, thread):
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread

    async def require_run(self, request: Request, run_id: str) -> AgentRun:
        run = await self.runtime.store.get_run(run_id)
        if not run or not run_visible(request, run):
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    async def require_thread_run(self, request: Request, thread_id: str, run_id: str) -> AgentRun:
        await self.require_thread(request, thread_id)
        run = await self.require_run(request, run_id)
        if run.thread_id != thread_id:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    async def workspace_visible(self, request: Request, workspace: AgentWorkspace) -> bool:
        if not org_visible(request, workspace.org_id):
            return False
        if workspace.run_id:
            run = await self.runtime.store.get_run(workspace.run_id)
            return run is not None and run_visible(request, run)
        if workspace.thread_id:
            thread = await self.runtime.store.get_thread(workspace.thread_id)
            return thread is not None and thread_visible(request, thread)
        return True

    async def approval_visible(self, request: Request, approval: AgentApproval) -> bool:
        run = await self.runtime.store.get_run(approval.run_id)
        return run is not None and run_visible(request, run)

    async def require_approval(self, request: Request, approval_id: str) -> AgentApproval:
        approval = await self.runtime.store.get_approval(approval_id)
        if not approval or not await self.approval_visible(request, approval):
            raise HTTPException(status_code=404, detail="Approval not found")
        return approval

    async def artifact_visible(self, request: Request, artifact: AgentArtifact) -> bool:
        if not org_visible(request, artifact.org_id):
            return False
        if artifact.run_id:
            run = await self.runtime.store.get_run(artifact.run_id)
            return run is not None and run_visible(request, run)
        workspace = await self.runtime.store.get_workspace(artifact.workspace_id)
        return workspace is not None and await self.workspace_visible(request, workspace)

    async def require_artifact(self, request: Request, artifact_id: str) -> AgentArtifact:
        artifact = await self.runtime.store.get_artifact(artifact_id)
        if not artifact or not await self.artifact_visible(request, artifact):
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    def resolve_run_skill(self, run: AgentRun):
        if not run.skill_id:
            return None
        skill = resolve_skill_for_org(self.runtime.skill_resolver, run.org_id, run.skill_id)
        if not skill:
            raise HTTPException(status_code=409, detail=f"Skill not found: {run.skill_id}")
        return skill

    async def follow_run_events(
        self,
        run_id: str,
        *,
        after_sequence: int,
        poll_interval_seconds: float,
        timeout_seconds: float,
    ) -> AsyncIterator[str]:
        cursor = after_sequence
        interval = max(0.01, poll_interval_seconds)
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout_seconds)
        while True:
            if await self._has_terminal_run_event_at_or_before(run_id, cursor):
                break
            events = await self.runtime.event_store.list_after_sequence(run_id, cursor)
            if events:
                saw_terminal_event = False
                for event in events:
                    cursor = event.sequence
                    yield format_sse_event(event)
                    if event.type in TERMINAL_RUN_EVENT_TYPES:
                        saw_terminal_event = True
                if saw_terminal_event:
                    break
                continue

            run = await self.runtime.store.get_run(run_id)
            if run is None:
                break
            if asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(interval)

    async def _has_terminal_run_event_at_or_before(self, run_id: str, sequence: int) -> bool:
        if sequence <= 0:
            return False
        return any(
            event.sequence <= sequence and event.type in TERMINAL_RUN_EVENT_TYPES
            for event in await self.runtime.event_store.list_by_run(run_id)
        )

    async def wait_for_run(
        self,
        run_id: str,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> AgentRun:
        try:
            return await self.runtime.runner.join_run(
                run_id,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
        except AgentError as err:
            if err.code == "NOT_FOUND":
                raise HTTPException(status_code=404, detail=err.message) from err
            if err.code == "RUN_JOIN_TIMEOUT":
                raise HTTPException(status_code=408, detail=err.message) from err
            raise HTTPException(status_code=409, detail=err.message) from err


TERMINAL_RUN_EVENT_TYPES = frozenset({"run.completed", "run.failed", "run.cancelled"})


def api_deps(request: Request) -> ApiDependencies:
    return request.app.state.aithru_api


def scopes_allowed(requested: list[str], allowed: list[str]) -> bool:
    if "*" in allowed:
        return True
    return all(scope in allowed for scope in requested)


def identity_value(
    request: Request,
    body: BaseModel,
    field_name: str,
    body_value: str,
    header_name: str,
) -> str:
    header_value = request.headers.get(header_name)
    if header_value is None:
        return body_value
    if field_name in body.model_fields_set and body_value != header_value:
        raise HTTPException(status_code=403, detail="Request identity conflicts with authenticated context")
    return header_value


def identity_query_value(
    request: Request,
    query_value: str | None,
    default_value: str,
    header_name: str,
) -> str:
    header_value = request.headers.get(header_name)
    if header_value is None:
        return query_value or default_value
    if query_value is not None and query_value != header_value:
        raise HTTPException(status_code=403, detail="Request identity conflicts with authenticated context")
    return header_value


def memory_scope_id_for_request(request: Request, scope: str | None, scope_id: str | None) -> str | None:
    if scope != "user":
        return scope_id
    trusted_user_id = request.headers.get("x-aithru-user-id")
    if trusted_user_id is None:
        return scope_id
    if scope_id is not None and scope_id != trusted_user_id:
        raise HTTPException(status_code=403, detail="Request identity conflicts with authenticated context")
    return trusted_user_id


def filter_memory_entries_for_request(
    request: Request,
    entries: list[AgentMemoryEntry],
) -> list[AgentMemoryEntry]:
    trusted_user_id = request.headers.get("x-aithru-user-id")
    visibility_policy = AgentMemoryVisibilityPolicy(actor_user_id=trusted_user_id)
    return [
        entry
        for entry in entries
        if (trusted_user_id is None or entry.scope != "user" or entry.scope_id == trusted_user_id)
        and visibility_policy.allows(entry)
    ]


def thread_visible(request: Request, thread: AgentThread) -> bool:
    user_id = request.headers.get("x-aithru-user-id")
    if not org_visible(request, thread.org_id):
        return False
    if user_id is not None and thread.owner_user_id != user_id:
        return False
    return True


def run_visible(request: Request, run: AgentRun) -> bool:
    user_id = request.headers.get("x-aithru-user-id")
    if not org_visible(request, run.org_id):
        return False
    if user_id is not None and run.actor_user_id != user_id:
        return False
    return True


def org_visible(request: Request, org_id: str) -> bool:
    trusted_org_id = request.headers.get("x-aithru-org-id")
    return trusted_org_id is None or org_id == trusted_org_id


def dump_model(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json")
