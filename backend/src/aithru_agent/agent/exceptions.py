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


class RunPausedForExternalApproval(AgentError):
    """Raised when a run is paused waiting for a provider-owned approval."""

    def __init__(self, run_id: str, approval_id: str, capability_run_id: str) -> None:
        super().__init__(
            "RUN_PAUSED_FOR_EXTERNAL_APPROVAL",
            f"Run {run_id} paused for external approval {approval_id} on capability run {capability_run_id}",
        )
        self.run_id = run_id
        self.approval_id = approval_id
        self.capability_run_id = capability_run_id


class RunPausedForExternalRun(AgentError):
    """Raised when a run is paused waiting for a provider-owned external run."""

    def __init__(self, run_id: str, capability_run_id: str) -> None:
        super().__init__(
            "RUN_PAUSED_FOR_EXTERNAL_RUN",
            f"Run {run_id} paused for external capability run {capability_run_id}",
        )
        self.run_id = run_id
        self.capability_run_id = capability_run_id


class RunPausedForSubagent(AgentError):
    """Raised when a run is paused waiting for a child subagent run."""

    def __init__(self, run_id: str, subagent_run_id: str, child_run_id: str) -> None:
        super().__init__(
            "RUN_PAUSED_FOR_SUBAGENT",
            f"Run {run_id} paused for subagent {subagent_run_id} on child run {child_run_id}",
        )
        self.run_id = run_id
        self.subagent_run_id = subagent_run_id
        self.child_run_id = child_run_id


class RunPausedForInput(AgentError):
    """Raised when a run is paused waiting for user input."""

    def __init__(self, run_id: str, input_request_id: str) -> None:
        super().__init__(
            "RUN_PAUSED_FOR_INPUT",
            f"Run {run_id} paused for user input {input_request_id}",
        )
        self.run_id = run_id
        self.input_request_id = input_request_id
