import pytest

from aithru_agent.agent import PydanticAgentDeps
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.capabilities import AithruCapabilityRouter
from aithru_agent.domain import (
    AgentMemoryRecall,
    AgentMemoryRecallItem,
    AgentMemoryPolicy,
    AgentModelCapabilities,
    AgentRunCompressedContext,
    AgentRunContextBudgetUsage,
    AgentRunContextCounts,
    AgentRunContextPacket,
    AgentRunContextToolResult,
    AgentRunResearchActionContext,
    AgentRunResearchContinuationContext,
    AgentRunResearchEvidenceContext,
    AgentRunResearchSectionContext,
    AgentRunHarnessOptions,
    AgentSkill,
    AgentWorkspaceImageAttachment,
    ResearchLimitation,
)
from aithru_agent.harness import ContextBuilder
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore


def file_report_skill() -> AgentSkill:
    return AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Read files first. Then write a report.",
        allowed_tools=["workspace.list_files"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )


async def build_deps(
    *,
    store: InMemoryAgentStore,
    skill: AgentSkill | None = None,
    harness_options: AgentRunHarnessOptions | None = None,
    context_packet: AgentRunContextPacket | None = None,
) -> PydanticAgentDeps:
    workspace = await store.create_workspace(org_id="org_1")
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Write a report.",
        workspace_id=workspace.id,
        scopes=["*"],
        harness_options=harness_options,
        skill_id=skill.key if skill else None,
    )
    return PydanticAgentDeps(
        run=run,
        run_context=ContextBuilder().build(run, run.scopes, skill),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=AithruCapabilityRouter(adapters=[]),
        store=store,
        skill=skill,
        context_packet=context_packet,
    )


@pytest.mark.asyncio
async def test_instruction_builder_combines_base_and_skill_instructions() -> None:
    deps = await build_deps(store=InMemoryAgentStore(), skill=file_report_skill())

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert instructions == (
        "Base instructions.\n\n"
        "## When to Ask for Clarification\n\n"
        "You have access to the `ask_clarification` tool. Use it before taking tool actions when:\n"
        "- The user's task is too vague to proceed safely\n"
        "- You need to choose between different approaches — provide `options` (2-5 choices)\n"
        "- A requested action has important implications that need user confirmation\n"
        "\n"
        "When providing options, keep them concise. When there are no clear discrete options, ask a focused open-ended question without providing options.\n"
        "\n"
        "Do NOT use `ask_clarification` for:\n"
        "- Simple informational questions you can answer directly\n"
        "- Tasks where the task is clear enough to start working\n"
        "- Situations where you already have enough context from the workspace or memory\n\n"
        "Skill instructions:\nRead files first. Then write a report."
    )


@pytest.mark.asyncio
async def test_instruction_builder_adds_memory_entries_to_instructions() -> None:
    store = InMemoryAgentStore()
    skill = file_report_skill().model_copy(
        update={
            "instructions": "Use relevant memory.",
            "memory_policy": AgentMemoryPolicy(read=True, write=False, scopes=["user"]),
        }
    )
    await store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
    )
    deps = await build_deps(store=store, skill=skill)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Memory:" in instructions
    assert "- user:preference.language = Prefers Chinese summaries." in instructions


@pytest.mark.asyncio
async def test_instruction_builder_adds_run_harness_instructions() -> None:
    deps = await build_deps(
        store=InMemoryAgentStore(),
        harness_options=AgentRunHarnessOptions(instructions="Use terse bullet points."),
    )

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert instructions == (
        "Base instructions.\n\n"
        "## When to Ask for Clarification\n\n"
        "You have access to the `ask_clarification` tool. Use it before taking tool actions when:\n"
        "- The user's task is too vague to proceed safely\n"
        "- You need to choose between different approaches — provide `options` (2-5 choices)\n"
        "- A requested action has important implications that need user confirmation\n"
        "\n"
        "When providing options, keep them concise. When there are no clear discrete options, ask a focused open-ended question without providing options.\n"
        "\n"
        "Do NOT use `ask_clarification` for:\n"
        "- Simple informational questions you can answer directly\n"
        "- Tasks where the task is clear enough to start working\n"
        "- Situations where you already have enough context from the workspace or memory\n\n"
        "Run instructions:\nUse terse bullet points."
    )


@pytest.mark.asyncio
async def test_instruction_builder_renders_image_attachments_with_view_image_guidance() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="What does this chart show?",
        attachments=[
            AgentWorkspaceImageAttachment(
                kind="workspace_image",
                workspace_id=workspace.id,
                path="/uploads/chart.png",
                media_type="image/png",
                size=12,
                content_hash="sha256:chart",
            )
        ],
    )
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Describe attached image.",
        workspace_id=workspace.id,
        scopes=["agent.workspace.read"],
        thread_id=thread.id,
    )
    deps = PydanticAgentDeps(
        run=run,
        run_context=ContextBuilder().build(run, run.scopes, None),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=AithruCapabilityRouter(adapters=[]),
        store=store,
        skill=None,
        context_packet=None,
    )

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Attached images:" in instructions
    assert f"- user: /uploads/chart.png ({workspace.id}, image/png, 12 bytes)" in instructions
    assert "Model vision is not enabled for this run; use workspace.view_image when available." in instructions
    assert "content_base64" not in instructions


@pytest.mark.asyncio
async def test_instruction_builder_renders_direct_vision_guidance_when_enabled() -> None:
    store = InMemoryAgentStore()
    thread = await store.create_thread(org_id="org_1", owner_user_id="user_1")
    workspace = await store.create_workspace(org_id="org_1", thread_id=thread.id)
    await store.append_message(
        thread_id=thread.id,
        role="user",
        content="Inspect this screenshot.",
        attachments=[
            AgentWorkspaceImageAttachment(
                kind="workspace_image",
                workspace_id=workspace.id,
                path="/uploads/screenshot.webp",
                media_type="image/webp",
                size=20,
            )
        ],
    )
    run = await store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Describe attached image.",
        workspace_id=workspace.id,
        scopes=["agent.workspace.read"],
        thread_id=thread.id,
        harness_options=AgentRunHarnessOptions(
            model_capabilities=AgentModelCapabilities(vision=True)
        ),
    )
    deps = PydanticAgentDeps(
        run=run,
        run_context=ContextBuilder().build(run, run.scopes, None),
        event_writer=AgentEventWriter(InMemoryAgentEventStore()),
        capability_router=AithruCapabilityRouter(adapters=[]),
        store=store,
        skill=None,
        context_packet=None,
    )

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Attached images:" in instructions
    assert "- user: /uploads/screenshot.webp" in instructions
    assert "Model vision is enabled for this run; attached workspace images are directly viewable." in instructions
    assert "use workspace.view_image" not in instructions


@pytest.mark.asyncio
async def test_instruction_builder_renders_context_budget_and_compressed_context() -> None:
    context_packet = AgentRunContextPacket(
        run_id="run_1",
        task_msg="Continue the report.",
        status="running",
        compressed_context=AgentRunCompressedContext(
            summary="Compressed context: 2 older thread messages; 1 additional todo.",
            counts=AgentRunContextCounts(thread_messages=2, todos=1, artifacts=0),
        ),
        budget=AgentRunContextBudgetUsage(
            max_chars=120,
            used_chars=64,
            dropped_thread_messages=2,
            dropped_todos=1,
            truncated_items=1,
        ),
    )
    deps = await build_deps(store=InMemoryAgentStore(), context_packet=context_packet)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Run context packet:" in instructions
    assert "Compressed context:" in instructions
    assert "- Compressed context: 2 older thread messages; 1 additional todo." in instructions
    assert (
        "Context budget: 64/120 chars used, 56 remaining; "
        "dropped details: 2 messages, 1 todo, 0 artifacts, 0 tool results, "
        "0 memory entries; truncated items: 1"
    ) in instructions


@pytest.mark.asyncio
async def test_instruction_builder_renders_tool_result_context() -> None:
    context_packet = AgentRunContextPacket(
        run_id="run_1",
        task_msg="Continue after tools.",
        status="running",
        tool_results=[
            AgentRunContextToolResult(
                tool_call_id="toolcall_fetch",
                tool_name="web.fetch",
                status="completed",
                summary="url=https://example.com/source; content=Fetched evidence.",
                source_sequence=4,
            )
        ],
        budget=AgentRunContextBudgetUsage(max_chars=120, used_chars=62),
    )
    deps = await build_deps(store=InMemoryAgentStore(), context_packet=context_packet)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Recent tool results:" in instructions
    assert "- web.fetch [completed]: url=https://example.com/source; content=Fetched evidence." in instructions


@pytest.mark.asyncio
async def test_instruction_builder_renders_external_run_result_context() -> None:
    context_packet = AgentRunContextPacket(
        run_id="run_1",
        task_msg="Continue after workflow capability.",
        status="running",
        tool_results=[
            AgentRunContextToolResult(
                tool_call_id="tc_workflow",
                tool_name="workflow.report_review",
                status="completed",
                summary="review_status=accepted; notes=Approved by Workbench",
                source_sequence=7,
                source_type="external_run",
                capability_key="report_review",
                capability_run_id="caprun_1",
            )
        ],
        budget=AgentRunContextBudgetUsage(max_chars=160, used_chars=62),
    )
    deps = await build_deps(store=InMemoryAgentStore(), context_packet=context_packet)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Recent tool results:" in instructions
    assert (
        "- workflow.report_review [completed external caprun_1]: "
        "review_status=accepted; notes=Approved by Workbench"
    ) in instructions


@pytest.mark.asyncio
async def test_instruction_builder_renders_memory_recall_context() -> None:
    context_packet = AgentRunContextPacket(
        run_id="run_1",
        task_msg="Use memory.",
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
                )
            ],
            count=1,
        ),
        budget=AgentRunContextBudgetUsage(
            max_chars=160,
            used_chars=34,
            dropped_memory=2,
        ),
    )
    deps = await build_deps(store=InMemoryAgentStore(), context_packet=context_packet)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Relevant memory:" in instructions
    assert (
        "- user:preference.language = Prefers Chinese summaries. "
        "(Current user memory is readable by this run.)"
    ) in instructions
    assert "2 memory entries" in instructions


@pytest.mark.asyncio
async def test_instruction_builder_renders_research_continuation_context() -> None:
    context_packet = AgentRunContextPacket(
        run_id="run_1",
        task_msg="Continue research.",
        status="running",
        research=AgentRunResearchContinuationContext(
            source_run_id="run_source",
            query="aithru deerflow parity",
            status="degraded",
            report_status="partial",
            target_section_ids=["gaps"],
            completed_steps=["Search sources"],
            pending_steps=["Create research report"],
            blocked_steps=["Fetch and review sources"],
            report_artifact_ids=["artifact_report"],
            report_artifact_uris=["/reports/aithru.md"],
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
                )
            ],
            limitations=[
                ResearchLimitation(
                    code="web_fetch_failed",
                    severity="warning",
                    message="One source could not be fetched.",
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
                    reason="Fetch failed for one supporting source.",
                    target_section_ids=["gaps"],
                    suggested_tool_names=["web.fetch"],
                    suggested_research_phases=["fetch"],
                ),
                AgentRunResearchActionContext(
                    kind="regenerate_report",
                    priority="medium",
                    title="Regenerate the research report",
                    reason="Create a fresh report after repairing evidence gaps.",
                    suggested_tool_names=["research.create_report"],
                    suggested_research_phases=["report"],
                ),
            ],
        ),
        budget=AgentRunContextBudgetUsage(max_chars=400, used_chars=240),
    )
    deps = await build_deps(store=InMemoryAgentStore(), context_packet=context_packet)

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "Research continuation:" in instructions
    assert "- Status: degraded; report status: partial; query: aithru deerflow parity" in instructions
    assert "- Source run: run_source" in instructions
    assert "- Target sections: gaps" in instructions
    assert "- Completed steps: Search sources" in instructions
    assert "- Pending steps: Create research report" in instructions
    assert "- Blocked steps: Fetch and review sources" in instructions
    assert "- Report artifacts: artifact_report (/reports/aithru.md)" in instructions
    assert "Research sections:" in instructions
    assert (
        "- Section architecture [covered, high]: Architecture - "
        "How is the backend structured? sources=1; evidence=1"
    ) in instructions
    assert (
        "- Section gaps [missing, medium]: Open gaps - "
        "What remains incomplete? sources=0; evidence=0"
    ) in instructions
    assert "- Evidence [1] Aithru Agent (high, https://example.com/aithru): Harness evidence. Fetched evidence." in instructions
    assert "- Limitation warning web_fetch_failed: One source could not be fetched. (https://example.com/aithru)" in instructions
    assert "- Next action: Resolve blocked research steps before finalizing." in instructions
    assert (
        "- Action hint [high] retry_fetch: Retry controlled web fetch - "
        "Fetch failed for one supporting source. sections: gaps; Tools: web.fetch; phases: fetch"
    ) in instructions
    assert (
        "- Action hint [medium] regenerate_report: Regenerate the research report - "
        "Create a fresh report after repairing evidence gaps. Tools: research.create_report; phases: report"
    ) in instructions
