from pathlib import Path

import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import (
    AgentArtifactRetentionPolicy,
    AgentContextSummary,
    AgentMemoryCandidate,
    AgentMemoryRetentionPolicy,
    AgentRunStatus,
)
from aithru_agent.domain.errors import AgentError
from tests.utils.step_runtime import Step, StepAgentRuntime
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.stream import AgentEventWriter


@pytest.mark.asyncio
async def test_sqlite_store_persists_runs_workspace_files_and_events(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    event_store = SQLiteAgentEventStore(db_path)
    writer = AgentEventWriter(event_store)

    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Persist this",
        workspace_id=workspace.id,
        scopes=["agent.workspace.write"],
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/report.md",
        content="# Report\n",
        media_type="text/markdown",
    )
    running = await store.claim_run(run.id)
    assert running is not None
    completed = await store.update_run(running.id, status=AgentRunStatus.COMPLETED)
    approval = await store.create_approval(
        run_id=run.id,
        tool_call_id="toolcall_1",
        tool_name="workspace.write_file",
        metadata={"harness_driver": "pydantic_ai"},
    )
    await writer.write(
        run_id=run.id,
        type="run.completed",
        source={"kind": "harness"},
        payload={"status": "completed"},
    )

    reopened_store = SQLiteAgentStore(db_path)
    reopened_events = SQLiteAgentEventStore(db_path)
    persisted_run = await reopened_store.get_run(run.id)
    persisted_file = await reopened_store.read_workspace_file(workspace.id, "/reports/report.md")
    persisted_approval = await reopened_store.get_approval(approval.id)
    events = await reopened_events.list_by_run(run.id)

    assert completed.status == AgentRunStatus.COMPLETED
    assert persisted_run is not None
    assert persisted_run.status == AgentRunStatus.COMPLETED
    assert persisted_run.scopes == ["agent.workspace.write"]
    assert persisted_file.content == "# Report\n"
    assert persisted_approval is not None
    assert persisted_approval.metadata == {"harness_driver": "pydantic_ai"}
    assert [event.type for event in events] == ["run.completed"]


@pytest.mark.asyncio
async def test_sqlite_store_round_trips_context_summaries(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    first = AgentContextSummary(
        id="summary_run_1",
        org_id="org_1",
        thread_id="thread_1",
        run_id="run_1",
        summary="Earlier discussion established the report scope.",
        source="semantic_processor",
        source_sequence=3,
        message_count=8,
        token_estimate=24,
        created_at="2026-06-22T01:00:00Z",
    )
    second = AgentContextSummary(
        id="summary_run_2",
        org_id="org_1",
        thread_id="thread_1",
        run_id="run_2",
        summary="Later discussion chose the output format.",
        source="manual",
        message_count=2,
        created_at="2026-06-22T02:00:00Z",
    )

    await store.create_context_summary(first)
    await store.create_context_summary(second)
    reopened = SQLiteAgentStore(db_path)

    assert await reopened.list_context_summaries(org_id="org_1", thread_id="thread_1") == [
        first,
        second,
    ]
    assert await reopened.list_context_summaries(org_id="org_1", run_id="run_2") == [second]


@pytest.mark.asyncio
async def test_sqlite_store_persists_thread_lifecycle_updates(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1", title="Draft")

    renamed = await store.update_thread(thread.id, title="Research archive")
    archived = await store.update_thread(thread.id, title=None, status="archived")

    reopened = SQLiteAgentStore(db_path)
    persisted = await reopened.get_thread(thread.id)

    assert renamed.title == "Research archive"
    assert renamed.status == "active"
    assert archived.title is None
    assert archived.status == "archived"
    assert archived.created_at == thread.created_at
    assert archived.updated_at >= thread.updated_at
    assert persisted == archived


@pytest.mark.asyncio
async def test_sqlite_store_persists_workspace_file_versions_snapshots_and_diffs(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    workspace = await store.create_workspace(org_id="org_1")

    first = await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/notes.md",
        content="one\n",
        media_type="text/markdown",
    )
    second_file = await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/todo.md",
        content="todo\n",
        media_type="text/markdown",
    )
    second = await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/notes.md",
        content="one\ntwo\n",
        media_type="text/markdown",
    )
    await store.delete_workspace_file(workspace.id, "/todo.md")

    reopened = SQLiteAgentStore(db_path)
    note_versions = await reopened.list_workspace_file_versions(
        workspace_id=workspace.id,
        path="/notes.md",
    )
    all_versions = await reopened.list_workspace_file_versions(workspace_id=workspace.id)
    current_snapshot = await reopened.get_workspace_snapshot(workspace.id)
    early_snapshot = await reopened.get_workspace_snapshot(workspace.id, version=2)
    diff = await reopened.diff_workspace_snapshots(
        workspace_id=workspace.id,
        base_version=2,
        target_version=4,
    )

    assert first.version == 1
    assert first.file_version == 1
    assert second_file.version == 2
    assert second.version == 3
    assert second.file_version == 2
    assert [version.version for version in note_versions] == [1, 3]
    assert [version.file_version for version in note_versions] == [1, 2]
    assert [version.operation for version in all_versions] == ["write", "write", "write", "delete"]
    assert current_snapshot.version == 4
    assert [file.path for file in current_snapshot.files] == ["/notes.md"]
    assert early_snapshot.version == 2
    assert [file.path for file in early_snapshot.files] == ["/notes.md", "/todo.md"]
    assert [(change.path, change.operation) for change in diff.changes] == [
        ("/notes.md", "modified"),
        ("/todo.md", "deleted"),
    ]


@pytest.mark.asyncio
async def test_sqlite_store_promotes_workspace_file_to_retained_artifact(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Promote report",
        workspace_id=workspace.id,
    )
    written = await store.write_workspace_file(
        workspace_id=workspace.id,
        path="reports/report.md",
        content="# Report\n",
        media_type="text/markdown",
    )

    promoted = await store.promote_workspace_file_to_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        path="reports/report.md",
        run_id=run.id,
        type="report",
        name="Promoted report",
        retention=AgentArtifactRetentionPolicy(
            mode="expires_at",
            expires_at="2026-07-01T00:00:00Z",
        ),
        metadata={"kind": "promoted"},
    )
    reopened = SQLiteAgentStore(db_path)
    persisted = await reopened.get_artifact(promoted.artifact.id)

    assert promoted.workspace_id == workspace.id
    assert promoted.path == "/reports/report.md"
    assert promoted.version == written.version
    assert promoted.file_version == written.file_version
    assert promoted.content_hash == written.content_hash
    assert persisted is not None
    assert persisted.type == "report"
    assert persisted.uri == "/reports/report.md"
    assert persisted.content == {"path": "/reports/report.md"}
    assert persisted.media_type == "text/markdown"
    assert persisted.retention is not None
    assert persisted.retention.mode == "expires_at"
    assert persisted.retention.expires_at == "2026-07-01T00:00:00Z"
    assert persisted.metadata is not None
    assert persisted.metadata["kind"] == "promoted"
    assert persisted.metadata["source"] == "workspace_file"
    assert persisted.metadata["workspace_file"] == {
        "workspace_id": workspace.id,
        "path": "/reports/report.md",
        "version": written.version,
        "file_version": written.file_version,
        "content_hash": written.content_hash,
        "size": written.size,
    }


@pytest.mark.asyncio
async def test_sqlite_store_filters_artifact_listing_by_lifecycle_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    workspace = await store.create_workspace(org_id="org_1")
    other_workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="List artifacts",
        workspace_id=workspace.id,
    )
    default_retained = await store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="report",
        name="Default retained report",
    )
    expiring = await store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="report",
        name="Expiring report",
        retention=AgentArtifactRetentionPolicy(
            mode="expires_at",
            expires_at="2026-07-01T00:00:00Z",
        ),
    )
    ephemeral = await store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="json",
        name="Ephemeral data",
        retention=AgentArtifactRetentionPolicy(mode="ephemeral"),
    )
    finalized = await store.finalize_artifact(ephemeral.id)
    other = await store.create_artifact(
        org_id="org_1",
        workspace_id=other_workspace.id,
        run_id=None,
        type="report",
        name="Other workspace",
    )
    reopened = SQLiteAgentStore(db_path)

    reports = await reopened.list_artifacts(workspace_id=workspace.id, type="report")
    retained = await reopened.list_artifacts(workspace_id=workspace.id, retention_mode="retained")
    expiring_only = await reopened.list_artifacts(
        workspace_id=workspace.id,
        retention_mode="expires_at",
    )
    finalized_only = await reopened.list_artifacts(workspace_id=workspace.id, finalized=True)
    unfinished = await reopened.list_artifacts(workspace_id=workspace.id, finalized=False)

    assert [artifact.id for artifact in reports] == [default_retained.id, expiring.id]
    assert [artifact.id for artifact in retained] == [default_retained.id]
    assert [artifact.id for artifact in expiring_only] == [expiring.id]
    assert [artifact.id for artifact in finalized_only] == [finalized.id]
    assert [artifact.id for artifact in unfinished] == [default_retained.id, expiring.id]
    assert other.id not in [artifact.id for artifact in reports]


@pytest.mark.asyncio
async def test_sqlite_store_filters_expired_entries_and_forgets_memory(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    active = await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Chinese",
        retention=AgentMemoryRetentionPolicy(mode="retained"),
    )
    expired = await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.region",
        value="APAC",
        retention=AgentMemoryRetentionPolicy(
            mode="expires_at",
            expires_at="2000-01-01T00:00:00Z",
        ),
    )
    reopened = SQLiteAgentStore(db_path)

    visible = await reopened.list_memory_entries(org_id="org_1", scope="user", scope_id="user_1")
    all_entries = await reopened.list_memory_entries(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        include_expired=True,
    )
    forget = await reopened.delete_memory_entry(active.id)

    assert [entry.id for entry in visible] == [active.id]
    assert [entry.id for entry in all_entries] == [active.id, expired.id]
    assert forget.memory_id == active.id
    assert forget.forgotten is True
    assert forget.deleted_count == 1
    assert await reopened.get_memory_entry(active.id) is None


@pytest.mark.asyncio
async def test_sqlite_store_persists_agent_memory_candidates(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    candidate = AgentMemoryCandidate(
        id="memcand_run_1",
        org_id="org_1",
        run_id="run_1",
        scope="thread",
        scope_id="thread_1",
        key="run_run_1_outcome",
        value="Thread outcome worth reviewing.",
        confidence=0.6,
        created_at="2026-06-22T00:00:00Z",
    )

    created = await store.create_memory_candidate(candidate)
    reopened = SQLiteAgentStore(db_path)
    idempotent = await reopened.create_memory_candidate(
        candidate.model_copy(update={"value": "Do not overwrite."})
    )
    pending = await reopened.list_memory_candidates(
        org_id="org_1",
        status="pending",
        scope="thread",
        scope_id="thread_1",
    )
    resolved = await reopened.update_memory_candidate(
        candidate.id,
        org_id="org_1",
        status="rejected",
        resolved_at="2026-06-22T00:01:00Z",
    )

    assert created == candidate
    assert idempotent == candidate
    assert pending == [candidate]
    assert await reopened.get_memory_candidate(candidate.id, org_id="org_2") is None
    assert resolved.status == "rejected"
    assert resolved.resolved_at == "2026-06-22T00:01:00Z"


@pytest.mark.asyncio
async def test_sqlite_store_approves_memory_candidate_once(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    candidate = AgentMemoryCandidate(
        id="memcand_run_1",
        org_id="org_1",
        run_id="run_1",
        scope="user",
        scope_id="user_1",
        key="run_run_1_outcome",
        value="Prefers concise summaries.",
        confidence=0.6,
        created_at="2026-06-22T00:00:00Z",
    )
    await store.create_memory_candidate(candidate)

    approved = await store.approve_memory_candidate(
        candidate.id,
        org_id="org_1",
        owner="user_1",
        resolved_at="2026-06-22T00:01:00Z",
    )
    reopened = SQLiteAgentStore(db_path)
    entries = await reopened.list_memory_entries(org_id="org_1")

    with pytest.raises(AgentError) as conflict:
        await reopened.approve_memory_candidate(candidate.id, org_id="org_1", owner="user_1")
    with pytest.raises(AgentError) as reject_conflict:
        await reopened.update_memory_candidate(
            candidate.id,
            org_id="org_1",
            status="rejected",
            resolved_at="2026-06-22T00:02:00Z",
            expected_status="pending",
        )

    assert approved.candidate.status == "approved"
    assert approved.candidate.resolved_at == "2026-06-22T00:01:00Z"
    assert approved.memory_entry.source == "memory_candidate"
    assert approved.memory_entry.owner == "user_1"
    assert entries == [approved.memory_entry]
    assert conflict.value.code == "CONFLICT"
    assert reject_conflict.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_sqlite_store_restores_workspace_snapshot_with_persisted_version_content(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    store = SQLiteAgentStore(db_path)
    workspace = await store.create_workspace(org_id="org_1")
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/notes.md",
        content="one\n",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/todo.md",
        content="todo\n",
        media_type="text/markdown",
    )
    await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/notes.md",
        content="one\ntwo\n",
        media_type="text/markdown",
    )
    await store.delete_workspace_file(workspace.id, "/todo.md")

    reopened = SQLiteAgentStore(db_path)
    restored = await reopened.restore_workspace_snapshot(workspace.id, version=2)
    notes = await reopened.read_workspace_file(workspace.id, "/notes.md")
    todo = await reopened.read_workspace_file(workspace.id, "/todo.md")
    all_versions = await reopened.list_workspace_file_versions(workspace_id=workspace.id)
    latest_snapshot = await reopened.get_workspace_snapshot(workspace.id)

    assert notes.content == "one\n"
    assert todo.content == "todo\n"
    assert restored.target_version == 2
    assert restored.restored_count == 2
    assert [(change.path, change.operation) for change in restored.changes] == [
        ("/notes.md", "restored"),
        ("/todo.md", "restored"),
    ]
    assert [version.operation for version in all_versions] == [
        "write",
        "write",
        "write",
        "delete",
        "write",
        "write",
    ]
    assert latest_snapshot.version == 6


@pytest.mark.asyncio
async def test_runtime_can_execute_worker_runs_on_sqlite_store(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "workspace.write_file",
                    {"path": "/reports/report.md", "content": "# Report\n"},
                ),
                Step.finish(),
            ]
        ),
    )

    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write report",
        scopes=["*"],
    )
    await runtime.worker.drain()

    reopened_store = SQLiteAgentStore(db_path)
    reopened_events = SQLiteAgentEventStore(db_path)
    persisted_run = await reopened_store.get_run(queued.id)
    persisted_file = await reopened_store.read_workspace_file(queued.workspace_id, "/reports/report.md")
    events = await reopened_events.list_by_run(queued.id)

    assert persisted_run is not None
    assert persisted_run.status == AgentRunStatus.COMPLETED
    assert persisted_file.content == "# Report\n"
    assert [event.type for event in events][-1] == "run.completed"


@pytest.mark.asyncio
async def test_worker_discovers_queued_sqlite_runs_across_runtime_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    api_runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        agent_runtime=StepAgentRuntime([]),
    )
    queued = await api_runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Execute elsewhere",
        scopes=["*"],
    )

    worker_runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        agent_runtime=StepAgentRuntime([Step.finish()]),
    )
    completed = await worker_runtime.worker.work_once()

    assert completed is not None
    assert completed.id == queued.id
    assert completed.status == AgentRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_sqlite_workers_claim_queued_runs_once_across_runtime_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    api_runtime = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        agent_runtime=StepAgentRuntime([]),
    )
    queued = await api_runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Claim once",
        scopes=["*"],
    )
    worker_one = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        agent_runtime=StepAgentRuntime([Step.finish()]),
    )
    worker_two = create_agent_runtime(
        store=SQLiteAgentStore(db_path),
        event_store=SQLiteAgentEventStore(db_path),
        agent_runtime=StepAgentRuntime([Step.finish()]),
    )

    claimed_one = await worker_one.runner.claim_next_queued_run()
    claimed_two = await worker_two.runner.claim_next_queued_run()

    assert claimed_one is not None
    assert claimed_one.id == queued.id
    assert claimed_one.status == AgentRunStatus.RUNNING
    assert claimed_two is None
