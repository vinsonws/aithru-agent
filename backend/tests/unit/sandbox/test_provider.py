import pytest
from pydantic import ValidationError

from aithru_agent.sandbox import (
    MAX_TIMEOUT_MS,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxExecutionSummary,
    SandboxRunDiagnostics,
    SandboxRunPythonOutput,
    SandboxWorkspaceEffectsSummary,
    LocalPythonSandboxProvider,
)


def test_sandbox_execution_request_is_pydantic_contract() -> None:
    request = SandboxExecutionRequest(
        code="result = input_data['a'] + input_data['b']",
        input={"a": 2, "b": 3},
        timeout_ms=250,
    )

    assert request.model_dump() == {
        "code": "result = input_data['a'] + input_data['b']",
        "input": {"a": 2, "b": 3},
        "timeout_ms": 250,
    }


def test_sandbox_execution_request_rejects_blank_code_and_invalid_timeout() -> None:
    with pytest.raises(ValidationError, match="code"):
        SandboxExecutionRequest(code=" ")

    with pytest.raises(ValidationError, match="timeout_ms"):
        SandboxExecutionRequest(code="result = 1", timeout_ms=MAX_TIMEOUT_MS + 1)


def test_sandbox_run_diagnostics_is_pydantic_contract() -> None:
    execution = SandboxExecutionSummary(timeout_ms=250, result_type="dict")
    diagnostics = SandboxRunDiagnostics(
        sandbox_run_id="sandbox_toolcall_1",
        status="completed",
        execution=execution,
        workspace_effects=SandboxWorkspaceEffectsSummary(
            declared_count=1,
            persisted_count=1,
            promoted_count=0,
            paths=["/reports/summary.md"],
        ),
    )
    output = SandboxRunPythonOutput(
        sandbox_run_id="sandbox_toolcall_1",
        stdout="ok\n",
        result={"ok": True},
        execution=execution,
        diagnostics=diagnostics,
        workspace_files=[{"path": "/reports/summary.md"}],
    )

    assert output.model_dump(mode="json")["diagnostics"]["workspace_effects"] == {
        "declared_count": 1,
        "persisted_count": 1,
        "promoted_count": 0,
        "paths": ["/reports/summary.md"],
        "persistence_error": None,
    }

    with pytest.raises(ValidationError, match="promoted_count"):
        SandboxWorkspaceEffectsSummary(
            declared_count=1,
            persisted_count=0,
            promoted_count=1,
        )

    with pytest.raises(ValidationError, match="diagnostics execution"):
        SandboxRunPythonOutput(
            sandbox_run_id="sandbox_toolcall_1",
            execution=SandboxExecutionSummary(timeout_ms=500),
            diagnostics=diagnostics,
        )


@pytest.mark.asyncio
async def test_local_python_sandbox_provider_returns_normalized_result() -> None:
    provider = LocalPythonSandboxProvider()

    result = await provider.run_python(
        SandboxExecutionRequest(
            code="print('rows', len(input_data['rows']))\nresult = sum(input_data['rows'])",
            input={"rows": [1, 2, 3]},
        )
    )

    assert isinstance(result, SandboxExecutionResult)
    assert result.status == "completed"
    assert result.stdout == "rows 3\n"
    assert result.stderr == ""
    assert result.result == 6
    assert result.error is None
    assert result.execution is not None
    assert result.execution.language == "python"
    assert result.execution.timeout_ms == 1_000
    assert result.execution.exit_code == 0
    assert result.execution.stdout_chars == len("rows 3\n")
    assert result.execution.stderr_chars == 0
    assert result.execution.stdout_truncated is False
    assert result.execution.stderr_truncated is False
    assert result.execution.result_type == "int"
    assert result.execution.timed_out is False


@pytest.mark.asyncio
async def test_local_python_sandbox_provider_returns_declared_workspace_files() -> None:
    provider = LocalPythonSandboxProvider()

    result = await provider.run_python(
        SandboxExecutionRequest(
            code=(
                "workspace_files = ["
                "{"
                "'path': '/reports/summary.md', "
                "'content': '# Summary', "
                "'media_type': 'text/markdown', "
                "'artifact': {'name': 'Sandbox Summary', 'type': 'report'}"
                "}"
                "]\n"
                "result = 'created'"
            ),
        )
    )

    assert result.status == "completed"
    assert [file.model_dump(mode="json") for file in result.workspace_files] == [
        {
            "path": "/reports/summary.md",
            "content": "# Summary",
            "media_type": "text/markdown",
            "artifact": {"name": "Sandbox Summary", "type": "report"},
        }
    ]
