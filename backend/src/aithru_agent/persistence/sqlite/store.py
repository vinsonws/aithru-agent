from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Literal, TypeVar

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifact,
    AgentMemoryEntry,
    AgentMessage,
    AgentRun,
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
    AgentWorkspaceFile,
)
from aithru_agent.domain.artifact import AgentArtifactType
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
            id=self._next_id("msg"),
            thread_id=thread_id,
            role=role,
            content=content,
            run_id=run_id,
            artifact_ids=artifact_ids or [],
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
        goal: str,
        workspace_id: str,
        scopes: list[str] | None = None,
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
            goal=goal,
            scopes=scopes or [],
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
        updated = run.model_copy(update=updates)
        self._save_doc("run", run_id, updated)
        return updated

    async def claim_run(self, run_id: str) -> AgentRun | None:
        return self._claim_queued_run(run_id=run_id)

    async def claim_next_queued_run(self) -> AgentRun | None:
        return self._claim_queued_run(run_id=None)

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
        file = AgentWorkspaceFile(
            workspace_id=workspace_id,
            path=safe_path,
            size=len(content.encode("utf-8")) if isinstance(content, str) else len(content),
            media_type=media_type,
            created_at=created_at,
            updated_at=now,
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

    async def delete_workspace_file(self, workspace_id: str, path: str) -> dict[str, str]:
        safe_path = normalize_path(path)
        row = self._db.query_one(
            """
            SELECT path
            FROM agent_workspace_files
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, safe_path),
        )
        if row is None:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        self._db.execute(
            """
            DELETE FROM agent_workspace_files
            WHERE workspace_id = ? AND path = ?
            """,
            (workspace_id, safe_path),
        )
        return {"path": safe_path}

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
        artifact = AgentArtifact(
            id=self._next_id("artifact"),
            org_id=org_id,
            workspace_id=workspace_id,
            run_id=run_id,
            type=type,
            name=name,
            media_type=media_type,
            uri=uri,
            content=content,
            metadata=metadata,
            created_at=utc_now(),
        )
        self._save_doc("artifact", artifact.id, artifact)
        return artifact

    async def get_artifact(self, artifact_id: str) -> AgentArtifact | None:
        return self._get_doc("artifact", artifact_id, AgentArtifact)

    async def list_artifacts(self, *, run_id: str | None = None) -> list[AgentArtifact]:
        artifacts = self._list_docs("artifact", AgentArtifact)
        if run_id is None:
            return artifacts
        return [artifact for artifact in artifacts if artifact.run_id == run_id]

    async def finalize_artifact(self, artifact_id: str) -> AgentArtifact:
        artifact = await self.get_artifact(artifact_id)
        if artifact is None:
            raise AgentError("NOT_FOUND", f"Artifact not found: {artifact_id}")
        finalized = artifact.model_copy(update={"finalized_at": utc_now()})
        self._save_doc("artifact", artifact_id, finalized)
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
        retention: str | None = None,
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
            retention=retention,
            created_at=now,
            updated_at=now,
        )
        self._save_doc("memory", entry.id, entry)
        return entry

    async def list_memory_entries(
        self,
        *,
        org_id: str,
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
    ) -> list[AgentMemoryEntry]:
        entries = [entry for entry in self._list_docs("memory", AgentMemoryEntry) if entry.org_id == org_id]
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
        updated = subagent_run.model_copy(update=updates)
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

    def _save_doc(self, kind: str, id: str, model: AithruBaseModel) -> None:
        self._db.execute(
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

    def _claim_queued_run(self, *, run_id: str | None) -> AgentRun | None:
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
            for row in rows:
                if row is None:
                    continue
                run = AgentRun.model_validate_json(row["payload"])
                if run.status != AgentRunStatus.QUEUED:
                    continue
                claimed = run.model_copy(update={"status": AgentRunStatus.RUNNING})
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
