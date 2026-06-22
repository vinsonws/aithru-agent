from __future__ import annotations

from aithru_agent.domain import AgentRunStatus

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class ClarificationPreflightProcessor(AgentRuntimeProcessor):
    name: str = "clarification_preflight"

    def __init__(self, *, min_goal_words: int = 4) -> None:
        self.min_goal_words = min_goal_words

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()
        if "agent.input.write" not in context.run.scopes and "*" not in context.run.scopes:
            return AgentRuntimeProcessorDecision()
        if _word_count(context.run.goal) >= self.min_goal_words:
            return AgentRuntimeProcessorDecision()
        if await _has_received_input(context):
            return AgentRuntimeProcessorDecision()

        input_request_id = f"clarify_{context.run.id}"
        payload = {
            "input_request_id": input_request_id,
            "tool_call_id": input_request_id,
            "prompt": "What should the agent focus on, and what result should it produce?",
            "reason": "The run goal is too short to execute safely.",
        }
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="input.requested",
            source={"kind": "harness"},
            payload=payload,
        )
        paused = await context.store.update_run(
            context.run.id,
            status=AgentRunStatus.WAITING_INPUT,
        )
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={"status": "waiting_input", **payload},
        )
        return AgentRuntimeProcessorDecision(paused_run=paused)


def _word_count(value: str) -> int:
    return len([word for word in value.split() if word.strip()])


async def _has_received_input(context: AgentRuntimeProcessorContext) -> bool:
    if context.event_store is None:
        return False
    events = await context.event_store.list_by_run(context.run.id)
    return any(event.type == "input.received" for event in events)
