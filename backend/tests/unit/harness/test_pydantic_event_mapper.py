from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
)

from aithru_agent.harness.drivers.pydantic_ai.event_mapper import map_pydantic_event


def test_maps_pydantic_text_delta_to_message_delta_intent() -> None:
    intent = map_pydantic_event(PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="hello")))

    assert intent == {"type": "message.delta", "payload": {"delta": "hello"}}


def test_maps_pydantic_tool_call_and_result_to_tool_intents() -> None:
    call_part = ToolCallPart(
        tool_name="workspace.read_file",
        args={"input": {"path": "/notes.md"}},
        tool_call_id="tc_1",
    )
    result_part = ToolReturnPart(
        tool_name="workspace.read_file",
        content={"content": "notes"},
        tool_call_id="tc_1",
    )

    call_intent = map_pydantic_event(FunctionToolCallEvent(part=call_part, args_valid=True))
    result_intent = map_pydantic_event(FunctionToolResultEvent(part=result_part))

    assert call_intent == {
        "type": "tool.proposed",
        "payload": {
            "tool_call_id": "tc_1",
            "tool_name": "workspace.read_file",
            "args": {"input": {"path": "/notes.md"}},
        },
    }
    assert result_intent == {
        "type": "tool.completed",
        "payload": {
            "tool_call_id": "tc_1",
            "tool_name": "workspace.read_file",
            "content": {"content": "notes"},
        },
    }


def test_maps_final_result_to_final_intent() -> None:
    intent = map_pydantic_event(FinalResultEvent(tool_name=None, tool_call_id=None))

    assert intent == {"type": "final_result", "payload": {}}
