from aithru_agent.domain import (
    AgentActorContext,
    AgentArtifact,
    AgentApproval,
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentMessage,
    AgentRun,
    AgentRunStatus,
    AgentRunSource,
    AgentSkill,
    AgentThread,
    AgentThreadStatus,
    AgentTodo,
    AgentTodoStatus,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
    AgentWorkspace,
    AgentWorkspaceFile,
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
    assert call.model_dump(mode="json")["requested_by"] == "model"
    assert result.model_dump(mode="json")["status"] == "completed"
    assert approval.model_dump(mode="json")["status"] == "pending"
    assert file.model_dump(mode="json")["path"] == "/notes.md"
    assert artifact.model_dump(mode="json")["type"] == "report"
    assert message.model_dump(mode="json")["artifact_ids"] == ["artifact_1"]
    assert skill.model_dump(mode="json")["status"] == "published"
    assert AgentApprovalDecision.APPROVED.value == "approved"
