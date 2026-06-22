from aithru_agent.domain import (
    AgentMemoryRecall,
    AgentMemoryRecallItem,
    AgentMessage,
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
    ResearchLimitation,
)


def test_context_message_truncates_content_with_pydantic_metadata() -> None:
    message = AgentMessage(
        id="msg_1",
        thread_id="thread_1",
        role="user",
        content="Explain Aithru context engineering in detail.",
        run_id="run_1",
        artifact_ids=[],
        created_at="2026-06-18T00:00:00Z",
    )

    summary = AgentRunContextMessage.from_message(message, max_content_chars=16)

    assert summary.model_dump(mode="json") == {
        "id": "msg_1",
        "role": "user",
        "content": "Explain Aithru c",
        "run_id": "run_1",
        "artifact_ids": [],
        "created_at": "2026-06-18T00:00:00Z",
        "truncated": True,
        "original_length": 45,
    }


def test_context_packet_exposes_counts_and_truncation_status() -> None:
    packet = AgentRunContextPacket(
        run_id="run_1",
        thread_id="thread_1",
        skill_id="deep-research",
        goal="Research Aithru parity.",
        status="running",
        resume=AgentRunResumeContext(reason="input_received", detail="Latest user input is available."),
        thread_messages=[
            AgentRunContextMessage(
                id="msg_1",
                role="user",
                content="Use APAC.",
                run_id="run_1",
                artifact_ids=[],
                created_at="2026-06-18T00:00:00Z",
            )
        ],
        todos=[
            AgentRunContextTodo(
                id="todo_1",
                title="Search sources",
                status="done",
                order=1,
            )
        ],
        artifacts=[
            AgentRunContextArtifact(
                id="artifact_1",
                type="report",
                name="Research Report",
                uri="/reports/research.md",
                media_type="text/markdown",
                summary="Collected source evidence.",
                truncated=True,
                created_at="2026-06-18T00:00:00Z",
            )
        ],
    )

    assert packet.counts.model_dump(mode="json") == {
        "thread_messages": 1,
        "todos": 1,
        "artifacts": 1,
        "tool_results": 0,
        "memory": 0,
        "research_evidence": 0,
    }
    assert packet.has_context is True
    assert packet.has_truncated_content is True


def test_context_packet_tracks_budget_and_compressed_context() -> None:
    packet = AgentRunContextPacket(
        run_id="run_1",
        thread_id="thread_1",
        skill_id="deep-research",
        goal="Research Aithru parity.",
        status="running",
        compressed_context=AgentRunCompressedContext(
            summary="Compressed context: 2 older thread messages, 1 additional todo.",
            counts=AgentRunContextCounts(thread_messages=2, todos=1, artifacts=0),
        ),
        budget=AgentRunContextBudgetUsage(
            max_chars=120,
            used_chars=96,
            dropped_thread_messages=2,
            dropped_todos=1,
            truncated_items=3,
        ),
    )

    assert packet.budget is not None
    assert packet.budget.remaining_chars == 24
    assert packet.has_context is True
    assert packet.has_dropped_context is True
    assert packet.event_payload() == {
        "thread_messages": 0,
        "todos": 0,
        "artifacts": 0,
        "tool_results": 0,
        "memory": 0,
        "research_evidence": 0,
        "has_truncated_content": False,
        "has_dropped_context": True,
        "budget": {
            "max_chars": 120,
            "used_chars": 96,
            "remaining_chars": 24,
            "dropped_thread_messages": 2,
            "dropped_todos": 1,
            "dropped_artifacts": 0,
            "dropped_tool_results": 0,
            "dropped_memory": 0,
            "dropped_research_evidence": 0,
            "truncated_items": 3,
        },
    }


def test_context_packet_tracks_tool_result_summaries() -> None:
    packet = AgentRunContextPacket(
        run_id="run_1",
        thread_id="thread_1",
        goal="Continue after fetching sources.",
        status="running",
        tool_results=[
            AgentRunContextToolResult(
                tool_call_id="toolcall_fetch",
                tool_name="web.fetch",
                status="completed",
                summary="url=https://example.com/source; content=Important fetched evidence.",
                source_sequence=6,
                truncated=True,
                original_length=240,
            )
        ],
        budget=AgentRunContextBudgetUsage(
            max_chars=120,
            used_chars=80,
            truncated_items=1,
        ),
    )

    assert packet.counts.model_dump(mode="json") == {
        "thread_messages": 0,
        "todos": 0,
        "artifacts": 0,
        "tool_results": 1,
        "memory": 0,
        "research_evidence": 0,
    }
    assert packet.has_context is True
    assert packet.has_truncated_content is True
    assert packet.event_payload()["tool_results"] == 1


def test_context_packet_tracks_memory_recall() -> None:
    packet = AgentRunContextPacket(
        run_id="run_1",
        thread_id="thread_1",
        goal="Use memory.",
        status="running",
        memory=AgentMemoryRecall(
            run_id="run_1",
            items=[
                AgentMemoryRecallItem(
                    memory_id="memory_1",
                    scope="user",
                    scope_id="user_1",
                    key="preference.language",
                    value="Prefers Chinese summaries.",
                    reason="Current user memory is readable by this run.",
                    created_at="2026-06-19T00:00:00Z",
                    updated_at="2026-06-19T00:00:00Z",
                    truncated=True,
                    original_length=120,
                )
            ],
            count=1,
            dropped=1,
        ),
        budget=AgentRunContextBudgetUsage(
            max_chars=120,
            used_chars=90,
            dropped_memory=1,
            truncated_items=1,
        ),
    )

    assert packet.counts.model_dump(mode="json") == {
        "thread_messages": 0,
        "todos": 0,
        "artifacts": 0,
        "tool_results": 0,
        "memory": 1,
        "research_evidence": 0,
    }
    assert packet.has_context is True
    assert packet.has_truncated_content is True
    assert packet.has_dropped_context is True
    assert packet.event_payload()["memory"] == 1
    assert packet.event_payload()["budget"]["dropped_memory"] == 1


def test_context_packet_tracks_research_continuation_context() -> None:
    packet = AgentRunContextPacket(
        run_id="run_1",
        thread_id="thread_1",
        skill_id="deep-research",
        goal="Continue research.",
        status="running",
        research=AgentRunResearchContinuationContext(
            source_run_id="run_source",
            query="aithru deerflow parity",
            status="degraded",
            report_status="partial",
            target_section_ids=["gaps"],
            source_event_sequence=6,
            completed_steps=["Search sources"],
            pending_steps=["Create research report"],
            blocked_steps=["Fetch and review sources"],
            report_artifact_ids=["artifact_report"],
            report_artifact_uris=["/reports/research.md"],
            sections=[
                AgentRunResearchSectionContext(
                    section_id="architecture",
                    title="Architecture",
                    question="How is the backend structured?",
                    priority="high",
                    source_count=1,
                    evidence_count=1,
                    covered=True,
                ),
                AgentRunResearchSectionContext(
                    section_id="gaps",
                    title="Open gaps",
                    question="What remains incomplete?",
                    priority="medium",
                    source_count=0,
                    evidence_count=0,
                    covered=False,
                    truncated=True,
                    original_length=80,
                ),
            ],
            evidence=[
                AgentRunResearchEvidenceContext(
                    citation_number=1,
                    title="Aithru Agent",
                    url="https://example.com/aithru",
                    quality_label="high",
                    snippet="Harness evidence.",
                    excerpt="Fetched evidence.",
                    truncated=True,
                    original_length=240,
                )
            ],
            limitations=[
                ResearchLimitation(
                    code="web_fetch_failed",
                    severity="warning",
                    message="Fetch failed for one supporting source.",
                    source_url="https://example.com/aithru",
                )
            ],
            next_actions=[
                "Resolve blocked research steps before finalizing.",
                "Reuse existing cited evidence where relevant.",
            ],
            action_hints=[
                AgentRunResearchActionContext(
                    kind="retry_fetch",
                    priority="high",
                    title="Retry controlled web fetch",
                    reason="Fetch was blocked for a cited source.",
                    suggested_tool_names=["web.fetch"],
                    suggested_research_phases=["fetch"],
                )
            ],
            dropped_evidence=2,
        ),
        budget=AgentRunContextBudgetUsage(
            max_chars=240,
            used_chars=180,
            dropped_research_evidence=2,
            truncated_items=1,
        ),
    )

    assert packet.counts.model_dump(mode="json") == {
        "thread_messages": 0,
        "todos": 0,
        "artifacts": 0,
        "tool_results": 0,
        "memory": 0,
        "research_evidence": 1,
    }
    assert packet.has_context is True
    assert packet.has_truncated_content is True
    assert packet.has_dropped_context is True
    assert packet.event_payload()["research"] == {
        "status": "degraded",
        "report_status": "partial",
        "evidence": 1,
        "limitations": 1,
            "sections": 2,
            "missing_sections": 1,
            "target_sections": 1,
            "action_hints": 1,
            "dropped_evidence": 2,
            "source_run_id": "run_source",
        }
    assert packet.event_payload()["budget"]["dropped_research_evidence"] == 2
