from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal

from aithru_agent.domain import (
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifact,
    AgentMemoryEntry,
    AgentMessage,
    AgentRun,
    AgentRunHarnessOptions,
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
        self._runs: dict[str, AgentRun] = {}
        self._todos: dict[str, AgentTodo] = {}
        self._todos_by_run: dict[str, list[str]] = defaultdict(list)
        self._approvals: dict[str, AgentApproval] = {}
        self._workspaces: dict[str, AgentWorkspace] = {}
        self._workspace_files: dict[tuple[str, str], tuple[AgentWorkspaceFile, WorkspaceFileContent]] = {}
        self._artifacts: dict[str, AgentArtifact] = {}
        self._memory_entries: dict[str, AgentMemoryEntry] = {}
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
        updated = AgentRun.model_validate({**run.model_dump(mode="python"), **updates})
        self._runs[run_id] = updated
        return updated

    async def claim_run(self, run_id: str) -> AgentRun | None:
        run = self._runs.get(run_id)
        if run is None or run.status != AgentRunStatus.QUEUED:
            return None
        updated = run.model_copy(update={"status": AgentRunStatus.RUNNING})
        self._runs[run_id] = updated
        return updated

    async def claim_next_queued_run(self) -> AgentRun | None:
        for run in self._runs.values():
            if run.status == AgentRunStatus.QUEUED:
                return await self.claim_run(run.id)
        return None

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
        file = AgentWorkspaceFile(
            workspace_id=workspace_id,
            path=safe_path,
            size=len(content.encode("utf-8")) if isinstance(content, str) else len(content),
            media_type=media_type,
            created_at=existing[0].created_at if existing else now,
            updated_at=now,
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

    async def delete_workspace_file(self, workspace_id: str, path: str) -> dict[str, str]:
        safe_path = normalize_path(path)
        key = (workspace_id, safe_path)
        if key not in self._workspace_files:
            raise AgentError("NOT_FOUND", f"File not found: {path}")
        del self._workspace_files[key]
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
            created_at=utc_now(),
        )
        self._artifacts[artifact.id] = artifact
        return artifact

    async def get_artifact(self, artifact_id: str) -> AgentArtifact | None:
        return self._artifacts.get(artifact_id)

    async def list_artifacts(self, *, run_id: str | None = None) -> list[AgentArtifact]:
        artifacts = list(self._artifacts.values())
        if run_id is None:
            return artifacts
        return [artifact for artifact in artifacts if artifact.run_id == run_id]

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
        retention: str | None = None,
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
            retention=retention,
            created_at=now,
            updated_at=now,
        )
        self._memory_entries[entry.id] = entry
        return entry

    async def list_memory_entries(
        self,
        *,
        org_id: str,
        scope: str | None = None,
        scope_id: str | None = None,
        query: str | None = None,
    ) -> list[AgentMemoryEntry]:
        entries = [entry for entry in self._memory_entries.values() if entry.org_id == org_id]
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
        updated = subagent_run.model_copy(update=updates)
        self._subagent_runs[subagent_run_id] = updated
        return updated
