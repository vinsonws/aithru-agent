from __future__ import annotations

from aithru_agent.domain import AgentRunStatus
from aithru_agent.memory import (
    LongTermMemoryMessage,
    LongTermMemoryProvider,
    can_write_long_term_memory,
)
from aithru_agent.memory.redaction import contains_no_memory_marker, sanitize_memory_text
from aithru_agent.settings import AgentLongTermMemorySettings

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


class Mem0MemoryProcessor(AgentRuntimeProcessor):
    name = "mem0_memory"

    def __init__(
        self,
        *,
        provider: LongTermMemoryProvider,
        settings: AgentLongTermMemorySettings,
    ) -> None:
        self._provider = provider
        self._settings = settings

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        terminal_status = context.terminal_status or context.run.status
        if terminal_status != AgentRunStatus.COMPLETED:
            return AgentRuntimeProcessorDecision()
        if not self._settings.mem0_add_on_run_complete:
            await self._write_skip(context, "disabled")
            return AgentRuntimeProcessorDecision()
        if not can_write_long_term_memory(context.run.scopes):
            await self._write_skip(context, "missing_memory_write_scope")
            return AgentRuntimeProcessorDecision()
        marker_source = context.run.task_msg
        if contains_no_memory_marker(marker_source, self._settings.mem0_no_memory_markers):
            await self._write_skip(context, "no_memory_marker")
            return AgentRuntimeProcessorDecision()
        messages = await _messages_for_run(context)
        if not messages:
            await self._write_skip(context, "no_messages")
            return AgentRuntimeProcessorDecision()
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.add.started",
            source={"kind": "harness"},
            visibility="debug",
            payload={"provider": "mem0", "message_count": len(messages)},
        )
        try:
            result = await self._provider.add_messages(run=context.run, messages=messages)
        except Exception as exc:
            await context.event_writer.write(
                run_id=context.run.id,
                thread_id=context.run.thread_id,
                type="memory.add.failed",
                source={"kind": "harness"},
                visibility="debug",
                payload={"provider": "mem0", "error": {"message": str(exc)}},
            )
            return AgentRuntimeProcessorDecision()
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.add.completed",
            source={"kind": "harness"},
            visibility="debug",
            payload={
                "provider": "mem0",
                "status": result.status,
                "event_id": result.event_id,
                "message_count": len(messages),
            },
        )
        return AgentRuntimeProcessorDecision()

    async def _write_skip(
        self,
        context: AgentRuntimeProcessorContext,
        reason: str,
    ) -> None:
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="memory.add.skipped",
            source={"kind": "harness"},
            visibility="debug",
            payload={"provider": "mem0", "reason": reason},
        )


async def _messages_for_run(
    context: AgentRuntimeProcessorContext,
) -> list[LongTermMemoryMessage]:
    messages: list[LongTermMemoryMessage] = []
    if context.run.thread_id:
        thread_messages = await context.store.list_messages(context.run.thread_id)
        for message in thread_messages:
            if message.run_id != context.run.id:
                continue
            if message.role not in {"user", "assistant"}:
                continue
            content = sanitize_memory_text(message.content.strip())
            if content:
                messages.append(LongTermMemoryMessage(role=message.role, content=content))
    if messages:
        return messages
    if context.run.result and context.run.result.content.strip():
        return [
            LongTermMemoryMessage(
                role="user",
                content=sanitize_memory_text(context.run.task_msg.strip()),
            ),
            LongTermMemoryMessage(
                role="assistant",
                content=sanitize_memory_text(context.run.result.content.strip()),
            ),
        ]
    return []
