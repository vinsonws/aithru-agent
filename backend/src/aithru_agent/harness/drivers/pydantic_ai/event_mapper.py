from typing import Any

from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    TextPartDelta,
)


def map_pydantic_event(event: object) -> dict[str, Any] | None:
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return {
            "type": "message.delta",
            "payload": {"delta": event.delta.content_delta},
        }
    if isinstance(event, FunctionToolCallEvent):
        return {
            "type": "tool.proposed",
            "payload": {
                "tool_call_id": event.part.tool_call_id,
                "tool_name": event.part.tool_name,
                "args": event.part.args,
            },
        }
    if isinstance(event, FunctionToolResultEvent):
        return {
            "type": "tool.completed",
            "payload": {
                "tool_call_id": event.part.tool_call_id,
                "tool_name": event.part.tool_name,
                "content": event.part.content,
            },
        }
    if isinstance(event, FinalResultEvent):
        return {"type": "final_result", "payload": {}}
    return None

