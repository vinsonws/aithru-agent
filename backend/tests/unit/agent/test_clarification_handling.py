"""Unit tests for ask_clarification deferred tool call handling in AgentRuntime."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests

from aithru_agent.agent.runtime import AgentRuntime
from aithru_agent.domain import AgentRunStatus


@pytest.fixture
def runtime() -> AgentRuntime:
    """Return a basic AgentRuntime with a mock model factory."""
    rt = AgentRuntime(model="test")
    rt.model_factory = lambda _: MagicMock()
    return rt


def make_tool_call_part(name: str, args: dict, call_id: str = "call_1") -> ToolCallPart:
    """Create a ToolCallPart with the given name and args."""
    return ToolCallPart(
        tool_name=name,
        args=args,
        tool_call_id=call_id,
    )


def test_detect_clarification_call_in_requests():
    """Verify we can detect ask_clarification in DeferredToolRequests.calls."""
    requests = DeferredToolRequests(
        calls=[
            make_tool_call_part("ask_clarification", {
                "question": "What topic?",
                "clarification_type": "missing_info",
                "options": ["A", "B"],
            }),
        ],
    )
    # The method should detect this as a clarification request
    clarification_call = next(
        (c for c in requests.calls if c.tool_name == "ask_clarification"),
        None,
    )
    assert clarification_call is not None
    assert clarification_call.tool_name == "ask_clarification"
    args = clarification_call.args_as_dict(raise_if_invalid=True)
    assert args["question"] == "What topic?"
    assert args["options"] == ["A", "B"]


def test_clarification_not_detected_for_other_tools():
    """Verify non-clarification calls are not misidentified."""
    requests = DeferredToolRequests(
        calls=[
            make_tool_call_part("shell", {"command": "ls"}),
            make_tool_call_part("file_read", {"path": "/tmp/test"}),
        ],
    )
    clarification_call = next(
        (c for c in requests.calls if c.tool_name == "ask_clarification"),
        None,
    )
    assert clarification_call is None


def test_has_pending_clarification_returns_false_when_empty(runtime: AgentRuntime):
    """has_pending_clarification returns False when no clarifications are pending."""
    assert runtime.has_pending_clarification("run_1") is False


def test_has_pending_clarification_returns_false_for_unknown_run(runtime: AgentRuntime):
    """has_pending_clarification returns False for a run_id not in the dict."""
    runtime._pending_clarifications["run_abc"] = MagicMock()
    assert runtime.has_pending_clarification("run_xyz") is False


def test_has_pending_clarification_returns_true_when_pending(runtime: AgentRuntime):
    """has_pending_clarification returns True when a clarification is pending."""
    runtime._pending_clarifications["run_1"] = MagicMock()
    assert runtime.has_pending_clarification("run_1") is True
