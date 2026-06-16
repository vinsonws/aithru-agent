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


class WorkspaceLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="workspace.list_files",
                kind=AgentToolKind.LOCAL_TOOL,
                description="List files in the current Agent workspace.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="workspace.read_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Read a file from the current Agent workspace.",
                input_schema={"type": "object", "required": ["path"]},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="workspace.write_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Write a file to the current Agent workspace.",
                input_schema={"type": "object", "required": ["path", "content"]},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.workspace.write"],
                approval_policy="on_risk",
            ),
            AgentToolDescriptor(
                name="workspace.delete_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Delete a file from the current Agent workspace.",
                input_schema={"type": "object", "required": ["path"]},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.workspace.write"],
                approval_policy="on_risk",
            ),
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        input_data = _input_dict(request.input)
        match request.tool_name:
            case "workspace.list_files":
                files = await self._store.list_workspace_files(context.workspace_id)
                output: Any = {"files": [file.model_dump(mode="json") for file in files]}
            case "workspace.read_file":
                content = await self._store.read_workspace_file(
                    context.workspace_id,
                    str(input_data["path"]),
                )
                output = {
                    "path": input_data["path"],
                    "content": content.content,
                    "media_type": content.media_type,
                }
            case "workspace.write_file":
                file = await self._store.write_workspace_file(
                    workspace_id=context.workspace_id,
                    path=str(input_data["path"]),
                    content=input_data["content"],
                    media_type=input_data.get("media_type"),
                )
                output = file.model_dump(mode="json")
            case "workspace.delete_file":
                output = await self._store.delete_workspace_file(
                    context.workspace_id,
                    str(input_data["path"]),
                )
            case _:
                return AgentToolCallResult(
                    status="denied",
                    error={"message": f"Unknown workspace tool: {request.tool_name}"},
                    redaction="none",
                )
        return AgentToolCallResult(status="completed", output=output, redaction="none")


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value
