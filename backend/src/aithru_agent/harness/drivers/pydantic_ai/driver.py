from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import PartDeltaEvent, TextPartDelta
from pydantic_ai.run import AgentRunResultEvent

from aithru_agent.domain import AgentMemoryEntry, AgentSkill, AgentWorkspaceFile
from aithru_agent.harness.drivers.pydantic_ai.tool_bridge import PydanticAIToolBridge
from aithru_agent.harness.engine import HarnessRunDeps, HarnessStep


MAX_WORKSPACE_FILES_IN_PROMPT = 50


class PydanticAIHarnessDriver:
    def __init__(
        self,
        *,
        model: object | str | None = None,
        instructions: str | None = None,
    ) -> None:
        self._model = model
        self._instructions = instructions or "You are Aithru Agent. Help the user complete the task."

    async def run(self, goal: str | None = None, deps: HarnessRunDeps | None = None) -> list[HarnessStep]:
        tools = await self._build_tools(deps) if deps else []
        memory_entries = await self._memory_entries_for_run(deps) if deps else []
        workspace_files = await self._workspace_files_for_run(deps) if deps else []
        agent = Agent(
            self._model,
            instructions=self.instructions_for_run(
                deps.skill if deps else None,
                memory_entries=memory_entries,
                workspace_files=workspace_files,
            ),
            output_type=str,
            tools=tools,
        )
        steps: list[HarnessStep] = []
        async with agent.run_stream_events(goal or "") as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        steps.append(HarnessStep(type="message", text=event.delta.content_delta))
                elif isinstance(event, AgentRunResultEvent):
                    steps.append(HarnessStep(type="finish"))
        if not steps or steps[-1].type != "finish":
            steps.append(HarnessStep(type="finish"))
        return steps

    def instructions_for_run(
        self,
        skill: AgentSkill | None = None,
        *,
        memory_entries: list[AgentMemoryEntry] | None = None,
        workspace_files: list[AgentWorkspaceFile] | None = None,
    ) -> str:
        sections = [self._instructions]
        if skill:
            sections.append(f"Skill instructions:\n{skill.instructions}")
        if workspace_files:
            lines = [
                f"- {file.path} ({file.media_type or 'unknown'}, {file.size} bytes)"
                for file in workspace_files
            ]
            sections.append("Workspace files:\n" + "\n".join(lines))
        if memory_entries:
            lines = [
                f"- {entry.scope}:{entry.key} = {entry.value}"
                for entry in memory_entries
            ]
            sections.append("Memory:\n" + "\n".join(lines))
        return "\n\n".join(sections)

    async def _memory_entries_for_run(self, deps: HarnessRunDeps) -> list[AgentMemoryEntry]:
        skill = deps.skill
        if not skill or not skill.memory_policy or not skill.memory_policy.read:
            return []
        entries: list[AgentMemoryEntry] = []
        seen: set[str] = set()
        for scope in skill.memory_policy.scopes or ["user", "thread", "workspace", "organization", "skill"]:
            scope_id = _memory_scope_id(scope, deps)
            scoped_entries = await deps.store.list_memory_entries(
                org_id=deps.run.org_id,
                scope=scope,
                scope_id=scope_id,
            )
            for entry in scoped_entries:
                if entry.id in seen:
                    continue
                seen.add(entry.id)
                entries.append(entry)
        return entries

    async def _workspace_files_for_run(self, deps: HarnessRunDeps) -> list[AgentWorkspaceFile]:
        skill = deps.skill
        if skill and skill.workspace_policy and not skill.workspace_policy.read:
            return []
        files = await deps.store.list_workspace_files(deps.run.workspace_id)
        if skill and skill.workspace_policy and skill.workspace_policy.allowed_paths:
            files = [
                file
                for file in files
                if _workspace_path_allowed(file.path, skill.workspace_policy.allowed_paths)
            ]
        return files[:MAX_WORKSPACE_FILES_IN_PROMPT]

    async def _build_tools(self, deps: HarnessRunDeps | None) -> list[Tool]:
        if deps is None:
            return []
        descriptors = await deps.capability_router.list_tools(deps.run_context)
        bridge = PydanticAIToolBridge(
            run=deps.run,
            run_context=deps.run_context,
            event_writer=deps.event_writer,
            capability_router=deps.capability_router,
            store=deps.store,
        )

        def make_tool(tool_name: str, description: str) -> Tool:
            async def aithru_tool(
                ctx: RunContext[None],
                input: dict[str, Any] | None = None,
            ) -> object:
                tool_call_id = ctx.tool_call_id or f"pydantic:{tool_name}:{ctx.run_step}"
                return await bridge.call_tool(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    tool_input=input or {},
                )

            return Tool(
                aithru_tool,
                takes_ctx=True,
                name=tool_name,
                description=description,
            )

        return [make_tool(descriptor.name, descriptor.description) for descriptor in descriptors]


def _workspace_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    return any(path == allowed or path.startswith(allowed.rstrip("/") + "/") for allowed in allowed_paths)


def _memory_scope_id(scope: str, deps: HarnessRunDeps) -> str | None:
    match scope:
        case "thread":
            return deps.run.thread_id or deps.run.id
        case "workspace":
            return deps.run.workspace_id
        case "user":
            return deps.run.actor_user_id
        case "organization":
            return deps.run.org_id
        case "skill":
            return deps.run.skill_id
        case _:
            return None
