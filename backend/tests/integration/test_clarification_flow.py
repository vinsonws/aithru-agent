"""Integration tests for the full clarification flow via ClarificationLocalTool."""

import pytest
from aithru_agent.capabilities.local_tools.clarification import ClarificationLocalTool
from aithru_agent.capabilities.descriptors import AgentRunContext
from aithru_agent.domain import AgentToolCallRequest


@pytest.fixture
def tool() -> ClarificationLocalTool:
    return ClarificationLocalTool()


@pytest.fixture
def context() -> AgentRunContext:
    return AgentRunContext(
        run_id="run_clarify",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        thread_id="thread_clarify",
        scopes=["agent.input.write"],
    )


def test_clarification_descriptor_is_discoverable(tool: ClarificationLocalTool):
    """The tool descriptor should appear in capability router's tool list."""
    descriptors = tool.list_tools()
    names = [d.name for d in descriptors]
    assert "ask_clarification" in names


@pytest.mark.asyncio
async def test_clarification_with_options(tool: ClarificationLocalTool, context: AgentRunContext):
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_options",
            tool_name="ask_clarification",
            input={
                "question": "Which approach?",
                "clarification_type": "approach_choice",
                "options": ["Option 1", "Option 2", "Option 3"],
            },
            requested_by="model",
        ),
        context,
    )
    assert result.status == "completed"
    assert result.output["question"] == "Which approach?"
    assert result.output["clarification_type"] == "approach_choice"
    assert result.output["options"] == ["Option 1", "Option 2", "Option 3"]


@pytest.mark.asyncio
async def test_clarification_without_options(tool: ClarificationLocalTool, context: AgentRunContext):
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_no_options",
            tool_name="ask_clarification",
            input={
                "question": "What is the project name?",
                "clarification_type": "missing_info",
            },
            requested_by="model",
        ),
        context,
    )
    assert result.status == "completed"
    assert result.output["options"] is None


@pytest.mark.asyncio
async def test_clarification_denied_without_thread(tool: ClarificationLocalTool):
    ctx = AgentRunContext(
        run_id="run_no_thread",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        thread_id=None,
        scopes=["agent.input.write"],
    )
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="ask_clarification",
            input={"question": "Test?"},
            requested_by="model",
        ),
        ctx,
    )
    assert result.status == "denied"
