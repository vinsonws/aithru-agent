"""Internal Pydantic AI capability composition for Aithru Agent."""

from aithru_agent.agent.capabilities.approvals import (
    require_approved_tool_call,
    tool_requires_approval,
)
from aithru_agent.agent.capabilities.boundary import AithruBoundaryCapability
from aithru_agent.agent.capabilities.events import (
    AITHRU_BOUNDARY_METADATA_KEY,
    AITHRU_BOUNDARY_METADATA_VALUE,
    AITHRU_REQUIRES_APPROVAL_METADATA_KEY,
    AITHRU_RISK_LEVEL_METADATA_KEY,
    AITHRU_TOOL_KIND_METADATA_KEY,
    AITHRU_TOOL_NAME_METADATA_KEY,
    mark_aithru_boundary_tool,
    metadata_for_descriptor,
)
from aithru_agent.agent.capabilities.skills import SkillInstructionCapability
from aithru_agent.agent.capabilities.subagents import TASK_TOOL_NAME, SubagentTaskCapability
from aithru_agent.agent.capabilities.toolset import AithruToolset

__all__ = [
    "AITHRU_BOUNDARY_METADATA_KEY",
    "AITHRU_BOUNDARY_METADATA_VALUE",
    "AITHRU_REQUIRES_APPROVAL_METADATA_KEY",
    "AITHRU_RISK_LEVEL_METADATA_KEY",
    "AITHRU_TOOL_KIND_METADATA_KEY",
    "AITHRU_TOOL_NAME_METADATA_KEY",
    "AithruBoundaryCapability",
    "AithruToolset",
    "SkillInstructionCapability",
    "SubagentTaskCapability",
    "TASK_TOOL_NAME",
    "mark_aithru_boundary_tool",
    "metadata_for_descriptor",
    "require_approved_tool_call",
    "tool_requires_approval",
]
