import pytest

from aithru_agent.application.runtime import create_agent_runtime
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
