from __future__ import annotations

from aithru_agent.domain import AgentRunStatus

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class ClarificationPreflightProcessor(AgentRuntimeProcessor):
    """Guard against completely empty task messages.

    Model-driven clarification is now handled by the ask_clarification tool.
    This processor only intercepts truly empty task messages to avoid sending blank
    input to the model.
    """
    name: str = "clarification_preflight"

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()
        if not _is_empty(context.run.task_msg):
            return AgentRuntimeProcessorDecision()

        input_request_id = f"empty_task_msg_{context.run.id}"
        payload = {
            "input_request_id": input_request_id,
            "tool_call_id": input_request_id,
            "prompt": "What should the agent help you with?",
            "reason": "The run task message is empty.",
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


def _is_empty(value: str) -> bool:
    return not value or not value.strip()
