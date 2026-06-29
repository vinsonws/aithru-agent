import base64
from typing import Any

from pydantic import ValidationError

from aithru_agent.domain import (
    AgentWorkspaceDiff,
    AgentWorkspacePatchResult,
    AgentWorkspaceFile,
    AgentWorkspaceFileVersion,
    AgentWorkspaceTextPatchRequest,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
    apply_workspace_text_patch,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.sandbox import (
    LocalPythonSandboxProvider,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxExecutionStatus,
    SandboxExecutionSummary,
    SandboxFileDeleteRequest,
    SandboxFileDeleteResult,
    SandboxFileListRequest,
    SandboxFileListResult,
    SandboxFileReadRequest,
    SandboxFileReadResult,
    SandboxFileWriteRequest,
    SandboxFileWriteResult,
    SandboxProvider,
    SandboxRunDiagnostics,
    SandboxRunPythonOutput,
    SandboxWorkspaceDiffRequest,
    SandboxWorkspaceEffectsSummary,
    SandboxWorkspaceOutputFile,
)
from aithru_agent.stream import AgentEventWriter

from ..descriptors import AgentRunContext


class SandboxLocalTool:
    def __init__(
        self,
        event_writer: AgentEventWriter,
        *,
        store: AgentStore | None = None,
        provider: SandboxProvider | None = None,
    ) -> None:
        self._event_writer = event_writer
        self._store = store
        self._provider = provider or LocalPythonSandboxProvider()

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="sandbox.list_files",
                kind=AgentToolKind.LOCAL_TOOL,
                description="List current Agent workspace file metadata through the sandbox boundary.",
                input_schema=SandboxFileListRequest.model_json_schema(),
                output_schema=SandboxFileListResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.sandbox.execute", "agent.workspace.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="sandbox.read_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Read a file from the current Agent workspace through the sandbox boundary.",
                input_schema=SandboxFileReadRequest.model_json_schema(),
                output_schema=SandboxFileReadResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.sandbox.execute", "agent.workspace.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="sandbox.diff",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Inspect metadata changes between Agent workspace snapshots through the sandbox boundary.",
                input_schema=SandboxWorkspaceDiffRequest.model_json_schema(),
                output_schema=AgentWorkspaceDiff.model_json_schema(),
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.sandbox.execute", "agent.workspace.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="sandbox.write_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Write a file to the current Agent workspace through the sandbox boundary.",
                input_schema=SandboxFileWriteRequest.model_json_schema(),
                output_schema=SandboxFileWriteResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.sandbox.execute", "agent.workspace.write"],
                approval_policy="on_risk",
            ),
            AgentToolDescriptor(
                name="sandbox.patch_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Patch a text file in the current Agent workspace through the sandbox boundary.",
                input_schema=AgentWorkspaceTextPatchRequest.model_json_schema(),
                output_schema=AgentWorkspacePatchResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.sandbox.execute", "agent.workspace.write"],
                approval_policy="on_risk",
            ),
            AgentToolDescriptor(
                name="sandbox.delete_file",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Delete a file from the current Agent workspace through the sandbox boundary.",
                input_schema=SandboxFileDeleteRequest.model_json_schema(),
                output_schema=SandboxFileDeleteResult.model_json_schema(),
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.sandbox.execute", "agent.workspace.write"],
                approval_policy="on_risk",
            ),
            AgentToolDescriptor(
                name="sandbox.run_python",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Run restricted Python code with explicit input and captured output.",
                input_schema=SandboxExecutionRequest.model_json_schema(),
                output_schema=SandboxRunPythonOutput.model_json_schema(),
                risk_level=AgentToolRiskLevel.DANGEROUS,
                required_scopes=["agent.sandbox.execute"],
                approval_policy="on_risk",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name == "sandbox.list_files":
            return await self._list_workspace_files(request, context)
        if request.tool_name == "sandbox.read_file":
            return await self._read_workspace_file(request, context)
        if request.tool_name == "sandbox.diff":
            return await self._diff_workspace(request, context)
        if request.tool_name == "sandbox.write_file":
            return await self._write_workspace_file(request, context)
        if request.tool_name == "sandbox.patch_file":
            return await self._patch_workspace_file(request, context)
        if request.tool_name == "sandbox.delete_file":
            return await self._delete_workspace_file(request, context)
        if request.tool_name != "sandbox.run_python":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown sandbox tool: {request.tool_name}"},
                redaction="none",
            )
        execution_request = _execution_request(request.input, context)
        sandbox_run_id = f"sandbox_{request.id}"

        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="sandbox.started",
            source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
            payload={
                "sandbox_run_id": sandbox_run_id,
                "language": "python",
                "status": "running",
                "timeout_ms": execution_request.timeout_ms,
            },
        )
        result = await self._provider.run_python(execution_request)
        execution = result.execution or _execution_summary(execution_request, result)
        if result.stdout:
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.stdout",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={
                    "sandbox_run_id": sandbox_run_id,
                    "stream": "stdout",
                    "delta": result.stdout,
                },
            )
        if result.stderr:
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.stderr",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={
                    "sandbox_run_id": sandbox_run_id,
                    "stream": "stderr",
                    "delta": result.stderr,
                },
            )

        persisted_files, persistence_error = await self._persist_workspace_files(
            context=context,
            sandbox_run_id=sandbox_run_id,
            files=result.workspace_files,
        )
        status: SandboxExecutionStatus = (
            "failed" if persistence_error is not None or result.status != "completed" else "completed"
        )
        diagnostics = _run_diagnostics(
            sandbox_run_id=sandbox_run_id,
            status=status,
            execution=execution,
            declared_files=result.workspace_files,
            persisted_files=persisted_files,
            persistence_error=persistence_error,
        )

        output = SandboxRunPythonOutput(
            sandbox_run_id=sandbox_run_id,
            stdout=result.stdout,
            stderr=result.stderr,
            result=result.result,
            execution=execution,
            diagnostics=diagnostics,
            workspace_files=persisted_files,
        ).model_dump(mode="json")
        if persistence_error is not None:
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.failed",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={**output, "status": "failed", "error": persistence_error},
            )
            return AgentToolCallResult(
                status="failed",
                output=output,
                error=persistence_error,
                redaction="none",
            )
        if status == "completed":
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.completed",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={**output, "status": "completed"},
            )
            return AgentToolCallResult(status="completed", output=output, redaction="none")

        error = result.error or {"message": "Sandbox failed"}
        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="sandbox.failed",
            source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
            payload={**output, "status": "failed", "error": error},
        )
        return AgentToolCallResult(status="failed", output=output, error=error, redaction="none")

    async def _list_workspace_files(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._store is None:
            return AgentToolCallResult(
                status="failed",
                error={"message": "Sandbox file listing requires a workspace store"},
                redaction="none",
            )
        list_request = _file_list_request(request.input)
        if isinstance(list_request, AgentToolCallResult):
            return list_request
        if list_request.prefix is not None and not _path_allowed(
            list_request.prefix,
            context.workspace_allowed_paths,
        ):
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Path is outside allowed workspace paths: {list_request.prefix}"},
                redaction="none",
            )
        files = [
            file
            for file in await self._store.list_workspace_files(context.workspace_id)
            if _path_allowed(file.path, context.workspace_allowed_paths)
            and _path_has_prefix(file.path, list_request.prefix)
        ]
        files = sorted(files, key=lambda file: file.path)
        total_count = len(files)
        limited_files = files[: list_request.limit]
        output = SandboxFileListResult(
            workspace_id=context.workspace_id,
            prefix=list_request.prefix,
            files=limited_files,
            count=len(limited_files),
            total_count=total_count,
            truncated=len(limited_files) < total_count,
        )
        return AgentToolCallResult(
            status="completed",
            output=output.model_dump(mode="json"),
            redaction="none",
        )

    async def _persist_workspace_files(
        self,
        *,
        context: AgentRunContext,
        sandbox_run_id: str,
        files: list[SandboxWorkspaceOutputFile],
    ) -> tuple[list[dict[str, object]], dict[str, str] | None]:
        if not files:
            return [], None
        if self._store is None:
            return [], {"message": "Sandbox declared workspace files but no workspace store is configured"}
        if not _can_write_workspace(context.scopes):
            return [], {"message": "Missing required scope: agent.workspace.write"}
        for file in files:
            if not _path_allowed(file.path, context.workspace_allowed_paths):
                return [], {
                    "message": f"Path is outside allowed workspace paths: {file.path}",
                }
        persisted: list[dict[str, object]] = []
        for file in files:
            written = await self._store.write_workspace_file(
                workspace_id=context.workspace_id,
                path=file.path,
                content=file.content,
                media_type=file.media_type,
            )
            payload = {
                "source": "sandbox.run_python",
                "sandbox_run_id": sandbox_run_id,
                **written.model_dump(mode="json"),
            }
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="workspace.file.created",
                source={"kind": "workspace"},
                payload=payload,
            )
            persisted.append(_workspace_output_payload(file=file, written=written))
        return persisted, None

    async def _read_workspace_file(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._store is None:
            return AgentToolCallResult(
                status="failed",
                error={"message": "Sandbox file reads require a workspace store"},
                redaction="none",
            )
        read_request = _file_read_request(request.input)
        if isinstance(read_request, AgentToolCallResult):
            return read_request
        if not _path_allowed(read_request.path, context.workspace_allowed_paths):
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Path is outside allowed workspace paths: {read_request.path}"},
                redaction="none",
            )
        try:
            content = await self._store.read_workspace_file(
                context.workspace_id,
                read_request.path,
            )
        except AgentError as err:
            return AgentToolCallResult(
                status="denied",
                error={"message": err.message},
                redaction="none",
            )
        output = _file_read_result(
            path=read_request.path,
            content=content.content,
            media_type=content.media_type,
            max_bytes=read_request.max_bytes,
        )
        return AgentToolCallResult(
            status="completed",
            output=output.model_dump(mode="json"),
            redaction="none",
        )

    async def _diff_workspace(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._store is None:
            return AgentToolCallResult(
                status="failed",
                error={"message": "Sandbox workspace diffs require a workspace store"},
                redaction="none",
            )
        diff_request = _workspace_diff_request(request.input)
        if isinstance(diff_request, AgentToolCallResult):
            return diff_request
        diff = await self._store.diff_workspace_snapshots(
            workspace_id=context.workspace_id,
            base_version=diff_request.base_version,
            target_version=diff_request.target_version,
        )
        output = _filter_workspace_diff(diff, context.workspace_allowed_paths)
        return AgentToolCallResult(
            status="completed",
            output=output.model_dump(mode="json"),
            redaction="none",
        )

    async def _patch_workspace_file(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._store is None:
            return AgentToolCallResult(
                status="failed",
                error={"message": "Sandbox file patches require a workspace store"},
                redaction="none",
            )
        patch_request = _file_patch_request(request.input)
        if isinstance(patch_request, AgentToolCallResult):
            return patch_request
        if not _path_allowed(patch_request.path, context.workspace_allowed_paths):
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Path is outside allowed workspace paths: {patch_request.path}"},
                redaction="none",
            )
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
                error={"message": "sandbox.patch_file only supports text files"},
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
        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="workspace.file.created",
            source={"kind": "workspace"},
            payload={
                "source": "sandbox.patch_file",
                "tool_call_id": request.id,
                **patched_file.model_dump(mode="json"),
            },
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
        )
        return AgentToolCallResult(
            status="completed",
            output=output.model_dump(mode="json"),
            redaction="none",
        )

    async def _delete_workspace_file(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._store is None:
            return AgentToolCallResult(
                status="failed",
                error={"message": "Sandbox file deletion requires a workspace store"},
                redaction="none",
            )
        delete_request = _file_delete_request(request.input)
        if isinstance(delete_request, AgentToolCallResult):
            return delete_request
        if not _path_allowed(delete_request.path, context.workspace_allowed_paths):
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Path is outside allowed workspace paths: {delete_request.path}"},
                redaction="none",
            )
        try:
            before_file = await _workspace_file(
                self._store,
                workspace_id=context.workspace_id,
                path=delete_request.path,
            )
            await self._store.delete_workspace_file(context.workspace_id, delete_request.path)
            delete_version = await _latest_deleted_workspace_file_version(
                self._store,
                workspace_id=context.workspace_id,
                path=delete_request.path,
            )
        except AgentError as err:
            return AgentToolCallResult(
                status="denied",
                error={"message": err.message},
                redaction="none",
            )
        output = SandboxFileDeleteResult(
            workspace_id=context.workspace_id,
            path=before_file.path,
            version_before=before_file.version,
            deleted_version=delete_version.version,
            file_version_before=before_file.file_version,
            deleted_file_version=delete_version.file_version,
            size_before=before_file.size,
            media_type=before_file.media_type,
            content_hash_before=before_file.content_hash,
        )
        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="workspace.file.deleted",
            source={"kind": "workspace"},
            payload={
                "source": "sandbox.delete_file",
                "tool_call_id": request.id,
                **output.model_dump(mode="json"),
            },
        )
        return AgentToolCallResult(
            status="completed",
            output=output.model_dump(mode="json"),
            redaction="none",
        )

    async def _write_workspace_file(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._store is None:
            return AgentToolCallResult(
                status="failed",
                error={"message": "Sandbox file writes require a workspace store"},
                redaction="none",
            )
        write_request = _file_write_request(request.input)
        if isinstance(write_request, AgentToolCallResult):
            return write_request
        if not _path_allowed(write_request.path, context.workspace_allowed_paths):
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Path is outside allowed workspace paths: {write_request.path}"},
                redaction="none",
            )
        overwritten = await _workspace_file_exists(
            self._store,
            workspace_id=context.workspace_id,
            path=write_request.path,
        )
        written = await self._store.write_workspace_file(
            workspace_id=context.workspace_id,
            path=write_request.path,
            content=write_request.content,
            media_type=write_request.media_type,
        )
        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="workspace.file.created",
            source={"kind": "workspace"},
            payload={
                "source": "sandbox.write_file",
                "tool_call_id": request.id,
                **written.model_dump(mode="json"),
            },
        )
        output = SandboxFileWriteResult(
            workspace_id=context.workspace_id,
            path=written.path,
            file=written,
            size=written.size,
            media_type=written.media_type,
            overwritten=overwritten,
        )
        return AgentToolCallResult(
            status="completed",
            output=output.model_dump(mode="json"),
            redaction="none",
        )


def _execution_request(value: object, context: AgentRunContext) -> SandboxExecutionRequest:
    input_data = _input_dict(value)
    try:
        execution_request = SandboxExecutionRequest.model_validate(input_data)
    except ValidationError as exc:
        raise AgentError("BAD_REQUEST", f"Invalid sandbox input: {exc}") from exc
    timeout_ms = context.sandbox_policy.timeout_ms if context.sandbox_policy else None
    if timeout_ms is not None and execution_request.timeout_ms > timeout_ms:
        return execution_request.model_copy(update={"timeout_ms": timeout_ms})
    return execution_request


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value


def _file_list_request(value: object) -> SandboxFileListRequest | AgentToolCallResult:
    try:
        return SandboxFileListRequest.model_validate(_input_dict(value))
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={
                "message": "Invalid sandbox file list request",
                "details": err.errors(include_context=False),
            },
            redaction="none",
        )
    except TypeError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": str(err)},
            redaction="none",
        )


def _file_read_request(value: object) -> SandboxFileReadRequest | AgentToolCallResult:
    try:
        return SandboxFileReadRequest.model_validate(_input_dict(value))
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={
                "message": "Invalid sandbox file read request",
                "details": err.errors(include_context=False),
            },
            redaction="none",
        )
    except TypeError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": str(err)},
            redaction="none",
        )


def _file_write_request(value: object) -> SandboxFileWriteRequest | AgentToolCallResult:
    try:
        return SandboxFileWriteRequest.model_validate(_input_dict(value))
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={
                "message": "Invalid sandbox file write request",
                "details": err.errors(include_context=False),
            },
            redaction="none",
        )
    except TypeError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": str(err)},
            redaction="none",
        )


def _file_delete_request(value: object) -> SandboxFileDeleteRequest | AgentToolCallResult:
    try:
        return SandboxFileDeleteRequest.model_validate(_input_dict(value))
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={
                "message": "Invalid sandbox file deletion request",
                "details": err.errors(include_context=False),
            },
            redaction="none",
        )
    except TypeError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": str(err)},
            redaction="none",
        )


def _file_patch_request(value: object) -> AgentWorkspaceTextPatchRequest | AgentToolCallResult:
    try:
        return AgentWorkspaceTextPatchRequest.model_validate(_input_dict(value))
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={
                "message": "Invalid sandbox file patch request",
                "details": err.errors(include_context=False),
            },
            redaction="none",
        )
    except TypeError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": str(err)},
            redaction="none",
        )


def _workspace_diff_request(value: object) -> SandboxWorkspaceDiffRequest | AgentToolCallResult:
    try:
        return SandboxWorkspaceDiffRequest.model_validate(_input_dict(value))
    except ValidationError as err:
        return AgentToolCallResult(
            status="denied",
            error={
                "message": "Invalid sandbox workspace diff request",
                "details": err.errors(include_context=False),
            },
            redaction="none",
        )
    except TypeError as err:
        return AgentToolCallResult(
            status="denied",
            error={"message": str(err)},
            redaction="none",
        )


def _file_read_result(
    *,
    path: str,
    content: str | bytes,
    media_type: str | None,
    max_bytes: int,
) -> SandboxFileReadResult:
    raw = content.encode("utf-8") if isinstance(content, str) else content
    returned = raw[:max_bytes]
    if isinstance(content, str):
        encoded_content = returned.decode("utf-8", "replace")
        encoding = "utf-8"
    else:
        encoded_content = base64.b64encode(returned).decode("ascii")
        encoding = "base64"
    return SandboxFileReadResult(
        path=path,
        content=encoded_content,
        media_type=media_type,
        content_encoding=encoding,
        size=len(raw),
        returned_bytes=len(returned),
        truncated=len(returned) < len(raw),
    )


def _execution_summary(
    request: SandboxExecutionRequest,
    result: SandboxExecutionResult,
) -> SandboxExecutionSummary:
    error = result.error or {}
    return SandboxExecutionSummary(
        timeout_ms=request.timeout_ms,
        stdout_chars=len(result.stdout),
        stderr_chars=len(result.stderr),
        result_type=_result_type(result.result),
        error_code=error.get("code"),
        timed_out=error.get("code") == "timeout",
    )


def _run_diagnostics(
    *,
    sandbox_run_id: str,
    status: SandboxExecutionStatus,
    execution: SandboxExecutionSummary,
    declared_files: list[SandboxWorkspaceOutputFile],
    persisted_files: list[dict[str, object]],
    persistence_error: dict[str, str] | None,
) -> SandboxRunDiagnostics:
    return SandboxRunDiagnostics(
        sandbox_run_id=sandbox_run_id,
        status=status,
        execution=execution,
        workspace_effects=_workspace_effects_summary(
            declared_files=declared_files,
            persisted_files=persisted_files,
            persistence_error=persistence_error,
        ),
        error_code=execution.error_code,
        timed_out=execution.timed_out,
    )


def _workspace_effects_summary(
    *,
    declared_files: list[SandboxWorkspaceOutputFile],
    persisted_files: list[dict[str, object]],
    persistence_error: dict[str, str] | None,
) -> SandboxWorkspaceEffectsSummary:
    return SandboxWorkspaceEffectsSummary(
        declared_count=len(declared_files),
        persisted_count=len(persisted_files),
        paths=[
            path
            for file in persisted_files
            if isinstance(path := file.get("path"), str)
        ],
        persistence_error=persistence_error,
    )


def _result_type(value: object) -> str | None:
    if value is None:
        return None
    return type(value).__name__


def _filter_workspace_diff(
    diff: AgentWorkspaceDiff,
    allowed_paths: list[str] | None,
) -> AgentWorkspaceDiff:
    if not allowed_paths:
        return diff
    changes = [
        change
        for change in diff.changes
        if _path_allowed(change.path, allowed_paths)
    ]
    return AgentWorkspaceDiff(
        workspace_id=diff.workspace_id,
        base_version=diff.base_version,
        target_version=diff.target_version,
        changes=changes,
        added_count=sum(1 for change in changes if change.operation == "added"),
        modified_count=sum(1 for change in changes if change.operation == "modified"),
        deleted_count=sum(1 for change in changes if change.operation == "deleted"),
    )


async def _workspace_file_exists(
    store: AgentStore,
    *,
    workspace_id: str,
    path: str,
) -> bool:
    normalized = _normalize_workspace_path(path)
    return any(file.path == normalized for file in await store.list_workspace_files(workspace_id))


async def _workspace_file(
    store: AgentStore,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceFile:
    normalized = _normalize_workspace_path(path)
    for file in await store.list_workspace_files(workspace_id):
        if file.path == normalized:
            return file
    raise AgentError("NOT_FOUND", f"Workspace file not found: {path}")


async def _latest_deleted_workspace_file_version(
    store: AgentStore,
    *,
    workspace_id: str,
    path: str,
) -> AgentWorkspaceFileVersion:
    normalized = _normalize_workspace_path(path)
    versions = await store.list_workspace_file_versions(
        workspace_id=workspace_id,
        path=normalized,
    )
    deleted_versions = [version for version in versions if version.operation == "delete"]
    if not deleted_versions:
        raise AgentError("NOT_FOUND", f"Workspace deletion version not found: {path}")
    return max(deleted_versions, key=lambda version: version.version)


def _can_write_workspace(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.workspace.write" in scopes


def _workspace_output_payload(
    *,
    file: SandboxWorkspaceOutputFile,
    written: AgentWorkspaceFile,
) -> dict[str, object]:
    return {
        "path": file.path,
        "media_type": file.media_type,
        "file": written.model_dump(mode="json"),
    }


def _path_allowed(path: str, allowed_paths: list[str] | None) -> bool:
    if not allowed_paths:
        return True
    normalized = _normalize_workspace_path(path)
    return any(
        normalized == allowed or normalized.startswith(allowed.rstrip("/") + "/")
        for allowed in (_normalize_workspace_path(allowed_path) for allowed_path in allowed_paths)
    )


def _path_has_prefix(path: str, prefix: str | None) -> bool:
    if prefix is None:
        return True
    normalized = _normalize_workspace_path(path)
    normalized_prefix = _normalize_workspace_path(prefix)
    return normalized == normalized_prefix or normalized.startswith(
        normalized_prefix.rstrip("/") + "/"
    )


def _normalize_workspace_path(path: str) -> str:
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
