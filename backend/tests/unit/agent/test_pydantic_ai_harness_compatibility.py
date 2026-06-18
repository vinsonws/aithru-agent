import importlib
import inspect

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.tools import DeferredToolResults


def test_pydantic_ai_harness_dependency_is_available() -> None:
    assert importlib.import_module("pydantic_ai_harness")


def test_pydantic_ai_runtime_apis_used_by_aithru_still_match() -> None:
    stream_events_params = inspect.signature(Agent.run_stream_events).parameters

    assert "deps" in stream_events_params
    assert "deferred_tool_results" in stream_events_params
    assert "message_history" in stream_events_params

    async def compat_tool(ctx: RunContext[object], value: str) -> str:
        return value

    tool = Tool.from_schema(
        compat_tool,
        takes_ctx=True,
        name="compat.echo",
        description="Echo a compatibility probe value.",
        json_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    tool.requires_approval = True

    assert tool.requires_approval is True

    assert DeferredToolResults(approvals={"call_1": True}).approvals == {"call_1": True}

    message_history_json = ModelMessagesTypeAdapter.dump_json([])
    assert ModelMessagesTypeAdapter.validate_json(message_history_json) == []
