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


class MemoryLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="memory.search",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Search Agent memory entries available to this run.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.memory.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="memory.remember",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Store a memory entry for later Agent runs.",
                input_schema={"type": "object", "required": ["key", "value"]},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.memory.write"],
                approval_policy="on_risk",
            ),
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        input_data = _input_dict(request.input)
        match request.tool_name:
            case "memory.search":
                entries = await self._store.list_memory_entries(
                    org_id=context.org_id,
                    scope=input_data.get("scope"),
                    scope_id=input_data.get("scope_id"),
                    query=input_data.get("query"),
                )
                return AgentToolCallResult(
                    status="completed",
                    output={"entries": [entry.model_dump(mode="json") for entry in entries]},
                    redaction="none",
                )
            case "memory.remember":
                scope = str(input_data.get("scope", "thread"))
                entry = await self._store.create_memory_entry(
                    org_id=context.org_id,
                    scope=scope,
                    scope_id=input_data.get("scope_id") or _default_scope_id(scope, context),
                    key=str(input_data["key"]),
                    value=str(input_data["value"]),
                    owner=input_data.get("owner") or context.actor_user_id,
                    source=input_data.get("source") or "agent",
                    confidence=input_data.get("confidence"),
                    visibility=input_data.get("visibility"),
                    retention=input_data.get("retention"),
                )
                return AgentToolCallResult(
                    status="completed",
                    output=entry.model_dump(mode="json"),
                    redaction="none",
                )
            case _:
                return AgentToolCallResult(
                    status="denied",
                    error={"message": f"Unknown memory tool: {request.tool_name}"},
                    redaction="none",
                )


def _default_scope_id(scope: str, context: AgentRunContext) -> str | None:
    match scope:
        case "thread":
            return context.thread_id or context.run_id
        case "workspace":
            return context.workspace_id
        case "user":
            return context.actor_user_id
        case "organization":
            return context.org_id
        case "skill":
            return context.skill_id
        case _:
            return None


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value
