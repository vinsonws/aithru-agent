import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.harness.drivers.pydantic_ai.driver import PydanticAIHarnessDriver


@pytest.mark.asyncio
async def test_pydantic_ai_driver_streams_text_steps_from_test_model() -> None:
    driver = PydanticAIHarnessDriver(model=TestModel(custom_output_text="done"))

    steps = await driver.run("Say done")

    assert [step.type for step in steps] == ["message", "message", "finish"]
    assert "".join(step.text or "" for step in steps) == "done"


@pytest.mark.asyncio
async def test_pydantic_ai_driver_routes_model_tool_calls_through_aithru_bridge() -> None:
    runtime = create_agent_runtime(
        driver=PydanticAIHarnessDriver(
            model=TestModel(call_tools=["workspace.list_files"], custom_output_text="done")
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="List files and finish.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    assert "tool.proposed" in event_types
    assert "tool.started" in event_types
    assert "tool.completed" in event_types
    assert event_types[-1] == "run.completed"
