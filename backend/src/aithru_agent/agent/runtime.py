"""Native Pydantic AI runtime for Aithru Agent runs."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter, PartDeltaEvent, TextPartDelta
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults

from aithru_agent.agent.capabilities import (
    AithruBoundaryCapability,
    AithruToolset,
    SkillInstructionCapability,
    SubagentTaskCapability,
)
from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.agent.skills import ProgressiveSkill, SkillActivator, SkillRegistry
from aithru_agent.agent.tools.bridge import PydanticAIToolBridge
from aithru_agent.domain import AgentRun, AgentRunStatus, AgentToolDescriptor
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
    skill_registry: SkillRegistry | None = None
    _pending_approvals: dict[tuple[str, str], PendingApprovalState] = field(default_factory=dict)

    async def build_agent(
        self,
        deps: PydanticAgentDeps,
    ) -> Agent[PydanticAgentDeps, str | DeferredToolRequests]:
        """Build a Pydantic AI agent configured for this run."""
        descriptors = await deps.capability_router.list_tools(deps.run_context)
        active_skills = await self._activate_progressive_skills(deps)
        descriptors = self._apply_progressive_skill_tool_policy(descriptors, active_skills)
        tool_specs = [
            (
                descriptor,
                await deps.capability_router.requires_approval_for_tool(
                    descriptor.name,
                    deps.run_context,
                ),
            )
            for descriptor in descriptors
        ]
        bridge = PydanticAIToolBridge(deps=deps)
        capabilities = [
            AithruBoundaryCapability(
                toolset=AithruToolset(
                    tool_specs=tool_specs,
                    tool_callback=bridge.call_tool,
                ),
            )
        ]
        if deps.skill is not None:
            capabilities.append(SkillInstructionCapability([deps.skill]))
        if any(descriptor.name == "task" for descriptor, _ in tool_specs):
            capabilities.append(SubagentTaskCapability())

        instruction_builder = InstructionBuilder(self.instructions)
        system_prompt = await instruction_builder.build(deps)
        if self.skill_registry and active_skills:
            system_prompt = SkillActivator(self.skill_registry).inject_skill_context(
                system_prompt,
                active_skills,
            )

        return Agent[PydanticAgentDeps, str | DeferredToolRequests](
            self._model_for_run(deps.run),
            deps_type=PydanticAgentDeps,
            instructions=system_prompt,
            output_type=str | DeferredToolRequests,
            capabilities=capabilities,
        )

    async def _activate_progressive_skills(self, deps: PydanticAgentDeps) -> list[ProgressiveSkill]:
        if self.skill_registry is None:
            return []
        activator = SkillActivator(self.skill_registry)
        matches = activator.detect_skills_for_goal(
            deps.run.goal,
            skill_id_hint=deps.run.skill_id,
        )
        active: list[ProgressiveSkill] = []
        for match in matches:
            skill = self.skill_registry.get_skill(match.skill_name)
            if skill is None:
                continue
            active.append(skill)
            await deps.event_writer.write(
                run_id=deps.run.id,
                thread_id=deps.run.thread_id,
                type="skill.activated",
                source={"kind": "harness"},
                visibility="debug",
                payload={
                    "skill_name": match.skill_name,
                    "confidence": match.confidence,
                    "matched_trigger": match.matched_trigger,
                },
            )
        return active

    def _apply_progressive_skill_tool_policy(
        self,
        descriptors: list[AgentToolDescriptor],
        skills: list[ProgressiveSkill],
    ) -> list[AgentToolDescriptor]:
        if not skills:
            return descriptors
        allowed_sets = [
            set(skill.allowed_tools)
            for skill in skills
            if skill.allowed_tools is not None
        ]
        denied = {
            tool
            for skill in skills
            for tool in (skill.denied_tools or [])
        }
        filtered = descriptors
        if allowed_sets:
            allowed = set().union(*allowed_sets)
            filtered = [descriptor for descriptor in filtered if descriptor.name in allowed]
        if denied:
            filtered = [descriptor for descriptor in filtered if descriptor.name not in denied]
        return filtered

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

        async with agent.run_stream_events(goal, deps=deps) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        content_parts.append(event.delta.content_delta)
                        await deps.event_writer.write(
                            run_id=deps.run.id,
                            thread_id=deps.run.thread_id,
                            type="message.delta",
                            source={"kind": "model"},
                            payload={"message_id": message_id, "delta": event.delta.content_delta},
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
        ) as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    if event.delta.content_delta:
                        content_parts.append(event.delta.content_delta)
                        await deps.event_writer.write(
                            run_id=deps.run.id,
                            thread_id=deps.run.thread_id,
                            type="message.delta",
                            source={"kind": "model"},
                            payload={"message_id": message_id, "delta": event.delta.content_delta},
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

    def _model_for_run(self, run: AgentRun | None) -> object:
        if run and run.harness_options and run.harness_options.model:
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
        """Persist a deferred tool approval request and pause the run."""
        if not requests.approvals:
            raise AgentError("BAD_REQUEST", "Deferred tool calls without approval are not supported")

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

        message_history_json = ModelMessagesTypeAdapter.dump_json(message_history).decode("utf-8")
        approval = await deps.store.create_approval(
            run_id=deps.run.id,
            tool_call_id=tool_call.tool_call_id,
            tool_name=tool_call.tool_name,
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
                "tool_name": tool_call.tool_name,
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
                "tool_name": tool_call.tool_name,
            },
        )
        return pending_state

    async def _emit_usage_event(self, deps: PydanticAgentDeps, usage: object) -> None:
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="model.usage",
            source={"kind": "model"},
            visibility="debug",
            payload=_map_run_usage(usage),
        )


def _result_content(content_parts: list[str], final_output: str | None) -> str:
    if content_parts:
        return "".join(content_parts)
    return final_output or ""


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
