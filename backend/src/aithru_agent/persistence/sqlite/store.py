from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3
from typing import Literal, TypeVar

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentContextSummary,
    AgentMemoryCandidate,
    AgentMemoryCandidateApprovalResult,
    AgentMemoryCandidateStatus,
    AgentMemoryEntry,
    AgentMemoryForgetResult,
    AgentMemoryRetentionPolicy,
    AgentMessage,
    AgentMessageAttachment,
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
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.errors import AgentError
from aithru_agent.domain.message import AgentMessageRole
from aithru_agent.persistence.protocols import WorkspaceFileContent
from aithru_agent.stream.events import AgentStreamEvent


ModelT = TypeVar("ModelT", bound=AithruBaseModel)


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
                    target_version=target_file.version,
                    target_size=target_file.size,
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
                    base_size=base_file.size,
                    base_hash=base_file.content_hash,
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


class SQLiteConnection:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def execute(self, sql: str, params: Iterable[object] = ()) -> sqlite3.Cursor:
        with self._conn:
            return self._conn.execute(sql, tuple(params))

    def query_one(self, sql: str, params: Iterable[object] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, tuple(params)).fetchone()

    def query_all(self, sql: str, params: Iterable[object] = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, tuple(params)).fetchall())

    def _migrate(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_counters (
                    prefix TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_documents (
                    kind TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (kind, id)
                );

                CREATE TABLE IF NOT EXISTS agent_workspace_files (
                    workspace_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    file_payload TEXT NOT NULL,
                    content BLOB NOT NULL,
                    is_bytes INTEGER NOT NULL,
                    media_type TEXT,
                    PRIMARY KEY (workspace_id, path)
                );

                CREATE TABLE IF NOT EXISTS agent_workspace_file_versions (
                    workspace_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    content BLOB,
                    is_bytes INTEGER NOT NULL DEFAULT 0,
                    media_type TEXT,
                    PRIMARY KEY (workspace_id, version)
                );

                CREATE TABLE IF NOT EXISTS agent_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                """
            )


class SQLiteAgentStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db = SQLiteConnection(db_path)

    async def create_thread(
        self,
        *,
        org_id: str,
        owner_user_id: str,
        title: str | None = None,
    ) -> AgentThread:
        now = utc_now()
        thread = AgentThread(
            id=self._next_id("thread"),
            org_id=org_id,
            owner_user_id=owner_user_id,
            title=title,
            status=AgentThreadStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._save_doc("thread", thread.id, thread)
        return thread

    async def get_thread(self, thread_id: str) -> AgentThread | None:
        return self._get_doc("thread", thread_id, AgentThread)

    async def list_threads(self) -> list[AgentThread]:
        return self._list_docs("thread", AgentThread)

    async def update_thread(self, thread_id: str, **updates: object) -> AgentThread:
        thread = await self.get_thread(thread_id)
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
        self._save_doc("thread", updated.id, updated)
        return updated

    async def append_message(
        self,
        *,
        thread_id: str,
        role: AgentMessageRole,
        content: str,
        run_id: str | None = None,
        workspace_paths: list[str] | None = None,
        attachments: list[AgentMessageAttachment] | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            id=self._next_id("msg"),
            thread_id=thread_id,
            role=role,
            content=content,
            run_id=run_id,
            workspace_paths=workspace_paths or [],
            attachments=attachments or [],
            created_at=utc_now(),
        )
        self._save_doc("message", message.id, message)
        return message

    async def list_messages(self, thread_id: str) -> list[AgentMessage]:
        return [
            message
            for message in self._list_docs("message", AgentMessage)
            if message.thread_id == thread_id
        ]

    async def create_context_summary(
        self,
        summary: AgentContextSummary,
    ) -> AgentContextSummary:
        self._save_doc("context_summary", summary.id, summary)
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
            for summary in self._list_docs("context_summary", AgentContextSummary)
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
            id=self._next_id("ws"),
            org_id=org_id,
            thread_id=thread_id,
            run_id=run_id,
            storage_backend="sqlite",
            created_at=utc_now(),
        )
        self._save_doc("workspace", workspace.id, workspace)
        return workspace

    async def get_workspace(self, workspace_id: str) -> AgentWorkspace | None:
        return self._get_doc("workspace", workspace_id, AgentWorkspace)

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
        run = AgentRun(
            id=self._next_id("run"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            source=source,
            thread_id=thread_id,
            skill_id=skill_id,
            workspace_id=workspace_id,
            task_msg=task_msg,
            scopes=scopes or [],
            harness_options=harness_options,
            retry_policy=retry_policy,
            status=AgentRunStatus.QUEUED,
            started_at=utc_now(),
        )
        self._save_doc("run", run.id, run)
        return run

    async def get_run(self, run_id: str) -> AgentRun | None:
        return self._get_doc("run", run_id, AgentRun)

    async def list_runs(self) -> list[AgentRun]:
        return self._list_docs("run", AgentRun)

    async def update_run(self, run_id: str, **updates: object) -> AgentRun:
        run = await self.get_run(run_id)
        if run is None:
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
        self._save_doc("run", run_id, updated)
        return updated

    async def claim_run(
        self,
        run_id: str,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        return self._claim_queued_run(
            run_id=run_id,
            worker_id=worker_id,
            claimed_at=claimed_at,
            lease_seconds=lease_seconds,
        )

    async def claim_next_queued_run(
        self,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        return self._claim_queued_run(
            run_id=None,
            worker_id=worker_id,
            claimed_at=claimed_at,
            lease_seconds=lease_seconds,
        )

    async def renew_run_claim(
        self,
        run_id: str,
        *,
        worker_id: str,
        heartbeat_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        conn = self._db._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT id, payload
                FROM agent_documents
                WHERE kind = ? AND id = ?
                """,
                ("run", run_id),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            run = AgentRun.model_validate_json(row["payload"])
            if not _run_claim_renewable(run, worker_id, heartbeat_at):
                conn.commit()
                return None
            updated = run.model_copy(
                update={
                    "claim": run.claim.renew(
                        heartbeat_at=heartbeat_at,
                        lease_seconds=lease_seconds,
                    )
                }
            )
            conn.execute(
                """
                UPDATE agent_documents
                SET payload = ?
                WHERE kind = ? AND id = ?
                """,
                (updated.model_dump_json(), "run", run.id),
            )
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise

    async def create_todo(
        self,
        *,
        run_id: str,
        title: str,
        status: AgentTodoStatus | str = AgentTodoStatus.PENDING,
        description: str | None = None,
        created_by: Literal["agent", "user", "system"] = "agent",
    ) -> AgentTodo:
        todo = AgentTodo(
            id=self._next_id("todo"),
            run_id=run_id,
            title=title,
            description=description,
            status=status,
            created_by=created_by,
            order=len(await self.list_todos(run_id)) + 1,
        )
        self._save_doc("todo", todo.id, todo)
        return todo

    async def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: AgentTodoStatus | str | None = None,
    ) -> AgentTodo:
        todo = self._get_doc("todo", todo_id, AgentTodo)
        if todo is None:
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
        self._save_doc("todo", todo_id, updated)
        return updated

    async def list_todos(self, run_id: str) -> list[AgentTodo]:
        return [
            todo
            for todo in self._list_docs("todo", AgentTodo)
            if todo.run_id == run_id
        ]

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
            id=self._next_id("approval"),
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_input=tool_input,
            status=AgentApprovalStatus.PENDING,
            decision=None,
            metadata=metadata,
            created_at=utc_now(),
        )
        self._save_doc("approval", approval.id, approval)
        return approval

    async def get_approval(self, approval_id: str) -> AgentApproval | None:
        return self._get_doc("approval", approval_id, AgentApproval)

    async def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | str | None = None,
    ) -> list[AgentApproval]:
        approvals = self._list_docs("approval", AgentApproval)
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
        approval = await self.get_approval(approval_id)
        if approval is None:
            raise AgentError("APPROVAL_NOT_FOUND", f"Approval not found: {approval_id}")
        resolved = approval.model_copy(
            update={
                "status": AgentApprovalStatus.RESOLVED,
                "decision": decision,
                "comment": comment,
                "resolved_at": utc_now(),
            }
        )
        self._save_doc("approval", approval_id, resolved)
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
        existing = self._db.query_one(
            """
            SELECT file_payload
            FROM agent_workspace_files
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, safe_path),
        )
        now = utc_now()
        created_at = (
            AgentWorkspaceFile.model_validate_json(existing["file_payload"]).created_at
            if existing
            else now
        )
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
            created_at=created_at,
            updated_at=now,
        )
        version = AgentWorkspaceFileVersion(
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
        content_bytes = content if isinstance(content, bytes) else content.encode("utf-8")
        self._db.execute(
            """
            INSERT OR REPLACE INTO agent_workspace_files (
                workspace_id, path, file_payload, content, is_bytes, media_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                safe_path,
                file.model_dump_json(),
                sqlite3.Binary(content_bytes),
                1 if isinstance(content, bytes) else 0,
                media_type,
            ),
        )
        self._db.execute(
            """
            INSERT INTO agent_workspace_file_versions (
                workspace_id, version, path, payload, content, is_bytes, media_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                workspace_version,
                safe_path,
                version.model_dump_json(),
                sqlite3.Binary(content_bytes),
                1 if isinstance(content, bytes) else 0,
                media_type,
            ),
        )
        return file

    async def read_workspace_file(self, workspace_id: str, path: str) -> WorkspaceFileContent:
        safe_path = normalize_path(path)
        row = self._db.query_one(
            """
            SELECT content, is_bytes, media_type
            FROM agent_workspace_files
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, safe_path),
        )
        if row is None:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        raw = bytes(row["content"])
        content: str | bytes = raw if row["is_bytes"] else raw.decode("utf-8")
        return WorkspaceFileContent(content=content, media_type=row["media_type"])

    async def list_workspace_files(self, workspace_id: str) -> list[AgentWorkspaceFile]:
        rows = self._db.query_all(
            """
            SELECT file_payload
            FROM agent_workspace_files
            WHERE workspace_id = ?
            ORDER BY path
            """,
            (workspace_id,),
        )
        return [AgentWorkspaceFile.model_validate_json(row["file_payload"]) for row in rows]

    async def list_workspace_file_versions(
        self,
        *,
        workspace_id: str,
        path: str | None = None,
    ) -> list[AgentWorkspaceFileVersion]:
        safe_path = normalize_path(path) if path else None
        if safe_path is None:
            rows = self._db.query_all(
                """
                SELECT payload
                FROM agent_workspace_file_versions
                WHERE workspace_id = ?
                ORDER BY version
                """,
                (workspace_id,),
            )
        else:
            rows = self._db.query_all(
                """
                SELECT payload
                FROM agent_workspace_file_versions
                WHERE workspace_id = ? AND path = ?
                ORDER BY version
                """,
                (workspace_id, safe_path),
            )
        return [AgentWorkspaceFileVersion.model_validate_json(row["payload"]) for row in rows]

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
            await self.delete_workspace_file(workspace_id, path)
            changes.append(
                AgentWorkspaceRestoreChange(
                    path=path,
                    operation="deleted",
                    source_version=source.version,
                    target_version=None,
                    new_version=self._latest_workspace_version(workspace_id),
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
            content = self._get_workspace_version_content(workspace_id, target.version)
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
        row = self._db.query_one(
            """
            SELECT path, file_payload
            FROM agent_workspace_files
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, safe_path),
        )
        if row is None:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        existing = AgentWorkspaceFile.model_validate_json(row["file_payload"])
        workspace_version = self._next_workspace_version(workspace_id)
        file_version = self._next_workspace_file_version(workspace_id, safe_path)
        version = AgentWorkspaceFileVersion(
            workspace_id=workspace_id,
            path=safe_path,
            version=workspace_version,
            file_version=file_version,
            operation="delete",
            size=0,
            media_type=existing.media_type,
            content_hash=None,
            created_at=utc_now(),
        )
        self._db.execute(
            """
            INSERT INTO agent_workspace_file_versions (
                workspace_id, version, path, payload, content, is_bytes, media_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                workspace_version,
                safe_path,
                version.model_dump_json(),
                None,
                0,
                existing.media_type,
            ),
        )
        self._db.execute(
            """
            DELETE FROM agent_workspace_files
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, safe_path),
        )
        return {"path": safe_path}

    def _latest_workspace_version(self, workspace_id: str) -> int:
        row = self._db.query_one(
            """
            SELECT MAX(version) AS version
            FROM agent_workspace_file_versions
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )
        if row is None or row["version"] is None:
            return 0
        return int(row["version"])

    def _next_workspace_version(self, workspace_id: str) -> int:
        return self._latest_workspace_version(workspace_id) + 1

    def _next_workspace_file_version(self, workspace_id: str, path: str) -> int:
        row = self._db.query_one(
            """
            SELECT payload
            FROM agent_workspace_file_versions
            WHERE workspace_id = ? AND path = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (workspace_id, path),
        )
        if row is None:
            return 1
        return AgentWorkspaceFileVersion.model_validate_json(row["payload"]).file_version + 1

    def _get_workspace_version_content(
        self,
        workspace_id: str,
        version: int,
    ) -> WorkspaceFileContent | None:
        row = self._db.query_one(
            """
            SELECT content, is_bytes, media_type
            FROM agent_workspace_file_versions
            WHERE workspace_id = ? AND version = ?
            """,
            (workspace_id, version),
        )
        if row is None or row["content"] is None:
            return None
        raw = bytes(row["content"])
        content: str | bytes = raw if row["is_bytes"] else raw.decode("utf-8")
        return WorkspaceFileContent(content=content, media_type=row["media_type"])

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
            id=self._next_id("memory"),
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
        self._save_doc("memory", entry.id, entry)
        return entry

    async def get_memory_entry(self, memory_id: str) -> AgentMemoryEntry | None:
        return self._get_doc("memory", memory_id, AgentMemoryEntry)

    async def list_memory_entries(
        self,
        *,
        org_id: str,
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
        include_expired: bool = False,
    ) -> list[AgentMemoryEntry]:
        entries = [entry for entry in self._list_docs("memory", AgentMemoryEntry) if entry.org_id == org_id]
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
        entry = await self.get_memory_entry(memory_id)
        deleted_count = self._delete_doc("memory", memory_id)
        return AgentMemoryForgetResult(
            memory_id=memory_id,
            org_id=entry.org_id if entry else "unknown",
            forgotten=deleted_count > 0,
            deleted_count=deleted_count,
        )

    async def create_memory_candidate(
        self,
        candidate: AgentMemoryCandidate,
    ) -> AgentMemoryCandidate:
        existing = await self.get_memory_candidate(candidate.id)
        if existing is not None:
            return existing
        self._save_doc("memory_candidate", candidate.id, candidate)
        return candidate

    async def get_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str | None = None,
    ) -> AgentMemoryCandidate | None:
        candidate = self._get_doc("memory_candidate", candidate_id, AgentMemoryCandidate)
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
            for candidate in self._list_docs("memory_candidate", AgentMemoryCandidate)
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
        expected_status: AgentMemoryCandidateStatus | str | None = None,
    ) -> AgentMemoryCandidate:
        if expected_status is not None:
            return self._update_memory_candidate_in_transaction(
                candidate_id,
                org_id=org_id,
                status=status,
                resolved_at=resolved_at,
                expected_status=expected_status,
            )
        candidate = self._get_doc("memory_candidate", candidate_id, AgentMemoryCandidate)
        if candidate is None or candidate.org_id != org_id:
            raise AgentError("NOT_FOUND", f"Memory candidate not found: {candidate_id}")
        if expected_status is not None and candidate.status != expected_status:
            raise AgentError("CONFLICT", "Memory candidate is already resolved")
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
        self._save_doc("memory_candidate", candidate_id, updated)
        return updated

    def _update_memory_candidate_in_transaction(
        self,
        candidate_id: str,
        *,
        org_id: str,
        status: AgentMemoryCandidateStatus | str | None,
        resolved_at: str | None,
        expected_status: AgentMemoryCandidateStatus | str,
    ) -> AgentMemoryCandidate:
        conn = self._db._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT payload
                FROM agent_documents
                WHERE kind = ? AND id = ?
                """,
                ("memory_candidate", candidate_id),
            ).fetchone()
            if row is None:
                raise AgentError("NOT_FOUND", f"Memory candidate not found: {candidate_id}")
            candidate = AgentMemoryCandidate.model_validate_json(row["payload"])
            if candidate.org_id != org_id:
                raise AgentError("NOT_FOUND", f"Memory candidate not found: {candidate_id}")
            if candidate.status != expected_status:
                raise AgentError("CONFLICT", "Memory candidate is already resolved")
            updates = {
                key: value
                for key, value in {
                    "status": status,
                    "resolved_at": resolved_at,
                }.items()
                if value is not None
            }
            if not updates:
                conn.commit()
                return candidate
            updated = AgentMemoryCandidate.model_validate(
                {**candidate.model_dump(mode="python"), **updates}
            )
            self._save_doc_in_transaction(conn, "memory_candidate", candidate_id, updated)
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise

    async def approve_memory_candidate(
        self,
        candidate_id: str,
        *,
        org_id: str,
        owner: str | None = None,
        resolved_at: str | None = None,
    ) -> AgentMemoryCandidateApprovalResult:
        conn = self._db._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT payload
                FROM agent_documents
                WHERE kind = ? AND id = ?
                """,
                ("memory_candidate", candidate_id),
            ).fetchone()
            if row is None:
                raise AgentError("NOT_FOUND", f"Memory candidate not found: {candidate_id}")
            candidate = AgentMemoryCandidate.model_validate_json(row["payload"])
            if candidate.org_id != org_id:
                raise AgentError("NOT_FOUND", f"Memory candidate not found: {candidate_id}")
            if candidate.status != "pending":
                raise AgentError("CONFLICT", "Memory candidate is already resolved")

            now = utc_now()
            memory_entry = AgentMemoryEntry(
                id=self._next_id_in_transaction(conn, "memory"),
                org_id=candidate.org_id,
                scope=candidate.scope,
                scope_id=candidate.scope_id,
                key=candidate.key,
                value=candidate.value,
                owner=owner,
                source="memory_candidate",
                confidence=candidate.confidence,
                retention=_memory_retention_policy(candidate.retention),
                created_at=now,
                updated_at=now,
            )
            resolved = AgentMemoryCandidate.model_validate(
                {
                    **candidate.model_dump(mode="python"),
                    "status": "approved",
                    "resolved_at": resolved_at or now,
                }
            )
            self._save_doc_in_transaction(conn, "memory", memory_entry.id, memory_entry)
            self._save_doc_in_transaction(conn, "memory_candidate", candidate_id, resolved)
            conn.commit()
            return AgentMemoryCandidateApprovalResult(
                candidate=resolved,
                memory_entry=memory_entry,
            )
        except Exception:
            conn.rollback()
            raise

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
            id=existing.id if existing else self._next_id("subagent_spec"),
            org_id=org_id,
            key=key,
            name=name,
            instructions=instructions,
            allowed_tools=allowed_tools or [],
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._save_doc("subagent_spec", spec.id, spec)
        return spec

    async def get_subagent_spec(self, org_id: str, key: str) -> AgentSubagentSpec | None:
        for spec in self._list_docs("subagent_spec", AgentSubagentSpec):
            if spec.org_id == org_id and spec.key == key:
                return spec
        return None

    async def list_subagent_specs(self, org_id: str) -> list[AgentSubagentSpec]:
        return [
            spec
            for spec in self._list_docs("subagent_spec", AgentSubagentSpec)
            if spec.org_id == org_id
        ]

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
            id=self._next_id("subagent_run"),
            org_id=org_id,
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            name=name,
            task=task,
            spec_key=spec_key,
            status=AgentSubagentRunStatus.RUNNING,
            created_at=utc_now(),
        )
        self._save_doc("subagent_run", subagent_run.id, subagent_run)
        return subagent_run

    async def get_subagent_run(self, subagent_run_id: str) -> AgentSubagentRun | None:
        return self._get_doc("subagent_run", subagent_run_id, AgentSubagentRun)

    async def list_subagent_runs(
        self,
        *,
        parent_run_id: str | None = None,
        child_run_id: str | None = None,
    ) -> list[AgentSubagentRun]:
        runs = self._list_docs("subagent_run", AgentSubagentRun)
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
        subagent_run = await self.get_subagent_run(subagent_run_id)
        if subagent_run is None:
            raise AgentError("NOT_FOUND", f"Subagent run not found: {subagent_run_id}")
        updated = AgentSubagentRun.model_validate(
            {**subagent_run.model_dump(mode="python"), **updates}
        )
        self._save_doc("subagent_run", subagent_run_id, updated)
        return updated

    def _next_id(self, prefix: str) -> str:
        row = self._db.query_one(
            "SELECT value FROM agent_counters WHERE prefix = ?",
            (prefix,),
        )
        next_value = int(row["value"]) + 1 if row else 1
        self._db.execute(
            """
            INSERT INTO agent_counters (prefix, value)
            VALUES (?, ?)
            ON CONFLICT(prefix) DO UPDATE SET value = excluded.value
            """,
            (prefix, next_value),
        )
        return f"{prefix}_{next_value}"

    def _next_id_in_transaction(self, conn: sqlite3.Connection, prefix: str) -> str:
        row = conn.execute(
            "SELECT value FROM agent_counters WHERE prefix = ?",
            (prefix,),
        ).fetchone()
        next_value = int(row["value"]) + 1 if row else 1
        conn.execute(
            """
            INSERT INTO agent_counters (prefix, value)
            VALUES (?, ?)
            ON CONFLICT(prefix) DO UPDATE SET value = excluded.value
            """,
            (prefix, next_value),
        )
        return f"{prefix}_{next_value}"

    def _save_doc(self, kind: str, id: str, model: AithruBaseModel) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO agent_documents (kind, id, payload)
            VALUES (?, ?, ?)
            """,
            (kind, id, model.model_dump_json()),
        )

    def _save_doc_in_transaction(
        self,
        conn: sqlite3.Connection,
        kind: str,
        id: str,
        model: AithruBaseModel,
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO agent_documents (kind, id, payload)
            VALUES (?, ?, ?)
            """,
            (kind, id, model.model_dump_json()),
        )

    def _get_doc(self, kind: str, id: str, model_type: type[ModelT]) -> ModelT | None:
        row = self._db.query_one(
            """
            SELECT payload
            FROM agent_documents
            WHERE kind = ? AND id = ?
            """,
            (kind, id),
        )
        return model_type.model_validate_json(row["payload"]) if row else None

    def _list_docs(self, kind: str, model_type: type[ModelT]) -> list[ModelT]:
        rows = self._db.query_all(
            """
            SELECT payload
            FROM agent_documents
            WHERE kind = ?
            ORDER BY id
            """,
            (kind,),
        )
        return [model_type.model_validate_json(row["payload"]) for row in rows]

    def _delete_doc(self, kind: str, id: str) -> int:
        cursor = self._db.execute(
            """
            DELETE FROM agent_documents
            WHERE kind = ? AND id = ?
            """,
            (kind, id),
        )
        return cursor.rowcount

    def _claim_queued_run(
        self,
        *,
        run_id: str | None,
        worker_id: str,
        claimed_at: str | None,
        lease_seconds: int,
    ) -> AgentRun | None:
        conn = self._db._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = (
                [conn.execute(
                    """
                    SELECT id, payload
                    FROM agent_documents
                    WHERE kind = ? AND id = ?
                    """,
                    ("run", run_id),
                ).fetchone()]
                if run_id is not None
                else conn.execute(
                    """
                    SELECT id, payload
                    FROM agent_documents
                    WHERE kind = ?
                    ORDER BY id
                    """,
                    ("run",),
                ).fetchall()
            )
            run_rows = [row for row in rows if row is not None]
            for status in (AgentRunStatus.QUEUED, AgentRunStatus.RUNNING):
                for row in run_rows:
                    run = AgentRun.model_validate_json(row["payload"])
                    if run.status != status or not _run_claimable(run, claimed_at):
                        continue
                    previous_attempt = run.claim.attempt if run.claim else 0
                    claimed = run.model_copy(
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
                    conn.execute(
                        """
                        UPDATE agent_documents
                        SET payload = ?
                        WHERE kind = ? AND id = ?
                        """,
                        (claimed.model_dump_json(), "run", run.id),
                    )
                    conn.commit()
                    return claimed
            conn.commit()
            return None
        except Exception:
            conn.rollback()
            raise


class SQLiteAgentEventStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db = SQLiteConnection(db_path)

    async def append(self, event: AgentStreamEvent) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO agent_events (run_id, sequence, payload)
            VALUES (?, ?, ?)
            """,
            (event.run_id, event.sequence, event.model_dump_json()),
        )

    async def list_by_run(self, run_id: str) -> list[AgentStreamEvent]:
        rows = self._db.query_all(
            """
            SELECT payload
            FROM agent_events
            WHERE run_id = ?
            ORDER BY sequence
            """,
            (run_id,),
        )
        return [AgentStreamEvent.model_validate_json(row["payload"]) for row in rows]

    async def list_after_sequence(self, run_id: str, after_sequence: int) -> list[AgentStreamEvent]:
        rows = self._db.query_all(
            """
            SELECT payload
            FROM agent_events
            WHERE run_id = ? AND sequence > ?
            ORDER BY sequence
            """,
            (run_id, after_sequence),
        )
        return [AgentStreamEvent.model_validate_json(row["payload"]) for row in rows]

    async def next_sequence(self, run_id: str) -> int:
        row = self._db.query_one(
            """
            SELECT MAX(sequence) AS max_sequence
            FROM agent_events
            WHERE run_id = ?
            """,
            (run_id,),
        )
        current = row["max_sequence"] if row and row["max_sequence"] is not None else 0
        return int(current) + 1
