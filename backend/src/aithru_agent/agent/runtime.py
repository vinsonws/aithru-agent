"""Native Pydantic AI runtime for Aithru Agent runs."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartEndEvent,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from aithru_agent.agent.capabilities import (
    AithruBoundaryCapability,
    AithruSkillActivationObserver,
    AithruSkillCapability,
    AithruToolset,
    SubagentTaskCapability,
)
from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.agent.tools.bridge import PydanticAIToolBridge
from aithru_agent.domain import (
    AgentArtifactSummary,
    AgentModelProfileEntry,
    AgentModelReasoningEffort,
    AgentRun,
    AgentRunStatus,
)
from aithru_agent.domain.errors import AgentError


PYDANTIC_APPROVAL_METADATA_DRIVER = "pydantic_ai_native"
PYDANTIC_APPROVAL_METADATA_HISTORY = "pydantic_message_history"
PYDANTIC_APPROVAL_LEGACY_METADATA_HISTORY = "message_history_json"


@dataclass
class PendingApprovalState:
    approval_id: str
    tool_call_id: str
    message_history: list[Any]


@dataclass
class AgentRuntimeResult:
    content: str
    pending_approval: PendingApprovalState | None = None


@dataclass
class AgentRuntime:
    """Pydantic AI-native agent runtime for Aithru."""

    model: str | object = "test"
    instructions: str = "You are Aithru Agent. Help the user complete the task."
    model_factory: Callable[[str], str | object] = field(default_factory=lambda: _default_model_factory)
    model_profile_resolver: Callable[[str, str], AgentModelProfileEntry | None] | None = None
    profile_model_factory: Callable[[AgentModelProfileEntry], str | object] | None = None
    _pending_approvals: dict[tuple[str, str], PendingApprovalState] = field(default_factory=dict)
    _pending_clarifications: dict[str, PendingApprovalState] = field(default_factory=dict)

    async def build_agent(
        self,
        deps: PydanticAgentDeps,
    ) -> Agent[PydanticAgentDeps, str | DeferredToolRequests]:
        """Build a Pydantic AI agent configured for this run."""
        model = self._model_for_run(deps.run)
        descriptors = await deps.capability_router.list_tools(deps.run_context)
        bridge = PydanticAIToolBridge(deps=deps)
        capabilities = [
            AithruBoundaryCapability(
                toolset=AithruToolset(
                    tool_specs=None,
                    tool_callback=bridge.call_tool,
                    expose_safe_tool_names=_requires_model_safe_tool_names(model),
                ),
            )
        ]

        # Map visible skill packages to Pydantic AI capabilities
        capabilities.extend(
            _skill_capabilities_for_run(deps),
        )

        # Emit skill lifecycle events
        capabilities.append(AithruSkillActivationObserver())

        task_tool_names = {"task", "subagent.delegate"}
        if any(
            descriptor.name in task_tool_names
            for descriptor in descriptors
        ):
            capabilities.append(SubagentTaskCapability())

        instruction_builder = InstructionBuilder(self.instructions)
        system_prompt = await instruction_builder.build(deps)

        return Agent[PydanticAgentDeps, str | DeferredToolRequests](
            model,
            deps_type=PydanticAgentDeps,
            instructions=system_prompt,
            output_type=str | DeferredToolRequests,
            capabilities=capabilities,
        )

    async def run(
        self,
        goal: str,
        deps: PydanticAgentDeps,
    ) -> AgentRuntimeResult:
        """Run the native agent for a goal."""
        agent = await self.build_agent(deps)
        content_parts: list[str] = []
        final_output: str | None = None
        message_id = "msg_1"

        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": message_id, "role": "assistant"},
        )

        async with agent.run_stream_events(
            goal,
            deps=deps,
            model_settings=_model_settings_for_run(deps.run),
        ) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent | PartEndEvent):
                    await _emit_model_stream_part_event(
                        deps,
                        event=event,
                        message_id=message_id,
                        content_parts=content_parts,
                    )
                elif isinstance(event, AgentRunResultEvent):
                    await self._emit_usage_event(deps, event.result.usage)
                    if isinstance(event.result.output, DeferredToolRequests):
                        pending = await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        return AgentRuntimeResult(
                            content=_result_content(content_parts, final_output),
                            pending_approval=pending,
                        )
                    if isinstance(event.result.output, str):
                        final_output = event.result.output

        return AgentRuntimeResult(
            content=_result_content(content_parts, final_output),
            pending_approval=None,
        )

    def has_pending_approval(self, run_id: str, approval_id: str) -> bool:
        return (run_id, approval_id) in self._pending_approvals

    async def resume_approval(
        self,
        *,
        run_id: str,
        approval_id: str,
        approved: bool,
        deps: PydanticAgentDeps,
        persisted_message_history: str | None = None,
        persisted_tool_call_id: str | None = None,
    ) -> AgentRuntimeResult:
        """Resume a run after an approval decision."""
        pending = self._pending_approvals.pop((run_id, approval_id), None)
        if pending is None and persisted_message_history:
            pending = PendingApprovalState(
                approval_id=approval_id,
                tool_call_id=persisted_tool_call_id or approval_id,
                message_history=ModelMessagesTypeAdapter.validate_json(persisted_message_history),
            )
        if pending is None:
            raise AgentError("RUN_NOT_RESUMABLE", f"No pending approval for run {run_id}")

        agent = await self.build_agent(deps)
        content_parts: list[str] = []
        final_output: str | None = None
        message_id = "msg_1"
        deferred_tool_results = DeferredToolResults(approvals={pending.tool_call_id: approved})

        async with agent.run_stream_events(
            message_history=pending.message_history,
            deferred_tool_results=deferred_tool_results,
            deps=deps,
            model_settings=_model_settings_for_run(deps.run),
        ) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent | PartEndEvent):
                    await _emit_model_stream_part_event(
                        deps,
                        event=event,
                        message_id=message_id,
                        content_parts=content_parts,
                    )
                elif isinstance(event, AgentRunResultEvent):
                    await self._emit_usage_event(deps, event.result.usage)
                    if isinstance(event.result.output, DeferredToolRequests):
                        new_pending = await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        return AgentRuntimeResult(
                            content=_result_content(content_parts, final_output),
                            pending_approval=new_pending,
                        )
                    if isinstance(event.result.output, str):
                        final_output = event.result.output

        return AgentRuntimeResult(
            content=_result_content(content_parts, final_output),
            pending_approval=None,
        )

    async def resume_subagent(
        self,
        *,
        run_id: str,
        subagent_run_id: str,
        child_run_id: str,
        child_result: str | None,
        child_artifacts: list[AgentArtifactSummary] | None = None,
        deps: PydanticAgentDeps,
    ) -> AgentRuntimeResult:
        """Resume a parent run after a delegated child completed."""
        child_output = child_result or "No textual child result was persisted."
        artifact_context = _render_child_artifact_context(child_artifacts or [])
        prompt = (
            f"{deps.run.task_msg}\n\n"
            "A delegated subagent run completed while this parent run was paused.\n"
            f"Parent run id: {run_id}\n"
            f"Subagent run id: {subagent_run_id}\n"
            f"Child run id: {child_run_id}\n"
            f"Child result:\n{child_output}\n\n"
            f"{artifact_context}"
            "Continue the parent Agent Run using the child result."
        )
        return await self.run(prompt, deps)

    def _model_for_run(self, run: AgentRun | None) -> object:
        if run and run.harness_options and run.harness_options.model:
            if (
                run.harness_options.model_profile_key
                and self.model_profile_resolver
                and self.profile_model_factory
            ):
                profile = self.model_profile_resolver(
                    run.org_id,
                    run.harness_options.model_profile_key,
                )
                if profile is not None:
                    return self.profile_model_factory(profile)
            return self.model_factory(run.harness_options.model)
        if self.model == "test":
            return self.model_factory("test")
        return self.model

    async def _pause_for_deferred_approval(
        self,
        deps: PydanticAgentDeps,
        requests: DeferredToolRequests,
        message_history: list[Any],
    ) -> PendingApprovalState:
        """Persist a deferred tool approval request and pause the run.

        Handles ask_clarification deferred tool calls by writing input.requested
        events and pausing as waiting_input, before falling through to standard
        approval handling.
        """
        # --- Handle clarification calls ---
        clarification_call = next(
            (c for c in requests.calls if c.tool_name == "ask_clarification"),
            None,
        )
        if clarification_call is not None:
            return await self._handle_clarification_request(
                deps, clarification_call, message_history,
            )

        if not requests.approvals:
            raise AgentError("BAD_REQUEST", "Deferred tool calls without approval are not supported")

        tool_call = requests.approvals[0]
        tool_input = tool_call.args_as_dict(raise_if_invalid=True)
        tool_name = deps.tool_name_aliases.get(tool_call.tool_name, tool_call.tool_name)
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="tool.proposed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_name,
                "input": tool_input,
            },
        )

        message_history_json = ModelMessagesTypeAdapter.dump_json(message_history).decode("utf-8")
        approval = await deps.store.create_approval(
            run_id=deps.run.id,
            tool_call_id=tool_call.tool_call_id,
            tool_name=tool_name,
            tool_input=tool_input,
            metadata={
                "driver": PYDANTIC_APPROVAL_METADATA_DRIVER,
                "harness_driver": "pydantic_ai",
                PYDANTIC_APPROVAL_METADATA_HISTORY: message_history_json,
                PYDANTIC_APPROVAL_LEGACY_METADATA_HISTORY: message_history_json,
            },
        )

        pending_state = PendingApprovalState(
            approval_id=approval.id,
            tool_call_id=tool_call.tool_call_id,
            message_history=message_history,
        )
        self._pending_approvals[(deps.run.id, approval.id)] = pending_state

        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="approval.requested",
            source={"kind": "approval"},
            payload={
                "approval_id": approval.id,
                "tool_call_id": tool_call.tool_call_id,
                "tool_name": tool_name,
                "status": "pending",
            },
        )
        await deps.store.update_run(
            deps.run.id,
            status=AgentRunStatus.WAITING_APPROVAL,
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
                "tool_name": tool_name,
            },
        )
        return pending_state

    async def _handle_clarification_request(
        self,
        deps: PydanticAgentDeps,
        tool_call: ToolCallPart,
        message_history: list[Any],
    ) -> PendingApprovalState:
        """Handle an ask_clarification deferred tool call: write input.requested, pause as waiting_input."""
        args = tool_call.args_as_dict(raise_if_invalid=True)
        question = str(args.get("question", ""))
        clarification_type = str(args.get("clarification_type", "missing_info"))
        context_str = str(args.get("context", "")) if args.get("context") else None
        options = args.get("options")

        input_request_id = f"clarify_{deps.run.id}_{tool_call.tool_call_id}"
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="input.requested",
            source={"kind": "harness"},
            payload={
                "input_request_id": input_request_id,
                "tool_call_id": tool_call.tool_call_id,
                "prompt": question,
                "reason": context_str or "The agent needs more information to proceed.",
                "clarification_type": clarification_type,
                "options": options if isinstance(options, list) else None,
            },
        )

        pending_state = PendingApprovalState(
            approval_id=input_request_id,
            tool_call_id=tool_call.tool_call_id,
            message_history=message_history,
        )
        self._pending_clarifications[deps.run.id] = pending_state

        await deps.store.update_run(
            deps.run.id,
            status=AgentRunStatus.WAITING_INPUT,
        )
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_input",
                "pause_reason": "clarification_requested",
                "input_request_id": input_request_id,
            },
        )
        return pending_state

    def has_pending_clarification(self, run_id: str) -> bool:
        """Return True if the given run has a pending clarification request."""
        return run_id in self._pending_clarifications

    async def resume_clarification(
        self,
        *,
        run_id: str,
        input_text: str,
        deps: PydanticAgentDeps,
    ) -> AgentRuntimeResult:
        """Resume a run after the user responded to a clarification request."""
        pending = self._pending_clarifications.pop(run_id, None)
        if pending is None:
            raise AgentError("RUN_NOT_RESUMABLE", f"No pending clarification for run {run_id}")

        agent = await self.build_agent(deps)
        content_parts: list[str] = []
        final_output: str | None = None
        message_id = "msg_1"

        from pydantic_ai.messages import ToolReturn

        deferred_tool_results = DeferredToolResults(
            calls={pending.tool_call_id: ToolReturn(input_text)}
        )

        async with agent.run_stream_events(
            message_history=pending.message_history,
            deferred_tool_results=deferred_tool_results,
            deps=deps,
            model_settings=_model_settings_for_run(deps.run),
        ) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent | PartEndEvent):
                    await _emit_model_stream_part_event(
                        deps,
                        event=event,
                        message_id=message_id,
                        content_parts=content_parts,
                    )
                elif isinstance(event, AgentRunResultEvent):
                    await self._emit_usage_event(deps, event.result.usage)
                    if isinstance(event.result.output, DeferredToolRequests):
                        new_pending = await self._pause_for_deferred_approval(
                            deps,
                            event.result.output,
                            event.result.all_messages(),
                        )
                        return AgentRuntimeResult(
                            content=_result_content(content_parts, final_output),
                            pending_approval=new_pending,
                        )
                    if isinstance(event.result.output, str):
                        final_output = event.result.output

        return AgentRuntimeResult(
            content=_result_content(content_parts, final_output),
            pending_approval=None,
        )

    async def _emit_usage_event(self, deps: PydanticAgentDeps, usage: object) -> None:
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="model.usage",
            source={"kind": "model"},
            visibility="debug",
            payload=_map_run_usage(usage),
        )


def _skill_capabilities_for_run(deps: PydanticAgentDeps) -> list[AithruSkillCapability]:
    capabilities = []
    for package in deps.visible_skill_packages.values():
        capabilities.append(
            AithruSkillCapability(
                package=package,
                explicit=package.key == deps.explicit_skill_key,
            )
        )
    return capabilities


def _result_content(content_parts: list[str], final_output: str | None) -> str:
    if content_parts:
        return "".join(content_parts)
    return final_output or ""


async def _emit_model_stream_part_event(
    deps: PydanticAgentDeps,
    *,
    event: PartDeltaEvent | PartEndEvent,
    message_id: str,
    content_parts: list[str],
) -> None:
    if isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta):
            if event.delta.content_delta:
                content_parts.append(event.delta.content_delta)
                await deps.event_writer.write(
                    run_id=deps.run.id,
                    thread_id=deps.run.thread_id,
                    type="message.delta",
                    source={"kind": "model"},
                    payload={"message_id": message_id, "delta": event.delta.content_delta},
                )
            return

        if isinstance(event.delta, ThinkingPartDelta) and event.delta.content_delta:
            await deps.event_writer.write(
                run_id=deps.run.id,
                thread_id=deps.run.thread_id,
                type="reasoning.delta",
                source={"kind": "model"},
                payload={
                    "message_id": message_id,
                    "reasoning_id": _thinking_part_id(message_id, event.index),
                    "delta": event.delta.content_delta,
                },
            )
        return

    if isinstance(event.part, ThinkingPart):
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="reasoning.completed",
            source={"kind": "model"},
            payload={
                "message_id": message_id,
                "reasoning_id": _thinking_part_id(message_id, event.index),
            },
        )


def _thinking_part_id(message_id: str, part_index: int) -> str:
    return f"{message_id}:thinking:{part_index}"


def _model_settings_for_run(run: AgentRun | None) -> dict[str, bool | str] | None:
    effort = run.harness_options.model_reasoning_effort if run.harness_options else None
    if effort is None:
        return None
    if effort == AgentModelReasoningEffort.NONE:
        return {"thinking": False}
    return {"thinking": effort.value}


def _render_child_artifact_context(artifacts: list[AgentArtifactSummary]) -> str:
    if not artifacts:
        return ""
    lines = ["Child artifacts:"]
    for artifact in artifacts:
        location = f" ({artifact.uri})" if artifact.uri else ""
        summary = artifact.summary or "No summary available."
        suffix = "..." if artifact.truncated else ""
        lines.append(
            f"- {artifact.type} {artifact.name}{location}: {summary}{suffix}"
        )
    return "\n".join(lines) + "\n\n"


def _map_run_usage(usage: object) -> dict[str, int]:
    input_tokens = _int_attr(usage, "input_tokens")
    output_tokens = _int_attr(usage, "output_tokens")
    total_tokens = _int_attr(usage, "total_tokens")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens if total_tokens else input_tokens + output_tokens,
        "requests": _int_attr(usage, "requests"),
    }


def _int_attr(value: object, name: str) -> int:
    raw = getattr(value, name, 0)
    if callable(raw):
        raw = raw()
    return int(raw or 0)


def _default_model_factory(model: str) -> str | object:
    if model == "test":
        from pydantic_ai.models.test import TestModel

        return TestModel(call_tools=[], custom_output_text="Done.")
    return model


def _requires_model_safe_tool_names(model: object) -> bool:
    """Use OpenAI-compatible tool names for real providers while preserving TestModel tests."""
    model_class = model.__class__
    return not (
        model_class.__module__ == "pydantic_ai.models.test"
        and model_class.__name__ == "TestModel"
    )
