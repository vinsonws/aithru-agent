import pytest

from aithru_agent.domain import (
    AgentContextSummary,
    AgentRunHarnessOptions,
    AgentRunResearchContinuationOptions,
    AgentRunStatus,
)
from aithru_agent.harness import ContextPacketBuilder
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


@pytest.mark.asyncio
async def test_context_packet_builder_collects_bounded_run_context() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Research",
    )
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Older message should be dropped.",
    )
    await store.append_message(
        thread_id=thread.id,
        role="assistant",
        content="I found an existing report artifact.",
    )
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Use APAC as the geographic scope for the report.",
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue research.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        skill_id="deep-research",
        scopes=["*"],
    )
    await store.create_todo(
        run_id=run.id,
        title="Search sources",
        status="done",
        description="Find sources that compare Aithru and DeerFlow.",
    )
    await store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Existing Research",
        uri="/reports/existing.md",
        media_type="text/markdown",
        content="# Existing Research\n" + ("Evidence. " * 20),
    )

    packet = await ContextPacketBuilder(
        max_thread_messages=2,
        max_artifacts=1,
        max_content_chars=32,
    ).build(run, store)

    assert packet.run_id == run.id
    assert packet.thread_id == thread.id
    assert packet.skill_id == "deep-research"
    assert packet.counts.thread_messages == 2
    assert [message.role for message in packet.thread_messages] == ["assistant", "user"]
    assert packet.thread_messages[-1].content == "Use APAC as the geographic scope"
    assert packet.thread_messages[-1].truncated is True
    assert [todo.title for todo in packet.todos] == ["Search sources"]
    assert packet.artifacts[0].summary == "# Existing Research\nEvidence. Ev"
    assert packet.artifacts[0].truncated is True
    assert packet.has_context is True
    assert packet.has_truncated_content is True


@pytest.mark.asyncio
async def test_context_packet_builder_describes_waiting_resume_state() -> None:
    store = InMemoryAgentStore()
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Ask for missing context.",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    packet = await ContextPacketBuilder().build(
        run.model_copy(update={"status": AgentRunStatus.WAITING_INPUT}),
        store,
    )

    assert packet.resume is not None
    assert packet.resume.reason == "waiting_input"
    assert packet.resume.detail == "The run is paused waiting for user input."


@pytest.mark.asyncio
async def test_context_packet_builder_tracks_budget_and_compresses_dropped_context() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Long Research",
    )
    for index in range(5):
        await store.append_message(
            thread_id=thread.id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"message {index} " + ("detail " * 10),
        )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue a long research run.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["*"],
    )
    await store.create_todo(
        run_id=run.id,
        title="Search sources",
        status="done",
        description="Older todo details should be compressed.",
    )
    await store.create_todo(
        run_id=run.id,
        title="Write report",
        status="pending",
        description="Retained todo details should fit the budget.",
    )
    await store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Older Report",
        uri="/reports/older.md",
        content="Older artifact evidence should be compressed.",
    )
    await store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Latest Report",
        uri="/reports/latest.md",
        content="Latest artifact evidence should be retained.",
    )

    packet = await ContextPacketBuilder(
        max_thread_messages=2,
        max_todos=1,
        max_artifacts=1,
        max_content_chars=80,
        max_total_chars=260,
    ).build(run, store)

    assert [message.content.startswith(prefix) for message, prefix in zip(packet.thread_messages, ["message 3", "message 4"])] == [
        True,
        True,
    ]
    assert [todo.title for todo in packet.todos] == ["Search sources"]
    assert [artifact.name for artifact in packet.artifacts] == ["Latest Report"]
    assert packet.compressed_context is not None
    assert packet.compressed_context.counts.thread_messages == 3
    assert packet.compressed_context.counts.todos == 1
    assert packet.compressed_context.counts.artifacts == 1
    assert packet.compressed_context.summary.startswith(
        "Compressed context: 3 older thread messages; 1 additional todo; 1 older artifact."
    )
    assert packet.budget is not None
    assert packet.budget.max_chars == 260
    assert packet.budget.used_chars <= 260
    assert packet.budget.dropped_thread_messages == 3
    assert packet.budget.dropped_todos == 1
    assert packet.budget.dropped_artifacts == 1
    assert packet.has_dropped_context is True


@pytest.mark.asyncio
async def test_context_packet_builder_includes_latest_summary_when_thread_messages_are_dropped() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Long Research",
    )
    for index in range(4):
        await store.append_message(
            thread_id=thread.id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"message {index}",
        )
    await store.create_context_summary(
        AgentContextSummary(
            id="summary_old",
            org_id="org_1",
            thread_id=thread.id,
            run_id="run_old",
            summary="Older durable summary should lose to the latest one.",
            source="semantic_processor",
            message_count=4,
            created_at="2026-06-22T01:00:00Z",
        )
    )
    await store.create_context_summary(
        AgentContextSummary(
            id="summary_latest",
            org_id="org_1",
            thread_id=thread.id,
            run_id="run_latest",
            summary="Earlier thread decided APAC scope and markdown output.",
            source="semantic_processor",
            message_count=4,
            created_at="2026-06-22T02:00:00Z",
        )
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue a long research run.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["*"],
    )

    packet = await ContextPacketBuilder(
        max_thread_messages=2,
        max_content_chars=120,
        max_total_chars=300,
    ).build(run, store)

    assert packet.compressed_context is not None
    assert packet.compressed_context.counts.thread_messages == 2
    assert "Earlier thread decided APAC scope and markdown output." in packet.compressed_context.summary
    assert "Older durable summary" not in packet.compressed_context.summary
    assert packet.budget is not None
    assert packet.budget.dropped_thread_messages == 2


@pytest.mark.asyncio
async def test_context_packet_builder_does_not_force_summary_when_no_thread_messages_are_dropped() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Short Research",
    )
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Keep the visible message.",
    )
    await store.create_context_summary(
        AgentContextSummary(
            id="summary_latest",
            org_id="org_1",
            thread_id=thread.id,
            run_id="run_latest",
            summary="This summary exists but should not be injected yet.",
            source="semantic_processor",
            message_count=1,
            created_at="2026-06-22T02:00:00Z",
        )
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue a short thread.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["*"],
    )

    packet = await ContextPacketBuilder(max_thread_messages=4).build(run, store)

    assert packet.compressed_context is None
    assert packet.budget is not None
    assert packet.budget.dropped_thread_messages == 0


@pytest.mark.asyncio
async def test_context_packet_builder_summarizes_recent_tool_results_from_events() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue after tool use.",
        workspace_id=workspace.id,
        scopes=["*"],
    )
    await writer.write(
        run_id=run.id,
        type="tool.completed",
        source={"kind": "tool"},
        payload={
            "tool_call_id": "toolcall_search",
            "tool_name": "web.search",
            "status": "completed",
            "output": {
                "query": "aithru deerflow parity",
                "results": [
                    {
                        "title": "Aithru Agent",
                        "url": "https://example.com/aithru",
                        "snippet": "Harness backend.",
                    }
                ],
            },
            "error": None,
        },
    )
    await writer.write(
        run_id=run.id,
        type="tool.completed",
        source={"kind": "tool"},
        payload={
            "tool_call_id": "toolcall_fetch",
            "tool_name": "web.fetch",
            "status": "completed",
            "output": {
                "url": "https://example.com/aithru",
                "status_code": 200,
                "content": "Fetched evidence " * 40,
            },
            "error": None,
        },
    )

    packet = await ContextPacketBuilder(
        max_tool_results=1,
        max_content_chars=90,
        max_total_chars=220,
    ).build(run, store, event_store=event_store)

    assert [result.tool_name for result in packet.tool_results] == ["web.fetch"]
    assert packet.tool_results[0].tool_call_id == "toolcall_fetch"
    assert packet.tool_results[0].source_sequence == 2
    assert packet.tool_results[0].summary.startswith(
        "url=https://example.com/aithru; status_code=200; content=Fetched evidence"
    )
    assert packet.tool_results[0].truncated is True
    assert packet.counts.tool_results == 1
    assert packet.budget is not None
    assert packet.budget.dropped_tool_results == 1
    assert packet.event_payload()["tool_results"] == 1


@pytest.mark.asyncio
async def test_context_packet_builder_includes_completed_external_run_results() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue after workflow capability.",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    await writer.write(
        run_id=run.id,
        type="external_run.completed",
        source={"kind": "workflow"},
        payload={
            "kind": "workflow_capability",
            "capability_key": "report_review",
            "capability_run_id": "caprun_1",
            "tool_call_id": "tc_workflow",
            "tool_name": "workflow.report_review",
            "status": "completed",
            "correlation_id": "run_1:tc_workflow",
            "output": {
                "review_status": "accepted",
                "notes": "Approved by Workbench",
            },
            "comment": "completed in Workbench",
        },
    )

    packet = await ContextPacketBuilder(
        max_tool_results=2,
        max_content_chars=120,
        max_total_chars=260,
    ).build(run, store, event_store=event_store)

    assert len(packet.tool_results) == 1
    result = packet.tool_results[0]
    assert result.source_type == "external_run"
    assert result.tool_call_id == "tc_workflow"
    assert result.tool_name == "workflow.report_review"
    assert result.status == "completed"
    assert result.capability_key == "report_review"
    assert result.capability_run_id == "caprun_1"
    assert result.source_sequence == 1
    assert "review_status=accepted" in result.summary
    assert "notes=Approved by Workbench" in result.summary
    assert packet.counts.tool_results == 1


@pytest.mark.asyncio
async def test_context_packet_builder_adds_research_continuation_from_report_events() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Continue research with collected evidence.",
        workspace_id=workspace.id,
        skill_id="deep-research",
        scopes=["*"],
    )
    await store.create_todo(
        run_id=run.id,
        title="Search sources",
        status="done",
    )
    await store.create_todo(
        run_id=run.id,
        title="Fetch and review sources",
        status="blocked",
    )
    await store.create_todo(
        run_id=run.id,
        title="Create research report",
        status="pending",
    )
    artifact = await store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Aithru Research",
        uri="/reports/aithru.md",
        metadata={
            "generated_by": "research.create_report",
            "report_status": "partial",
        },
    )
    await writer.write(
        run_id=run.id,
        type="tool.completed",
        source={"kind": "tool"},
        payload={
            "tool_call_id": "toolcall_report",
            "tool_name": "research.create_report",
            "status": "completed",
            "output": {
                "report": {
                    "title": "Aithru Research",
                    "query": "aithru deerflow parity",
                    "status": "partial",
                    "summary": "Collected one source with one fetch limitation.",
                    "source_input_count": 1,
                    "duplicate_source_count": 0,
                    "quality_summary": {"high": 1, "medium": 0, "low": 0},
                    "section_summary": [
                        {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
                    ],
                    "sections": [
                        {
                            "section_id": "architecture",
                            "title": "Architecture",
                            "question": "How is the backend structured?",
                            "priority": "high",
                        },
                        {
                            "section_id": "gaps",
                            "title": "Open gaps",
                            "question": "What remains incomplete?",
                            "priority": "medium",
                        },
                    ],
                    "limitations": [
                        {
                            "code": "web_fetch_failed",
                            "severity": "warning",
                            "message": "One source could not be fetched.",
                            "source_url": "https://example.com/aithru",
                        }
                    ],
                    "findings": ["Aithru Agent: Harness evidence."],
                    "evidence": [
                        {
                            "citation_number": 1,
                            "title": "Aithru Agent",
                            "url": "https://example.com/aithru",
                            "snippet": "Harness evidence.",
                            "excerpt": "Fetched evidence " * 20,
                            "source": "example-search",
                            "published_at": "2026-06-19",
                            "section_id": "architecture",
                            "quality": {
                                "label": "high",
                                "score": 100,
                                "reasons": [
                                    "valid_http_source",
                                    "has_search_snippet",
                                    "has_fetched_content",
                                    "has_provider",
                                    "has_published_date",
                                ],
                            },
                        }
                    ],
                    "sources": [
                        {
                            "title": "Aithru Agent",
                            "url": "https://example.com/aithru",
                            "snippet": "Harness evidence.",
                            "content": "Fetched evidence.",
                            "source": "example-search",
                            "published_at": "2026-06-19",
                            "section_id": "architecture",
                        }
                    ],
                    "markdown": "# Aithru Research\n",
                },
                "artifact": {"id": artifact.id},
            },
            "error": None,
        },
    )

    packet = await ContextPacketBuilder(
        max_content_chars=60,
        max_total_chars=600,
    ).build(run, store, event_store=event_store)

    assert packet.research is not None
    assert packet.research.query == "aithru deerflow parity"
    assert packet.research.status == "degraded"
    assert packet.research.report_status == "partial"
    assert packet.research.source_event_sequence == 1
    assert packet.research.completed_steps == ["Search sources"]
    assert packet.research.pending_steps == ["Create research report"]
    assert packet.research.blocked_steps == ["Fetch and review sources"]
    assert packet.research.report_artifact_ids == [artifact.id]
    assert packet.research.report_artifact_uris == ["/reports/aithru.md"]
    assert [(section.section_id, section.covered) for section in packet.research.sections] == [
        ("architecture", True),
        ("gaps", False),
    ]
    assert packet.research.sections[0].priority == "high"
    assert packet.research.sections[0].source_count == 1
    assert packet.research.sections[0].evidence_count == 1
    assert packet.research.sections[1].source_count == 0
    assert packet.research.sections[1].evidence_count == 0
    assert packet.research.evidence[0].title == "Aithru Agent"
    assert packet.research.evidence[0].quality_label == "high"
    assert packet.research.evidence[0].excerpt.startswith("Fetched evidence")
    assert packet.research.evidence[0].truncated is True
    assert [limitation.code for limitation in packet.research.limitations] == ["web_fetch_failed"]
    assert packet.research.next_actions == [
        "Resolve blocked research steps before finalizing.",
        "Review limitations before relying on this report as complete.",
        "Reuse existing cited evidence where relevant.",
    ]
    assert [(action.kind, action.priority) for action in packet.research.action_hints] == [
        ("collect_more_sources", "medium"),
        ("retry_fetch", "high"),
        ("address_limitations", "medium"),
        ("regenerate_report", "medium"),
    ]
    assert packet.research.action_hints[0].suggested_tool_names == ["web.search", "web.fetch"]
    assert packet.research.action_hints[0].target_section_ids == ["gaps"]
    assert packet.research.action_hints[1].suggested_research_phases == ["fetch"]
    assert packet.research.action_hints[3].suggested_tool_names == ["research.create_report"]
    assert packet.research.action_hints[3].target_section_ids == ["gaps"]
    assert packet.event_payload()["research"]["evidence"] == 1
    assert packet.event_payload()["research"]["action_hints"] == 4


@pytest.mark.asyncio
async def test_context_packet_builder_loads_source_run_research_for_continuation_runs() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Continuation Thread",
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    source_run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Research Aithru and DeerFlow.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        skill_id="deep-research",
        scopes=["*"],
    )
    await store.create_todo(
        run_id=source_run.id,
        title="Search sources",
        status="done",
    )
    await store.create_todo(
        run_id=source_run.id,
        title="Fetch and review sources",
        status="blocked",
    )
    artifact = await store.create_artifact(
        org_id=source_run.org_id,
        workspace_id=source_run.workspace_id,
        run_id=source_run.id,
        type="report",
        name="Source Research",
        uri="/reports/source.md",
        metadata={
            "generated_by": "research.create_report",
            "report_status": "partial",
        },
    )
    await writer.write(
        run_id=source_run.id,
        type="tool.completed",
        source={"kind": "tool"},
        payload={
            "tool_call_id": "toolcall_source_report",
            "tool_name": "research.create_report",
            "status": "completed",
            "output": {
                "report": {
                    "title": "Source Research",
                    "query": "aithru deerflow parity",
                    "status": "partial",
                    "summary": "Architecture has evidence but gaps needs stronger support.",
                    "source_input_count": 1,
                    "duplicate_source_count": 0,
                    "quality_summary": {"high": 1, "medium": 0, "low": 0},
                    "section_summary": [
                        {"section_id": "architecture", "source_count": 1, "evidence_count": 1}
                    ],
                    "sections": [
                        {
                            "section_id": "architecture",
                            "title": "Architecture",
                            "question": "How is the backend structured?",
                            "priority": "high",
                        },
                        {
                            "section_id": "gaps",
                            "title": "Open gaps",
                            "question": "What remains incomplete?",
                            "priority": "medium",
                        },
                    ],
                    "limitations": [
                        {
                            "code": "section_missing_evidence",
                            "severity": "warning",
                            "message": "The gaps section has no evidence.",
                        }
                    ],
                    "findings": ["Aithru Agent has harness architecture evidence."],
                    "evidence": [
                        {
                            "citation_number": 1,
                            "title": "Aithru Agent Architecture",
                            "url": "https://example.com/aithru-architecture",
                            "snippet": "Harness architecture evidence.",
                            "excerpt": "Aithru keeps tools behind the capability router.",
                            "source": "example-search",
                            "published_at": "2026-06-19",
                            "section_id": "architecture",
                            "quality": {
                                "label": "high",
                                "score": 100,
                                "reasons": ["valid_http_source", "has_fetched_content"],
                            },
                        }
                    ],
                    "sources": [
                        {
                            "title": "Aithru Agent Architecture",
                            "url": "https://example.com/aithru-architecture",
                            "snippet": "Harness architecture evidence.",
                            "content": "Aithru keeps tools behind the capability router.",
                            "source": "example-search",
                            "published_at": "2026-06-19",
                            "section_id": "architecture",
                        }
                    ],
                    "markdown": "# Source Research\n",
                },
                "artifact": {"id": artifact.id},
            },
            "error": None,
        },
    )
    continuation_run = await store.create_run(
        org_id=source_run.org_id,
        actor_user_id=source_run.actor_user_id,
        source="api",
        goal="Continue source research.",
        workspace_id=source_run.workspace_id,
        thread_id=source_run.thread_id,
        skill_id=source_run.skill_id,
        scopes=source_run.scopes,
        harness_options=AgentRunHarnessOptions(
            research_continuation=AgentRunResearchContinuationOptions(
                source_run_id=source_run.id,
                continuation_status="needs_research",
                query="aithru deerflow parity",
                action_ids=["collect_more_sources"],
                target_section_ids=["gaps"],
            )
        ),
    )

    packet = await ContextPacketBuilder(max_content_chars=80).build(
        continuation_run,
        store,
        event_store=event_store,
    )

    assert packet.research is not None
    assert packet.research.source_run_id == source_run.id
    assert packet.research.target_section_ids == ["gaps"]
    assert packet.research.query == "aithru deerflow parity"
    assert packet.research.status == "degraded"
    assert packet.research.report_artifact_ids == [artifact.id]
    assert [(section.section_id, section.covered) for section in packet.research.sections] == [
        ("architecture", True),
        ("gaps", False),
    ]
    assert packet.research.evidence[0].section_id == "architecture"
    assert packet.research.action_hints[0].target_section_ids == ["gaps"]
    assert packet.event_payload()["research"]["source_run_id"] == source_run.id
    assert packet.event_payload()["research"]["target_sections"] == 1


@pytest.mark.asyncio
async def test_context_packet_builder_includes_scoped_memory_recall() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Memory Thread",
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Use scoped memory.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        skill_id="skill_1",
        scopes=["agent.memory.read"],
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
        confidence=0.9,
        visibility="private",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_2",
        key="preference.language",
        value="Prefers English summaries.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="thread",
        scope_id=thread.id,
        key="thread.region",
        value="Use APAC region.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="workspace",
        scope_id=workspace.id,
        key="workspace.report_style",
        value="Use concise sections with citations.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="organization",
        scope_id="org_1",
        key="org.policy",
        value="Do not include secrets in reports.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="skill",
        scope_id="skill_1",
        key="skill.output",
        value="Return markdown.",
    )

    packet = await ContextPacketBuilder(
        max_memory_entries=3,
        max_content_chars=24,
        max_total_chars=260,
    ).build(run, store)

    assert packet.memory is not None
    assert [item.key for item in packet.memory.items] == [
        "preference.language",
        "thread.region",
        "workspace.report_style",
    ]
    assert packet.memory.items[0].scope == "user"
    assert packet.memory.items[0].scope_id == "user_1"
    assert packet.memory.items[0].reason == "Current user memory is readable by this run."
    assert packet.memory.items[2].value == "Use concise sections wit"
    assert packet.memory.items[2].truncated is True
    assert packet.memory.dropped == 2
    assert packet.counts.memory == 3
    assert packet.event_payload()["memory"] == 3
    assert packet.budget is not None
    assert packet.budget.dropped_memory == 2


@pytest.mark.asyncio
async def test_context_packet_builder_exposes_memory_recall_projection() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Memory Projection",
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Inspect memory.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["agent.memory.read"],
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="thread",
        scope_id=thread.id,
        key="thread.region",
        value="Use APAC.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_2",
        key="preference.language",
        value="Prefers English summaries.",
    )

    recall = await ContextPacketBuilder(max_memory_entries=1).build_memory_recall(run, store)

    assert recall.run_id == run.id
    assert recall.count == 1
    assert recall.dropped == 1
    assert [item.key for item in recall.items] == ["preference.language"]
    assert recall.items[0].scope_id == "user_1"


@pytest.mark.asyncio
async def test_context_packet_builder_omits_expired_memory_recall() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Memory Expiry",
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Inspect current memory.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["agent.memory.read"],
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="thread",
        scope_id=thread.id,
        key="thread.expired",
        value="Do not recall.",
        retention={"mode": "expires_at", "expires_at": "2000-01-01T00:00:00Z"},
    )

    recall = await ContextPacketBuilder().build_memory_recall(run, store)

    assert [item.key for item in recall.items] == ["preference.language"]
    assert recall.dropped == 0


@pytest.mark.asyncio
async def test_context_packet_builder_filters_private_memory_by_actor() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Private Memory",
    )
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        goal="Recall visible memory.",
        workspace_id=workspace.id,
        thread_id=thread.id,
        scopes=["agent.memory.read"],
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="thread",
        scope_id=thread.id,
        key="private.owned",
        value="Owned by actor.",
        owner="user_1",
        visibility="private",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="thread",
        scope_id=thread.id,
        key="private.other",
        value="Owned by another actor.",
        owner="user_2",
        visibility="private",
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="thread",
        scope_id=thread.id,
        key="shared.thread",
        value="Shared thread memory.",
        owner="user_2",
        visibility="shared",
    )

    recall = await ContextPacketBuilder().build_memory_recall(run, store)

    assert [item.key for item in recall.items] == ["private.owned", "shared.thread"]
