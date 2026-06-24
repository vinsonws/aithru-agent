import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.settings import AgentSettings


@pytest.mark.asyncio
async def test_thread_title_is_generated_after_first_assistant_response() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="Aithru DeerFlow Research",
        )
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Compare Aithru Agent with DeerFlow for long running research tasks",
        scopes=["agent.workspace.read"],
        thread_id=thread.id,
    )

    result = await runtime.runner.execute_run(run.id)

    updated_thread = await runtime.store.get_thread(thread.id)
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    title_events = [event for event in events if event.type == "thread.title.generated"]
    assert result.status == AgentRunStatus.COMPLETED
    assert updated_thread is not None
    assert updated_thread.title == "Aithru DeerFlow Research"
    assert len(title_events) == 1
    assert title_events[0].visibility == "debug"
    assert title_events[0].payload == {
        "thread_id": thread.id,
        "title": "Aithru DeerFlow Research",
    }
    assert event_types.index("message.completed") < event_types.index(
        "thread.title.generated"
    )
    assert event_types.index("thread.title.generated") < event_types.index("run.completed")


@pytest.mark.asyncio
async def test_disabled_title_generation_leaves_thread_untitled() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="title generation disabled",
            processors={
                "clarification_enabled": False,
                "title_generation_enabled": False,
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
        task_msg="Fix it",
        scopes=["agent.input.write"],
        thread_id=thread.id,
    )

    result = await runtime.runner.execute_run(run.id)

    updated_thread = await runtime.store.get_thread(thread.id)
    events = await runtime.event_store.list_by_run(run.id)
    assert result.status == AgentRunStatus.COMPLETED
    assert updated_thread is not None
    assert updated_thread.title is None
    assert "thread.title.generated" not in [event.type for event in events]


@pytest.mark.asyncio
async def test_thread_title_uses_title_model_not_raw_user_input() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="Report Export Fix",
        )
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Fix the report export bug",
        scopes=["agent.input.write"],
        thread_id=thread.id,
    )

    # With a non-empty goal the preflight does not intercept.
    completed = await runtime.runner.execute_run(run.id)

    updated_thread = await runtime.store.get_thread(thread.id)
    events = await runtime.event_store.list_by_run(run.id)
    title_events = [event for event in events if event.type == "thread.title.generated"]
    assert completed.status == AgentRunStatus.COMPLETED
    assert updated_thread is not None
    assert updated_thread.title == "Report Export Fix"
    assert len(title_events) == 1
    assert title_events[0].payload == {
        "thread_id": thread.id,
        "title": "Report Export Fix",
    }
