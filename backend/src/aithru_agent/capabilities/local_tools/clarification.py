from typing import Any

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)

from ..descriptors import AgentRunContext


class ClarificationLocalTool:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="ask_clarification",
                kind=AgentToolKind.LOCAL_TOOL,
                description=(
                    "Ask the user for clarification before proceeding. "
                    "Use this when the request is ambiguous, incomplete, or you need to "
                    "confirm an approach before taking action. The user will see the "
                    "question and can respond directly or choose from provided options."
                ),
                input_schema={
                    "type": "object",
                    "required": ["question"],
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The clarification question to ask the user.",
                        },
                        "clarification_type": {
                            "type": "string",
                            "enum": [
                                "missing_info",
                                "ambiguous_requirement",
                                "approach_choice",
                                "risk_confirmation",
                                "suggestion",
                            ],
                            "default": "missing_info",
                            "description": "Category of clarification needed.",
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional background explaining why clarification is needed.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of choices for the user to pick from.",
                        },
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
        if request.tool_name != "ask_clarification":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown clarification tool: {request.tool_name}"},
                redaction="none",
            )
        if context.thread_id is None:
            return AgentToolCallResult(
                status="denied",
                error={"message": "Clarification requests require an Agent Thread"},
                redaction="none",
            )
        input_data = _input_dict(request.input)
        question = _required_string(input_data, "question")
        clarification_type = _optional_string(input_data.get("clarification_type")) or "missing_info"
        context_str = _optional_string(input_data.get("context"))
        options = _optional_string_list(input_data.get("options"))
        return AgentToolCallResult(
            status="completed",
            output={
                "tool_call_id": request.id,
                "question": question,
                "clarification_type": clarification_type,
                "context": context_str,
                "options": options,
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


def _optional_string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    result = [str(item).strip() for item in value if item is not None and str(item).strip()]
    return result or None
