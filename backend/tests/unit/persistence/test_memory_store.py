import pytest

from aithru_agent.domain import (
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentArtifactRetentionPolicy,
    AgentContextSummary,
    AgentMemoryCandidate,
    AgentMemoryRetentionPolicy,
    AgentRunStatus,
    AgentWorkspaceImageAttachment,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.memory.store import InMemoryAgentStore


@pytest.mark.asyncio
async def test_memory_store_manages_threads_messages_runs_and_approvals() -> None:
    store = InMemoryAgentStore()

    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1", title="Work")
    attachment = AgentWorkspaceImageAttachment(
        kind="workspace_image",
        workspace_id="ws_1",
        path="/uploads/chart.png",
        media_type="image/png",
        size=4,
        content_hash="sha256:abcd",
    )
    message = await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Analyze this",
        attachments=[attachment],
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="chat",
        goal="Analyze this",
        workspace_id=workspace.id,
        thread_id=thread.id,
    )
    approval = await store.create_approval(
        run_id=run.id,
        tool_call_id="toolcall_1",
        tool_name="workspace.write_file",
        metadata={"harness_driver": "pydantic_ai"},
    )

    running = await store.claim_run(run.id)
    assert running is not None
    await store.update_run(running.id, status=AgentRunStatus.WAITING_APPROVAL, current_approval_id=approval.id)
    resolved = await store.resolve_approval(
        approval.id,
        decision=AgentApprovalDecision.APPROVED,
        comment="Looks good",
    )

    assert (await store.get_thread(thread.id)) == thread
    assert await store.list_threads() == [thread]
    assert await store.list_messages(thread.id) == [message]
    assert message.attachments == [attachment]
    assert (await store.get_run(run.id)).status == AgentRunStatus.WAITING_APPROVAL
    assert await store.list_runs() == [await store.get_run(run.id)]
    assert resolved.status == AgentApprovalStatus.RESOLVED
    assert resolved.decision == AgentApprovalDecision.APPROVED
    assert resolved.metadata == {"harness_driver": "pydantic_ai"}
    assert await store.list_approvals(status=AgentApprovalStatus.RESOLVED) == [resolved]


@pytest.mark.asyncio
async def test_memory_store_round_trips_context_summaries() -> None:
    store = InMemoryAgentStore()
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

    created = await store.create_context_summary(first)
    await store.create_context_summary(second)

    assert created == first
    assert await store.list_context_summaries(org_id="org_1", thread_id="thread_1") == [
        first,
        second,
    ]
    assert await store.list_context_summaries(org_id="org_1", run_id="run_2") == [second]


@pytest.mark.asyncio
async def test_memory_store_updates_thread_lifecycle() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1", title="Draft")

    renamed = await store.update_thread(thread.id, title="Research archive")
    archived = await store.update_thread(thread.id, title=None, status="archived")

    assert renamed.title == "Research archive"
    assert renamed.status == "active"
    assert archived.title is None
    assert archived.status == "archived"
    assert archived.created_at == thread.created_at
    assert archived.updated_at >= thread.updated_at
    assert await store.list_threads() == [archived]


@pytest.mark.asyncio
async def test_memory_store_manages_workspace_files_and_artifacts() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Write report",
        workspace_id=workspace.id,
    )

    written = await store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/report.md",
        content="# Report\n",
        media_type="text/markdown",
    )
    content = await store.read_workspace_file(workspace.id, "/reports/report.md")
    artifact = await store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="report",
        name="Report",
        media_type="text/markdown",
        uri="/reports/report.md",
        content={"path": "/reports/report.md"},
    )

    assert written.path == "/reports/report.md"
    assert content.content == "# Report\n"
    assert content.media_type == "text/markdown"
    assert await store.list_workspace_files(workspace.id) == [written]
    assert await store.get_artifact(artifact.id) == artifact
    assert await store.list_artifacts(run_id=run.id) == [artifact]

    deleted = await store.delete_workspace_file(workspace.id, "/reports/report.md")
    assert deleted == {"path": "/reports/report.md"}
    assert await store.list_workspace_files(workspace.id) == []


@pytest.mark.asyncio
async def test_memory_store_promotes_workspace_file_to_retained_artifact() -> None:
    store = InMemoryAgentStore()
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
    artifact = promoted.artifact
    persisted = await store.get_artifact(artifact.id)

    assert promoted.workspace_id == workspace.id
    assert promoted.path == "/reports/report.md"
    assert promoted.version == written.version
    assert promoted.file_version == written.file_version
    assert promoted.content_hash == written.content_hash
    assert artifact.type == "report"
    assert artifact.uri == "/reports/report.md"
    assert artifact.content == {"path": "/reports/report.md"}
    assert artifact.media_type == "text/markdown"
    assert artifact.retention is not None
    assert artifact.retention.mode == "expires_at"
    assert artifact.retention.expires_at == "2026-07-01T00:00:00Z"
    assert artifact.metadata is not None
    assert artifact.metadata["kind"] == "promoted"
    assert artifact.metadata["source"] == "workspace_file"
    assert artifact.metadata["workspace_file"] == {
        "workspace_id": workspace.id,
        "path": "/reports/report.md",
        "version": written.version,
        "file_version": written.file_version,
        "content_hash": written.content_hash,
        "size": written.size,
    }
    assert persisted == artifact


@pytest.mark.asyncio
async def test_memory_store_filters_artifact_listing_by_lifecycle_fields() -> None:
    store = InMemoryAgentStore()
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

    reports = await store.list_artifacts(workspace_id=workspace.id, type="report")
    retained = await store.list_artifacts(workspace_id=workspace.id, retention_mode="retained")
    expiring_only = await store.list_artifacts(
        workspace_id=workspace.id,
        retention_mode="expires_at",
    )
    finalized_only = await store.list_artifacts(workspace_id=workspace.id, finalized=True)
    unfinished = await store.list_artifacts(workspace_id=workspace.id, finalized=False)

    assert reports == [default_retained, expiring]
    assert retained == [default_retained]
    assert expiring_only == [expiring]
    assert finalized_only == [finalized]
    assert unfinished == [default_retained, expiring]
    assert other not in reports


@pytest.mark.asyncio
async def test_memory_store_filters_expired_entries_and_forgets_memory() -> None:
    store = InMemoryAgentStore()
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

    visible = await store.list_memory_entries(org_id="org_1", scope="user", scope_id="user_1")
    all_entries = await store.list_memory_entries(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        include_expired=True,
    )
    forget = await store.delete_memory_entry(active.id)

    assert [entry.id for entry in visible] == [active.id]
    assert [entry.id for entry in all_entries] == [active.id, expired.id]
    assert forget.memory_id == active.id
    assert forget.forgotten is True
    assert forget.deleted_count == 1
    assert await store.get_memory_entry(active.id) is None


@pytest.mark.asyncio
async def test_memory_store_tracks_workspace_file_versions_snapshots_and_diffs() -> None:
    store = InMemoryAgentStore()
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

    note_versions = await store.list_workspace_file_versions(
        workspace_id=workspace.id,
        path="/notes.md",
    )
    all_versions = await store.list_workspace_file_versions(workspace_id=workspace.id)
    current_snapshot = await store.get_workspace_snapshot(workspace.id)
    early_snapshot = await store.get_workspace_snapshot(workspace.id, version=2)
    diff = await store.diff_workspace_snapshots(
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
    assert current_snapshot.file_count == 1
    assert [file.path for file in current_snapshot.files] == ["/notes.md"]
    assert early_snapshot.version == 2
    assert [file.path for file in early_snapshot.files] == ["/notes.md", "/todo.md"]
    assert [(change.path, change.operation) for change in diff.changes] == [
        ("/notes.md", "modified"),
        ("/todo.md", "deleted"),
    ]
    assert diff.modified_count == 1
    assert diff.deleted_count == 1


@pytest.mark.asyncio
async def test_memory_store_restores_workspace_snapshot_with_auditable_versions() -> None:
    store = InMemoryAgentStore()
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

    restored = await store.restore_workspace_snapshot(workspace.id, version=2)
    notes = await store.read_workspace_file(workspace.id, "/notes.md")
    todo = await store.read_workspace_file(workspace.id, "/todo.md")
    all_versions = await store.list_workspace_file_versions(workspace_id=workspace.id)
    latest_snapshot = await store.get_workspace_snapshot(workspace.id)

    assert notes.content == "one\n"
    assert todo.content == "todo\n"
    assert restored.target_version == 2
    assert restored.restored_count == 2
    assert restored.deleted_count == 0
    assert restored.unchanged_count == 0
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
    assert [file.path for file in latest_snapshot.files] == ["/notes.md", "/todo.md"]


@pytest.mark.asyncio
async def test_memory_store_manages_agent_memory_entries() -> None:
    store = InMemoryAgentStore()

    entry = await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
        owner="user_1",
        source="agent",
        visibility="private",
    )
    unrelated = await store.create_memory_entry(
        org_id="org_2",
        scope="user",
        scope_id="user_2",
        key="preference.language",
        value="Prefers English summaries.",
    )

    matches = await store.list_memory_entries(org_id="org_1", query="Chinese")
    scoped = await store.list_memory_entries(org_id="org_1", scope="user", scope_id="user_1")

    assert matches == [entry]
    assert scoped == [entry]
    assert unrelated not in matches


@pytest.mark.asyncio
async def test_memory_store_manages_agent_memory_candidates() -> None:
    store = InMemoryAgentStore()
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
    duplicate = candidate.model_copy(update={"value": "Do not overwrite."})

    created = await store.create_memory_candidate(candidate)
    idempotent = await store.create_memory_candidate(duplicate)
    pending = await store.list_memory_candidates(org_id="org_1", status="pending")
    hidden = await store.get_memory_candidate(candidate.id, org_id="org_2")
    resolved = await store.update_memory_candidate(
        candidate.id,
        org_id="org_1",
        status="approved",
        resolved_at="2026-06-22T00:01:00Z",
    )
    approved = await store.list_memory_candidates(org_id="org_1", status="approved")

    assert created == candidate
    assert idempotent == candidate
    assert pending == [candidate]
    assert hidden is None
    assert resolved.status == "approved"
    assert resolved.resolved_at == "2026-06-22T00:01:00Z"
    assert approved == [resolved]


@pytest.mark.asyncio
async def test_memory_store_approves_memory_candidate_once() -> None:
    store = InMemoryAgentStore()
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
    entries = await store.list_memory_entries(org_id="org_1")

    with pytest.raises(AgentError) as conflict:
        await store.approve_memory_candidate(candidate.id, org_id="org_1", owner="user_1")
    with pytest.raises(AgentError) as reject_conflict:
        await store.update_memory_candidate(
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
