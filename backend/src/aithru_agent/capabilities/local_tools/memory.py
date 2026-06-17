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
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": ["thread", "workspace", "user", "organization", "skill"],
                        },
                        "scope_id": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.READ,
                required_scopes=["agent.memory.read"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="memory.remember",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Store a memory entry for later Agent runs.",
                input_schema={
                    "type": "object",
                    "required": ["key", "value"],
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": ["thread", "workspace", "user", "organization", "skill"],
                        },
                        "scope_id": {"type": "string"},
                        "owner": {"type": "string"},
                        "source": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "visibility": {"type": "string"},
                        "retention": {"type": "string"},
                    },
                },
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
                scope = input_data.get("scope")
                entries = []
                if scope is None:
                    entries = await self._search_accessible_entries(
                        context,
                        query=input_data.get("query"),
                    )
                else:
                    scope_id = _scope_id_for_request(scope, input_data.get("scope_id"), context)
                    if isinstance(scope_id, AgentToolCallResult):
                        return scope_id
                    entries = await self._store.list_memory_entries(
                        org_id=context.org_id,
                        scope=scope,
                        scope_id=scope_id,
                        query=input_data.get("query"),
                    )
                return AgentToolCallResult(
                    status="completed",
                    output={"entries": [entry.model_dump(mode="json") for entry in entries]},
                    redaction="none",
                )
            case "memory.remember":
                scope = str(input_data.get("scope", "thread"))
                scope_id = _scope_id_for_request(scope, input_data.get("scope_id"), context)
                if isinstance(scope_id, AgentToolCallResult):
                    return scope_id
                entry = await self._store.create_memory_entry(
                    org_id=context.org_id,
                    scope=scope,
                    scope_id=scope_id,
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

    async def _search_accessible_entries(
        self,
        context: AgentRunContext,
        *,
        query: object,
    ) -> list[object]:
        entries = []
        seen: set[str] = set()
        for scope, scope_id in _accessible_memory_scopes(context):
            scoped_entries = await self._store.list_memory_entries(
                org_id=context.org_id,
                scope=scope,
                scope_id=scope_id,
                query=query,
            )
            for entry in scoped_entries:
                if entry.id in seen:
                    continue
                seen.add(entry.id)
                entries.append(entry)
        return entries


def _scope_id_for_request(
    scope_value: object,
    requested_scope_id: object,
    context: AgentRunContext,
) -> str | None | AgentToolCallResult:
    scope = str(scope_value) if scope_value is not None else None
    if scope is None:
        return None
    if scope not in _LOCAL_MEMORY_SCOPES:
        return AgentToolCallResult(
            status="denied",
            error={"message": f"Unsupported memory scope: {scope}"},
            redaction="none",
        )
    default_scope_id = _default_scope_id(scope, context)
    if requested_scope_id is None:
        return default_scope_id
    requested = str(requested_scope_id)
    if default_scope_id is not None and requested != default_scope_id:
        return AgentToolCallResult(
            status="denied",
            error={"message": f"Memory scope_id is outside the current run context: {scope}"},
            redaction="none",
        )
    return requested


def _accessible_memory_scopes(context: AgentRunContext) -> list[tuple[str, str | None]]:
    scopes = [
        ("user", context.actor_user_id),
        ("thread", context.thread_id or context.run_id),
        ("workspace", context.workspace_id),
        ("organization", context.org_id),
    ]
    if context.skill_id:
        scopes.append(("skill", context.skill_id))
    return scopes


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


_LOCAL_MEMORY_SCOPES = {"thread", "workspace", "user", "organization", "skill"}


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value
