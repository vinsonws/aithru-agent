"""Agent thread message routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from aithru_agent.api.dependencies import (
    ApiDependencies,
    AppendMessageRequest,
    api_deps,
)
from aithru_agent.domain import (
    AgentMessage,
    AgentThread,
    AgentWorkspaceFile,
    AgentWorkspaceImageAttachment,
)
from aithru_agent.domain.errors import AgentError

router = APIRouter()


@router.post(
    "/api/threads/{thread_id}/messages",
    status_code=201,
    response_model=AgentMessage,
)
async def append_message(
    request: Request,
    thread_id: str,
    body: AppendMessageRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentMessage:
    thread = await deps.require_thread(request, thread_id)
    attachments = await _validated_image_attachments(
        request,
        thread=thread,
        attachments=body.attachments,
        deps=deps,
    )
    message = await deps.runtime.store.append_message(
        thread_id=thread_id,
        role=body.role,
        content=body.content,
        attachments=attachments,
    )
    return message


@router.get("/api/threads/{thread_id}/messages", response_model=list[AgentMessage])
async def list_messages(
    request: Request,
    thread_id: str,
    deps: ApiDependencies = Depends(api_deps),
) -> list[AgentMessage]:
    await deps.require_thread(request, thread_id)
    return await deps.runtime.store.list_messages(thread_id)


async def _validated_image_attachments(
    request: Request,
    *,
    thread: AgentThread,
    attachments: list[AgentWorkspaceImageAttachment],
    deps: ApiDependencies,
) -> list[AgentWorkspaceImageAttachment]:
    validated: list[AgentWorkspaceImageAttachment] = []
    for attachment in attachments:
        workspace = await deps.require_workspace(request, attachment.workspace_id)
        if workspace.org_id != thread.org_id:
            raise HTTPException(status_code=404, detail="Workspace not found")
        try:
            file = await _workspace_file_metadata(
                deps,
                workspace_id=attachment.workspace_id,
                path=attachment.path,
            )
        except AgentError as err:
            raise HTTPException(status_code=404, detail=err.message) from err
        actual = _attachment_from_workspace_file(file)
        if attachment.media_type != actual.media_type:
            raise HTTPException(status_code=409, detail="Attachment media_type does not match workspace file")
        if attachment.size != actual.size:
            raise HTTPException(status_code=409, detail="Attachment size does not match workspace file")
        if attachment.content_hash is not None and attachment.content_hash != actual.content_hash:
            raise HTTPException(status_code=409, detail="Attachment content_hash does not match workspace file")
        validated.append(actual)
    return validated


def _attachment_from_workspace_file(file: AgentWorkspaceFile) -> AgentWorkspaceImageAttachment:
    try:
        return AgentWorkspaceImageAttachment(
            kind="workspace_image",
            workspace_id=file.workspace_id,
            path=file.path,
            media_type=file.media_type or "",
            size=file.size,
            content_hash=file.content_hash,
        )
    except ValidationError as err:
        raise _workspace_image_http_error(err) from err


async def _workspace_file_metadata(
    deps: ApiDependencies,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceFile:
    for file in await deps.runtime.store.list_workspace_files(workspace_id):
        if file.path == path:
            return file
    raise AgentError("NOT_FOUND", f"Workspace file not found: {path}")


def _workspace_image_http_error(err: ValidationError) -> HTTPException:
    message = "; ".join(str(error.get("msg", "")) for error in err.errors()) or str(err)
    if "Unsupported image media type" in message:
        return HTTPException(status_code=415, detail=message)
    if "maximum image size" in message:
        return HTTPException(status_code=413, detail=message)
    return HTTPException(status_code=409, detail=message)
