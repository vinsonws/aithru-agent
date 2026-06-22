import pytest
from pydantic import ValidationError

from aithru_agent.domain import (
    AgentActorContext,
    AgentAuthorizationDecision,
    AgentCapabilityAuditEvent,
    AgentCapabilityAuditLog,
    AgentCapabilityAuditLogEntry,
    AgentArtifact,
    AgentArtifactDownloadInfo,
    AgentArtifactListFilters,
    AgentArtifactListPage,
    AgentArtifactPromotionResult,
    AgentArtifactRetentionPolicy,
    AgentArtifactSummary,
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentContextSummary,
    AgentMemoryEntry,
    AgentMemoryForgetResult,
    AgentMemoryRecall,
    AgentMemoryRecallItem,
    AgentMemoryRetentionPolicy,
    AgentMemoryVisibilityPolicy,
    AgentMessage,
    AgentRun,
    AgentRunExportArtifactResult,
    AgentRunExportBundle,
    AgentRunExportSummary,
    AgentRunStatus,
    AgentRunSource,
    AgentRunOperatorFollowUpOptions,
    AgentSandboxPolicy,
    AgentSkill,
    AgentScopeGrant,
    AgentSubagentResultSummary,
    AgentThread,
    AgentThreadStatus,
    AgentTodo,
    AgentTodoStatus,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolFailurePolicy,
    AgentToolKind,
    AgentToolRiskLevel,
    AgentRedactedPayload,
    AgentWorkspace,
    AgentWorkspaceDiff,
    AgentWorkspaceFile,
    AgentWorkspaceFileDiff,
    AgentWorkspaceFileVersion,
    AgentWorkspaceRestoreChange,
    AgentWorkspaceRestoreResult,
    AgentWorkspaceSnapshot,
    AgentWorkspaceSnapshotFile,
    WorkbenchWorkflowDraft,
)


def test_domain_models_serialize_with_stable_string_values() -> None:
    actor = AgentActorContext(
        actor_type="user",
        user_id="user_1",
        org_id="org_1",
        scopes=["agent.run.create"],
    )
    thread = AgentThread(
        id="thread_1",
        org_id="org_1",
        owner_user_id="user_1",
        title="Research",
        status=AgentThreadStatus.ACTIVE,
        created_at="2026-06-16T00:00:00Z",
        updated_at="2026-06-16T00:00:00Z",
    )
    workspace = AgentWorkspace(
        id="ws_1",
        org_id="org_1",
        thread_id=thread.id,
        run_id="run_1",
        storage_backend="memory",
        created_at="2026-06-16T00:00:00Z",
    )
    run = AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.CHAT,
        thread_id=thread.id,
        skill_id="skill_1",
        workspace_id=workspace.id,
        goal="Analyze files",
        status=AgentRunStatus.RUNNING,
        started_at="2026-06-16T00:00:00Z",
    )
    message = AgentMessage(
        id="msg_1",
        thread_id=thread.id,
        role="assistant",
        content="Working",
        run_id=run.id,
        artifact_ids=["artifact_1"],
        created_at="2026-06-16T00:00:00Z",
    )
    todo = AgentTodo(
        id="todo_1",
        run_id=run.id,
        title="Read files",
        status=AgentTodoStatus.RUNNING,
        created_by="agent",
        order=1,
    )
    descriptor = AgentToolDescriptor(
        name="workspace.read_file",
        kind=AgentToolKind.LOCAL_TOOL,
        description="Read a workspace file.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level=AgentToolRiskLevel.READ,
        required_scopes=["agent.workspace.read"],
        approval_policy="never",
    )
    call = AgentToolCallRequest(
        id="toolcall_1",
        tool_name=descriptor.name,
        input={"path": "/notes.md"},
        requested_by="model",
    )
    result = AgentToolCallResult(
        status="completed",
        output={"content": "# Notes"},
        redaction="none",
    )
    approval = AgentApproval(
        id="approval_1",
        run_id=run.id,
        tool_call_id=call.id,
        tool_name=descriptor.name,
        status=AgentApprovalStatus.PENDING,
        decision=None,
        created_at="2026-06-16T00:00:00Z",
    )
    file = AgentWorkspaceFile(
        workspace_id=workspace.id,
        path="/notes.md",
        size=7,
        media_type="text/markdown",
        created_at="2026-06-16T00:00:00Z",
        updated_at="2026-06-16T00:00:00Z",
    )
    artifact = AgentArtifact(
        id="artifact_1",
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="report",
        name="Report",
        media_type="text/markdown",
        uri="/reports/report.md",
        content={"summary": "Done"},
        created_at="2026-06-16T00:00:00Z",
    )
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Analyze files and write a report.",
        allowed_tools=["workspace.read_file"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )

    assert actor.model_dump(mode="json")["actor_type"] == "user"
    assert run.model_dump(mode="json")["status"] == "running"
    assert thread.model_dump(mode="json")["status"] == "active"
    assert todo.model_dump(mode="json")["status"] == "running"
    assert descriptor.model_dump(mode="json")["kind"] == "local_tool"
    assert descriptor.model_dump(mode="json")["risk_level"] == "read"
    assert descriptor.model_dump(mode="json")["failure_policy"] == "fail_run"
    assert AgentToolFailurePolicy.RETURN_RECOVERABLE.value == "return_recoverable"
    assert AgentToolKind.EXTERNAL_TOOL.value == "external_tool"
    assert call.model_dump(mode="json")["requested_by"] == "model"
    assert result.model_dump(mode="json")["status"] == "completed"
    assert approval.model_dump(mode="json")["status"] == "pending"
    assert file.model_dump(mode="json")["path"] == "/notes.md"
    assert artifact.model_dump(mode="json")["type"] == "report"
    assert message.model_dump(mode="json")["artifact_ids"] == ["artifact_1"]
    assert skill.model_dump(mode="json")["status"] == "published"
    assert AgentApprovalDecision.APPROVED.value == "approved"


def test_subagent_result_summary_derives_output_and_artifact_counts() -> None:
    summary = AgentSubagentResultSummary(
        content="Child result.",
        artifact_ids=["artifact_1", "artifact_1"],
        artifacts=[
            AgentArtifactSummary(
                id="artifact_2",
                type="report",
                name="Child Report",
                uri="/reports/child.md",
                summary="# Child Report",
            )
        ],
    )

    payload = summary.model_dump(mode="json")

    assert payload["artifact_ids"] == ["artifact_1", "artifact_2"]
    assert payload["artifact_count"] == 2
    assert payload["has_output"] is True


def test_subagent_result_summary_rejects_blank_artifact_ids() -> None:
    with pytest.raises(ValidationError):
        AgentSubagentResultSummary(artifact_ids=[" "])


def test_context_summary_requires_thread_or_run_and_nonblank_content() -> None:
    summary = AgentContextSummary(
        id=" summary_1 ",
        org_id=" org_1 ",
        thread_id="thread_1",
        summary=" Durable context. ",
        source="manual",
        created_at=" 2026-06-22T00:00:00Z ",
    )

    assert summary.id == "summary_1"
    assert summary.org_id == "org_1"
    assert summary.summary == "Durable context."
    assert summary.created_at == "2026-06-22T00:00:00Z"

    with pytest.raises(ValidationError, match="thread or run"):
        AgentContextSummary(
            id="summary_2",
            org_id="org_1",
            thread_id=" ",
            summary="No anchor.",
            source="manual",
            created_at="2026-06-22T00:00:00Z",
        )


def test_platform_governance_models_are_pydantic_contracts() -> None:
    actor = AgentActorContext(
        actor_type="user",
        org_id=" org_1 ",
        user_id=" user_1 ",
        scopes=[" agent.workspace.read ", "agent.workspace.read"],
    )
    grant = AgentScopeGrant(scope="agent.workspace.read", source="api_token")
    allowed = AgentAuthorizationDecision.from_scope_check(
        actor=actor,
        required_scopes=["agent.workspace.read"],
        granted_scopes=[grant.scope],
        resource_type="tool",
        resource_id="workspace.read_file",
    )
    denied = AgentAuthorizationDecision.from_scope_check(
        actor=actor,
        required_scopes=["agent.workspace.write"],
        granted_scopes=[grant.scope],
        resource_type="tool",
        resource_id="workspace.write_file",
    )
    audit = AgentCapabilityAuditEvent(
        action="tool.execute",
        outcome="denied",
        run_id="run_1",
        tool_name="workspace.write_file",
        actor=actor,
        authorization=denied,
        reason="Missing required scope: agent.workspace.write",
    )
    redacted = AgentRedactedPayload(
        payload={"api_key": "[REDACTED]", "path": "/notes.md"},
        redaction="partial",
        redacted_paths=["api_key"],
    )

    assert actor.org_id == "org_1"
    assert actor.user_id == "user_1"
    assert actor.scopes == ["agent.workspace.read"]
    assert grant.covers("agent.workspace.read") is True
    assert grant.covers("agent.workspace.write") is False
    assert allowed.status == "allowed"
    assert allowed.missing_scopes == []
    assert denied.status == "denied"
    assert denied.missing_scopes == ["agent.workspace.write"]
    assert audit.model_dump(mode="json")["authorization"]["status"] == "denied"
    assert audit.model_dump(mode="json", by_alias=True)["authorization_decision"]["status"] == "denied"
    audit_log = AgentCapabilityAuditLog(
        run_id="run_1",
        entries=[
            AgentCapabilityAuditLogEntry(
                source_event_id="run_1:4",
                source_event_type="tool.denied",
                sequence=4,
                audit=audit,
            )
        ],
        count=1,
    )
    assert audit_log.model_dump(mode="json", by_alias=True)["entries"][0]["audit"][
        "authorization_decision"
    ]["status"] == "denied"
    assert redacted.model_dump(mode="json") == {
        "payload": {"api_key": "[REDACTED]", "path": "/notes.md"},
        "redaction": "partial",
        "redacted_paths": ["api_key"],
    }

    with pytest.raises(ValidationError):
        AgentActorContext(actor_type="user", org_id="org_1")
    with pytest.raises(ValidationError):
        AgentActorContext(actor_type="service", org_id="org_1")
    with pytest.raises(ValidationError):
        AgentScopeGrant(scope=" ")
    with pytest.raises(ValidationError):
        AgentAuthorizationDecision(
            status="denied",
            actor=actor,
            required_scopes=["agent.workspace.write"],
            granted_scopes=["agent.workspace.read"],
            missing_scopes=[],
            reason="Missing scope",
        )
    with pytest.raises(ValidationError):
        AgentCapabilityAuditLog(run_id="run_1", entries=[], count=1)


def test_memory_recall_models_are_pydantic_contracts() -> None:
    item = AgentMemoryRecallItem(
        memory_id="memory_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
        owner="user_1",
        source="agent",
        confidence=0.9,
        visibility="private",
        reason="Current user memory is readable by this run.",
        created_at="2026-06-19T00:00:00Z",
        updated_at="2026-06-19T00:00:00Z",
    )
    recall = AgentMemoryRecall(
        run_id="run_1",
        items=[item],
        count=1,
        dropped=2,
    )

    assert item.model_dump(mode="json") == {
        "memory_id": "memory_1",
        "scope": "user",
        "scope_id": "user_1",
        "key": "preference.language",
        "value": "Prefers Chinese summaries.",
        "owner": "user_1",
        "source": "agent",
        "confidence": 0.9,
        "visibility": "private",
        "reason": "Current user memory is readable by this run.",
        "created_at": "2026-06-19T00:00:00Z",
        "updated_at": "2026-06-19T00:00:00Z",
        "truncated": False,
        "original_length": 0,
    }
    assert recall.count == 1
    assert recall.dropped == 2

    with pytest.raises(ValidationError):
        AgentMemoryRecall(run_id="run_1", items=[item], count=0)
    with pytest.raises(ValidationError):
        AgentMemoryRecallItem(
            memory_id="memory_2",
            scope="user",
            key=" ",
            value="x",
            reason="Readable memory.",
            created_at="2026-06-19T00:00:00Z",
            updated_at="2026-06-19T00:00:00Z",
        )


def test_memory_lifecycle_models_are_pydantic_contracts() -> None:
    retained = AgentMemoryRetentionPolicy(mode="retained")
    expiring = AgentMemoryRetentionPolicy(
        mode="expires_at",
        expires_at="2026-06-20T00:00:00Z",
    )
    entry = AgentMemoryEntry(
        id="memory_1",
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
        retention=expiring,
        created_at="2026-06-19T00:00:00Z",
        updated_at="2026-06-19T00:00:00Z",
    )
    result = AgentMemoryForgetResult(
        memory_id="memory_1",
        org_id="org_1",
        forgotten=True,
        deleted_count=1,
    )

    assert retained.model_dump(mode="json") == {
        "mode": "retained",
        "expires_at": None,
    }
    assert entry.is_expired("2026-06-19T12:00:00Z") is False
    assert entry.is_expired("2026-06-20T00:00:01Z") is True
    assert result.deleted_count == 1

    with pytest.raises(ValidationError):
        AgentMemoryRetentionPolicy(mode="expires_at")
    with pytest.raises(ValidationError):
        AgentMemoryRetentionPolicy(mode="retained", expires_at="2026-06-20T00:00:00Z")
    with pytest.raises(ValidationError):
        AgentMemoryForgetResult(
            memory_id="memory_1",
            org_id="org_1",
            forgotten=False,
            deleted_count=1,
        )


def test_memory_visibility_policy_filters_private_entries() -> None:
    owned_private = AgentMemoryEntry(
        id="memory_1",
        org_id="org_1",
        scope="organization",
        scope_id="org_1",
        key="private.owned",
        value="Owned private memory.",
        owner="user_1",
        visibility="private",
        created_at="2026-06-19T00:00:00Z",
        updated_at="2026-06-19T00:00:00Z",
    )
    other_private = owned_private.model_copy(
        update={
            "id": "memory_2",
            "key": "private.other",
            "owner": "user_2",
        }
    )
    user_scoped_private = owned_private.model_copy(
        update={
            "id": "memory_3",
            "scope": "user",
            "scope_id": "user_1",
            "key": "private.user_scope",
            "owner": None,
        }
    )
    shared = owned_private.model_copy(
        update={
            "id": "memory_4",
            "key": "shared.memory",
            "owner": "user_2",
            "visibility": "shared",
        }
    )
    policy = AgentMemoryVisibilityPolicy(actor_user_id="user_1")
    anonymous_policy = AgentMemoryVisibilityPolicy()

    assert policy.allows(owned_private) is True
    assert policy.allows(other_private) is False
    assert policy.allows(user_scoped_private) is True
    assert policy.allows(shared) is True
    assert anonymous_policy.allows(owned_private) is False
    assert anonymous_policy.allows(shared) is True


def test_artifact_retention_and_promotion_models_are_pydantic_contracts() -> None:
    retention = AgentArtifactRetentionPolicy(
        mode="expires_at",
        expires_at="2026-07-01T00:00:00Z",
    )
    artifact = AgentArtifact(
        id="artifact_1",
        org_id="org_1",
        workspace_id="ws_1",
        run_id="run_1",
        type="report",
        name="Report",
        media_type="text/markdown",
        uri="/reports/report.md",
        content={"path": "/reports/report.md"},
        metadata={"source": "workspace_file"},
        retention=retention,
        created_at="2026-06-18T00:00:00Z",
    )
    result = AgentArtifactPromotionResult(
        artifact=artifact,
        workspace_id="ws_1",
        path="/reports/report.md",
        version=3,
        file_version=2,
        content_hash="sha256:abc",
    )

    assert artifact.retention.mode == "expires_at"
    assert artifact.model_dump(mode="json")["retention"] == {
        "mode": "expires_at",
        "expires_at": "2026-07-01T00:00:00Z",
        "legal_hold": False,
    }
    assert result.artifact.id == "artifact_1"
    assert result.version == 3

    with pytest.raises(ValidationError):
        AgentArtifactRetentionPolicy(mode="expires_at")
    with pytest.raises(ValidationError):
        AgentArtifactRetentionPolicy(mode="ephemeral", legal_hold=True)


def test_artifact_list_models_are_pydantic_contracts() -> None:
    artifact = AgentArtifact(
        id="artifact_1",
        org_id="org_1",
        workspace_id="ws_1",
        run_id="run_1",
        type="report",
        name="Report",
        retention=AgentArtifactRetentionPolicy(
            mode="expires_at",
            expires_at="2026-07-01T00:00:00Z",
        ),
        created_at="2026-06-18T00:00:00Z",
    )
    filters = AgentArtifactListFilters(
        run_id="run_1",
        workspace_id="ws_1",
        type="report",
        retention_mode="expires_at",
        finalized=False,
    )
    page = AgentArtifactListPage(
        items=[artifact],
        total=3,
        count=1,
        limit=1,
        offset=2,
        order_by="created_at",
        order_direction="desc",
        filters=filters,
    )

    dumped = page.model_dump(mode="json")

    assert dumped["items"][0]["id"] == "artifact_1"
    assert dumped["filters"]["retention_mode"] == "expires_at"
    assert dumped["total"] == 3
    assert dumped["count"] == 1
    assert dumped["order_by"] == "created_at"
    assert dumped["order_direction"] == "desc"

    with pytest.raises(ValidationError):
        AgentArtifactListFilters(run_id=" ")
    with pytest.raises(ValidationError):
        AgentArtifactListPage(
            items=[artifact],
            total=1,
            count=2,
            limit=1,
            offset=0,
            order_direction="asc",
            filters=AgentArtifactListFilters(),
        )


def test_artifact_download_info_is_pydantic_contract() -> None:
    info = AgentArtifactDownloadInfo(
        artifact_id="artifact_1",
        filename="Run_run_1_export.json",
        media_type="application/json",
        content_length=128,
        disposition="attachment",
        source_path="/exports/runs/run_1.export.json",
    )

    assert info.model_dump(mode="json") == {
        "artifact_id": "artifact_1",
        "filename": "Run_run_1_export.json",
        "media_type": "application/json",
        "content_length": 128,
        "disposition": "attachment",
        "source_path": "/exports/runs/run_1.export.json",
    }

    with pytest.raises(ValidationError):
        AgentArtifactDownloadInfo(
            artifact_id="artifact_1",
            filename="../bad.json",
            media_type="application/json",
            content_length=128,
            disposition="attachment",
        )
    with pytest.raises(ValidationError):
        AgentArtifactDownloadInfo(
            artifact_id="artifact_1",
            filename="",
            media_type="application/json",
            content_length=128,
            disposition="attachment",
        )


def test_run_export_bundle_models_are_pydantic_contracts() -> None:
    run = AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        workspace_id="ws_1",
        goal="Export this",
        status=AgentRunStatus.COMPLETED,
        started_at="2026-06-18T00:00:00Z",
        completed_at="2026-06-18T00:00:05Z",
    )
    todo = AgentTodo(
        id="todo_1",
        run_id=run.id,
        title="Write report",
        status="done",
        created_by="agent",
        order=1,
    )
    approval = AgentApproval(
        id="approval_1",
        run_id=run.id,
        tool_call_id="toolcall_1",
        tool_name="workspace.write_file",
        status="resolved",
        decision="approved",
        created_at="2026-06-18T00:00:01Z",
        resolved_at="2026-06-18T00:00:02Z",
    )
    artifact = AgentArtifact(
        id="artifact_1",
        org_id="org_1",
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Report",
        uri="/reports/report.md",
        created_at="2026-06-18T00:00:03Z",
    )
    workspace_snapshot = AgentWorkspaceSnapshot(
        workspace_id=run.workspace_id,
        version=1,
        files=[
            AgentWorkspaceSnapshotFile(
                workspace_id=run.workspace_id,
                path="/reports/report.md",
                size=10,
                version=1,
                file_version=1,
                created_at="2026-06-18T00:00:03Z",
                updated_at="2026-06-18T00:00:03Z",
            )
        ],
        file_count=1,
        total_size=10,
        created_at="2026-06-18T00:00:04Z",
    )
    summary = AgentRunExportSummary(
        run_id=run.id,
        workspace_id=run.workspace_id,
        status="completed",
        event_count=1,
        trace_span_count=1,
        todo_count=1,
        approval_count=1,
        artifact_count=1,
        workspace_file_count=1,
    )
    bundle = AgentRunExportBundle(
        schema_version="run_export.v1",
        exported_at="2026-06-18T00:00:06Z",
        run=run,
        events=[{"id": "event_1", "type": "run.completed"}],
        trace=[{"id": "run:run_1", "kind": "run", "status": "completed"}],
        todos=[todo],
        approvals=[approval],
        artifacts=[artifact],
        workspace_snapshot=workspace_snapshot,
        summary=summary,
    )

    dumped = bundle.model_dump(mode="json")

    assert dumped["schema_version"] == "run_export.v1"
    assert dumped["run"]["id"] == "run_1"
    assert dumped["summary"]["artifact_count"] == 1
    assert dumped["workspace_snapshot"]["file_count"] == 1

    with pytest.raises(ValidationError):
        AgentRunExportBundle(
            schema_version="run_export.v1",
            exported_at="2026-06-18T00:00:06Z",
            run=run,
            events=[],
            trace=[],
            todos=[todo],
            approvals=[approval],
            artifacts=[artifact],
            workspace_snapshot=workspace_snapshot,
            summary=summary,
        )


def test_run_export_artifact_result_validates_artifact_pointer() -> None:
    summary = AgentRunExportSummary(
        run_id="run_1",
        workspace_id="ws_1",
        status="completed",
        event_count=1,
        trace_span_count=1,
        todo_count=0,
        approval_count=0,
        artifact_count=1,
        workspace_file_count=1,
    )
    artifact = AgentArtifact(
        id="artifact_1",
        org_id="org_1",
        workspace_id="ws_1",
        run_id="run_1",
        type="json",
        name="Run export",
        media_type="application/json",
        uri="/exports/runs/run_1.export.json",
        content={"path": "/exports/runs/run_1.export.json"},
        created_at="2026-06-18T00:00:00Z",
    )
    workspace_file = AgentWorkspaceFile(
        workspace_id="ws_1",
        path="/exports/runs/run_1.export.json",
        size=42,
        media_type="application/json",
        version=2,
        file_version=1,
        content_hash="sha256:abc",
        created_at="2026-06-18T00:00:00Z",
        updated_at="2026-06-18T00:00:00Z",
    )
    result = AgentRunExportArtifactResult(
        artifact=artifact,
        workspace_file=workspace_file,
        export_summary=summary,
        schema_version="run_export.v1",
        path="/exports/runs/run_1.export.json",
    )

    assert result.artifact.id == "artifact_1"
    assert result.workspace_file.content_hash == "sha256:abc"
    assert result.export_summary.run_id == "run_1"

    with pytest.raises(ValidationError):
        AgentRunExportArtifactResult(
            artifact=artifact.model_copy(update={"uri": "/different.json"}),
            workspace_file=workspace_file,
            export_summary=summary,
            schema_version="run_export.v1",
            path="/exports/runs/run_1.export.json",
        )


def test_workspace_version_snapshot_and_diff_models_are_pydantic_contracts() -> None:
    version = AgentWorkspaceFileVersion(
        workspace_id="ws_1",
        path="/reports/report.md",
        version=3,
        file_version=2,
        operation="write",
        size=12,
        media_type="text/markdown",
        content_hash="sha256:abc",
        created_at="2026-06-18T00:00:00Z",
    )
    snapshot_file = AgentWorkspaceSnapshotFile(
        workspace_id="ws_1",
        path="/reports/report.md",
        size=12,
        media_type="text/markdown",
        content_hash="sha256:abc",
        version=3,
        file_version=2,
        created_at="2026-06-18T00:00:00Z",
        updated_at="2026-06-18T00:00:00Z",
    )
    snapshot = AgentWorkspaceSnapshot(
        workspace_id="ws_1",
        version=3,
        files=[snapshot_file],
        file_count=1,
        total_size=12,
        created_at="2026-06-18T00:00:00Z",
    )
    diff = AgentWorkspaceDiff(
        workspace_id="ws_1",
        base_version=1,
        target_version=3,
        changes=[
            AgentWorkspaceFileDiff(
                path="/reports/report.md",
                operation="modified",
                base_version=1,
                target_version=3,
                base_size=8,
                target_size=12,
                base_hash="sha256:old",
                target_hash="sha256:abc",
            )
        ],
        added_count=0,
        modified_count=1,
        deleted_count=0,
    )

    assert version.model_dump(mode="json")["operation"] == "write"
    assert snapshot.file_count == 1
    assert snapshot.total_size == 12
    assert diff.changes[0].operation == "modified"


def test_workspace_restore_result_validates_change_counts() -> None:
    result = AgentWorkspaceRestoreResult(
        workspace_id="ws_1",
        target_version=2,
        restored_version=5,
        changes=[
            AgentWorkspaceRestoreChange(
                path="/notes.md",
                operation="restored",
                source_version=4,
                target_version=1,
                new_version=5,
            ),
            AgentWorkspaceRestoreChange(
                path="/old.md",
                operation="deleted",
                source_version=3,
                target_version=None,
                new_version=6,
            ),
            AgentWorkspaceRestoreChange(
                path="/same.md",
                operation="unchanged",
                source_version=2,
                target_version=2,
                new_version=None,
            ),
        ],
        restored_count=1,
        deleted_count=1,
        unchanged_count=1,
    )

    assert result.restored_version == 5
    assert result.changes[0].operation == "restored"


def test_sandbox_policy_is_pydantic_validated_contract() -> None:
    policy = AgentSandboxPolicy(
        enabled=True,
        network="allowlist",
        allowed_commands=["python"],
        allowed_packages=["pandas"],
        allowed_mounts=[
            {"source": "/workspace", "target": "/sandbox/workspace", "mode": "read"},
        ],
        timeout_ms=2_500,
    )

    assert policy.model_dump(mode="json") == {
        "enabled": True,
        "network": "allowlist",
        "allowed_commands": ["python"],
        "allowed_packages": ["pandas"],
        "allowed_mounts": [
            {"source": "/workspace", "target": "/sandbox/workspace", "mode": "read"},
        ],
        "timeout_ms": 2_500,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enabled": True, "network": "open"},
        {"enabled": True, "allowed_commands": ["python", " "]},
        {"enabled": True, "allowed_packages": [" "]},
        {"enabled": True, "allowed_mounts": [{"source": "relative", "target": "/sandbox", "mode": "read"}]},
        {"enabled": True, "allowed_mounts": [{"source": "/workspace", "target": "/sandbox", "mode": "execute"}]},
        {"enabled": True, "timeout_ms": 0},
    ],
)
def test_sandbox_policy_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentSandboxPolicy(**kwargs)


def test_workbench_workflow_draft_is_structured_non_executable_artifact_content() -> None:
    draft = WorkbenchWorkflowDraft(
        title="Review generated report",
        summary="Draft a future Workbench workflow for report review.",
        source_run_id="run_1",
        source_workspace_id="workspace_1",
        source_thread_id="thread_1",
        suggested_steps=[
            "Collect report artifact.",
            "Ask a reviewer for approval.",
            "Publish the approved report.",
        ],
        required_inputs=["Reviewer user id"],
        risks=["Needs human review before any Workbench workflow is created."],
        open_questions=["Who owns the final approval?"],
        handoff_notes="This is a non-executable draft for Workbench review.",
    )

    payload = draft.model_dump(mode="json")

    assert payload["title"] == "Review generated report"
    assert payload["source_run_id"] == "run_1"
    assert payload["suggested_steps"][0] == "Collect report artifact."
    assert payload["draft_kind"] == "workbench_workflow_draft"
    assert payload["executable"] is False

    with pytest.raises(ValidationError):
        WorkbenchWorkflowDraft(
            title="Graph-like draft",
            summary="Should be rejected.",
            source_run_id="run_1",
            source_workspace_id="workspace_1",
            suggested_steps=["Review."],
            nodes=[],
        )


def test_operator_follow_up_options_validate_provenance() -> None:
    follow_up = AgentRunOperatorFollowUpOptions(
        source_run_id=" run_1 ",
        action_kind=" retry_sandbox_run ",
        action_label=" Retry sandbox run ",
        action_reason=" Create a follow-up after fixing sandbox inputs. ",
        action_ids=["retry_sandbox_run", "retry_sandbox_run"],
        sandbox_run_ids=["sandbox_1", "sandbox_1"],
        workspace_paths=["/reports/output.md", "/reports/output.md"],
        method="POST",
        path="/api/runs",
    )

    payload = follow_up.model_dump(mode="json")

    assert payload == {
        "source_run_id": "run_1",
        "action_kind": "retry_sandbox_run",
        "action_label": "Retry sandbox run",
        "action_reason": "Create a follow-up after fixing sandbox inputs.",
        "action_ids": ["retry_sandbox_run"],
        "sandbox_run_ids": ["sandbox_1"],
        "workspace_paths": ["/reports/output.md"],
        "method": "POST",
        "path": "/api/runs",
    }

    with pytest.raises(ValidationError):
        AgentRunOperatorFollowUpOptions(
            source_run_id=" ",
            action_kind="retry_sandbox_run",
            action_label="Retry sandbox run",
            action_reason="Create a follow-up.",
        )
