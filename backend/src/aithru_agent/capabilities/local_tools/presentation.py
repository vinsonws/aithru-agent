from typing import Literal

from pydantic import Field, model_validator

from aithru_agent.domain import (
    AgentPresentation,
    AgentPresentationAction,
    AgentPresentationEffect,
    AgentPresentationResource,
    AgentPresentationSource,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.stream.presentations import (
    available_views_for_file,
    preferred_view_for_file,
)

from ..descriptors import AgentRunContext


class PresentResourceRef(AithruBaseModel):
    kind: Literal["workspace_file", "artifact"]
    path: str | None = None
    id: str | None = None


class PresentationEffectRequest(AithruBaseModel):
    kind: Literal["open_panel", "focus_presentation", "scroll_to", "highlight", "none"]
    panel: str | None = None
    surface: Literal["conversation", "side_panel", "approval_panel", "activity", "header"] | None = None
    presentation_id: str | None = None
    mode: Literal["soft", "assertive"] = "soft"

    @model_validator(mode="after")
    def _effect_request_has_required_target(self) -> "PresentationEffectRequest":
        if self.kind == "open_panel" and self.panel is None:
            raise ValueError("open_panel presentation effects require panel")
        return self


class PresentationPresentRequest(AithruBaseModel):
    resources: list[PresentResourceRef] = Field(min_length=1)
    surfaces: list[Literal["conversation", "side_panel", "approval_panel", "activity", "header"]] = Field(
        default_factory=lambda: ["conversation"],
        min_length=1,
    )
    preferred_view: str | None = None
    effects: list[PresentationEffectRequest] = Field(default_factory=list)
    reason: str | None = None


class PresentationLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="presentation.present",
                kind=AgentToolKind.LOCAL_TOOL,
                description=(
                    "Request that existing workspace files or artifacts be presented to the user. "
                    "The harness validates resources, views, surfaces, actions, and effects; "
                    "the tool does not accept custom UI schemas."
                ),
                input_schema=PresentationPresentRequest.model_json_schema(),
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
        if request.tool_name != "presentation.present":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unsupported tool: {request.tool_name}"},
                redaction="none",
            )
        try:
            input_data = PresentationPresentRequest.model_validate(request.input)
        except (AgentError, ValueError) as err:
            return AgentToolCallResult(
                status="denied",
                error={"message": _error_message(err)},
                redaction="none",
            )

        presentations: list[AgentPresentation] = []
        rejected_requests: list[dict] = []

        for resource_ref in input_data.resources:
            presentation, rejection = await self._build_presentation(
                resource_ref=resource_ref,
                input_data=input_data,
                request_id=request.id,
                context=context,
            )
            if presentation is not None:
                presentations.append(presentation)
            if rejection is not None:
                rejected_requests.append(rejection)

        return AgentToolCallResult(
            status="completed",
            output={
                "presentations": [
                    presentation.model_dump(mode="json", exclude_none=True)
                    for presentation in presentations
                ],
                "rejected_requests": rejected_requests,
            },
            redaction="none",
        )

    async def _build_presentation(
        self,
        *,
        resource_ref: PresentResourceRef,
        input_data: PresentationPresentRequest,
        request_id: str,
        context: AgentRunContext,
    ) -> tuple[AgentPresentation | None, dict | None]:
        if resource_ref.kind == "workspace_file":
            return await self._build_workspace_file_presentation(
                resource_ref=resource_ref,
                input_data=input_data,
                request_id=request_id,
                context=context,
            )
        return await self._build_artifact_presentation(
            resource_ref=resource_ref,
            input_data=input_data,
            request_id=request_id,
            context=context,
        )

    async def _build_workspace_file_presentation(
        self,
        *,
        resource_ref: PresentResourceRef,
        input_data: PresentationPresentRequest,
        request_id: str,
        context: AgentRunContext,
    ) -> tuple[AgentPresentation | None, dict | None]:
        if resource_ref.path is None:
            return None, {"resource": {"kind": "workspace_file"}, "reason": "workspace_file resources require path"}
        file = await _workspace_file(self._store, context.workspace_id, resource_ref.path)
        if file is None:
            return None, {"resource": {"kind": "workspace_file", "path": resource_ref.path}, "reason": "Workspace file not found"}
        name = _basename(file.path)
        views = available_views_for_file(name=name, media_type=file.media_type)
        preferred = _coerce_preferred_view(input_data.preferred_view, views)
        preferred_view, rejection = preferred

        return self._make_presentation(
            resource=AgentPresentationResource(kind="workspace_file", path=file.path),
            title=name,
            summary=file.path,
            input_data=input_data,
            request_id=request_id,
            context=context,
            available_views=views,
            preferred_view=preferred_view,
            rejection=rejection,
            resource_ref={"kind": "workspace_file", "path": resource_ref.path},
            metadata={
                "workspace_id": file.workspace_id,
                "media_type": file.media_type,
                "size": file.size,
            },
        )

    async def _build_artifact_presentation(
        self,
        *,
        resource_ref: PresentResourceRef,
        input_data: PresentationPresentRequest,
        request_id: str,
        context: AgentRunContext,
    ) -> tuple[AgentPresentation | None, dict | None]:
        if resource_ref.id is None:
            return None, {"resource": {"kind": "artifact"}, "reason": "artifact resources require id"}
        artifact = await self._store.get_artifact(resource_ref.id)
        if artifact is None:
            return None, {"resource": {"kind": "artifact", "id": resource_ref.id}, "reason": f"Artifact does not exist: {resource_ref.id}"}
        if artifact.workspace_id != context.workspace_id:
            return None, {"resource": {"kind": "artifact", "id": resource_ref.id}, "reason": f"Artifact is outside this workspace: {resource_ref.id}"}
        if artifact.run_id is not None and artifact.run_id != context.run_id:
            return None, {"resource": {"kind": "artifact", "id": resource_ref.id}, "reason": f"Artifact is outside this run: {resource_ref.id}"}
        name = artifact.name
        views = available_views_for_file(name=name, media_type=artifact.media_type, artifact_type=artifact.type)
        preferred = _coerce_preferred_view(input_data.preferred_view, views)
        preferred_view, rejection = preferred

        return self._make_presentation(
            resource=AgentPresentationResource(kind="artifact", id=artifact.id),
            title=name,
            summary=artifact.uri,
            input_data=input_data,
            request_id=request_id,
            context=context,
            available_views=views,
            preferred_view=preferred_view,
            rejection=rejection,
            resource_ref={"kind": "artifact", "id": resource_ref.id},
            metadata={
                "type": artifact.type,
                "media_type": artifact.media_type,
                "uri": artifact.uri,
            },
        )

    def _make_presentation(
        self,
        *,
        resource: AgentPresentationResource,
        title: str,
        summary: str | None,
        input_data: PresentationPresentRequest,
        request_id: str,
        context: AgentRunContext,
        available_views: list[str],
        preferred_view: str,
        rejection: dict | None,
        resource_ref: dict,
        metadata: dict,
    ) -> tuple[AgentPresentation | None, dict | None]:
        presentation_id = _presentation_id(
            context.run_id,
            request_id,
            resource.kind,
            resource.id or resource.path or title,
        )
        actions = [
            AgentPresentationAction(kind="open_view", label=_view_label(view), view=view)
            for view in available_views
            if view not in {"download"}
        ]
        if "download" in available_views:
            actions.append(AgentPresentationAction(kind="download", label="Download"))
        effects = [
            _presentation_effect(effect, presentation_id)
            for effect in input_data.effects
        ]
        return (
            AgentPresentation(
                id=presentation_id,
                org_id=context.org_id,
                thread_id=context.thread_id,
                run_id=context.run_id,
                status="ready",
                priority="normal",
                title=title,
                summary=summary,
                reason=input_data.reason,
                resource=resource,
                surfaces=input_data.surfaces,
                preferred_view=preferred_view,
                available_views=available_views,
                effects=effects,
                actions=actions,
                source=AgentPresentationSource(
                    created_by="model_request",
                    tool_call_id=request_id,
                    tool_name="presentation.present",
                ),
                metadata={key: value for key, value in metadata.items() if value is not None},
            ),
            rejection,
        )


def _coerce_preferred_view(requested: str | None, available: list[str]) -> tuple[str, dict | None]:
    if requested is None or requested in available:
        return requested or available[0], None
    return available[0], {
        "resource": {},
        "reason": f"Requested view {requested} is unavailable; using {available[0]}.",
    }


def _presentation_effect(
    effect: PresentationEffectRequest,
    presentation_id: str,
) -> AgentPresentationEffect:
    data = effect.model_dump(exclude_none=True)
    if effect.kind in {"focus_presentation", "scroll_to", "highlight"}:
        data["presentation_id"] = presentation_id
    return AgentPresentationEffect(**data)


def _presentation_id(run_id: str, tool_call_id: str, kind: str, value: str) -> str:
    return f"p_{run_id}_{tool_call_id}_{kind}_{_safe_id(value)}"


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_") or "resource"


def _view_label(view: str) -> str:
    labels = {
        "html_preview": "Preview",
        "source_text": "Source",
        "markdown": "Preview",
        "json": "JSON",
        "image": "Preview",
        "pdf": "Preview",
        "diff": "Diff",
        "approval_review": "Review",
        "activity_detail": "Details",
        "open_external": "Open",
        "none": "Open",
    }
    return labels.get(view, view.capitalize())


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or stripped or "file"


async def _workspace_file(store: AgentStore, workspace_id: str, path: str) -> object | None:
    files = await store.list_workspace_files(workspace_id)
    for file in files:
        if file.path == path:
            return file
    return None


def _error_message(err: Exception) -> str:
    if isinstance(err, AgentError):
        return err.message
    return str(err)
