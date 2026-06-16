import asyncio
import json
import sys
from typing import Any

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.stream import AgentEventWriter

from ..descriptors import AgentRunContext


MAX_CODE_SIZE = 20_000
MAX_TIMEOUT_MS = 5_000
MAX_STREAM_CHARS = 16_000


class SandboxLocalTool:
    def __init__(self, event_writer: AgentEventWriter) -> None:
        self._event_writer = event_writer

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="sandbox.run_python",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Run restricted Python code with explicit input and captured output.",
                input_schema={
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {"type": "string"},
                        "input": {},
                        "timeout_ms": {"type": "integer", "minimum": 1, "maximum": MAX_TIMEOUT_MS},
                    },
                },
                output_schema={"type": "object"},
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
        if request.tool_name != "sandbox.run_python":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown sandbox tool: {request.tool_name}"},
                redaction="none",
            )
        input_data = _input_dict(request.input)
        code = _required_code(input_data)
        timeout_ms = _timeout_ms(input_data.get("timeout_ms"))
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
                "timeout_ms": timeout_ms,
            },
        )
        result = await _run_restricted_python(
            code=code,
            input_value=input_data.get("input"),
            timeout_ms=timeout_ms,
        )
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        if stdout:
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.stdout",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={
                    "sandbox_run_id": sandbox_run_id,
                    "stream": "stdout",
                    "delta": stdout,
                },
            )
        if stderr:
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.stderr",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={
                    "sandbox_run_id": sandbox_run_id,
                    "stream": "stderr",
                    "delta": stderr,
                },
            )

        output = {
            "sandbox_run_id": sandbox_run_id,
            "language": "python",
            "stdout": stdout,
            "stderr": stderr,
            "result": result.get("result"),
        }
        if result.get("status") == "completed":
            await self._event_writer.write(
                run_id=context.run_id,
                thread_id=context.thread_id,
                type="sandbox.completed",
                source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
                payload={**output, "status": "completed"},
            )
            return AgentToolCallResult(status="completed", output=output, redaction="none")

        error = _error_dict(result.get("error"))
        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="sandbox.failed",
            source={"kind": "sandbox", "id": sandbox_run_id, "name": "python"},
            payload={**output, "status": "failed", "error": error},
        )
        return AgentToolCallResult(status="failed", output=output, error=error, redaction="none")


async def _run_restricted_python(
    *,
    code: str,
    input_value: object,
    timeout_ms: int,
) -> dict[str, object]:
    payload = json.dumps({"code": code, "input": input_value})
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
            timeout=timeout_ms / 1000,
        )
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return {
            "status": "failed",
            "stdout": _truncate(stdout.decode("utf-8", "replace")),
            "stderr": _truncate(stderr.decode("utf-8", "replace")),
            "error": {"message": f"Sandbox timed out after {timeout_ms}ms"},
        }

    raw_stdout = stdout.decode("utf-8", "replace")
    raw_stderr = _truncate(stderr.decode("utf-8", "replace"))
    try:
        result = json.loads(raw_stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "stdout": "",
            "stderr": raw_stderr,
            "error": {"message": "Sandbox returned invalid output"},
        }
    if isinstance(result, dict):
        result["stdout"] = _truncate(str(result.get("stdout") or ""))
        result["stderr"] = _truncate(raw_stderr or str(result.get("stderr") or ""))
        return result
    return {
        "status": "failed",
        "stdout": "",
        "stderr": raw_stderr,
        "error": {"message": "Sandbox returned an invalid payload"},
    }


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value


def _required_code(input_data: dict[str, Any]) -> str:
    value = input_data.get("code")
    if not isinstance(value, str) or not value.strip():
        raise AgentError("BAD_REQUEST", "Missing required sandbox field: code")
    if len(value) > MAX_CODE_SIZE:
        raise AgentError("BAD_REQUEST", f"Sandbox code exceeds {MAX_CODE_SIZE} characters")
    return value


def _timeout_ms(value: object) -> int:
    if value is None:
        return 1_000
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentError("BAD_REQUEST", "Sandbox timeout_ms must be an integer") from exc
    return max(1, min(parsed, MAX_TIMEOUT_MS))


def _truncate(value: str) -> str:
    return value[:MAX_STREAM_CHARS]


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
