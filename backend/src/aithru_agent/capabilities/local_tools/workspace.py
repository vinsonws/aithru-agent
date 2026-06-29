from typing import Any

from pydantic import ValidationError

from aithru_agent.capabilities.recovery import recoverable_tool_result
from aithru_agent.domain import (
    AgentToolFailureKind,
    AgentToolRecoveryAction,
    AgentWorkspacePatchResult,
    AgentWorkspaceImageViewResult,
    AgentWorkspaceTextPatchRequest,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
    apply_workspace_text_patch,
    normalize_workspace_image_path,
    workspace_image_content_base64,
)
from aithru_agent.domain.errors import AgentError
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
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read"],
                approval_policy="never",
                failure_policy="return_recoverable",
            ),
            AgentToolDescriptor(
                name="workspace.view_image",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Read a supported image file from the current Agent workspace as base64.",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
                output_schema=AgentWorkspaceImageViewResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.workspace.read"],
                approval_policy="never",
                failure_policy="return_recoverable",
            ),
            AgentToolDescriptor(
                name="workspace.write_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Write a file to the current Agent workspace.",
                input_schema={
                    "type": "object",
                    "required": ["path", "content"],
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "media_type": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.workspace.write"],
                approval_policy="on_risk",
                failure_policy="return_recoverable",
            ),
            AgentToolDescriptor(
                name="workspace.patch_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Patch a text file in the current Agent workspace with explicit replacements.",
                input_schema=AgentWorkspaceTextPatchRequest.model_json_schema(),
                output_schema=AgentWorkspacePatchResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.workspace.write"],
                approval_policy="on_risk",
                failure_policy="return_recoverable",
            ),
            AgentToolDescriptor(
                name="workspace.delete_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Delete a file from the current Agent workspace.",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.workspace.write"],
                approval_policy="on_risk",
                failure_policy="return_recoverable",
            ),
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        view_image_path: str | None = None
        if request.tool_name == "workspace.view_image":
            path_or_denied = _view_image_path(request.input)
            if isinstance(path_or_denied, AgentToolCallResult):
                return path_or_denied
            view_image_path = path_or_denied
            input_data: dict[str, Any] = {}
        else:
            input_data = _input_dict(request.input)
        match request.tool_name:
            case "workspace.list_files":
                files = await self._store.list_workspace_files(context.workspace_id)
                files = [
                    file
                    for file in files
                    if _path_allowed(file.path, context.workspace_allowed_paths)
                ]
                output: Any = {"files": [file.model_dump(mode="json") for file in files]}
            case "workspace.read_file":
                denied = _deny_if_path_outside_policy(input_data["path"], context)
                if denied:
                    return denied
                content = await self._store.read_workspace_file(
                    context.workspace_id,
                    str(input_data["path"]),
                )
                output = {
                    "path": input_data["path"],
                    "content": content.content,
                    "media_type": content.media_type,
                }
            case "workspace.view_image":
                if not context.model_vision_enabled:
                    return _denied_result("workspace.view_image requires a vision-capable model")
                image_path = view_image_path
                if image_path is None:
                    return _denied_result("workspace.view_image path must be a non-blank string")
                denied = _deny_if_path_outside_policy(image_path, context)
                if denied:
                    return denied
                try:
                    file = await _workspace_file(
                        self._store,
                        workspace_id=context.workspace_id,
                        path=image_path,
                    )
                    content = await self._store.read_workspace_file(
                        context.workspace_id,
                        image_path,
                    )
                    output = AgentWorkspaceImageViewResult(
                        workspace_id=context.workspace_id,
                        path=file.path,
                        media_type=file.media_type or "",
                        size=file.size,
                        content_hash=file.content_hash,
                        content_base64=workspace_image_content_base64(content.content),
                    ).model_dump(mode="json")
                except (AgentError, ValidationError, ValueError) as err:
                    return AgentToolCallResult(
                        status="denied",
                        error={"message": _error_message(err)},
                        redaction="none",
                    )
            case "workspace.write_file":
                denied = _deny_if_path_outside_policy(input_data["path"], context)
                if denied:
                    return denied
                file = await self._store.write_workspace_file(
                    workspace_id=context.workspace_id,
                    path=str(input_data["path"]),
                    content=input_data["content"],
                    media_type=input_data.get("media_type"),
                )
                output = file.model_dump(mode="json")
            case "workspace.patch_file":
                patch_request = _patch_request(input_data)
                if isinstance(patch_request, AgentToolCallResult):
                    return patch_request
                denied = _deny_if_path_outside_policy(patch_request.path, context)
                if denied:
                    return denied
                try:
                    current = await self._store.read_workspace_file(
                        context.workspace_id,
                        patch_request.path,
                    )
                    before_file = await _workspace_file(
                        self._store,
                        workspace_id=context.workspace_id,
                        path=patch_request.path,
                    )
                except AgentError as err:
                    return AgentToolCallResult(
                        status="denied",
                        error={"message": err.message},
                        redaction="none",
                    )
                if not isinstance(current.content, str):
                    return AgentToolCallResult(
                        status="denied",
                        error={"message": "workspace.patch_file only supports text files"},
                        redaction="none",
                    )
                try:
                    patched_content, replacement_count = apply_workspace_text_patch(
                        current.content,
                        patch_request,
                    )
                except ValueError as err:
                    return AgentToolCallResult(
                        status="denied",
                        error={"message": str(err)},
                        redaction="none",
                    )
                patched_file = await self._store.write_workspace_file(
                    workspace_id=context.workspace_id,
                    path=patch_request.path,
                    content=patched_content,
                    media_type=patch_request.media_type or current.media_type,
                )
                output = AgentWorkspacePatchResult(
                    workspace_id=context.workspace_id,
                    path=patched_file.path,
                    version_before=before_file.version,
                    version_after=patched_file.version,
                    file_version_before=before_file.file_version,
                    file_version_after=patched_file.file_version,
                    size_before=before_file.size,
                    size_after=patched_file.size,
                    replacement_count=replacement_count,
                    content_hash=patched_file.content_hash,
                ).model_dump(mode="json")
            case "workspace.delete_file":
                denied = _deny_if_path_outside_policy(input_data["path"], context)
                if denied:
                    return denied
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


def _view_image_path(value: object) -> str | AgentToolCallResult:
    if not isinstance(value, dict):
        return _denied_result("workspace.view_image input must be an object")
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        return _denied_result("workspace.view_image path must be a non-blank string")
    try:
        return normalize_workspace_image_path(path)
    except ValueError as err:
        return _denied_result(str(err))


def _denied_result(message: str) -> AgentToolCallResult:
    return AgentToolCallResult(
        status="denied",
        error={"message": message},
        redaction="none",
    )


def _error_message(err: Exception) -> str:
    if isinstance(err, AgentError):
        return err.message
    if isinstance(err, ValidationError):
        messages = [str(error.get("msg", "")) for error in err.errors()]
        return "; ".join(message for message in messages if message) or str(err)
    return str(err)


def _patch_request(input_data: dict[str, Any]) -> AgentWorkspaceTextPatchRequest | AgentToolCallResult:
    try:
        return AgentWorkspaceTextPatchRequest.model_validate(input_data)
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": "Invalid workspace patch request", "details": err.errors()},
            redaction="none",
        )


async def _workspace_file(
    store: AgentStore,
    *,
    workspace_id: str,
    path: str,
):
    normalized = _normalize_for_policy(path)
    for file in await store.list_workspace_files(workspace_id):
        if file.path == normalized:
            return file
    raise AgentError("NOT_FOUND", f"Workspace file not found: {path}")


def _suggest_workspace_path(path: object, allowed_paths: list[str] | None) -> str | None:
    if not allowed_paths or not isinstance(path, str) or not path.strip():
        return None
    filename = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not filename or filename in {".", ".."}:
        return None
    normalized_allowed = {_normalize_for_policy(allowed_path) for allowed_path in allowed_paths}
    preferred_root = "/outputs" if "/outputs" in normalized_allowed else allowed_paths[0]
    return f"{preferred_root.rstrip('/')}/{filename}"


def _deny_if_path_outside_policy(path: object, context: AgentRunContext) -> AgentToolCallResult | None:
    if _path_allowed(str(path), context.workspace_allowed_paths):
        return None
    suggested_path = _suggest_workspace_path(path, context.workspace_allowed_paths)
    suggested_input = {"path": suggested_path} if suggested_path is not None else None
    return recoverable_tool_result(
        status="denied",
        kind=AgentToolFailureKind.INVALID_INPUT,
        action=AgentToolRecoveryAction.RETRY_WITH_CORRECTED_INPUT,
        message="Path is outside allowed workspace paths.",
        model_guidance="Retry with an absolute workspace path under one of the allowed workspace paths.",
        suggested_input=suggested_input,
        allowed_values={"allowed_paths": context.workspace_allowed_paths or []},
        attempt_key="workspace_path_policy",
        error={"message": f"Path is outside allowed workspace paths: {path}"},
    )


def _path_allowed(path: str, allowed_paths: list[str] | None) -> bool:
    if not allowed_paths:
        return True
    normalized = _normalize_for_policy(path)
    return any(
        normalized == allowed or normalized.startswith(allowed.rstrip("/") + "/")
        for allowed in (_normalize_for_policy(allowed_path) for allowed_path in allowed_paths)
    )


def _normalize_for_policy(path: str) -> str:
    normalized = path.replace("\\", "/")
    parts: list[str] = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)
