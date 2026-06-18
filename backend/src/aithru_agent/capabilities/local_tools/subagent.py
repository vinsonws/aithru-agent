from collections.abc import Awaitable, Callable
from typing import Any

from aithru_agent.domain import (
    AgentRunSource,
    AgentSkill,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter

from ..descriptors import AgentRunContext


SubagentTaskRunner = Callable[[str, str], Awaitable[str]]


class SubagentLocalTool:
    def __init__(
        self,
        store: AgentStore,
        event_writer: AgentEventWriter,
        skill_resolver: AgentSkillResolver | None = None,
    ) -> None:
        self._store = store
        self._event_writer = event_writer
        self._skill_resolver = skill_resolver or EmptySkillResolver()
        self._task_runner: SubagentTaskRunner | None = None

    def set_task_runner(self, task_runner: SubagentTaskRunner) -> None:
        self._task_runner = task_runner

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="task",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Delegate a task to a child Agent run and wait for the joined result.",
                input_schema={
                    "type": "object",
                    "required": ["description", "prompt", "subagent_type"],
                    "properties": {
                        "description": {"type": "string"},
                        "prompt": {"type": "string"},
                        "subagent_type": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.subagent.write"],
                approval_policy="on_risk",
            ),
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
        if request.tool_name == "task":
            return await self._execute_task(request, context)
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
        skill_id = _optional_string(input_data.get("skill_id"))
        child_skill = self._resolve_child_skill(skill_id, context)
        if skill_id and child_skill is None:
            return _denied(f"Skill not found: {skill_id}")
        if child_skill and child_skill.org_id != context.org_id:
            return _denied(f"Skill not found: {skill_id}")

        requested_scopes = _scopes(input_data.get("scopes"))
        scopes = requested_scopes if requested_scopes is not None else list(context.scopes)
        if not _is_scope_subset(scopes, context.scopes):
            return _denied("Child scopes must be a subset of parent scopes")

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
            skill_id=skill_id,
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

    async def _execute_task(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if self._task_runner is None:
            return _denied("Subagent task runner is not configured")

        input_data = _input_dict(request.input)
        description = _required_string(input_data, "description")
        prompt = _required_string(input_data, "prompt")
        subagent_type = _required_string(input_data, "subagent_type")
        child_skill = self._resolve_child_skill(subagent_type, context)
        if child_skill is None:
            return _denied(f"Skill not found: {subagent_type}")
        if child_skill.org_id != context.org_id:
            return _denied(f"Skill not found: {subagent_type}")

        child, subagent_run = await self._create_child_run(
            context=context,
            name=child_skill.name,
            task=prompt,
            spec_key=subagent_type,
            skill_id=subagent_type,
            scopes=list(context.scopes),
        )
        result = await self._task_runner(child.id, subagent_run.id)
        output = {
            "subagent_run_id": subagent_run.id,
            "child_run_id": child.id,
            "name": child_skill.name,
            "description": description,
            "prompt": prompt,
            "subagent_type": subagent_type,
            "status": "completed",
            "result": result,
        }
        return AgentToolCallResult(status="completed", output=output, redaction="none")

    async def _create_child_run(
        self,
        *,
        context: AgentRunContext,
        name: str,
        task: str,
        spec_key: str | None,
        skill_id: str | None,
        scopes: list[str],
    ):
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
            skill_id=skill_id,
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
        return child, subagent_run

    def _resolve_child_skill(
        self,
        skill_id: str | None,
        context: AgentRunContext,
    ) -> AgentSkill | None:
        if skill_id is None:
            return None
        child_skill = self._skill_resolver.resolve(skill_id)
        if child_skill is None:
            return None
        if context.allowed_subagents is not None and not _is_allowed_subagent(
            child_skill,
            skill_id,
            context.allowed_subagents,
        ):
            return None
        return child_skill


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


def _is_scope_subset(child_scopes: list[str], parent_scopes: list[str]) -> bool:
    if "*" in parent_scopes:
        return True
    if "*" in child_scopes:
        return False
    return all(scope in parent_scopes for scope in child_scopes)


def _is_allowed_subagent(
    child_skill: AgentSkill,
    requested_skill_id: str,
    allowed_subagents: list[str],
) -> bool:
    allowed = set(allowed_subagents)
    return (
        requested_skill_id in allowed
        or child_skill.id in allowed
        or child_skill.key in allowed
    )


def _denied(message: str) -> AgentToolCallResult:
    return AgentToolCallResult(
        status="denied",
        error={"message": message},
        redaction="none",
    )
