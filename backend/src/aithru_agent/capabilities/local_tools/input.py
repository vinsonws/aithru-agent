from typing import Any

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)

from ..descriptors import AgentRunContext


class InputLocalTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="input.request",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Pause the current Agent Run and request user input in the Agent Thread.",
                input_schema={
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.input.write"],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name != "input.request":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown input tool: {request.tool_name}"},
                redaction="none",
            )
        if context.thread_id is None:
            return AgentToolCallResult(
                status="denied",
                error={"message": "Input requests require an Agent Thread"},
                redaction="none",
            )
        input_data = _input_dict(request.input)
        prompt = _required_string(input_data, "prompt")
        reason = _optional_string(input_data.get("reason"))
        return AgentToolCallResult(
            status="completed",
            output={
                "input_request_id": request.id,
                "tool_call_id": request.id,
                "prompt": prompt,
                "reason": reason,
            },
            redaction="none",
        )


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value


def _required_string(input_data: dict[str, Any], key: str) -> str:
    value = input_data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required input field: {key}")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    stripped = value.strip()
    return stripped or None
