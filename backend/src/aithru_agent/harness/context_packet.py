from dataclasses import dataclass
import json

from aithru_agent.domain import (
    AgentArtifact,
    AgentContextSummary,
    AgentMemoryRecall,
    AgentMemoryRecallItem,
    AgentMemoryVisibilityPolicy,
    AgentRun,
    AgentRunCompressedContext,
    AgentRunContextBudgetUsage,
    AgentRunContextArtifact,
    AgentRunContextCounts,
    AgentRunContextMessage,
    AgentRunContextPacket,
    AgentRunContextToolResult,
    AgentRunContextTodo,
    AgentRunResearchActionContext,
    AgentRunResearchContinuationContext,
    AgentRunResearchEvidenceContext,
    AgentRunResearchSectionContext,
    AgentRunResumeContext,
    ResearchEvidenceSectionSummary,
    ResearchPlanSection,
    ResearchReport,
)
from aithru_agent.memory import (
    LongTermMemoryProvider,
    LongTermMemorySearchResult,
    can_read_long_term_memory,
)
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.stream import AgentEventWriter, AgentStreamEvent


DEFAULT_CONTEXT_PACKET_MAX_THREAD_MESSAGES = 12
DEFAULT_CONTEXT_PACKET_MAX_TODOS = 20
DEFAULT_CONTEXT_PACKET_MAX_ARTIFACTS = 8
DEFAULT_CONTEXT_PACKET_MAX_TOOL_RESULTS = 8
DEFAULT_CONTEXT_PACKET_MAX_MEMORY_ENTRIES = 8
DEFAULT_CONTEXT_PACKET_MAX_RESEARCH_EVIDENCE = 5
DEFAULT_CONTEXT_PACKET_MAX_CONTENT_CHARS = 1_000
DEFAULT_CONTEXT_PACKET_MAX_TOTAL_CHARS = 6_000


@dataclass(frozen=True)
class ContextPacketBuilder:
    max_thread_messages: int = DEFAULT_CONTEXT_PACKET_MAX_THREAD_MESSAGES
    max_todos: int = DEFAULT_CONTEXT_PACKET_MAX_TODOS
    max_artifacts: int = DEFAULT_CONTEXT_PACKET_MAX_ARTIFACTS
    max_tool_results: int = DEFAULT_CONTEXT_PACKET_MAX_TOOL_RESULTS
    max_memory_entries: int = DEFAULT_CONTEXT_PACKET_MAX_MEMORY_ENTRIES
    max_research_evidence: int = DEFAULT_CONTEXT_PACKET_MAX_RESEARCH_EVIDENCE
    max_content_chars: int = DEFAULT_CONTEXT_PACKET_MAX_CONTENT_CHARS
    max_total_chars: int = DEFAULT_CONTEXT_PACKET_MAX_TOTAL_CHARS
    long_term_memory_provider: LongTermMemoryProvider | None = None

    async def build(
        self,
        run: AgentRun,
        store: AgentStore,
        *,
        event_store: AgentEventStore | None = None,
        event_writer: AgentEventWriter | None = None,
    ) -> AgentRunContextPacket:
        thread_messages, dropped_thread_messages = await self._thread_messages(run, store)
        all_todos = await store.list_todos(run.id)
        todos = [
            AgentRunContextTodo.from_todo(todo, max_content_chars=self.max_content_chars)
            for todo in all_todos[: self.max_todos]
        ]
        dropped_todos = max(0, len(all_todos) - len(todos))
        all_artifacts = await store.list_artifacts(run_id=run.id)
        artifacts = [
            self._artifact_context(artifact)
            for artifact in all_artifacts[-self.max_artifacts :]
        ]
        dropped_artifacts = max(0, len(all_artifacts) - len(artifacts))
        tool_results, dropped_tool_results = await self._tool_results(run, event_store)
        latest_context_summary = await self._latest_context_summary(
            run,
            store,
            dropped_thread_messages=dropped_thread_messages,
        )
        memory, dropped_memory = await self._memory_recall(
            run,
            store,
            thread_messages=thread_messages,
            latest_context_summary=latest_context_summary,
            event_writer=event_writer,
        )
        research = await self._research_context(
            run,
            store=store,
            todos=all_todos,
            artifacts=all_artifacts,
            event_store=event_store,
        )
        dropped_research_evidence = research.dropped_evidence if research else 0
        compressed_context = _compressed_context(
            dropped_thread_messages=dropped_thread_messages,
            dropped_todos=dropped_todos,
            dropped_artifacts=dropped_artifacts,
            dropped_tool_results=dropped_tool_results,
            dropped_memory=dropped_memory,
            dropped_research_evidence=dropped_research_evidence,
            durable_summary=latest_context_summary.summary if latest_context_summary else None,
        )
        thread_messages, todos, artifacts, tool_results, memory, research, compressed_context, budget = _apply_budget(
            thread_messages=thread_messages,
            todos=todos,
            artifacts=artifacts,
            tool_results=tool_results,
            memory=memory,
            research=research,
            compressed_context=compressed_context,
            max_total_chars=self.max_total_chars,
            dropped_thread_messages=dropped_thread_messages,
            dropped_todos=dropped_todos,
            dropped_artifacts=dropped_artifacts,
            dropped_tool_results=dropped_tool_results,
            dropped_memory=dropped_memory,
            dropped_research_evidence=dropped_research_evidence,
        )
        latest_message = thread_messages[-1] if thread_messages else None
        return AgentRunContextPacket(
            run_id=run.id,
            thread_id=run.thread_id,
            skill_id=run.skill_id,
            task_msg=run.task_msg,
            status=run.status,
            resume=AgentRunResumeContext.from_run(run, latest_message=latest_message),
            compressed_context=compressed_context,
            budget=budget,
            thread_messages=thread_messages,
            todos=todos,
            artifacts=artifacts,
            tool_results=tool_results,
            research=research,
            memory=memory,
        )

    async def build_memory_recall(
        self,
        run: AgentRun,
        store: AgentStore,
    ) -> AgentMemoryRecall:
        if not _can_read_memory(run.scopes):
            return AgentMemoryRecall(run_id=run.id, items=[], count=0, dropped=0)
        visibility_policy = AgentMemoryVisibilityPolicy(actor_user_id=run.actor_user_id)
        seen: set[str] = set()
        all_entries: list[AgentMemoryRecallItem] = []
        for scope, scope_id, reason in _memory_scopes_for_run(run):
            scoped_entries = await store.list_memory_entries(
                org_id=run.org_id,
                scope=scope,
                scope_id=scope_id,
            )
            for entry in scoped_entries:
                if entry.id in seen:
                    continue
                if not visibility_policy.allows(entry):
                    continue
                seen.add(entry.id)
                all_entries.append(
                    AgentMemoryRecallItem.from_entry(
                        entry,
                        reason=reason,
                        max_value_chars=self.max_content_chars,
                    )
                )
        entries = all_entries[: max(0, self.max_memory_entries)]
        return AgentMemoryRecall(
            run_id=run.id,
            items=entries,
            count=len(entries),
            dropped=max(0, len(all_entries) - len(entries)),
        )

    async def _thread_messages(
        self,
        run: AgentRun,
        store: AgentStore,
    ) -> tuple[list[AgentRunContextMessage], int]:
        if not run.thread_id:
            return [], 0
        messages = await store.list_messages(run.thread_id)
        retained = messages[-self.max_thread_messages :]
        dropped = max(0, len(messages) - len(retained))
        return (
            [
                AgentRunContextMessage.from_message(
                    message,
                    max_content_chars=self.max_content_chars,
                )
                for message in retained
            ],
            dropped,
        )

    async def _latest_context_summary(
        self,
        run: AgentRun,
        store: AgentStore,
        *,
        dropped_thread_messages: int,
    ) -> AgentContextSummary | None:
        if dropped_thread_messages <= 0 or not run.thread_id:
            return None
        summaries = await store.list_context_summaries(
            org_id=run.org_id,
            thread_id=run.thread_id,
        )
        return summaries[-1] if summaries else None

    def _artifact_context(self, artifact: AgentArtifact) -> AgentRunContextArtifact:
        summary, truncated = _artifact_summary(
            artifact,
            max_chars=self.max_content_chars,
        )
        return AgentRunContextArtifact.from_artifact(
            artifact,
            summary=summary,
            truncated=truncated,
        )

    async def _tool_results(
        self,
        run: AgentRun,
        event_store: AgentEventStore | None,
    ) -> tuple[list[AgentRunContextToolResult], int]:
        if event_store is None:
            return [], 0
        events = [
            event
            for event in await event_store.list_by_run(run.id)
            if event.type in {"tool.completed", "external_run.completed"}
        ]
        retained = events[-self.max_tool_results :]
        dropped = max(0, len(events) - len(retained))
        return (
            [
                _tool_result_context(
                    event,
                    max_chars=self.max_content_chars,
                )
                for event in retained
            ],
            dropped,
        )

    async def _memory_recall(
        self,
        run: AgentRun,
        store: AgentStore,
        *,
        thread_messages: list[AgentRunContextMessage],
        latest_context_summary: AgentContextSummary | None,
        event_writer: AgentEventWriter | None,
    ) -> tuple[AgentMemoryRecall | None, int]:
        recall = await self.build_memory_recall(run, store)
        local_dropped = recall.dropped
        mem0_items = await self._long_term_memory_recall(
            run,
            thread_messages=thread_messages,
            latest_context_summary=latest_context_summary,
            event_writer=event_writer,
            existing_count=len(recall.items),
        )
        merged = _dedupe_memory_items([*recall.items, *mem0_items])
        mem0_dropped = max(0, len(merged) - self.max_memory_entries)
        retained = merged[: self.max_memory_entries]
        total_dropped = local_dropped + mem0_dropped
        if not retained and not total_dropped:
            return None, 0
        return (
            AgentMemoryRecall(
                run_id=run.id,
                items=retained,
                count=len(retained),
                dropped=total_dropped,
            ),
            total_dropped,
        )

    async def _long_term_memory_recall(
        self,
        run: AgentRun,
        *,
        thread_messages: list[AgentRunContextMessage],
        latest_context_summary: AgentContextSummary | None,
        event_writer: AgentEventWriter | None,
        existing_count: int,
    ) -> list[AgentMemoryRecallItem]:
        provider = self.long_term_memory_provider
        if provider is None or not can_read_long_term_memory(run.scopes):
            return []
        remaining = max(0, self.max_memory_entries - existing_count)
        if remaining <= 0:
            return []
        query = _long_term_memory_query(
            run,
            thread_messages=thread_messages,
            latest_context_summary=latest_context_summary,
        )
        if event_writer is not None:
            await event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="memory.search.started",
                source={"kind": "harness"},
                visibility="debug",
                payload={"provider": "mem0", "limit": remaining},
            )
        try:
            results = await provider.search(run=run, query=query, limit=remaining)
        except Exception as exc:
            if event_writer is not None:
                await event_writer.write(
                    run_id=run.id,
                    thread_id=run.thread_id,
                    type="memory.search.failed",
                    source={"kind": "harness"},
                    visibility="debug",
                    payload={"provider": "mem0", "error": {"message": str(exc)}},
                )
            return []
        items = [
            _mem0_recall_item(result, max_value_chars=self.max_content_chars)
            for result in results
            if result.memory.strip()
        ]
        if event_writer is not None:
            await event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="memory.search.completed",
                source={"kind": "harness"},
                visibility="debug",
                payload={
                    "provider": "mem0",
                    "result_count": len(results),
                    "retained_count": len(items),
                },
            )
        return items

    async def _research_context(
        self,
        run: AgentRun,
        *,
        store: AgentStore,
        todos: list,
        artifacts: list[AgentArtifact],
        event_store: AgentEventStore | None,
    ) -> AgentRunResearchContinuationContext | None:
        continuation_options = run.harness_options.research_continuation if run.harness_options else None
        source_run_id = continuation_options.source_run_id if continuation_options else None
        target_section_ids = list(continuation_options.target_section_ids) if continuation_options else []
        events = await event_store.list_by_run(run.id) if event_store is not None else []
        report_result = _latest_research_report(events)
        research_todos = [todo for todo in todos if todo.title in _DEFAULT_RESEARCH_TODO_TITLES]
        report_artifacts = _research_report_artifacts(artifacts)
        if report_result is None and continuation_options is not None and event_store is not None:
            source_inputs = await self._source_research_context_inputs(
                run,
                store=store,
                event_store=event_store,
                source_run_id=continuation_options.source_run_id,
            )
            if source_inputs is not None:
                source_report_result, source_todos, source_artifacts = source_inputs
                if source_report_result is not None:
                    report_result = source_report_result
                if not research_todos:
                    research_todos = source_todos
                if not report_artifacts:
                    report_artifacts = source_artifacts
        if report_result is None and not research_todos and not report_artifacts:
            return None

        report, sequence = report_result if report_result is not None else (None, None)
        evidence, dropped_evidence = _research_evidence_context(
            report,
            max_items=self.max_research_evidence,
            max_chars=self.max_content_chars,
        )
        completed_steps = [todo.title for todo in research_todos if _todo_status_value(todo.status) == "done"]
        pending_steps = [
            todo.title
            for todo in research_todos
            if _todo_status_value(todo.status) in {"pending", "running"}
        ]
        blocked_steps = [todo.title for todo in research_todos if _todo_status_value(todo.status) == "blocked"]
        limitations = list(report.limitations) if report is not None else []
        status = _research_continuation_status(
            report=report,
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            blocked_steps=blocked_steps,
        )
        return AgentRunResearchContinuationContext(
            source_run_id=source_run_id,
            query=report.query if report is not None else None,
            status=status,
            report_status=report.status if report is not None else None,
            target_section_ids=target_section_ids,
            source_event_sequence=sequence,
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            blocked_steps=blocked_steps,
            report_artifact_ids=[artifact.id for artifact in report_artifacts],
            report_artifact_uris=[
                artifact.uri for artifact in report_artifacts if artifact.uri is not None
            ],
            sections=_research_section_context(report, max_chars=self.max_content_chars),
            evidence=evidence,
            limitations=limitations,
            next_actions=_research_next_actions(
                evidence=evidence,
                limitations=limitations,
                pending_steps=pending_steps,
                blocked_steps=blocked_steps,
                report=report,
            ),
            action_hints=_research_action_hints(
                evidence=evidence,
                limitations=limitations,
                blocked_steps=blocked_steps,
                report=report,
            ),
            dropped_evidence=dropped_evidence,
        )

    async def _source_research_context_inputs(
        self,
        run: AgentRun,
        *,
        store: AgentStore,
        event_store: AgentEventStore,
        source_run_id: str,
    ) -> tuple[tuple[ResearchReport, int] | None, list, list[AgentArtifact]] | None:
        source_run = await store.get_run(source_run_id)
        if not _compatible_research_source_run(run, source_run):
            return None
        source_events = await event_store.list_by_run(source_run.id)
        source_report_result = _latest_research_report(source_events)
        source_todos = [
            todo
            for todo in await store.list_todos(source_run.id)
            if todo.title in _DEFAULT_RESEARCH_TODO_TITLES
        ]
        source_artifacts = _research_report_artifacts(
            await store.list_artifacts(run_id=source_run.id)
        )
        if source_report_result is None and not source_todos and not source_artifacts:
            return None
        return source_report_result, source_todos, source_artifacts


def _artifact_summary(artifact: AgentArtifact, *, max_chars: int) -> tuple[str | None, bool]:
    value = _artifact_summary_value(artifact)
    if value is None:
        return None, False
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars], True


def _artifact_summary_value(artifact: AgentArtifact) -> str | None:
    if isinstance(artifact.content, str):
        return artifact.content
    if isinstance(artifact.content, bytes):
        return artifact.content.decode("utf-8", errors="replace")
    if isinstance(artifact.content, dict):
        for key in ("summary", "title", "path"):
            value = artifact.content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(artifact.content, sort_keys=True)
    if artifact.metadata:
        for key in ("summary", "report_status", "quality_label"):
            value = artifact.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _compressed_context(
    *,
    dropped_thread_messages: int,
    dropped_todos: int,
    dropped_artifacts: int,
    dropped_tool_results: int,
    dropped_memory: int,
    dropped_research_evidence: int,
    durable_summary: str | None = None,
) -> AgentRunCompressedContext | None:
    if not any(
        (
            dropped_thread_messages,
            dropped_todos,
            dropped_artifacts,
            dropped_tool_results,
            dropped_memory,
            dropped_research_evidence,
        )
    ):
        return None
    parts: list[str] = []
    if dropped_thread_messages:
        parts.append(_plural(dropped_thread_messages, "older thread message", "older thread messages"))
    if dropped_todos:
        parts.append(_plural(dropped_todos, "additional todo", "additional todos"))
    if dropped_artifacts:
        parts.append(_plural(dropped_artifacts, "older artifact", "older artifacts"))
    if dropped_tool_results:
        parts.append(_plural(dropped_tool_results, "older tool result", "older tool results"))
    if dropped_memory:
        parts.append(_plural(dropped_memory, "additional memory entry", "additional memory entries"))
    if dropped_research_evidence:
        parts.append(_plural(dropped_research_evidence, "additional research evidence row", "additional research evidence rows"))
    summary = "Compressed context: " + "; ".join(parts) + "."
    if durable_summary:
        summary += f"\nDurable context summary: {durable_summary}"
    return AgentRunCompressedContext(
        summary=summary,
        counts=AgentRunContextCounts(
            thread_messages=dropped_thread_messages,
            todos=dropped_todos,
            artifacts=dropped_artifacts,
            tool_results=dropped_tool_results,
            memory=dropped_memory,
            research_evidence=dropped_research_evidence,
        ),
        original_length=len(summary),
    )


def _apply_budget(
    *,
    thread_messages: list[AgentRunContextMessage],
    todos: list[AgentRunContextTodo],
    artifacts: list[AgentRunContextArtifact],
    tool_results: list[AgentRunContextToolResult],
    memory: AgentMemoryRecall | None,
    research: AgentRunResearchContinuationContext | None,
    compressed_context: AgentRunCompressedContext | None,
    max_total_chars: int,
    dropped_thread_messages: int,
    dropped_todos: int,
    dropped_artifacts: int,
    dropped_tool_results: int,
    dropped_memory: int,
    dropped_research_evidence: int,
) -> tuple[
    list[AgentRunContextMessage],
    list[AgentRunContextTodo],
    list[AgentRunContextArtifact],
    list[AgentRunContextToolResult],
    AgentMemoryRecall | None,
    AgentRunResearchContinuationContext | None,
    AgentRunCompressedContext | None,
    AgentRunContextBudgetUsage,
]:
    budget = _ContextBudget(max_total_chars)
    compressed_context = _budget_compressed_context(compressed_context, budget)
    thread_messages = [_budget_message(message, budget) for message in thread_messages]
    todos = [_budget_todo(todo, budget) for todo in todos]
    artifacts = [_budget_artifact(artifact, budget) for artifact in artifacts]
    tool_results = [_budget_tool_result(result, budget) for result in tool_results]
    memory = _budget_memory(memory, budget)
    research = _budget_research(research, budget)
    truncated_items = sum(message.truncated for message in thread_messages) + sum(
        todo.truncated for todo in todos
    ) + sum(artifact.truncated for artifact in artifacts) + int(
        bool(compressed_context and compressed_context.truncated)
    ) + sum(result.truncated for result in tool_results) + (
        sum(item.truncated for item in memory.items) if memory else 0
    ) + (
        sum(item.truncated for item in research.evidence) if research else 0
    ) + (
        sum(item.truncated for item in research.sections) if research else 0
    )
    return (
        thread_messages,
        todos,
        artifacts,
        tool_results,
        memory,
        research,
        compressed_context,
        AgentRunContextBudgetUsage(
            max_chars=max_total_chars,
            used_chars=budget.used_chars,
            dropped_thread_messages=dropped_thread_messages,
            dropped_todos=dropped_todos,
            dropped_artifacts=dropped_artifacts,
            dropped_tool_results=dropped_tool_results,
            dropped_memory=dropped_memory,
            dropped_research_evidence=dropped_research_evidence,
            truncated_items=truncated_items,
        ),
    )


def _budget_compressed_context(
    compressed_context: AgentRunCompressedContext | None,
    budget: "_ContextBudget",
) -> AgentRunCompressedContext | None:
    if compressed_context is None:
        return None
    summary, truncated = budget.take(compressed_context.summary)
    return compressed_context.model_copy(
        update={
            "summary": summary,
            "truncated": compressed_context.truncated or truncated,
            "original_length": compressed_context.original_length or len(compressed_context.summary),
        }
    )


def _budget_message(
    message: AgentRunContextMessage,
    budget: "_ContextBudget",
) -> AgentRunContextMessage:
    content, truncated = budget.take(message.content)
    return message.model_copy(update={"content": content, "truncated": message.truncated or truncated})


def _budget_todo(todo: AgentRunContextTodo, budget: "_ContextBudget") -> AgentRunContextTodo:
    description, truncated = budget.take(todo.description)
    return todo.model_copy(update={"description": description, "truncated": todo.truncated or truncated})


def _budget_artifact(
    artifact: AgentRunContextArtifact,
    budget: "_ContextBudget",
) -> AgentRunContextArtifact:
    summary, truncated = budget.take(artifact.summary)
    return artifact.model_copy(update={"summary": summary, "truncated": artifact.truncated or truncated})


def _budget_tool_result(
    result: AgentRunContextToolResult,
    budget: "_ContextBudget",
) -> AgentRunContextToolResult:
    summary, truncated = budget.take(result.summary)
    return result.model_copy(update={"summary": summary or "", "truncated": result.truncated or truncated})


def _budget_memory(
    memory: AgentMemoryRecall | None,
    budget: "_ContextBudget",
) -> AgentMemoryRecall | None:
    if memory is None:
        return None
    items = []
    for item in memory.items:
        value, truncated = budget.take(item.value)
        items.append(
            item.model_copy(
                update={
                    "value": value or "",
                    "truncated": item.truncated or truncated,
                    "original_length": item.original_length or len(item.value),
                }
            )
        )
    return memory.model_copy(update={"items": items, "count": len(items)})


def _budget_research(
    research: AgentRunResearchContinuationContext | None,
    budget: "_ContextBudget",
) -> AgentRunResearchContinuationContext | None:
    if research is None:
        return None
    evidence = []
    for item in research.evidence:
        snippet, snippet_truncated = budget.take(item.snippet)
        excerpt, excerpt_truncated = budget.take(item.excerpt)
        evidence.append(
            item.model_copy(
                update={
                    "snippet": snippet,
                    "excerpt": excerpt,
                    "truncated": item.truncated or snippet_truncated or excerpt_truncated,
                    "original_length": item.original_length
                    or len(item.snippet or "") + len(item.excerpt or ""),
                }
            )
        )
    sections = []
    for section in research.sections:
        question, question_truncated = budget.take(section.question)
        sections.append(
            section.model_copy(
                update={
                    "question": question,
                    "truncated": section.truncated or question_truncated,
                    "original_length": section.original_length or len(section.question or ""),
                }
            )
        )
    return research.model_copy(update={"evidence": evidence, "sections": sections})


class _ContextBudget:
    def __init__(self, max_chars: int) -> None:
        self._max_chars = max(1, max_chars)
        self.used_chars = 0

    def take(self, value: str | None) -> tuple[str | None, bool]:
        if value is None:
            return None, False
        remaining = self._max_chars - self.used_chars
        if remaining <= 0:
            return "", bool(value)
        if len(value) <= remaining:
            self.used_chars += len(value)
            return value, False
        taken = value[:remaining]
        self.used_chars += len(taken)
        return taken, True


def _plural(count: int, singular: str, plural: str) -> str:
    noun = singular if count == 1 else plural
    return f"{count} {noun}"


def _tool_result_context(event: AgentStreamEvent, *, max_chars: int) -> AgentRunContextToolResult:
    payload = event.payload if isinstance(event.payload, dict) else {}
    output = payload.get("output")
    summary_value = _tool_output_summary(
        tool_name=_string_value(payload.get("tool_name")) or "unknown",
        output=output,
    )
    summary, truncated = _bounded_string(summary_value, max_chars=max_chars)
    return AgentRunContextToolResult(
        tool_call_id=_string_value(payload.get("tool_call_id")) or event.id,
        tool_name=_string_value(payload.get("tool_name")) or "unknown",
        status=_string_value(payload.get("status")) or "completed",
        summary=summary,
        source_sequence=event.sequence,
        source_type="external_run" if event.type == "external_run.completed" else "tool",
        capability_key=_string_value(payload.get("capability_key")),
        capability_run_id=_string_value(payload.get("capability_run_id")),
        truncated=truncated,
        original_length=len(summary_value),
    )


def _tool_output_summary(*, tool_name: str, output: object) -> str:
    if isinstance(output, dict):
        if tool_name == "web.fetch":
            return _join_summary_parts(
                [
                    ("url", output.get("url")),
                    ("status_code", output.get("status_code")),
                    ("content", output.get("content")),
                ]
            )
        if tool_name == "web.search":
            return _web_search_summary(output)
        if tool_name == "workspace.view_image":
            return _join_summary_parts(
                [
                    ("workspace_id", output.get("workspace_id")),
                    ("path", output.get("path")),
                    ("media_type", output.get("media_type")),
                    ("size", output.get("size")),
                    ("content_hash", output.get("content_hash")),
                    ("content_encoding", output.get("content_encoding")),
                ]
            )
        if tool_name == "research.create_report":
            report = output.get("report")
            artifact = output.get("artifact")
            return _join_summary_parts(
                [
                    ("report", report.get("summary") if isinstance(report, dict) else None),
                    ("artifact", artifact.get("uri") if isinstance(artifact, dict) else None),
                ]
            )
        if tool_name.startswith("workflow."):
            return _flat_dict_summary(output)
        return json.dumps(output, sort_keys=True)
    if isinstance(output, str):
        return output
    if output is None:
        return "No output."
    return json.dumps(output, sort_keys=True)


def _web_search_summary(output: dict) -> str:
    results = output.get("results")
    result_parts: list[str] = []
    if isinstance(results, list):
        for item in results[:3]:
            if not isinstance(item, dict):
                continue
            title = _string_value(item.get("title")) or "Untitled"
            url = _string_value(item.get("url"))
            result_parts.append(f"{title} ({url})" if url else title)
    return _join_summary_parts(
        [
            ("query", output.get("query")),
            ("results", "; ".join(result_parts) if result_parts else None),
        ]
    )


def _join_summary_parts(parts: list[tuple[str, object]]) -> str:
    rendered = [
        f"{key}={value}"
        for key, value in parts
        if value is not None and str(value) != ""
    ]
    return "; ".join(rendered) if rendered else "No output."


def _flat_dict_summary(output: dict) -> str:
    return _join_summary_parts(
        [
            (str(key), value)
            for key, value in output.items()
            if not isinstance(value, (dict, list))
        ]
    )


def _bounded_string(value: str, *, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars], True


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _latest_research_report(events: list[AgentStreamEvent]) -> tuple[ResearchReport, int] | None:
    for event in reversed(events):
        if event.type != "tool.completed":
            continue
        payload = event.payload if isinstance(event.payload, dict) else {}
        if payload.get("tool_name") != "research.create_report":
            continue
        output = payload.get("output")
        if not isinstance(output, dict):
            continue
        report = _research_report_value(output.get("report"))
        if report is not None:
            return report, event.sequence
    return None


def _compatible_research_source_run(run: AgentRun, source_run: AgentRun | None) -> bool:
    if source_run is None:
        return False
    if source_run.id == run.id:
        return False
    if source_run.org_id != run.org_id:
        return False
    if source_run.actor_user_id != run.actor_user_id:
        return False
    if source_run.workspace_id != run.workspace_id:
        return False
    if source_run.thread_id != run.thread_id:
        return False
    return True


def _research_report_value(value: object) -> ResearchReport | None:
    if isinstance(value, ResearchReport):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return ResearchReport.model_validate(value)
    except ValueError:
        return None


def _research_report_artifacts(artifacts: list[AgentArtifact]) -> list[AgentArtifact]:
    return [
        artifact
        for artifact in artifacts
        if isinstance(artifact.metadata, dict)
        and artifact.metadata.get("generated_by") == "research.create_report"
    ]


def _research_evidence_context(
    report: ResearchReport | None,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[list[AgentRunResearchEvidenceContext], int]:
    if report is None:
        return [], 0
    retained = report.evidence[: max(0, max_items)]
    return (
        [
            _research_evidence_item(evidence, max_chars=max_chars)
            for evidence in retained
        ],
        max(0, len(report.evidence) - len(retained)),
    )


def _research_evidence_item(
    evidence: object,
    *,
    max_chars: int,
) -> AgentRunResearchEvidenceContext:
    snippet_value = getattr(evidence, "snippet", None)
    excerpt_value = getattr(evidence, "excerpt", None)
    snippet, snippet_truncated = _bounded_optional_string(snippet_value, max_chars=max_chars)
    excerpt, excerpt_truncated = _bounded_optional_string(excerpt_value, max_chars=max_chars)
    return AgentRunResearchEvidenceContext(
        citation_number=int(getattr(evidence, "citation_number", 1)),
        title=str(getattr(evidence, "title", "source")),
        url=str(getattr(evidence, "url", "")),
        section_id=getattr(evidence, "section_id", None),
        quality_label=getattr(getattr(evidence, "quality", None), "label", None),
        snippet=snippet,
        excerpt=excerpt,
        truncated=snippet_truncated or excerpt_truncated,
        original_length=len(snippet_value or "") + len(excerpt_value or ""),
    )


def _research_section_context(
    report: ResearchReport | None,
    *,
    max_chars: int,
) -> list[AgentRunResearchSectionContext]:
    if report is None:
        return []
    summary_by_id = {
        summary.section_id: summary
        for summary in report.section_summary
    }
    contexts: list[AgentRunResearchSectionContext] = []
    seen: set[str] = set()
    for section in getattr(report, "sections", []):
        contexts.append(
            _research_section_item(
                section=section,
                summary=summary_by_id.get(section.section_id),
                max_chars=max_chars,
            )
        )
        seen.add(section.section_id)
    for summary in report.section_summary:
        if summary.section_id in seen:
            continue
        contexts.append(
            _research_section_item(
                section=None,
                summary=summary,
                max_chars=max_chars,
            )
        )
    return contexts


def _research_section_item(
    *,
    section: ResearchPlanSection | None,
    summary: ResearchEvidenceSectionSummary | None,
    max_chars: int,
) -> AgentRunResearchSectionContext:
    section_id = section.section_id if section is not None else (summary.section_id if summary else "section")
    source_count = summary.source_count if summary is not None else 0
    evidence_count = summary.evidence_count if summary is not None else 0
    question_value = section.question if section is not None else None
    question, truncated = _bounded_optional_string(question_value, max_chars=max_chars)
    return AgentRunResearchSectionContext(
        section_id=section_id,
        title=section.title if section is not None else section_id,
        question=question,
        priority=section.priority if section is not None else "medium",
        source_count=source_count,
        evidence_count=evidence_count,
        covered=evidence_count > 0,
        truncated=truncated,
        original_length=len(question_value or ""),
    )


def _research_continuation_status(
    *,
    report: ResearchReport | None,
    completed_steps: list[str],
    pending_steps: list[str],
    blocked_steps: list[str],
) -> str:
    if report is not None:
        if report.status in {"partial", "insufficient_evidence"} or report.limitations or blocked_steps:
            return "degraded"
        return "completed"
    if blocked_steps:
        return "blocked"
    if completed_steps:
        return "running"
    if pending_steps:
        return "planned"
    return "none"


def _research_next_actions(
    *,
    evidence: list[AgentRunResearchEvidenceContext],
    limitations: list,
    pending_steps: list[str],
    blocked_steps: list[str],
    report: ResearchReport | None,
) -> list[str]:
    actions: list[str] = []
    if blocked_steps:
        actions.append("Resolve blocked research steps before finalizing.")
    if report is not None and (report.status in {"partial", "insufficient_evidence"} or limitations):
        actions.append("Review limitations before relying on this report as complete.")
    if pending_steps and report is None and not blocked_steps:
        actions.append("Continue pending research steps: " + ", ".join(pending_steps) + ".")
    if evidence:
        actions.append("Reuse existing cited evidence where relevant.")
    elif report is None:
        actions.append("Collect source evidence before report creation.")
    return _unique_strings(actions)


def _research_action_hints(
    *,
    evidence: list[AgentRunResearchEvidenceContext],
    limitations: list,
    blocked_steps: list[str],
    report: ResearchReport | None,
) -> list[AgentRunResearchActionContext]:
    action_hints: list[AgentRunResearchActionContext] = []
    target_section_ids = _research_missing_section_ids(report)
    if report is None:
        if not evidence:
            action_hints.append(
                AgentRunResearchActionContext(
                    kind="collect_more_sources",
                    priority="high",
                    title="Collect source evidence",
                    reason="No research report or citation evidence is available yet.",
                    suggested_tool_names=["web.search", "web.fetch"],
                    suggested_research_phases=["search", "fetch"],
                )
            )
        return action_hints

    if report.status in {"partial", "insufficient_evidence"} or not evidence:
        action_hints.append(
            AgentRunResearchActionContext(
                kind="collect_more_sources",
                priority="high" if report.status == "insufficient_evidence" or not evidence else "medium",
                title="Collect more evidence sources",
                reason="The current research report is not fully supported by available citation evidence.",
                target_section_ids=target_section_ids,
                suggested_tool_names=["web.search", "web.fetch"],
                suggested_research_phases=["search", "fetch"],
            )
        )

    if any("Search" in step for step in blocked_steps):
        action_hints.append(
            AgentRunResearchActionContext(
                kind="retry_search",
                priority="high",
                title="Retry controlled web search",
                reason="A search step is blocked and may need fresh candidate sources.",
                suggested_tool_names=["web.search"],
                suggested_research_phases=["search"],
            )
        )

    if any("Fetch" in step for step in blocked_steps):
        action_hints.append(
            AgentRunResearchActionContext(
                kind="retry_fetch",
                priority="high",
                title="Retry controlled web fetch",
                reason="A fetch step is blocked and may need fresh source content.",
                suggested_tool_names=["web.fetch"],
                suggested_research_phases=["fetch"],
            )
        )

    if limitations:
        action_hints.append(
            AgentRunResearchActionContext(
                kind="address_limitations",
                priority="high" if any(getattr(item, "severity", None) == "error" for item in limitations) else "medium",
                title="Address research limitations",
                reason="The current report records limitations that should be resolved or carried forward explicitly.",
                suggested_tool_names=[],
                suggested_research_phases=["synthesize"],
            )
        )

    if action_hints:
        action_hints.append(
            AgentRunResearchActionContext(
                kind="regenerate_report",
                priority="medium",
                title="Regenerate the research report",
                reason="After repairing evidence gaps, create a fresh report artifact and review it again.",
                target_section_ids=target_section_ids,
                suggested_tool_names=["research.create_report"],
                suggested_research_phases=["report"],
            )
        )

    return action_hints


def _research_missing_section_ids(report: ResearchReport | None) -> list[str]:
    if report is None:
        return []
    evidence_counts_by_section = {
        summary.section_id: summary.evidence_count
        for summary in report.section_summary
    }
    return [
        section.section_id
        for section in report.sections
        if evidence_counts_by_section.get(section.section_id, 0) == 0
    ]


def _todo_status_value(status: object) -> str:
    return str(status.value if hasattr(status, "value") else status)


def _bounded_optional_string(value: str | None, *, max_chars: int) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if len(value) <= max_chars:
        return value, False
    return value[:max_chars], True


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _can_read_memory(scopes: list[str]) -> bool:
    return "*" in scopes or "agent.memory.read" in scopes


def _memory_scopes_for_run(run: AgentRun) -> list[tuple[str, str | None, str]]:
    scopes = [
        ("user", run.actor_user_id, "Current user memory is readable by this run."),
        ("thread", run.thread_id or run.id, "Current thread memory is readable by this run."),
        ("workspace", run.workspace_id, "Current workspace memory is readable by this run."),
        ("organization", run.org_id, "Organization memory is readable by this run."),
    ]
    if run.skill_id:
        scopes.append(("skill", run.skill_id, "Current skill memory is readable by this run."))
    return scopes


_DEFAULT_RESEARCH_TODO_TITLES = {
    "Search sources",
    "Fetch and review sources",
    "Synthesize findings",
    "Create research report",
}


def _long_term_memory_query(
    run: AgentRun,
    *,
    thread_messages: list[AgentRunContextMessage],
    latest_context_summary: AgentContextSummary | None,
) -> str:
    parts = [run.task_msg]
    if thread_messages:
        parts.append(thread_messages[-1].content)
    if latest_context_summary is not None:
        parts.append(latest_context_summary.summary)
    return "\n\n".join(part for part in parts if part.strip())[:2_000]


def _mem0_recall_item(
    result: LongTermMemorySearchResult,
    *,
    max_value_chars: int,
) -> AgentMemoryRecallItem:
    value, truncated, original_length = _bounded_memory_text(result.memory, max_chars=max_value_chars)
    timestamp = result.updated_at or result.created_at or "1970-01-01T00:00:00Z"
    return AgentMemoryRecallItem(
        memory_id=f"mem0:{result.id}",
        scope="user",
        scope_id=None,
        key=f"mem0:{result.id}",
        value=value,
        source="mem0",
        confidence=result.score,
        visibility="private",
        reason="Mem0 returned this cross-thread memory for the current user query.",
        created_at=result.created_at or timestamp,
        updated_at=timestamp,
        truncated=truncated,
        original_length=original_length,
    )


def _dedupe_memory_items(items: list[AgentMemoryRecallItem]) -> list[AgentMemoryRecallItem]:
    seen: set[str] = set()
    retained: list[AgentMemoryRecallItem] = []
    for item in items:
        key = item.memory_id if item.memory_id.startswith("mem0:") else f"{item.key}:{item.value}"
        if key in seen:
            continue
        seen.add(key)
        retained.append(item)
    return retained


def _bounded_memory_text(value: str, *, max_chars: int) -> tuple[str, bool, int]:
    original_length = len(value)
    if original_length <= max_chars:
        return value, False, 0
    return value[:max_chars], True, original_length
