from __future__ import annotations

import asyncio
import json
import sys
from typing import Literal, Protocol, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from aithru_agent.domain.artifact import AgentArtifactRetentionPolicy, AgentArtifactType
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.workspace import AgentWorkspaceFile


MAX_CODE_SIZE = 20_000
MAX_TIMEOUT_MS = 5_000
MAX_STREAM_CHARS = 16_000
MAX_SANDBOX_FILE_READ_BYTES = 64_000
MAX_SANDBOX_FILE_LIST_LIMIT = 100
MAX_WORKSPACE_FILES = 8
MAX_WORKSPACE_FILE_CHARS = 64_000
SandboxFileReadContentEncoding = Literal["utf-8", "base64"]
SandboxFileDeleteSource = Literal["sandbox.delete_file"]
SandboxFileWriteSource = Literal["sandbox.write_file"]
SandboxExecutionStatus = Literal["completed", "failed"]


class SandboxFileReadRequest(AithruBaseModel):
    path: str = Field(min_length=1)
    max_bytes: int = Field(
        default=MAX_SANDBOX_FILE_READ_BYTES,
        ge=1,
        le=MAX_SANDBOX_FILE_READ_BYTES,
    )

    @field_validator("path")
    @classmethod
    def _path_must_be_absolute_workspace_path(cls, value: str) -> str:
        path = value.strip().replace("\\", "/")
        if not path.startswith("/"):
            raise ValueError("sandbox file read path must be absolute")
        parts = [part for part in path.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("sandbox file read path cannot contain traversal")
        return "/" + "/".join(parts)


class SandboxFileReadResult(AithruBaseModel):
    path: str
    content: str
    media_type: str | None = None
    content_encoding: SandboxFileReadContentEncoding
    size: int = Field(ge=0)
    returned_bytes: int = Field(ge=0)
    truncated: bool = False

    @model_validator(mode="after")
    def _byte_counts_match_truncation(self) -> Self:
        if self.returned_bytes > self.size:
            raise ValueError("returned_bytes cannot exceed size")
        if self.truncated != (self.returned_bytes < self.size):
            raise ValueError("truncated must match whether returned_bytes is less than size")
        return self


class SandboxFileListRequest(AithruBaseModel):
    prefix: str | None = None
    limit: int = Field(default=MAX_SANDBOX_FILE_LIST_LIMIT, ge=1, le=MAX_SANDBOX_FILE_LIST_LIMIT)

    @field_validator("prefix")
    @classmethod
    def _prefix_must_be_absolute_workspace_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = value.strip().replace("\\", "/")
        if not path.startswith("/"):
            raise ValueError("sandbox file list prefix must be absolute")
        parts = [part for part in path.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("sandbox file list prefix cannot contain traversal")
        return "/" + "/".join(parts)


class SandboxFileListResult(AithruBaseModel):
    workspace_id: str
    prefix: str | None = None
    files: list[AgentWorkspaceFile] = Field(default_factory=list)
    count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    truncated: bool = False

    @model_validator(mode="after")
    def _counts_match_files(self) -> Self:
        if self.count != len(self.files):
            raise ValueError("count must match listed file count")
        if self.total_count < self.count:
            raise ValueError("total_count must be greater than or equal to count")
        if self.truncated != (self.count < self.total_count):
            raise ValueError("truncated must match whether count is less than total_count")
        return self


class SandboxFileDeleteRequest(AithruBaseModel):
    path: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def _path_must_be_absolute_workspace_path(cls, value: str) -> str:
        path = value.strip().replace("\\", "/")
        if not path.startswith("/"):
            raise ValueError("sandbox file deletion path must be absolute")
        parts = [part for part in path.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("sandbox file deletion path cannot contain traversal")
        return "/" + "/".join(parts)


class SandboxFileDeleteResult(AithruBaseModel):
    workspace_id: str
    path: str
    deleted: bool = True
    source: SandboxFileDeleteSource = "sandbox.delete_file"
    version_before: int = Field(ge=1)
    deleted_version: int = Field(ge=1)
    file_version_before: int = Field(ge=1)
    deleted_file_version: int = Field(ge=1)
    size_before: int = Field(ge=0)
    media_type: str | None = None
    content_hash_before: str | None = None

    @model_validator(mode="after")
    def _delete_versions_advance(self) -> Self:
        if self.deleted_version <= self.version_before:
            raise ValueError("deleted_version must be greater than version_before")
        if self.deleted_file_version <= self.file_version_before:
            raise ValueError("deleted_file_version must be greater than file_version_before")
        return self


class SandboxFileWriteRequest(AithruBaseModel):
    path: str = Field(min_length=1)
    content: str = Field(max_length=MAX_WORKSPACE_FILE_CHARS)
    media_type: str | None = None

    @field_validator("path")
    @classmethod
    def _path_must_be_absolute_workspace_path(cls, value: str) -> str:
        path = value.strip().replace("\\", "/")
        if not path.startswith("/"):
            raise ValueError("sandbox file write path must be absolute")
        parts = [part for part in path.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("sandbox file write path cannot contain traversal")
        return "/" + "/".join(parts)

    @field_validator("media_type")
    @classmethod
    def _media_type_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SandboxFileWriteResult(AithruBaseModel):
    workspace_id: str
    path: str
    file: AgentWorkspaceFile
    size: int = Field(ge=0)
    media_type: str | None = None
    source: SandboxFileWriteSource = "sandbox.write_file"
    overwritten: bool = False

    @model_validator(mode="after")
    def _file_metadata_matches_write(self) -> Self:
        if self.file.workspace_id != self.workspace_id:
            raise ValueError("written file workspace must match write workspace")
        if self.file.path != self.path:
            raise ValueError("written file path must match write path")
        if self.file.size != self.size:
            raise ValueError("written file size must match write size")
        if self.file.media_type != self.media_type:
            raise ValueError("written file media type must match write media type")
        return self


class SandboxFilePromotionRequest(AithruBaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    type: AgentArtifactType = "file"
    retention: AgentArtifactRetentionPolicy | None = None
    metadata: dict | None = None

    @field_validator("path")
    @classmethod
    def _path_must_be_absolute_workspace_path(cls, value: str) -> str:
        path = value.strip().replace("\\", "/")
        if not path.startswith("/"):
            raise ValueError("sandbox file promotion path must be absolute")
        parts = [part for part in path.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("sandbox file promotion path cannot contain traversal")
        return "/" + "/".join(parts)

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SandboxWorkspaceDiffRequest(AithruBaseModel):
    base_version: int | None = Field(default=None, ge=0)
    target_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _target_version_must_not_precede_base_version(self) -> Self:
        if (
            self.base_version is not None
            and self.target_version is not None
            and self.target_version < self.base_version
        ):
            raise ValueError("target_version must be greater than or equal to base_version")
        return self


class SandboxExecutionRequest(AithruBaseModel):
    code: str = Field(min_length=1, max_length=MAX_CODE_SIZE)
    input: object = None
    timeout_ms: int = Field(default=1_000, ge=1, le=MAX_TIMEOUT_MS)

    @field_validator("code")
    @classmethod
    def _code_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code cannot be blank")
        return value


class SandboxExecutionSummary(AithruBaseModel):
    language: Literal["python"] = "python"
    timeout_ms: int = Field(ge=1, le=MAX_TIMEOUT_MS)
    exit_code: int | None = None
    stdout_chars: int = Field(default=0, ge=0)
    stderr_chars: int = Field(default=0, ge=0)
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    result_type: str | None = None
    error_code: str | None = None
    timed_out: bool = False


class SandboxWorkspaceEffectsSummary(AithruBaseModel):
    declared_count: int = Field(default=0, ge=0)
    persisted_count: int = Field(default=0, ge=0)
    promoted_count: int = Field(default=0, ge=0)
    paths: list[str] = Field(default_factory=list)
    persistence_error: dict[str, str] | None = None

    @model_validator(mode="after")
    def _counts_match_effects(self) -> Self:
        if self.persisted_count > self.declared_count:
            raise ValueError("persisted_count cannot exceed declared_count")
        if self.promoted_count > self.persisted_count:
            raise ValueError("promoted_count cannot exceed persisted_count")
        if len(self.paths) != self.persisted_count:
            raise ValueError("paths count must match persisted_count")
        return self


class SandboxRunDiagnostics(AithruBaseModel):
    sandbox_run_id: str = Field(min_length=1)
    status: SandboxExecutionStatus
    language: Literal["python"] = "python"
    execution: SandboxExecutionSummary
    workspace_effects: SandboxWorkspaceEffectsSummary = Field(
        default_factory=SandboxWorkspaceEffectsSummary
    )
    error_code: str | None = None
    timed_out: bool = False

    @model_validator(mode="after")
    def _matches_execution_summary(self) -> Self:
        if self.language != self.execution.language:
            raise ValueError("diagnostics language must match execution language")
        if self.error_code != self.execution.error_code:
            raise ValueError("diagnostics error_code must match execution error_code")
        if self.timed_out != self.execution.timed_out:
            raise ValueError("diagnostics timed_out must match execution timed_out")
        return self


class SandboxWorkspaceOutputArtifact(AithruBaseModel):
    name: str = Field(min_length=1)
    type: AgentArtifactType = "file"

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("sandbox workspace output artifact name cannot be blank")
        return stripped


class SandboxWorkspaceOutputFile(AithruBaseModel):
    path: str = Field(min_length=1)
    content: str = Field(max_length=MAX_WORKSPACE_FILE_CHARS)
    media_type: str | None = None
    artifact: SandboxWorkspaceOutputArtifact | None = None

    @field_validator("path")
    @classmethod
    def _path_must_be_absolute_workspace_path(cls, value: str) -> str:
        path = value.strip().replace("\\", "/")
        if not path.startswith("/"):
            raise ValueError("sandbox workspace output path must be absolute")
        parts = [part for part in path.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("sandbox workspace output path cannot contain traversal")
        return "/" + "/".join(parts)

    @field_validator("media_type")
    @classmethod
    def _media_type_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SandboxRunPythonOutput(AithruBaseModel):
    sandbox_run_id: str = Field(min_length=1)
    language: Literal["python"] = "python"
    stdout: str = ""
    stderr: str = ""
    result: object = None
    execution: SandboxExecutionSummary
    diagnostics: SandboxRunDiagnostics
    workspace_files: list[dict[str, object]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _diagnostics_match_output(self) -> Self:
        if self.diagnostics.sandbox_run_id != self.sandbox_run_id:
            raise ValueError("diagnostics sandbox_run_id must match output sandbox_run_id")
        if self.diagnostics.language != self.language:
            raise ValueError("diagnostics language must match output language")
        if self.diagnostics.execution != self.execution:
            raise ValueError("diagnostics execution must match output execution")
        return self


class SandboxExecutionResult(AithruBaseModel):
    status: SandboxExecutionStatus
    stdout: str = ""
    stderr: str = ""
    result: object = None
    error: dict[str, str] | None = None
    execution: SandboxExecutionSummary | None = None
    workspace_files: list[SandboxWorkspaceOutputFile] = Field(default_factory=list)


class SandboxProvider(Protocol):
    async def run_python(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        ...


class LocalPythonSandboxProvider:
    async def run_python(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        payload = json.dumps({"code": request.code, "input": request.input})
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            _PYTHON_SANDBOX_RUNNER,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(payload.encode("utf-8")),
                timeout=request.timeout_ms / 1000,
            )
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            stdout_value = stdout.decode("utf-8", "replace")
            stderr_value = stderr.decode("utf-8", "replace")
            stdout_text, stdout_truncated = _truncate_with_meta(stdout_value)
            stderr_text, stderr_truncated = _truncate_with_meta(stderr_value)
            return SandboxExecutionResult(
                status="failed",
                stdout=stdout_text,
                stderr=stderr_text,
                error={
                    "code": "timeout",
                    "message": f"Sandbox timed out after {request.timeout_ms}ms",
                },
                execution=SandboxExecutionSummary(
                    timeout_ms=request.timeout_ms,
                    exit_code=process.returncode,
                    stdout_chars=len(stdout_value),
                    stderr_chars=len(stderr_value),
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                    error_code="timeout",
                    timed_out=True,
                ),
            )

        raw_stdout = stdout.decode("utf-8", "replace")
        raw_stderr_value = stderr.decode("utf-8", "replace")
        raw_stderr, raw_stderr_truncated = _truncate_with_meta(raw_stderr_value)
        try:
            result = json.loads(raw_stdout)
        except json.JSONDecodeError:
            return SandboxExecutionResult(
                status="failed",
                stdout="",
                stderr=raw_stderr,
                error={"message": "Sandbox returned invalid output"},
                execution=SandboxExecutionSummary(
                    timeout_ms=request.timeout_ms,
                    exit_code=process.returncode,
                    stdout_chars=len(raw_stdout),
                    stderr_chars=len(raw_stderr_value),
                    stdout_truncated=len(raw_stdout) > MAX_STREAM_CHARS,
                    stderr_truncated=raw_stderr_truncated,
                    error_code="invalid_output",
                ),
            )
        if isinstance(result, dict):
            status = str(result.get("status") or "failed")
            stdout_value = str(result.get("stdout") or "")
            stderr_value = raw_stderr_value or str(result.get("stderr") or "")
            stdout_text, stdout_truncated = _truncate_with_meta(stdout_value)
            stderr_text, stderr_truncated = _truncate_with_meta(stderr_value)
            result_value = result.get("result")
            error = _error_dict(result.get("error")) if status != "completed" else None
            try:
                workspace_files = _workspace_output_files(result.get("workspace_files"))
            except ValueError as exc:
                return SandboxExecutionResult(
                    status="failed",
                    stdout=stdout_text,
                    stderr=stderr_text,
                    result=result_value,
                    error={
                        "code": "invalid_workspace_files",
                        "message": str(exc),
                    },
                    execution=SandboxExecutionSummary(
                        timeout_ms=request.timeout_ms,
                        exit_code=process.returncode,
                        stdout_chars=len(stdout_value),
                        stderr_chars=len(stderr_value),
                        stdout_truncated=stdout_truncated,
                        stderr_truncated=stderr_truncated,
                        result_type=_result_type(result_value),
                        error_code="invalid_workspace_files",
                    ),
                )
            return SandboxExecutionResult(
                status=status,
                stdout=stdout_text,
                stderr=stderr_text,
                result=result_value,
                error=error,
                workspace_files=workspace_files,
                execution=SandboxExecutionSummary(
                    timeout_ms=request.timeout_ms,
                    exit_code=process.returncode,
                    stdout_chars=len(stdout_value),
                    stderr_chars=len(stderr_value),
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                    result_type=_result_type(result_value),
                    error_code=error.get("code") if error else None,
                ),
            )
        return SandboxExecutionResult(
            status="failed",
            stdout="",
            stderr=raw_stderr,
            error={"message": "Sandbox returned an invalid payload"},
            execution=SandboxExecutionSummary(
                timeout_ms=request.timeout_ms,
                exit_code=process.returncode,
                stdout_chars=len(raw_stdout),
                stderr_chars=len(raw_stderr_value),
                stdout_truncated=len(raw_stdout) > MAX_STREAM_CHARS,
                stderr_truncated=raw_stderr_truncated,
                error_code="invalid_payload",
            ),
        )


def _truncate_with_meta(value: str) -> tuple[str, bool]:
    return value[:MAX_STREAM_CHARS], len(value) > MAX_STREAM_CHARS


def _result_type(value: object) -> str | None:
    if value is None:
        return None
    return type(value).__name__


def _workspace_output_files(value: object) -> list[SandboxWorkspaceOutputFile]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("sandbox workspace_files must be a list")
    if len(value) > MAX_WORKSPACE_FILES:
        raise ValueError(f"sandbox workspace_files cannot exceed {MAX_WORKSPACE_FILES} entries")
    files: list[SandboxWorkspaceOutputFile] = []
    try:
        for item in value:
            files.append(SandboxWorkspaceOutputFile.model_validate(item))
    except ValidationError as exc:
        raise ValueError(f"invalid sandbox workspace file: {exc}") from exc
    return files


def _error_dict(value: object) -> dict[str, str]:
    if isinstance(value, dict):
        message = value.get("message")
        code = value.get("code")
        error = {"message": str(message) if message else "Sandbox failed"}
        if code:
            error["code"] = str(code)
        return error
    return {"message": str(value) if value else "Sandbox failed"}


_PYTHON_SANDBOX_RUNNER = r"""
import ast
import contextlib
import io
import json
import math
import statistics
import sys

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class SandboxValidationError(Exception):
    pass


class SandboxValidator(ast.NodeVisitor):
    def visit_Import(self, node):
        raise SandboxValidationError("import statements are not allowed")

    def visit_ImportFrom(self, node):
        raise SandboxValidationError("import statements are not allowed")

    def visit_Attribute(self, node):
        if node.attr.startswith("__"):
            raise SandboxValidationError("dunder attribute access is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id.startswith("__"):
            raise SandboxValidationError("dunder names are not allowed")
        self.generic_visit(node)


def make_jsonable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def main():
    payload = json.loads(sys.stdin.read())
    code = payload.get("code", "")
    input_data = payload.get("input")
    stdout = io.StringIO()
    try:
        tree = ast.parse(code, mode="exec")
        SandboxValidator().visit(tree)
        env = {
            "__builtins__": SAFE_BUILTINS,
            "input_data": input_data,
            "math": math,
            "statistics": statistics,
        }
        compiled = compile(tree, "<aithru-sandbox>", "exec")
        with contextlib.redirect_stdout(stdout):
            exec(compiled, env, env)
        response = {
            "status": "completed",
            "stdout": stdout.getvalue(),
            "stderr": "",
            "result": make_jsonable(env.get("result")),
            "workspace_files": make_jsonable(env.get("workspace_files") or []),
        }
    except Exception as exc:
        response = {
            "status": "failed",
            "stdout": stdout.getvalue(),
            "stderr": "",
            "error": {
                "code": exc.__class__.__name__,
                "message": str(exc),
            },
        }
    json.dump(response, sys.stdout)


main()
"""
