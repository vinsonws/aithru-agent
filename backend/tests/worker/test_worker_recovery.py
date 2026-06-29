from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import ToolPolicy
from aithru_agent.domain import (
    AgentApprovalDecision,
    AgentRunSource,
    AgentRunStatus,
    AgentSubagentRunStatus,
    AgentWorkspaceFile,
)
from tests.utils.step_runtime import Step, StepAgentRuntime


class ResumeSubagentRuntime(AgentRuntime):
    async def resume_subagent(
        self,
        *,
        run_id: str,
        subagent_run_id: str,
        child_run_id: str,
        child_result: str,
        child_workspace_files: list[AgentWorkspaceFile] | None = None,
        deps: PydanticAgentDeps,
    ) -> AgentRuntimeResult:
        del run_id, subagent_run_id, child_run_id, child_workspace_files, deps
        return AgentRuntimeResult(content=f"Parent continued with: {child_result}")


class ResumeSubagentWorkspaceFileRuntime(AgentRuntime):
    async def resume_subagent(
        self,
        *,
        run_id: str,
        subagent_run_id: str,
        child_run_id: str,
        child_result: str | None,
        child_workspace_files: list[AgentWorkspaceFile] | None = None,
        deps: PydanticAgentDeps,
    ) -> AgentRuntimeResult:
        del run_id, subagent_run_id, child_run_id, child_result, deps
        paths = ", ".join(file.path for file in child_workspace_files or [])
        return AgentRuntimeResult(content=f"Parent continued with workspace files: {paths}")


@pytest.mark.asyncio
async def test_worker_recovers_waiting_input_after_reply_without_queue_entry() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime([Step.message("Recovered after input."), Step.finish()])
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Recovery",
    )
    workspace = await runtime.store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Recover input",
        workspace_id=workspace.id,
        scopes=["*"],
        thread_id=thread.id,
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    waiting = await runtime.store.update_run(running.id, status=AgentRunStatus.WAITING_INPUT)
    message = await runtime.store.append_message(
        thread_id=thread.id,
        role="user",
        content="Use APAC.",
        run_id=waiting.id,
    )
    await runtime.event_writer.write(
        run_id=waiting.id,
        thread_id=thread.id,
        type="run.paused",
        source={"kind": "harness"},
        payload={"status": "waiting_input", "input_request_id": "toolcall_input"},
    )
    await runtime.event_writer.write(
        run_id=waiting.id,
        thread_id=thread.id,
        type="input.received",
        source={"kind": "user", "id": "user_1"},
        payload={"message_id": message.id, "content": message.content},
    )

    recovered = await runtime.worker.work_once()
    stored = await runtime.store.get_run(run.id)
    event_types = [event.type for event in await runtime.event_store.list_by_run(run.id)]

    assert recovered is not None
    assert recovered.id == run.id
    assert stored.status == AgentRunStatus.COMPLETED
    assert event_types.index("run.resumed") < event_types.index("run.started")
    assert event_types[-1] == "run.completed"


@pytest.mark.asyncio
async def test_worker_recovers_resolved_approval_without_queue_entry() -> None:
    runtime = create_agent_runtime(
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Write a file.",
        scopes=["*"],
    )
    approval = (await runtime.store.list_approvals())[0]
    await runtime.store.resolve_approval(
        approval.id,
        decision=AgentApprovalDecision.APPROVED,
        comment="ok",
    )

    recovered = await runtime.worker.work_once()
    stored = await runtime.store.get_run(run.id)
    file = await runtime.store.read_workspace_file(run.workspace_id, "/a")

    assert recovered is not None
    assert recovered.id == run.id
    assert stored.status == AgentRunStatus.COMPLETED
    assert file.content == "a"


@pytest.mark.asyncio
async def test_worker_recovery_fails_parent_when_waited_child_failed() -> None:
    runtime = create_agent_runtime()
    workspace = await runtime.store.create_workspace(org_id="org_1")
    parent = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for child",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    child = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.DELEGATED_TASK,
        task_msg="Child failed",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    running_parent = await runtime.store.claim_run(parent.id)
    running_child = await runtime.store.claim_run(child.id)
    assert running_parent is not None
    assert running_child is not None
    waiting_parent = await runtime.store.update_run(
        running_parent.id,
        status=AgentRunStatus.WAITING_SUBAGENT,
    )
    failed_child = await runtime.store.update_run(
        running_child.id,
        status=AgentRunStatus.FAILED,
        error={"message": "Child failed"},
    )
    subagent = await runtime.store.create_subagent_run(
        org_id="org_1",
        parent_run_id=waiting_parent.id,
        child_run_id=failed_child.id,
        name="Researcher",
        task="Research",
    )
    await runtime.store.update_subagent_run(subagent.id, status=AgentSubagentRunStatus.FAILED)
    await runtime.event_writer.write(
        run_id=parent.id,
        thread_id=None,
        type="run.paused",
        source={"kind": "harness"},
        payload={
            "status": "waiting_subagent",
            "subagent_run_id": subagent.id,
            "child_run_id": child.id,
        },
    )

    recovered = await runtime.worker.work_once()
    stored = await runtime.store.get_run(parent.id)
    event_types = [event.type for event in await runtime.event_store.list_by_run(parent.id)]

    assert recovered is not None
    assert recovered.id == parent.id
    assert stored.status == AgentRunStatus.FAILED
    assert stored.error["code"] == "SUBAGENT_FAILED"
    assert event_types[-2:] == ["model.failed", "run.failed"]


@pytest.mark.asyncio
async def test_worker_recovery_resumes_parent_when_waited_child_completed_with_result() -> None:
    runtime = create_agent_runtime(agent_runtime=ResumeSubagentRuntime())
    workspace = await runtime.store.create_workspace(org_id="org_1")
    parent = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for child",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    child = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.DELEGATED_TASK,
        task_msg="Child work",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    running_parent = await runtime.store.claim_run(parent.id)
    running_child = await runtime.store.claim_run(child.id)
    assert running_parent is not None
    assert running_child is not None
    waiting_parent = await runtime.store.update_run(
        running_parent.id,
        status=AgentRunStatus.WAITING_SUBAGENT,
    )
    completed_child = await runtime.store.update_run(
        running_child.id,
        status=AgentRunStatus.COMPLETED,
        result={"content": "Child result."},
    )
    subagent = await runtime.store.create_subagent_run(
        org_id="org_1",
        parent_run_id=waiting_parent.id,
        child_run_id=completed_child.id,
        name="Researcher",
        task="Research",
    )
    await runtime.store.update_subagent_run(
        subagent.id,
        status=AgentSubagentRunStatus.COMPLETED,
        result="Child result.",
    )
    await runtime.event_writer.write(
        run_id=parent.id,
        thread_id=None,
        type="run.paused",
        source={"kind": "harness"},
        payload={
            "status": "waiting_subagent",
            "subagent_run_id": subagent.id,
            "child_run_id": child.id,
        },
    )

    recovered = await runtime.worker.work_once()
    stored = await runtime.store.get_run(parent.id)
    event_types = [event.type for event in await runtime.event_store.list_by_run(parent.id)]

    assert recovered is not None
    assert recovered.id == parent.id
    assert stored.status == AgentRunStatus.COMPLETED
    assert stored.result.content == "Parent continued with: Child result."
    assert event_types.index("run.resumed") < event_types.index("model.completed")
    assert event_types[-1] == "run.completed"


@pytest.mark.asyncio
async def test_worker_recovery_resumes_parent_when_waited_child_completed_with_workspace_file() -> None:
    runtime = create_agent_runtime(agent_runtime=ResumeSubagentWorkspaceFileRuntime())
    workspace = await runtime.store.create_workspace(org_id="org_1")
    parent = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for child workspace file",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    child = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.DELEGATED_TASK,
        task_msg="Child workspace file work",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    report_file = await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        content="# Child Report\nImportant findings.",
        path="/reports/child.md",
        media_type="text/markdown",
    )
    running_parent = await runtime.store.claim_run(parent.id)
    running_child = await runtime.store.claim_run(child.id)
    assert running_parent is not None
    assert running_child is not None
    waiting_parent = await runtime.store.update_run(
        running_parent.id,
        status=AgentRunStatus.WAITING_SUBAGENT,
    )
    completed_child = await runtime.store.update_run(
        running_child.id,
        status=AgentRunStatus.COMPLETED,
        result={"workspace_paths": [report_file.path]},
    )
    subagent = await runtime.store.create_subagent_run(
        org_id="org_1",
        parent_run_id=waiting_parent.id,
        child_run_id=completed_child.id,
        name="Researcher",
        task="Research",
    )
    await runtime.store.update_subagent_run(
        subagent.id,
        status=AgentSubagentRunStatus.COMPLETED,
        result=None,
    )
    await runtime.event_writer.write(
        run_id=parent.id,
        thread_id=None,
        type="run.paused",
        source={"kind": "harness"},
        payload={
            "status": "waiting_subagent",
            "subagent_run_id": subagent.id,
            "child_run_id": child.id,
        },
    )

    recovered = await runtime.worker.work_once()
    stored = await runtime.store.get_run(parent.id)
    event_types = [event.type for event in await runtime.event_store.list_by_run(parent.id)]

    assert recovered is not None
    assert recovered.id == parent.id
    assert stored.status == AgentRunStatus.COMPLETED
    assert stored.result.content == (
        "Parent continued with workspace files: /reports/child.md"
    )
    assert event_types.index("run.resumed") < event_types.index("model.completed")
    assert event_types[-1] == "run.completed"
