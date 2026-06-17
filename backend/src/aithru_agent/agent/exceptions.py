"""Native agent runtime exceptions."""

from aithru_agent.domain.errors import AgentError


class RunPausedForApproval(AgentError):
    """Raised when a run is paused waiting for tool approval."""

    def __init__(self, run_id: str, approval_id: str, tool_call_id: str) -> None:
        super().__init__(
            "RUN_PAUSED_FOR_APPROVAL",
            f"Run {run_id} paused for approval {approval_id} on tool {tool_call_id}",
        )
        self.run_id = run_id
        self.approval_id = approval_id
        self.tool_call_id = tool_call_id
