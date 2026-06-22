import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.settings import AgentSettings


@pytest.mark.asyncio
async def test_short_threaded_run_pauses_for_clarification_before_model() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="model should not run",
        )
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Fix it",
        scopes=["agent.input.write"],
        thread_id=thread.id,
    )

    result = await runtime.runner.execute_run(run.id)

    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    assert result.status == AgentRunStatus.WAITING_INPUT
    assert "input.requested" in event_types
    assert "run.paused" in event_types
    assert "model.started" not in event_types


@pytest.mark.asyncio
async def test_disabled_clarification_allows_model_to_start() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="model did run",
            processors={
                "clarification_enabled": False,
                "clarification_min_goal_words": 4,
            },
        )
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Fix it",
        scopes=["agent.input.write"],
        thread_id=thread.id,
    )

    result = await runtime.runner.execute_run(run.id)

    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    assert result.status == AgentRunStatus.COMPLETED
    assert "input.requested" not in event_types
    assert "run.paused" not in event_types
    assert "model.started" in event_types


@pytest.mark.asyncio
async def test_run_continues_after_clarification_input_is_received() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="clarified result",
        )
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Fix it",
        scopes=["agent.input.write"],
        thread_id=thread.id,
    )
    paused = await runtime.runner.execute_run(run.id)
    message = await runtime.store.append_message(
        thread_id=thread.id,
        role="user",
        content="Focus on the failing report export and produce a patch.",
        run_id=run.id,
    )
    await runtime.event_writer.write(
        run_id=run.id,
        thread_id=thread.id,
        type="input.received",
        source={"kind": "user", "id": "user_1"},
        payload={
            "message_id": message.id,
            "content": message.content,
        },
    )

    await runtime.worker.resume_waiting_input(paused.id)
    completed = await runtime.worker.work_once()

    assert completed is not None
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    assert completed.status == AgentRunStatus.COMPLETED
    assert event_types.count("input.requested") == 1
    assert "model.started" in event_types
