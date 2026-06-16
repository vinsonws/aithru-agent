from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import PartDeltaEvent, TextPartDelta
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from aithru_agent.domain import AgentMemoryEntry, AgentMessage, AgentSkill, AgentWorkspaceFile
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness.drivers.pydantic_ai.tool_bridge import PydanticAIToolBridge
from aithru_agent.harness.engine import HarnessRunDeps, HarnessRunPaused, HarnessStep


MAX_WORKSPACE_FILES_IN_PROMPT = 50
MAX_THREAD_MESSAGES_IN_PROMPT = 20
MAX_THREAD_MESSAGE_CHARS = 1_000


@dataclass
class PendingPydanticApproval:
    approval_id: str
    tool_call_id: str
    message_history: list[Any]


class PydanticAIHarnessDriver:
    def __init__(
        self,
        *,
        model: object | str | None = None,
        instructions: str | None = None,
    ) -> None:
        self._model = model
        self._instructions = instructions or "You are Aithru Agent. Help the user complete the task."
        self._pending_approvals: dict[tuple[str, str], PendingPydanticApproval] = {}

    async def run(self, goal: str | None = None, deps: HarnessRunDeps | None = None) -> list[HarnessStep]:
        tools = await self._build_tools(deps) if deps else []
        memory_entries = await self._memory_entries_for_run(deps) if deps else []
        thread_messages = await self._thread_messages_for_run(deps) if deps else []
        workspace_files = await self._workspace_files_for_run(deps) if deps else []
        agent = self._build_agent(
            deps,
            tools=tools,
            memory_entries=memory_entries,
            thread_messages=thread_messages,
            workspace_files=workspace_files,
        )
        steps: list[HarnessStep] = []
        async with agent.run_stream_events(goal or "") as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        steps.append(HarnessStep(type="message", text=event.delta.content_delta))
                elif isinstance(event, AgentRunResultEvent):
                    if isinstance(event.result.output, DeferredToolRequests):
                        if deps is None:
                            raise AgentError("BAD_REQUEST", "Deferred tool request requires run context")
                        await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        raise HarnessRunPaused(deps.run.id)
                    steps.append(HarnessStep(type="finish"))
        if not steps or steps[-1].type != "finish":
            steps.append(HarnessStep(type="finish"))
        return steps

    def has_pending_approval(self, run_id: str, approval_id: str) -> bool:
        return (run_id, approval_id) in self._pending_approvals

    async def resume_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        approved: bool,
        deps: HarnessRunDeps,
    ) -> list[HarnessStep]:
        pending = self._pending_approvals.pop((run_id, approval_id))
        tools = await self._build_tools(deps)
        memory_entries = await self._memory_entries_for_run(deps)
        thread_messages = await self._thread_messages_for_run(deps)
        workspace_files = await self._workspace_files_for_run(deps)
        agent = self._build_agent(
            deps,
            tools=tools,
            memory_entries=memory_entries,
            thread_messages=thread_messages,
            workspace_files=workspace_files,
        )
        steps: list[HarnessStep] = []
        deferred_tool_results = DeferredToolResults(approvals={pending.tool_call_id: approved})
        async with agent.run_stream_events(
            message_history=pending.message_history,
            deferred_tool_results=deferred_tool_results,
        ) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        steps.append(HarnessStep(type="message", text=event.delta.content_delta))
                elif isinstance(event, AgentRunResultEvent):
                    if isinstance(event.result.output, DeferredToolRequests):
                        await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        raise HarnessRunPaused(run_id)
                    steps.append(HarnessStep(type="finish"))
        if not steps or steps[-1].type != "finish":
            steps.append(HarnessStep(type="finish"))
        return steps

    def _build_agent(
        self,
        deps: HarnessRunDeps | None,
        *,
        tools: list[Tool],
        memory_entries: list[AgentMemoryEntry],
        thread_messages: list[AgentMessage],
        workspace_files: list[AgentWorkspaceFile],
    ) -> Agent:
        return Agent(
            self._model,
            instructions=self.instructions_for_run(
                deps.skill if deps else None,
                memory_entries=memory_entries,
                thread_messages=thread_messages,
                workspace_files=workspace_files,
            ),
            output_type=[str, DeferredToolRequests],
            tools=tools,
        )

    async def _pause_for_deferred_approval(
        self,
        deps: HarnessRunDeps,
        requests: DeferredToolRequests,
        message_history: list[Any],
    ) -> None:
        if not requests.approvals:
            raise AgentError("BAD_REQUEST", "Deferred tool calls without approval are not supported yet")
        tool_call = requests.approvals[0]
        tool_input = tool_call.args_as_dict(raise_if_invalid=True)
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="tool.proposed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
                "input": tool_input,
            },
        )
        approval = await deps.store.create_approval(
            run_id=deps.run.id,
            tool_call_id=tool_call.tool_call_id,
            tool_name=tool_call.tool_name,
            tool_input=tool_input,
        )
        self._pending_approvals[(deps.run.id, approval.id)] = PendingPydanticApproval(
            approval_id=approval.id,
            tool_call_id=tool_call.tool_call_id,
            message_history=message_history,
        )
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="approval.requested",
            source={"kind": "approval"},
            payload={
                "approval_id": approval.id,
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
                "status": "pending",
            },
        )
        await deps.store.update_run(
            deps.run.id,
            status="waiting_approval",
            current_approval_id=approval.id,
        )
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_approval",
                "approval_id": approval.id,
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_call.tool_name,
            },
        )

    def instructions_for_run(
        self,
        skill: AgentSkill | None = None,
        *,
        memory_entries: list[AgentMemoryEntry] | None = None,
        thread_messages: list[AgentMessage] | None = None,
        workspace_files: list[AgentWorkspaceFile] | None = None,
    ) -> str:
        sections = [self._instructions]
        if skill:
            sections.append(f"Skill instructions:\n{skill.instructions}")
        if thread_messages:
            lines = [
                f"- {message.role}: {_truncate_message(message.content)}"
                for message in thread_messages
            ]
            sections.append("Thread messages:\n" + "\n".join(lines))
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

    async def _thread_messages_for_run(self, deps: HarnessRunDeps) -> list[AgentMessage]:
        if not deps.run.thread_id:
            return []
        messages = await deps.store.list_messages(deps.run.thread_id)
        return messages[-MAX_THREAD_MESSAGES_IN_PROMPT:]

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

        def make_tool(
            tool_name: str,
            description: str,
            input_schema: dict[str, Any],
            requires_approval: bool,
        ) -> Tool:
            async def aithru_tool(
                ctx: RunContext[None],
                **tool_input: Any,
            ) -> object:
                tool_call_id = ctx.tool_call_id or f"pydantic:{tool_name}:{ctx.run_step}"
                already_approved = bool(getattr(ctx, "tool_call_approved", False))
                return await bridge.call_tool(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    tool_input=tool_input,
                    already_approved=already_approved,
                    emit_proposed=not already_approved,
                )

            tool = Tool.from_schema(
                aithru_tool,
                takes_ctx=True,
                name=tool_name,
                description=description,
                json_schema=input_schema,
            )
            tool.requires_approval = requires_approval
            return tool

        tools: list[Tool] = []
        for descriptor in descriptors:
            tools.append(
                make_tool(
                    descriptor.name,
                    descriptor.description,
                    descriptor.input_schema,
                    await deps.capability_router.requires_approval_for_tool(
                        descriptor.name,
                        deps.run_context,
                    ),
                )
            )
        return tools


def _workspace_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    return any(path == allowed or path.startswith(allowed.rstrip("/") + "/") for allowed in allowed_paths)


def _truncate_message(content: str) -> str:
    return content[:MAX_THREAD_MESSAGE_CHARS]


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
