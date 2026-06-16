import pytest

from aithru_agent.domain import AgentApprovalDecision, AgentApprovalStatus, AgentRunStatus
from aithru_agent.persistence.memory.store import InMemoryAgentStore


@pytest.mark.asyncio
async def test_memory_store_manages_threads_messages_runs_and_approvals() -> None:
    store = InMemoryAgentStore()

    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1", title="Work")
    message = await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Analyze this",
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
    )

    await store.update_run(run.id, status=AgentRunStatus.WAITING_APPROVAL, current_approval_id=approval.id)
    resolved = await store.resolve_approval(
        approval.id,
        decision=AgentApprovalDecision.APPROVED,
        comment="Looks good",
    )

    assert (await store.get_thread(thread.id)) == thread
    assert await store.list_threads() == [thread]
    assert await store.list_messages(thread.id) == [message]
    assert (await store.get_run(run.id)).status == AgentRunStatus.WAITING_APPROVAL
    assert await store.list_runs() == [await store.get_run(run.id)]
    assert resolved.status == AgentApprovalStatus.RESOLVED
    assert resolved.decision == AgentApprovalDecision.APPROVED
    assert await store.list_approvals(status=AgentApprovalStatus.RESOLVED) == [resolved]


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
