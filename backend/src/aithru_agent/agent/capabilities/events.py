"""Metadata helpers for Aithru-owned Pydantic AI tools."""

from dataclasses import replace
from typing import Any

from pydantic_ai.tools import ToolDefinition

from aithru_agent.domain import AgentToolDescriptor


AITHRU_BOUNDARY_METADATA_KEY = "aithru.boundary"
AITHRU_BOUNDARY_METADATA_VALUE = "capability_router"
AITHRU_REQUIRES_APPROVAL_METADATA_KEY = "aithru.requires_approval"
AITHRU_RISK_LEVEL_METADATA_KEY = "aithru.risk_level"
AITHRU_TOOL_KIND_METADATA_KEY = "aithru.tool_kind"
AITHRU_TOOL_NAME_METADATA_KEY = "aithru.tool_name"


def metadata_for_descriptor(
    descriptor: AgentToolDescriptor,
    *,
    requires_approval: bool,
) -> dict[str, Any]:
    """Return internal metadata that identifies an Aithru capability-router tool."""
    return {
        AITHRU_BOUNDARY_METADATA_KEY: AITHRU_BOUNDARY_METADATA_VALUE,
        AITHRU_REQUIRES_APPROVAL_METADATA_KEY: requires_approval,
        AITHRU_RISK_LEVEL_METADATA_KEY: str(descriptor.risk_level),
        AITHRU_TOOL_KIND_METADATA_KEY: str(descriptor.kind),
        AITHRU_TOOL_NAME_METADATA_KEY: descriptor.name,
    }


def mark_aithru_boundary_tool(tool_def: ToolDefinition) -> ToolDefinition:
    """Ensure a Pydantic tool definition carries Aithru boundary metadata."""
    return replace(
        tool_def,
        metadata={
            AITHRU_BOUNDARY_METADATA_KEY: AITHRU_BOUNDARY_METADATA_VALUE,
            **(tool_def.metadata or {}),
        },
    )
