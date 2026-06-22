from __future__ import annotations

from datetime import UTC, datetime

from aithru_agent.domain import AgentMemoryCandidate, AgentRunStatus

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class MemoryExtractionProcessor(AgentRuntimeProcessor):
    name = "memory_extraction"

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        terminal_status = context.terminal_status or context.run.status
        if terminal_status != AgentRunStatus.COMPLETED:
            return AgentRuntimeProcessorDecision()
        if not _can_write_memory(context.run.scopes):
            return AgentRuntimeProcessorDecision()

        result_content = context.run.result.content if context.run.result else None
        if result_content is None or not result_content.strip():
            return AgentRuntimeProcessorDecision()

        candidate_id = f"memcand_{context.run.id}"
        existing = await context.store.get_memory_candidate(
            candidate_id,
            org_id=context.run.org_id,
        )
        if existing is not None:
            return AgentRuntimeProcessorDecision()

        scope = "thread" if context.run.thread_id else "user"
        scope_id = context.run.thread_id or context.run.actor_user_id
        candidate = AgentMemoryCandidate(
            id=candidate_id,
            org_id=context.run.org_id,
            run_id=context.run.id,
            scope=scope,
            scope_id=scope_id,
            key=f"run_{context.run.id}_outcome",
            value=result_content[:800],
            confidence=0.6,
            status="pending",
            created_at=utc_now(),
        )
        created = await context.store.create_memory_candidate(candidate)
        if created.created_at == candidate.created_at:
            await context.event_writer.write(
                run_id=context.run.id,
                thread_id=context.run.thread_id,
                type="memory.candidate.created",
                source={"kind": "harness"},
                visibility="audit",
                payload={
                    "candidate_id": created.id,
                    "run_id": created.run_id,
                    "scope": created.scope,
                    "scope_id": created.scope_id,
                    "key": created.key,
                    "confidence": created.confidence,
                    "status": created.status,
                },
            )
        return AgentRuntimeProcessorDecision()


def _can_write_memory(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.memory.write" in scopes
