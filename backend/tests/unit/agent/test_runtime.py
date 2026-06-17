from aithru_agent.agent.runtime import AgentRuntime


def test_agent_runtime_can_be_constructed() -> None:
    runtime = AgentRuntime(
        model="test",
        instructions="You are a test agent",
    )

    assert runtime.instructions == "You are a test agent"
