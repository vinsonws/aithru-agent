from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from aithru_agent.domain import AgentContextSummary, AgentMessage, AgentRunStatus

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class SemanticSummaryProvider(Protocol):
    async def summarize_messages(self, messages: list[AgentMessage]) -> str:
        ...


class DeterministicSemanticSummaryProvider:
    def __init__(self, *, max_chars: int = 600) -> None:
        self._max_chars = max(1, max_chars)

    async def summarize_messages(self, messages: list[AgentMessage]) -> str:
        rendered = "\n".join(
            f"{message.role}: {message.content.strip()}"
            for message in messages
            if message.content.strip()
        ).strip()
        if len(rendered) <= self._max_chars:
            return rendered
        return rendered[: self._max_chars]


class ContextSummarizationProcessor(AgentRuntimeProcessor):
    name = "context_summarization"

    def __init__(
        self,
        *,
        provider: SemanticSummaryProvider | None = None,
        min_message_count: int = 6,
    ) -> None:
        self._provider = provider or DeterministicSemanticSummaryProvider()
        self._min_message_count = min_message_count

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        terminal_status = context.terminal_status or context.run.status
        if terminal_status != AgentRunStatus.COMPLETED:
            return AgentRuntimeProcessorDecision()
        if not context.run.thread_id:
            return AgentRuntimeProcessorDecision()

        messages = await context.store.list_messages(context.run.thread_id)
        if len(messages) < self._min_message_count:
            return AgentRuntimeProcessorDecision()
        summary_text = await self._provider.summarize_messages(messages)
        summary = AgentContextSummary(
            id=f"summary_{context.run.id}",
            org_id=context.run.org_id,
            thread_id=context.run.thread_id,
            run_id=context.run.id,
            summary=summary_text,
            source="semantic_processor",
            message_count=len(messages),
            token_estimate=_token_estimate(summary_text),
            created_at=utc_now(),
        )
        await context.store.create_context_summary(summary)
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=context.run.thread_id,
            type="context.summary.created",
            source={"kind": "harness"},
            visibility="debug",
            payload={
                "summary_id": summary.id,
                "thread_id": summary.thread_id,
                "run_id": summary.run_id,
                "source": summary.source,
                "message_count": summary.message_count,
                "token_estimate": summary.token_estimate,
                "summary": summary.summary,
            },
        )
        return AgentRuntimeProcessorDecision()


def _token_estimate(value: str) -> int:
    return max(1, (len(value) + 3) // 4)
