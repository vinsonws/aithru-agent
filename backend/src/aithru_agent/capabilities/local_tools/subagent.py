from typing import Any

from aithru_agent.domain import (
    AgentRunSource,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.stream import AgentEventWriter

from ..descriptors import AgentRunContext


class SubagentLocalTool:
    def __init__(self, store: AgentStore, event_writer: AgentEventWriter) -> None:
        self._store = store
        self._event_writer = event_writer

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="subagent.delegate",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Delegate a bounded task to a child Agent run.",
                input_schema={
                    "type": "object",
                    "required": ["name", "task"],
                    "properties": {
                        "name": {"type": "string"},
                        "task": {"type": "string"},
                        "spec_key": {"type": "string"},
                        "skill_id": {"type": "string"},
                        "scopes": {"type": "array", "items": {"type": "string"}},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.subagent.write"],
                approval_policy="on_risk",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name != "subagent.delegate":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown subagent tool: {request.tool_name}"},
                redaction="none",
            )
        input_data = _input_dict(request.input)
        name = _required_string(input_data, "name")
        task = _required_string(input_data, "task")
        spec_key = _optional_string(input_data.get("spec_key"))
        scopes = _scopes(input_data.get("scopes")) or list(context.scopes)
        parent = await self._store.get_run(context.run_id)
        if parent is None:
            raise AgentError("NOT_FOUND", f"Parent run not found: {context.run_id}")

        child = await self._store.create_run(
            org_id=context.org_id,
            actor_user_id=context.actor_user_id,
            source=AgentRunSource.DELEGATED_TASK,
            goal=task,
            workspace_id=context.workspace_id,
            scopes=scopes,
            thread_id=context.thread_id,
            skill_id=_optional_string(input_data.get("skill_id")),
        )
        subagent_run = await self._store.create_subagent_run(
            org_id=context.org_id,
            parent_run_id=context.run_id,
            child_run_id=child.id,
            name=name,
            task=task,
            spec_key=spec_key,
        )
        output = {
            "subagent_run_id": subagent_run.id,
            "child_run_id": child.id,
            "name": name,
            "task": task,
            "spec_key": spec_key,
            "status": subagent_run.status.value,
        }
        await self._event_writer.write(
            run_id=child.id,
            thread_id=child.thread_id,
            type="run.created",
            source={"kind": "harness"},
            payload={
                "status": "queued",
                "workspace_id": child.workspace_id,
                "parent_run_id": context.run_id,
                "subagent_run_id": subagent_run.id,
            },
        )
        await self._event_writer.write(
            run_id=context.run_id,
            thread_id=context.thread_id,
            type="subagent.started",
            source={"kind": "subagent", "id": subagent_run.id, "name": name},
            payload=output,
        )
        return AgentToolCallResult(status="completed", output=output, redaction="none")


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value


def _required_string(input_data: dict[str, Any], key: str) -> str:
    value = input_data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentError("BAD_REQUEST", f"Missing required subagent field: {key}")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _scopes(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(scope, str) for scope in value):
        raise AgentError("BAD_REQUEST", "Subagent scopes must be a string array")
    return value
