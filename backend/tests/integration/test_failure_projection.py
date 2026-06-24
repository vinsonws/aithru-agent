import pytest

from aithru_agent.agent import AgentRuntime
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from tests.utils.step_runtime import Step, StepAgentRuntime


class FailingRuntime(AgentRuntime):
    async def run(self, goal, deps):  # type: ignore[no-untyped-def]
        del goal, deps
        raise RuntimeError("model exploded")


@pytest.mark.asyncio
async def test_worker_records_model_failure_as_run_failure() -> None:
    runtime = create_agent_runtime(agent_runtime=FailingRuntime())

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="fail",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    types = [event.type for event in events]

    assert run.status == AgentRunStatus.FAILED
    assert types[-2:] == ["model.failed", "run.failed"]
    assert "run.completed" not in types


@pytest.mark.asyncio
async def test_worker_records_tool_failure_before_run_failure() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool("workspace.read_file", {"path": "/missing.md"}),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="read missing",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    types = [event.type for event in events]

    assert run.status == AgentRunStatus.FAILED
    assert types[-3:] == ["tool.failed", "model.failed", "run.failed"]
    assert "run.completed" not in types
