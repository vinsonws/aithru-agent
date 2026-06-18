"""Approval enforcement helpers for Aithru boundary capabilities."""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ApprovalRequired
from pydantic_ai.tools import AgentDepsT, ToolDefinition

from aithru_agent.agent.capabilities.events import AITHRU_REQUIRES_APPROVAL_METADATA_KEY


def tool_requires_approval(tool_def: ToolDefinition) -> bool:
    """Return whether an Aithru tool definition must be deferred for approval."""
    return bool((tool_def.metadata or {}).get(AITHRU_REQUIRES_APPROVAL_METADATA_KEY))


def require_approved_tool_call(
    ctx: RunContext[AgentDepsT],
    tool_def: ToolDefinition,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Raise Pydantic AI's approval signal when a required approval is missing."""
    if tool_requires_approval(tool_def) and not ctx.tool_call_approved:
        raise ApprovalRequired(metadata=metadata)
