"""Subagent task instructions for Pydantic AI capability assembly."""

from dataclasses import dataclass

from pydantic_ai.capabilities import AbstractCapability

from aithru_agent.agent.deps import PydanticAgentDeps


TASK_TOOL_NAME = "task"


@dataclass
class SubagentTaskCapability(AbstractCapability[PydanticAgentDeps]):
    """Describe Aithru's platform child-run task tool to the model."""

    def get_instructions(self) -> str:
        return (
            "Use task(description, prompt, subagent_type) to delegate bounded work "
            "to an Aithru platform child Agent Run when a specialized subagent is available. "
            "The task tool waits for the child run and returns its result."
        )
