import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from aithru_agent.harness.drivers.scripted.driver import ScriptedHarnessDriver, ScriptedStep
from aithru_agent.settings import AgentSettings


@pytest.mark.asyncio
async def test_runtime_uses_configured_pydantic_ai_driver_without_injected_driver() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            driver="pydantic_ai",
            model="test",
            test_model_output="configured",
            instructions="Answer concisely.",
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Return configured output",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    completed_message = next(event for event in events if event.type == "message.completed")

    assert completed_message.payload["content"] == "configured"


@pytest.mark.asyncio
async def test_runtime_resolves_run_model_override_from_settings() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            driver="pydantic_ai",
            test_model_output="run model",
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Return run model output",
        scopes=["*"],
        harness_options={"model": "test"},
    )
    events = await runtime.event_store.list_by_run(run.id)
    completed_message = next(event for event in events if event.type == "message.completed")

    assert completed_message.payload["content"] == "run model"


@pytest.mark.asyncio
async def test_runtime_uses_configured_sqlite_persistence(tmp_path) -> None:
    settings = AgentSettings(
        persistence_backend="sqlite",
        sqlite_path=str(tmp_path / "agent.sqlite"),
    )
    runtime = create_agent_runtime(
        settings=settings,
        driver=ScriptedHarnessDriver([ScriptedStep.finish()]),
    )

    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Persist via settings",
        scopes=["*"],
    )
    await runtime.worker.drain()

    reopened = create_agent_runtime(settings=settings, driver=ScriptedHarnessDriver([]))
    persisted = await reopened.store.get_run(queued.id)
    events = await reopened.event_store.list_by_run(queued.id)

    assert persisted is not None
    assert persisted.status == AgentRunStatus.COMPLETED
    assert [event.type for event in events][-1] == "run.completed"
