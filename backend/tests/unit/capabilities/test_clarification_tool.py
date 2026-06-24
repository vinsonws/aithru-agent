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
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="ws_1",
        thread_id="thread_1",
        scopes=["agent.input.write"],
    )


def test_lists_ask_clarification_descriptor(tool: ClarificationLocalTool):
    descriptors = tool.list_tools()
    assert len(descriptors) == 1
    d = descriptors[0]
    assert d.name == "ask_clarification"
    assert d.kind == "local_tool"
    assert d.risk_level == "safe"
    assert "agent.input.write" in d.required_scopes
    assert "question" in d.input_schema.get("required", [])
    assert "options" in d.input_schema["properties"]
    assert "clarification_type" in d.input_schema["properties"]
    assert "context" in d.input_schema["properties"]


def test_descriptor_input_schema_allows_options(tool: ClarificationLocalTool):
    d = tool.list_tools()[0]
    options_prop = d.input_schema["properties"]["options"]
    assert options_prop["type"] == "array"
    assert options_prop.get("items", {}).get("type") == "string"


@pytest.mark.asyncio
async def test_execute_ask_clarification_returns_completed(tool: ClarificationLocalTool, context: AgentRunContext):
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="ask_clarification",
            input={
                "question": "What topic?",
                "clarification_type": "missing_info",
                "options": ["A", "B"],
            },
            requested_by="model",
        ),
        context,
    )
    assert result.status == "completed"
    assert result.output["question"] == "What topic?"
    assert result.output["options"] == ["A", "B"]


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_denied(tool: ClarificationLocalTool, context: AgentRunContext):
    result = await tool.execute(
        AgentToolCallRequest(
            id="call_1",
            tool_name="unknown_tool",
            input={},
            requested_by="model",
        ),
        context,
    )
    assert result.status == "denied"


@pytest.mark.asyncio
async def test_execute_missing_question_raises(tool: ClarificationLocalTool, context: AgentRunContext):
    with pytest.raises(ValueError, match="question"):
        await tool.execute(
            AgentToolCallRequest(
                id="call_1",
                tool_name="ask_clarification",
                input={"options": ["A"]},
                requested_by="model",
            ),
            context,
        )
