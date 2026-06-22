from collections import defaultdict
from datetime import UTC, datetime
import hashlib
from typing import Literal

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifact,
    AgentArtifactPromotionResult,
    AgentArtifactRetentionPolicy,
    AgentContextSummary,
    AgentMemoryCandidate,
    AgentMemoryCandidateStatus,
    AgentMemoryEntry,
    AgentMemoryForgetResult,
    AgentMemoryRetentionPolicy,
    AgentMessage,
    AgentRun,
    AgentRunClaim,
    AgentRunHarnessOptions,
    AgentRunRetryPolicy,
    AgentRunSource,
    AgentRunStatus,
    AgentSubagentRun,
    AgentSubagentRunStatus,
    AgentSubagentSpec,
    AgentThread,
    AgentThreadStatus,
    AgentTodo,
    AgentTodoStatus,
    AgentWorkspace,
    AgentWorkspaceDiff,
    AgentWorkspaceFile,
    AgentWorkspaceFileDiff,
    AgentWorkspaceFileVersion,
    AgentWorkspaceRestoreChange,
    AgentWorkspaceRestoreResult,
    AgentWorkspaceSnapshot,
    AgentWorkspaceSnapshotFile,
    validate_run_status_transition,
)
from aithru_agent.domain.artifact import AgentArtifactRetentionMode, AgentArtifactType
from aithru_agent.domain.errors import AgentError
from aithru_agent.domain.message import AgentMessageRole
from aithru_agent.persistence.protocols import WorkspaceFileContent


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_path(raw: str) -> str:
    normalized = raw.replace("\\", "/")
    parts: list[str] = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                raise AgentError("PATH_TRAVERSAL_DENIED", f"Path traverses above root: {raw}")
            parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _content_hash(content: str | bytes) -> str:
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _artifact_retention_mode(artifact: AgentArtifact) -> AgentArtifactRetentionMode:
    if artifact.retention is None:
        return "retained"
    return artifact.retention.mode


def _memory_retention_policy(
    retention: AgentMemoryRetentionPolicy | dict[str, object] | str | None,
) -> AgentMemoryRetentionPolicy | None:
    if retention is None:
        return None
    if isinstance(retention, AgentMemoryRetentionPolicy):
        return retention
    if isinstance(retention, str):
        return AgentMemoryRetentionPolicy(mode=retention)
    return AgentMemoryRetentionPolicy.model_validate(retention)


def _artifact_matches_filters(
    artifact: AgentArtifact,
    *,
    run_id: str | None = None,
    workspace_id: str | None = None,
    type: AgentArtifactType | None = None,
    retention_mode: AgentArtifactRetentionMode | None = None,
    finalized: bool | None = None,
) -> bool:
    if run_id is not None and artifact.run_id != run_id:
        return False
    if workspace_id is not None and artifact.workspace_id != workspace_id:
        return False
    if type is not None and artifact.type != type:
        return False
    if retention_mode is not None and _artifact_retention_mode(artifact) != retention_mode:
        return False
    if finalized is not None and (artifact.finalized_at is not None) != finalized:
        return False
    return True


def _build_workspace_snapshot(
    *,
    workspace_id: str,
    version: int,
    versions: list[AgentWorkspaceFileVersion],
) -> AgentWorkspaceSnapshot:
    files: dict[str, AgentWorkspaceSnapshotFile] = {}
    created_at = utc_now()
    for file_version in sorted(versions, key=lambda item: item.version):
        if file_version.version > version:
            continue
        if file_version.operation == "delete":
            files.pop(file_version.path, None)
            continue
        existing = files.get(file_version.path)
        files[file_version.path] = AgentWorkspaceSnapshotFile(
            workspace_id=workspace_id,
            path=file_version.path,
            size=file_version.size,
            media_type=file_version.media_type,
            content_hash=file_version.content_hash,
            version=file_version.version,
            file_version=file_version.file_version,
            created_at=existing.created_at if existing else file_version.created_at,
            updated_at=file_version.created_at,
        )
    snapshot_files = [files[path] for path in sorted(files)]
    return AgentWorkspaceSnapshot(
        workspace_id=workspace_id,
        version=version,
        files=snapshot_files,
        file_count=len(snapshot_files),
        total_size=sum(file.size for file in snapshot_files),
        created_at=created_at,
    )


def _diff_workspace_snapshots(
    base: AgentWorkspaceSnapshot,
    target: AgentWorkspaceSnapshot,
) -> AgentWorkspaceDiff:
    base_files = {file.path: file for file in base.files}
    target_files = {file.path: file for file in target.files}
    changes: list[AgentWorkspaceFileDiff] = []
    for path in sorted(set(base_files) | set(target_files)):
        base_file = base_files.get(path)
        target_file = target_files.get(path)
        if base_file is None and target_file is not None:
            changes.append(
                AgentWorkspaceFileDiff(
                    path=path,
                    operation="added",
                    base_version=None,
                    target_version=target_file.version,
                    base_size=None,
                    target_size=target_file.size,
                    base_hash=None,
                    target_hash=target_file.content_hash,
                )
            )
            continue
        if base_file is not None and target_file is None:
            changes.append(
                AgentWorkspaceFileDiff(
                    path=path,
                    operation="deleted",
                    base_version=base_file.version,
                    target_version=None,
                    base_size=base_file.size,
                    target_size=None,
                    base_hash=base_file.content_hash,
                    target_hash=None,
                )
            )
            continue
        if base_file is None or target_file is None:
            continue
        if (
            base_file.content_hash,
            base_file.size,
            base_file.media_type,
        ) != (
            target_file.content_hash,
            target_file.size,
            target_file.media_type,
        ):
            changes.append(
                AgentWorkspaceFileDiff(
                    path=path,
                    operation="modified",
                    base_version=base_file.version,
                    target_version=target_file.version,
                    base_size=base_file.size,
                    target_size=target_file.size,
                    base_hash=base_file.content_hash,
                    target_hash=target_file.content_hash,
                )
            )
    return AgentWorkspaceDiff(
        workspace_id=target.workspace_id,
        base_version=base.version,
        target_version=target.version,
        changes=changes,
        added_count=sum(1 for change in changes if change.operation == "added"),
        modified_count=sum(1 for change in changes if change.operation == "modified"),
        deleted_count=sum(1 for change in changes if change.operation == "deleted"),
    )


def _snapshot_files_match(
    source: AgentWorkspaceSnapshotFile,
    target: AgentWorkspaceSnapshotFile,
) -> bool:
    return (
        source.content_hash,
        source.size,
        source.media_type,
    ) == (
        target.content_hash,
        target.size,
        target.media_type,
    )


def _run_claimable(run: AgentRun, claimed_at: str | None) -> bool:
    if run.status == AgentRunStatus.QUEUED:
        return run.retry_state is None or run.retry_state.ready_for_claim_at(claimed_at)
    return run.status == AgentRunStatus.RUNNING and (
        run.claim is None or run.claim.expired_at(claimed_at)
    )


def _run_claim_renewable(
    run: AgentRun,
    worker_id: str,
    heartbeat_at: str | None,
) -> bool:
    return (
        run.status == AgentRunStatus.RUNNING
        and run.claim is not None
        and run.claim.worker_id == worker_id
        and not run.claim.expired_at(heartbeat_at)
    )


class IdFactory:
    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)

    def next(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]}"


class InMemoryAgentStore:
    def __init__(self) -> None:
        self._ids = IdFactory()
        self._threads: dict[str, AgentThread] = {}
        self._messages: dict[str, AgentMessage] = {}
        self._messages_by_thread: dict[str, list[str]] = defaultdict(list)
        self._context_summaries: dict[str, AgentContextSummary] = {}
        self._runs: dict[str, AgentRun] = {}
        self._todos: dict[str, AgentTodo] = {}
        self._todos_by_run: dict[str, list[str]] = defaultdict(list)
        self._approvals: dict[str, AgentApproval] = {}
        self._workspaces: dict[str, AgentWorkspace] = {}
        self._workspace_files: dict[tuple[str, str], tuple[AgentWorkspaceFile, WorkspaceFileContent]] = {}
        self._workspace_file_versions: list[AgentWorkspaceFileVersion] = []
        self._workspace_version_contents: dict[tuple[str, int], WorkspaceFileContent] = {}
        self._artifacts: dict[str, AgentArtifact] = {}
        self._memory_entries: dict[str, AgentMemoryEntry] = {}
        self._memory_candidates: dict[str, AgentMemoryCandidate] = {}
        self._subagent_specs: dict[str, AgentSubagentSpec] = {}
        self._subagent_runs: dict[str, AgentSubagentRun] = {}

    async def create_thread(
        self,
        *,
        org_id: str,
        owner_user_id: str,
        title: str | None = None,
    ) -> AgentThread:
        now = utc_now()
        thread = AgentThread(
            id=self._ids.next("thread"),
            org_id=org_id,
            owner_user_id=owner_user_id,
            title=title,
            status=AgentThreadStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._threads[thread.id] = thread
        return thread

    async def get_thread(self, thread_id: str) -> AgentThread | None:
        return self._threads.get(thread_id)

    async def list_threads(self) -> list[AgentThread]:
        return list(self._threads.values())

    async def update_thread(self, thread_id: str, **updates: object) -> AgentThread:
        thread = self._threads.get(thread_id)
        if thread is None:
            raise AgentError("NOT_FOUND", f"Thread not found: {thread_id}")
        allowed = {"title", "status"}
        unexpected = set(updates) - allowed
        if unexpected:
            raise AgentError(
                "INVALID_THREAD_UPDATE",
                f"Unsupported thread update field: {sorted(unexpected)[0]}",
            )
        model_updates: dict[str, object] = {}
        if "title" in updates:
            title = updates["title"]
            if title is not None and not isinstance(title, str):
                raise AgentError("INVALID_THREAD_UPDATE", "Thread title must be a string or null")
            model_updates["title"] = title
        if "status" in updates:
            model_updates["status"] = AgentThreadStatus(str(updates["status"]))
        if not model_updates:
            return thread
        updated = thread.model_copy(update={**model_updates, "updated_at": utc_now()})
        self._threads[thread_id] = updated
        return updated

    async def append_message(
        self,
        *,
        thread_id: str,
        role: AgentMessageRole,
        content: str,
        run_id: str | None = None,
        artifact_ids: list[str] | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            id=self._ids.next("msg"),
            thread_id=thread_id,
            role=role,
            content=content,
            run_id=run_id,
            artifact_ids=artifact_ids or [],
            created_at=utc_now(),
        )
        self._messages[message.id] = message
        self._messages_by_thread[thread_id].append(message.id)
        return message

    async def list_messages(self, thread_id: str) -> list[AgentMessage]:
        return [
            self._messages[message_id]
            for message_id in self._messages_by_thread.get(thread_id, [])
        ]

    async def create_context_summary(
        self,
        summary: AgentContextSummary,
    ) -> AgentContextSummary:
        self._context_summaries[summary.id] = summary
        return summary

    async def list_context_summaries(
        self,
        *,
        org_id: str,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> list[AgentContextSummary]:
        summaries = [
            summary
            for summary in self._context_summaries.values()
            if summary.org_id == org_id
            and (thread_id is None or summary.thread_id == thread_id)
            and (run_id is None or summary.run_id == run_id)
        ]
        return sorted(summaries, key=lambda summary: (summary.created_at, summary.id))

    async def create_workspace(
        self,
        *,
        org_id: str,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> AgentWorkspace:
        workspace = AgentWorkspace(
            id=self._ids.next("ws"),
            org_id=org_id,
            thread_id=thread_id,
            run_id=run_id,
            storage_backend="memory",
            created_at=utc_now(),
        )
        self._workspaces[workspace.id] = workspace
        return workspace

    async def get_workspace(self, workspace_id: str) -> AgentWorkspace | None:
        return self._workspaces.get(workspace_id)

    async def create_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        source: AgentRunSource | str,
        goal: str,
        workspace_id: str,
        scopes: list[str] | None = None,
        harness_options: AgentRunHarnessOptions | None = None,
        retry_policy: AgentRunRetryPolicy | None = None,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=self._ids.next("run"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            source=source,
            thread_id=thread_id,
            skill_id=skill_id,
            workspace_id=workspace_id,
            goal=goal,
            scopes=scopes or [],
            harness_options=harness_options,
            retry_policy=retry_policy,
            status=AgentRunStatus.QUEUED,
            started_at=utc_now(),
        )
        self._runs[run.id] = run
        return run

    async def get_run(self, run_id: str) -> AgentRun | None:
        return self._runs.get(run_id)

    async def list_runs(self) -> list[AgentRun]:
        return list(self._runs.values())

    async def update_run(self, run_id: str, **updates: object) -> AgentRun:
        run = self._runs.get(run_id)
        if not run:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        updates_for_model = dict(updates)
        if "status" in updates_for_model:
            updates_for_model["status"] = validate_run_status_transition(
                run.status,
                updates_for_model["status"],
            )
            if updates_for_model["status"] != AgentRunStatus.RUNNING:
                updates_for_model["claim"] = None
        updated = AgentRun.model_validate({**run.model_dump(mode="python"), **updates_for_model})
        self._runs[run_id] = updated
        return updated

    async def claim_run(
        self,
        run_id: str,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        run = self._runs.get(run_id)
        if run is None or not _run_claimable(run, claimed_at):
            return None
        previous_attempt = run.claim.attempt if run.claim else 0
        updated = run.model_copy(
            update={
                "status": validate_run_status_transition(
                    run.status,
                    AgentRunStatus.RUNNING,
                ),
                "claim": AgentRunClaim.create(
                    worker_id=worker_id,
                    claimed_at=claimed_at,
                    lease_seconds=lease_seconds,
                    previous_attempt=previous_attempt,
                ),
            }
        )
        self._runs[run_id] = updated
        return updated

    async def claim_next_queued_run(
        self,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        for status in (AgentRunStatus.QUEUED, AgentRunStatus.RUNNING):
            for run in self._runs.values():
                if run.status == status:
                    claimed = await self.claim_run(
                        run.id,
                        worker_id=worker_id,
                        claimed_at=claimed_at,
                        lease_seconds=lease_seconds,
                    )
                    if claimed is not None:
                        return claimed
        return None

    async def renew_run_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        heartbeat_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        run = self._runs.get(run_id)
        if run is None or not _run_claim_renewable(run, worker_id, heartbeat_at):
            return None
        updated = run.model_copy(
            update={"claim": run.claim.renew(heartbeat_at=heartbeat_at, lease_seconds=lease_seconds)}
        )
        self._runs[run_id] = updated
        return updated

    async def create_todo(
        self,
        *,
        run_id: str,
        title: str,
        status: AgentTodoStatus | str = AgentTodoStatus.PENDING,
        description: str | None = None,
        created_by: Literal["agent", "user", "system"] = "agent",
    ) -> AgentTodo:
        order = len(self._todos_by_run.get(run_id, [])) + 1
        todo = AgentTodo(
            id=self._ids.next("todo"),
            run_id=run_id,
            title=title,
            description=description,
            status=status,
            created_by=created_by,
            order=order,
        )
        self._todos[todo.id] = todo
        self._todos_by_run[run_id].append(todo.id)
        return todo

    async def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: AgentTodoStatus | str | None = None,
    ) -> AgentTodo:
        todo = self._todos.get(todo_id)
        if not todo:
            raise AgentError("NOT_FOUND", f"Todo not found: {todo_id}")
        updates = {
            key: value
            for key, value in {
                "title": title,
                "description": description,
                "status": status,
            }.items()
            if value is not None
        }
        updated = todo.model_copy(update=updates)
        self._todos[todo_id] = updated
        return updated

    async def list_todos(self, run_id: str) -> list[AgentTodo]:
        return [self._todos[todo_id] for todo_id in self._todos_by_run.get(run_id, [])]

    async def create_approval(
        self,
        *,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_input: dict | None = None,
        metadata: dict | None = None,
    ) -> AgentApproval:
        approval = AgentApproval(
            id=self._ids.next("approval"),
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_input=tool_input,
            status=AgentApprovalStatus.PENDING,
            decision=None,
            metadata=metadata,
            created_at=utc_now(),
        )
        self._approvals[approval.id] = approval
        return approval

    async def get_approval(self, approval_id: str) -> AgentApproval | None:
        return self._approvals.get(approval_id)

    async def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | str | None = None,
    ) -> list[AgentApproval]:
        approvals = list(self._approvals.values())
        if status is None:
            return approvals
        return [approval for approval in approvals if approval.status == status]

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentApproval:
        approval = self._approvals.get(approval_id)
        if not approval:
            raise AgentError("APPROVAL_NOT_FOUND", f"Approval not found: {approval_id}")
        resolved = approval.model_copy(
            update={
                "status": AgentApprovalStatus.RESOLVED,
                "decision": decision,
                "comment": comment,
                "resolved_at": utc_now(),
            }
        )
        self._approvals[approval_id] = resolved
        return resolved

    async def write_workspace_file(
        self,
        *,
        workspace_id: str,
        path: str,
        content: str | bytes,
        media_type: str | None = None,
    ) -> AgentWorkspaceFile:
        safe_path = normalize_path(path)
        key = (workspace_id, safe_path)
        now = utc_now()
        existing = self._workspace_files.get(key)
        workspace_version = self._next_workspace_version(workspace_id)
        file_version = self._next_workspace_file_version(workspace_id, safe_path)
        content_hash = _content_hash(content)
        file = AgentWorkspaceFile(
            workspace_id=workspace_id,
            path=safe_path,
            size=len(content.encode("utf-8")) if isinstance(content, str) else len(content),
            media_type=media_type,
            version=workspace_version,
            file_version=file_version,
            content_hash=content_hash,
            created_at=existing[0].created_at if existing else now,
            updated_at=now,
        )
        self._workspace_file_versions.append(
            AgentWorkspaceFileVersion(
                workspace_id=workspace_id,
                path=safe_path,
                version=workspace_version,
                file_version=file_version,
                operation="write",
                size=file.size,
                media_type=media_type,
                content_hash=content_hash,
                created_at=now,
            )
        )
        self._workspace_version_contents[(workspace_id, workspace_version)] = WorkspaceFileContent(
            content=content,
            media_type=media_type,
        )
        self._workspace_files[key] = (
            file,
            WorkspaceFileContent(content=content, media_type=media_type),
        )
        return file

    async def read_workspace_file(self, workspace_id: str, path: str) -> WorkspaceFileContent:
        key = (workspace_id, normalize_path(path))
        record = self._workspace_files.get(key)
        if not record:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        return record[1]

    async def list_workspace_files(self, workspace_id: str) -> list[AgentWorkspaceFile]:
        return [
            file
            for (stored_workspace_id, _), (file, _) in self._workspace_files.items()
            if stored_workspace_id == workspace_id
        ]

    async def list_workspace_file_versions(
        self,
        *,
        workspace_id: str,
        path: str | None = None,
    ) -> list[AgentWorkspaceFileVersion]:
        safe_path = normalize_path(path) if path else None
        return [
            version
            for version in sorted(self._workspace_file_versions, key=lambda item: item.version)
            if version.workspace_id == workspace_id and (safe_path is None or version.path == safe_path)
        ]

    async def get_workspace_snapshot(
        self,
        workspace_id: str,
        *,
        version: int | None = None,
    ) -> AgentWorkspaceSnapshot:
        target_version = version if version is not None else self._latest_workspace_version(workspace_id)
        return _build_workspace_snapshot(
            workspace_id=workspace_id,
            version=target_version,
            versions=await self.list_workspace_file_versions(workspace_id=workspace_id),
        )

    async def diff_workspace_snapshots(
        self,
        *,
        workspace_id: str,
        base_version: int | None = None,
        target_version: int | None = None,
    ) -> AgentWorkspaceDiff:
        target = target_version if target_version is not None else self._latest_workspace_version(workspace_id)
        base = base_version if base_version is not None else 0
        base_snapshot = await self.get_workspace_snapshot(workspace_id, version=base)
        target_snapshot = await self.get_workspace_snapshot(workspace_id, version=target)
        return _diff_workspace_snapshots(base_snapshot, target_snapshot)

    async def restore_workspace_snapshot(
        self,
        workspace_id: str,
        *,
        version: int,
    ) -> AgentWorkspaceRestoreResult:
        target_snapshot = await self.get_workspace_snapshot(workspace_id, version=version)
        current_snapshot = await self.get_workspace_snapshot(workspace_id)
        target_files = {file.path: file for file in target_snapshot.files}
        current_files = {file.path: file for file in current_snapshot.files}
        changes: list[AgentWorkspaceRestoreChange] = []

        for path in sorted(current_files.keys() - target_files.keys()):
            source = current_files[path]
            deleted = await self.delete_workspace_file(workspace_id, path)
            del deleted
            latest_version = self._latest_workspace_version(workspace_id)
            changes.append(
                AgentWorkspaceRestoreChange(
                    path=path,
                    operation="deleted",
                    source_version=source.version,
                    target_version=None,
                    new_version=latest_version,
                )
            )

        for path in sorted(target_files):
            target = target_files[path]
            source = current_files.get(path)
            if source is not None and _snapshot_files_match(source, target):
                changes.append(
                    AgentWorkspaceRestoreChange(
                        path=path,
                        operation="unchanged",
                        source_version=source.version,
                        target_version=target.version,
                        new_version=None,
                    )
                )
                continue
            content = self._workspace_version_contents.get((workspace_id, target.version))
            if content is None:
                raise AgentError(
                    "WORKSPACE_VERSION_CONTENT_MISSING",
                    f"Workspace version content not available: {target.version}",
                )
            restored = await self.write_workspace_file(
                workspace_id=workspace_id,
                path=path,
                content=content.content,
                media_type=content.media_type,
            )
            changes.append(
                AgentWorkspaceRestoreChange(
                    path=path,
                    operation="restored",
                    source_version=source.version if source else None,
                    target_version=target.version,
                    new_version=restored.version,
                )
            )

        return AgentWorkspaceRestoreResult(
            workspace_id=workspace_id,
            target_version=version,
            restored_version=self._latest_workspace_version(workspace_id),
            changes=changes,
            restored_count=sum(1 for change in changes if change.operation == "restored"),
            deleted_count=sum(1 for change in changes if change.operation == "deleted"),
            unchanged_count=sum(1 for change in changes if change.operation == "unchanged"),
        )

    async def delete_workspace_file(self, workspace_id: str, path: str) -> dict[str, str]:
        safe_path = normalize_path(path)
        key = (workspace_id, safe_path)
        existing = self._workspace_files.get(key)
        if existing is None:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        workspace_version = self._next_workspace_version(workspace_id)
        file_version = self._next_workspace_file_version(workspace_id, safe_path)
        self._workspace_file_versions.append(
            AgentWorkspaceFileVersion(
                workspace_id=workspace_id,
                path=safe_path,
                version=workspace_version,
                file_version=file_version,
                operation="delete",
                size=0,
                media_type=existing[0].media_type,
                content_hash=None,
                created_at=utc_now(),
            )
        )
        del self._workspace_files[key]
        return {"path": safe_path}

    def _latest_workspace_version(self, workspace_id: str) -> int:
        versions = [
            version.version
            for version in self._workspace_file_versions
            if version.workspace_id == workspace_id
        ]
        return max(versions, default=0)

    def _next_workspace_version(self, workspace_id: str) -> int:
        return self._latest_workspace_version(workspace_id) + 1

    def _next_workspace_file_version(self, workspace_id: str, path: str) -> int:
        versions = [
            version.file_version
            for version in self._workspace_file_versions
            if version.workspace_id == workspace_id and version.path == path
        ]
        return max(versions, default=0) + 1

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
        artifact = AgentArtifact(
            id=self._ids.next("artifact"),
            org_id=org_id,
            workspace_id=workspace_id,
            run_id=run_id,
            type=type,
            name=name,
            media_type=media_type,
            uri=uri,
            content=content,
            metadata=metadata,
            retention=retention,
            created_at=utc_now(),
        )
        self._artifacts[artifact.id] = artifact
        return artifact

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
        safe_path = normalize_path(path)
        record = self._workspace_files.get((workspace_id, safe_path))
        if record is None:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        file, _ = record
        artifact = await self.create_artifact(
            org_id=org_id,
            workspace_id=workspace_id,
            run_id=run_id,
            type=type,
            name=name,
            media_type=file.media_type,
            uri=safe_path,
            content={"path": safe_path},
            metadata={
                **(metadata or {}),
                "source": "workspace_file",
                "workspace_file": {
                    "workspace_id": workspace_id,
                    "path": safe_path,
                    "version": file.version,
                    "file_version": file.file_version,
                    "content_hash": file.content_hash,
                    "size": file.size,
                },
            },
            retention=retention,
        )
        return AgentArtifactPromotionResult(
            artifact=artifact,
            workspace_id=workspace_id,
            path=safe_path,
            version=file.version,
            file_version=file.file_version,
            content_hash=file.content_hash,
        )

    async def get_artifact(self, artifact_id: str) -> AgentArtifact | None:
        return self._artifacts.get(artifact_id)

    async def list_artifacts(
        self,
        *,
        run_id: str | None = None,
        workspace_id: str | None = None,
        type: AgentArtifactType | None = None,
        retention_mode: AgentArtifactRetentionMode | None = None,
        finalized: bool | None = None,
    ) -> list[AgentArtifact]:
        artifacts = list(self._artifacts.values())
        return [
            artifact
            for artifact in artifacts
            if _artifact_matches_filters(
                artifact,
                run_id=run_id,
                workspace_id=workspace_id,
                type=type,
                retention_mode=retention_mode,
                finalized=finalized,
            )
        ]

    async def finalize_artifact(self, artifact_id: str) -> AgentArtifact:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            raise AgentError("NOT_FOUND", f"Artifact not found: {artifact_id}")
        finalized = artifact.model_copy(update={"finalized_at": utc_now()})
        self._artifacts[artifact_id] = finalized
        return finalized

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
        now = utc_now()
        entry = AgentMemoryEntry(
            id=self._ids.next("memory"),
            org_id=org_id,
            scope=scope,
            scope_id=scope_id,
            key=key,
            value=value,
            owner=owner,
            source=source,
            confidence=confidence,
            visibility=visibility,
            retention=_memory_retention_policy(retention),
            created_at=now,
            updated_at=now,
        )
        self._memory_entries[entry.id] = entry
        return entry

    async def get_memory_entry(self, memory_id: str) -> AgentMemoryEntry | None:
        return self._memory_entries.get(memory_id)

    async def list_memory_entries(
        self,
        *,
        org_id: str,
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        include_expired: bool = False,
    ) -> list[AgentMemoryEntry]:
        entries = [entry for entry in self._memory_entries.values() if entry.org_id == org_id]
        if not include_expired:
            entries = [entry for entry in entries if not entry.is_expired()]
        if scope is not None:
            entries = [entry for entry in entries if entry.scope == scope]
        if scope_id is not None:
            entries = [entry for entry in entries if entry.scope_id == scope_id]
        if query:
            needle = query.lower()
            entries = [
                entry
                for entry in entries
                if needle in entry.key.lower() or needle in entry.value.lower()
            ]
        return entries

    async def delete_memory_entry(self, memory_id: str) -> AgentMemoryForgetResult:
        entry = self._memory_entries.pop(memory_id, None)
        return AgentMemoryForgetResult(
            memory_id=memory_id,
            org_id=entry.org_id if entry else "unknown",
            forgotten=entry is not None,
            deleted_count=1 if entry else 0,
        )

    async def create_memory_candidate(
        self,
        candidate: AgentMemoryCandidate,
    ) -> AgentMemoryCandidate:
        existing = self._memory_candidates.get(candidate.id)
        if existing is not None:
            return existing
        self._memory_candidates[candidate.id] = candidate
        return candidate

    async def get_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str | None = None,
    ) -> AgentMemoryCandidate | None:
        candidate = self._memory_candidates.get(candidate_id)
        if candidate is None:
            return None
        if org_id is not None and candidate.org_id != org_id:
            return None
        return candidate

    async def list_memory_candidates(
        self,
        *,
        org_id: str,
        status: AgentMemoryCandidateStatus | str | None = None,
        run_id: str | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
    ) -> list[AgentMemoryCandidate]:
        candidates = [
            candidate
            for candidate in self._memory_candidates.values()
            if candidate.org_id == org_id
            and (status is None or candidate.status == status)
            and (run_id is None or candidate.run_id == run_id)
            and (scope is None or candidate.scope == scope)
            and (scope_id is None or candidate.scope_id == scope_id)
        ]
        return sorted(candidates, key=lambda candidate: (candidate.created_at, candidate.id))

    async def update_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str,
        status: AgentMemoryCandidateStatus | str | None = None,
        resolved_at: str | None = None,
    ) -> AgentMemoryCandidate:
        candidate = await self.get_memory_candidate(candidate_id, org_id=org_id)
        if candidate is None:
            raise AgentError("NOT_FOUND", f"Memory candidate not found: {candidate_id}")
        updates = {
            key: value
            for key, value in {
                "status": status,
                "resolved_at": resolved_at,
            }.items()
            if value is not None
        }
        if not updates:
            return candidate
        updated = AgentMemoryCandidate.model_validate(
            {**candidate.model_dump(mode="python"), **updates}
        )
        self._memory_candidates[candidate_id] = updated
        return updated

    async def create_subagent_spec(
        self,
        *,
        org_id: str,
        key: str,
        name: str,
        instructions: str,
        allowed_tools: list[str] | None = None,
    ) -> AgentSubagentSpec:
        now = utc_now()
        existing = await self.get_subagent_spec(org_id, key)
        spec = AgentSubagentSpec(
            id=existing.id if existing else self._ids.next("subagent_spec"),
            org_id=org_id,
            key=key,
            name=name,
            instructions=instructions,
            allowed_tools=allowed_tools or [],
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._subagent_specs[spec.id] = spec
        return spec

    async def get_subagent_spec(self, org_id: str, key: str) -> AgentSubagentSpec | None:
        for spec in self._subagent_specs.values():
            if spec.org_id == org_id and spec.key == key:
                return spec
        return None

    async def list_subagent_specs(self, org_id: str) -> list[AgentSubagentSpec]:
        return [spec for spec in self._subagent_specs.values() if spec.org_id == org_id]

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
        subagent_run = AgentSubagentRun(
            id=self._ids.next("subagent_run"),
            org_id=org_id,
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            name=name,
            task=task,
            spec_key=spec_key,
            status=AgentSubagentRunStatus.RUNNING,
            created_at=utc_now(),
        )
        self._subagent_runs[subagent_run.id] = subagent_run
        return subagent_run

    async def get_subagent_run(self, subagent_run_id: str) -> AgentSubagentRun | None:
        return self._subagent_runs.get(subagent_run_id)

    async def list_subagent_runs(
        self,
        *,
        parent_run_id: str | None = None,
        child_run_id: str | None = None,
    ) -> list[AgentSubagentRun]:
        runs = list(self._subagent_runs.values())
        if parent_run_id is not None:
            runs = [run for run in runs if run.parent_run_id == parent_run_id]
        if child_run_id is not None:
            runs = [run for run in runs if run.child_run_id == child_run_id]
        return runs

    async def update_subagent_run(
        self,
        subagent_run_id: str,
        **updates: object,
    ) -> AgentSubagentRun:
        subagent_run = self._subagent_runs.get(subagent_run_id)
        if not subagent_run:
            raise AgentError("NOT_FOUND", f"Subagent run not found: {subagent_run_id}")
        updated = AgentSubagentRun.model_validate(
            {**subagent_run.model_dump(mode="python"), **updates}
        )
        self._subagent_runs[subagent_run_id] = updated
        return updated
