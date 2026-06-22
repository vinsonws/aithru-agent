import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.settings import AgentSettings


@pytest.mark.asyncio
async def test_thread_title_is_generated_before_model_for_untitled_thread() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            test_model_output="title generation completed",
        )
    )
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Compare Aithru Agent with DeerFlow for long running research tasks",
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
    assert updated_thread.title == "Compare Aithru Agent With Deerflow For"
    assert len(title_events) == 1
    assert title_events[0].visibility == "debug"
    assert title_events[0].payload == {
        "thread_id": thread.id,
        "title": "Compare Aithru Agent With Deerflow For",
    }
    assert event_types.index("thread.title.generated") < event_types.index("model.started")


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
        goal="Fix it",
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
