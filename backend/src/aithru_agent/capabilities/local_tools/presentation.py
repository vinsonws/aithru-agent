from typing import Literal

from pydantic import Field

from aithru_agent.domain import (
    AgentDisplayCard,
    AgentDisplayCardAction,
    AgentDisplayCardResource,
    AgentDisplayCardSource,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore

from ..descriptors import AgentRunContext


class PresentResourceRef(AithruBaseModel):
    kind: Literal["workspace_file", "artifact"]
    path: str | None = None
    id: str | None = None


class PresentResourcesRequest(AithruBaseModel):
    surface: Literal["conversation", "side_panel", "both"] = "conversation"
    resources: list[PresentResourceRef] = Field(min_length=1)


class PresentationLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="present_resources",
                kind=AgentToolKind.LOCAL_TOOL,
                description=(
                    "Present existing workspace files or artifacts to the user as conversation cards. "
                    "This tool accepts resource references only; it does not accept custom UI."
                ),
                input_schema=PresentResourcesRequest.model_json_schema(),
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read"],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name != "present_resources":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unsupported tool: {request.tool_name}"},
                redaction="none",
            )
        try:
            input_data = PresentResourcesRequest.model_validate(request.input)
            cards = [
                await self._card_for_resource(resource, input_data.surface, request, context)
                for resource in input_data.resources
            ]
        except (AgentError, ValueError) as err:
            return AgentToolCallResult(
                status="denied",
                error={"message": _error_message(err)},
                redaction="none",
            )
        return AgentToolCallResult(
            status="completed",
            output={
                "cards": [card.model_dump(mode="json", exclude_none=True) for card in cards],
                "presented": [
                    card.resource.model_dump(mode="json", exclude_none=True) for card in cards
                ],
            },
            redaction="none",
        )

    async def _card_for_resource(
        self,
        resource: PresentResourceRef,
        surface: Literal["conversation", "side_panel", "both"],
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentDisplayCard:
        if resource.kind == "workspace_file":
            if resource.path is None:
                raise ValueError("workspace_file resources require path")
            file = await _workspace_file(self._store, context.workspace_id, resource.path)
            return AgentDisplayCard(
                id=f"card_{context.run_id}_{request.id}_workspace_{_safe_id(file.path)}",
                thread_id=context.thread_id,
                run_id=context.run_id,
                surface=surface,
                type="file",
                status="ready",
                title=_basename(file.path),
                summary=file.path,
                resource=AgentDisplayCardResource(kind="workspace_file", path=file.path),
                actions=[AgentDisplayCardAction(kind="preview", label="Preview")],
                source=AgentDisplayCardSource(
                    created_by="model_request",
                    tool_call_id=request.id,
                    tool_name=request.tool_name,
                ),
                metadata={
                    "workspace_id": file.workspace_id,
                    "media_type": file.media_type,
                    "size": file.size,
                },
            )
        if resource.id is None:
            raise ValueError("artifact resources require id")
        artifact = await self._store.get_artifact(resource.id)
        if artifact is None:
            raise AgentError("ARTIFACT_NOT_FOUND", f"Artifact does not exist: {resource.id}")
        if artifact.workspace_id != context.workspace_id:
            raise AgentError("ARTIFACT_SCOPE_DENIED", f"Artifact is outside this workspace: {resource.id}")
        if artifact.run_id is not None and artifact.run_id != context.run_id:
            raise AgentError("ARTIFACT_SCOPE_DENIED", f"Artifact is outside this run: {resource.id}")
        return AgentDisplayCard(
            id=f"card_{context.run_id}_{request.id}_artifact_{_safe_id(artifact.id)}",
            thread_id=context.thread_id,
            run_id=context.run_id,
            surface=surface,
            type="artifact",
            status="ready",
            title=artifact.name,
            resource=AgentDisplayCardResource(kind="artifact", id=artifact.id),
            actions=[
                AgentDisplayCardAction(kind="preview", label="Preview"),
                AgentDisplayCardAction(kind="download", label="Download"),
            ],
            source=AgentDisplayCardSource(
                created_by="model_request",
                tool_call_id=request.id,
                tool_name=request.tool_name,
            ),
            metadata={
                "type": artifact.type,
                "media_type": artifact.media_type,
                "uri": artifact.uri,
            },
        )


async def _workspace_file(store: AgentStore, workspace_id: str, path: str):
    files = await store.list_workspace_files(workspace_id)
    for file in files:
        if file.path == path:
            return file
    raise AgentError("WORKSPACE_FILE_NOT_FOUND", f"Workspace file does not exist: {path}")


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or stripped or "file"


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_") or "resource"


def _error_message(err: Exception) -> str:
    if isinstance(err, AgentError):
        return err.message
    return str(err)
