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


class ArtifactLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="artifact.create",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Create an Agent artifact.",
                input_schema={
                    "type": "object",
                    "required": ["type", "name"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "text",
                                "markdown",
                                "json",
                                "decision",
                                "report",
                                "file",
                                "patch",
                                "workflow_draft",
                            ],
                        },
                        "name": {"type": "string"},
                        "media_type": {"type": "string"},
                        "uri": {"type": "string"},
                        "content": {},
                        "metadata": {"type": "object"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.artifact.write"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="artifact.finalize",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Finalize an Agent artifact.",
                input_schema={
                    "type": "object",
                    "required": ["artifact_id"],
                    "properties": {"artifact_id": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.artifact.write"],
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
            case "artifact.create":
                artifact = await self._store.create_artifact(
                    org_id=context.org_id,
                    workspace_id=context.workspace_id,
                    run_id=context.run_id,
                    type=input_data["type"],
                    name=str(input_data["name"]),
                    media_type=input_data.get("media_type"),
                    uri=input_data.get("uri"),
                    content=input_data.get("content"),
                    metadata=input_data.get("metadata"),
                )
            case "artifact.finalize":
                artifact = await self._store.finalize_artifact(str(input_data["artifact_id"]))
            case _:
                return AgentToolCallResult(
                    status="denied",
                    error={"message": f"Unknown artifact tool: {request.tool_name}"},
                    redaction="none",
                )
        return AgentToolCallResult(
            status="completed",
            output=artifact.model_dump(mode="json"),
            redaction="none",
        )


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value
