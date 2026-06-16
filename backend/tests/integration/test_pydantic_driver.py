import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.harness.drivers.pydantic_ai.driver import PydanticAIHarnessDriver


@pytest.mark.asyncio
async def test_pydantic_ai_driver_streams_text_steps_from_test_model() -> None:
    driver = PydanticAIHarnessDriver(model=TestModel(custom_output_text="done"))

    steps = await driver.run("Say done")

    assert [step.type for step in steps] == ["message", "message", "finish"]
    assert "".join(step.text or "" for step in steps) == "done"
