"""Test helpers for deterministic Pydantic AI testing."""

from pydantic_ai.models.test import TestModel


def create_deterministic_test_model(
    output_text: str = "Test completed",
    *,
    call_tools: list[str] | str = "all",
) -> TestModel:
    """Create a TestModel using the installed pydantic_ai test API."""
    return TestModel(
        call_tools=call_tools,
        custom_output_text=output_text,
    )


def create_simple_test_agent(
    model_output: str = "Test completed",
    *,
    call_tools: list[str] | str = "all",
):
    """Create a native AgentRuntime backed by TestModel."""
    from aithru_agent.agent import AgentRuntime

    return AgentRuntime(
        model=create_deterministic_test_model(model_output, call_tools=call_tools),
        instructions="You are a test agent",
    )
