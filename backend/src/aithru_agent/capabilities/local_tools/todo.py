from typing import Any

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.persistence.protocols import AgentStore

from ..descriptors import AgentRunContext


class TodoLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="todo.create",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Create a runtime Agent todo.",
                input_schema={
                    "type": "object",
                    "required": ["title"],
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "running", "done", "blocked", "cancelled"],
                        },
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.todo.write"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="todo.update",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Update a runtime Agent todo.",
                input_schema={
                    "type": "object",
                    "required": ["todo_id"],
                    "properties": {
                        "todo_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "running", "done", "blocked", "cancelled"],
                        },
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.todo.write"],
                approval_policy="never",
            ),
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        input_data = _input_dict(request.input)
        match request.tool_name:
            case "todo.create":
                todo = await self._store.create_todo(
                    run_id=context.run_id,
                    title=str(input_data["title"]),
                    status=input_data.get("status", "pending"),
                    description=input_data.get("description"),
                    created_by="agent",
                )
            case "todo.update":
                todo = await self._store.update_todo(
                    str(input_data["todo_id"]),
                    title=input_data.get("title"),
                    description=input_data.get("description"),
                    status=input_data.get("status"),
                )
            case _:
                return AgentToolCallResult(
                    status="denied",
                    error={"message": f"Unknown todo tool: {request.tool_name}"},
                    redaction="none",
                )
        return AgentToolCallResult(status="completed", output=todo.model_dump(mode="json"), redaction="none")


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value
