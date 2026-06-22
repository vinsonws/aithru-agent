import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime
from aithru_agent.agent.instructions import InstructionBuilder
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.domain import (
    AgentMemoryEntry,
    AgentMemoryPolicy,
    AgentMessage,
    AgentRunHarnessOptions,
    AgentRunStatus,
    AgentSkill,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
    AgentWorkspaceFile,
    AgentWorkspacePolicy,
)
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.settings import AgentSettings
from aithru_agent.skills import InMemorySkillResolver
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker.runner import AgentWorkerRunner


class FailingToolAdapter:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="fail.now",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Always fail.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=[],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        del request, context
        return AgentToolCallResult(
            status="failed",
            error={"message": "tool exploded"},
            redaction="none",
        )


class SchemaEchoToolAdapter:
    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="schema.echo",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Echo a value generated from the descriptor schema.",
                input_schema={
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "string"}},
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=[],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        del context
        return AgentToolCallResult(status="completed", output=request.input, redaction="none")


class RecordingInstructionsAgentRuntime(AgentRuntime):
    def __init__(self) -> None:
        super().__init__(model=TestModel(call_tools=[], custom_output_text="done"))
        self.seen_memory_entries: list[AgentMemoryEntry] | None = None
        self.seen_thread_messages: list[AgentMessage] | None = None
        self.seen_workspace_files: list[AgentWorkspaceFile] | None = None
        self.seen_instructions: str | None = None

    async def build_agent(self, deps):  # type: ignore[no-untyped-def]
        builder = InstructionBuilder(self.instructions)
        self.seen_memory_entries = await builder._memory_entries_for_run(deps)
        self.seen_thread_messages = await builder._thread_messages_for_run(deps)
        self.seen_workspace_files = await builder._workspace_files_for_run(deps)
        self.seen_instructions = await builder.build(deps)
        return await super().build_agent(deps)


def _runtime(
    *,
    agent_runtime: AgentRuntime | None = None,
    policy: ToolPolicy | None = None,
    skill_resolver=None,
    store=None,
    event_store=None,
):
    return create_agent_runtime(
        settings=AgentSettings(model="test"),
        store=store,
        event_store=event_store,
        agent_runtime=agent_runtime or AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done")),
        policy=policy,
        skill_resolver=skill_resolver,
    )


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_streams_text_from_test_model() -> None:
    runtime = _runtime(agent_runtime=AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done")))

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Say done",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)

    assert run.status == AgentRunStatus.COMPLETED
    assert "".join(event.payload["delta"] for event in events if event.type == "message.delta") == "done"
    assert next(event for event in events if event.type == "message.completed").payload["content"] == "done"


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_emits_model_usage_event() -> None:
    runtime = _runtime(agent_runtime=AgentRuntime(model=TestModel(call_tools=[], custom_output_text="done")))

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Track usage.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    usage = next(event for event in events if event.type == "model.usage")

    assert usage.visibility == "debug"
    assert usage.payload["requests"] == 1
    assert usage.payload["input_tokens"] > 0
    assert usage.payload["output_tokens"] == 2
    assert usage.payload["total_tokens"] == usage.payload["input_tokens"] + usage.payload["output_tokens"]


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_uses_run_model_override() -> None:
    def model_factory(model: str):
        return TestModel(call_tools=[], custom_output_text=f"selected {model}")

    runtime = _runtime(
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=[], custom_output_text="default model"),
            model_factory=model_factory,
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Use the run model.",
        scopes=["*"],
        harness_options=AgentRunHarnessOptions(model="test-run-model"),
    )
    events = await runtime.event_store.list_by_run(run.id)
    completed_message = next(event for event in events if event.type == "message.completed")

    assert completed_message.payload["content"] == "selected test-run-model"


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_routes_model_tool_calls_through_aithru_bridge() -> None:
    runtime = _runtime(
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.list_files"], custom_output_text="done")
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="List files and finish.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]

    assert "tool.proposed" in event_types
    assert "tool.started" in event_types
    assert "tool.completed" in event_types
    assert event_types[-1] == "run.completed"


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_exposes_descriptor_input_schema_to_model() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    runner = AgentWorkerRunner(
        store=store,
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[SchemaEchoToolAdapter()],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["schema.echo"], custom_output_text="done")
        ),
    )

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Call schema echo.",
        scopes=["*"],
    )
    proposed = next(event for event in await event_store.list_by_run(run.id) if event.type == "tool.proposed")

    assert run.status == AgentRunStatus.COMPLETED
    assert proposed.payload["input"] == {"value": "a"}


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_fails_run_when_tool_execution_fails() -> None:
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    writer = AgentEventWriter(event_store)
    runner = AgentWorkerRunner(
        store=store,
        event_writer=writer,
        capability_router=AithruCapabilityRouter(
            adapters=[FailingToolAdapter()],
            policy=ToolPolicy(require_approval_for_risk=[]),
        ),
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["fail.now"], custom_output_text="done")
        ),
    )

    run = await runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Call a failing tool.",
        scopes=["*"],
    )
    event_types = [event.type for event in await event_store.list_by_run(run.id)]

    assert run.status == AgentRunStatus.FAILED
    assert event_types[-3:] == ["tool.failed", "model.failed", "run.failed"]
    assert "run.completed" not in event_types


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_pauses_when_tool_requires_approval() -> None:
    runtime = _runtime(
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write a file.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)

    assert run.status == AgentRunStatus.WAITING_APPROVAL
    assert [event.type for event in events][-2:] == ["approval.requested", "run.paused"]
    assert "run.failed" not in [event.type for event in events]


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_resumes_model_after_tool_approval() -> None:
    runtime = _runtime(
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write a file and then summarize.",
        scopes=["*"],
    )
    approval = (await runtime.store.list_approvals())[0]

    resumed = await runtime.runner.resume_run(
        run.id,
        approval_id=approval.id,
        decision="approved",
        comment="ok",
    )
    written = await runtime.store.read_workspace_file(run.workspace_id, "/a")
    events = await runtime.event_store.list_by_run(run.id)

    assert resumed.status == AgentRunStatus.COMPLETED
    assert written.content == "a"
    tool_completed_index = next(index for index, event in enumerate(events) if event.type == "tool.completed")
    first_delta_index = next(index for index, event in enumerate(events) if event.type == "message.delta")
    assert tool_completed_index < first_delta_index
    assert "".join(event.payload["delta"] for event in events if event.type == "message.delta") == "done"
    assert next(event for event in events if event.type == "message.completed").payload["content"] == "done"


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_resumes_model_after_worker_restart() -> None:
    runtime = _runtime(
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write a file and then summarize.",
        scopes=["*"],
    )
    approval = (await runtime.store.list_approvals())[0]
    restarted_runtime = _runtime(
        store=runtime.store,
        event_store=runtime.event_store,
        agent_runtime=AgentRuntime(
            model=TestModel(call_tools=["workspace.write_file"], custom_output_text="done")
        ),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )

    resumed = await restarted_runtime.runner.resume_run(
        run.id,
        approval_id=approval.id,
        decision="approved",
        comment="ok",
    )
    written = await restarted_runtime.store.read_workspace_file(run.workspace_id, "/a")
    events = await restarted_runtime.event_store.list_by_run(run.id)

    assert resumed.status == AgentRunStatus.COMPLETED
    assert written.content == "a"
    assert next(event for event in events if event.type == "message.completed").payload["content"] == "done"


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_loads_skill_memory_entries() -> None:
    agent_runtime = RecordingInstructionsAgentRuntime()
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="memory-skill",
        name="Memory Skill",
        instructions="Use memory.",
        allowed_tools=[],
        allowed_subagents=[],
        memory_policy=AgentMemoryPolicy(read=True, scopes=["user"]),
        version="0.1.0",
        status="published",
    )
    runtime = _runtime(
        agent_runtime=agent_runtime,
        skill_resolver=InMemorySkillResolver([skill]),
    )
    await runtime.store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="preference.language",
        value="Prefers Chinese summaries.",
    )

    await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Use memory.",
        scopes=["*"],
        skill_id="memory-skill",
    )

    assert agent_runtime.seen_memory_entries is not None
    assert [entry.key for entry in agent_runtime.seen_memory_entries] == ["preference.language"]


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_loads_workspace_file_summary() -> None:
    agent_runtime = RecordingInstructionsAgentRuntime()
    runtime = _runtime(agent_runtime=agent_runtime)
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Use workspace files.",
        scopes=["*"],
    )
    await runtime.store.write_workspace_file(
        workspace_id=run.workspace_id,
        path="/data/notes.md",
        content="# Notes",
        media_type="text/markdown",
    )

    await runtime.runner.execute_run(run.id)

    assert agent_runtime.seen_workspace_files is not None
    assert [file.path for file in agent_runtime.seen_workspace_files] == ["/data/notes.md"]


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_respects_workspace_read_policy_for_file_summary() -> None:
    agent_runtime = RecordingInstructionsAgentRuntime()
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="no-workspace",
        name="No Workspace",
        instructions="Do not inspect files.",
        allowed_tools=[],
        allowed_subagents=[],
        workspace_policy=AgentWorkspacePolicy(read=False),
        version="0.1.0",
        status="published",
    )
    runtime = _runtime(
        agent_runtime=agent_runtime,
        skill_resolver=InMemorySkillResolver([skill]),
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Do not use workspace files.",
        scopes=["*"],
        skill_id="no-workspace",
    )
    await runtime.store.write_workspace_file(
        workspace_id=run.workspace_id,
        path="/data/private.md",
        content="# Private",
        media_type="text/markdown",
    )

    await runtime.runner.execute_run(run.id)

    assert agent_runtime.seen_workspace_files == []


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_loads_thread_message_summary() -> None:
    agent_runtime = RecordingInstructionsAgentRuntime()
    runtime = _runtime(agent_runtime=agent_runtime)
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Planning",
    )
    await runtime.store.append_message(
        thread_id=thread.id,
        role="user",
        content="Remember that reports should be concise.",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Write a concise report draft.",
        scopes=["*"],
        thread_id=thread.id,
    )

    await runtime.runner.execute_run(run.id)

    assert agent_runtime.seen_thread_messages is not None
    assert [message.content for message in agent_runtime.seen_thread_messages] == [
        "Remember that reports should be concise."
    ]


@pytest.mark.asyncio
async def test_pydantic_ai_runtime_injects_context_packet_and_emits_debug_event() -> None:
    agent_runtime = RecordingInstructionsAgentRuntime()
    runtime = _runtime(agent_runtime=agent_runtime)
    thread = await runtime.store.create_thread(
        org_id="org_1",
        owner_user_id="user_1",
        title="Research",
    )
    await runtime.store.append_message(
        thread_id=thread.id,
        role="user",
        content="Use APAC as the scope.",
    )
    run = await runtime.runner.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Continue the APAC report draft.",
        scopes=["*"],
        thread_id=thread.id,
    )
    await runtime.store.create_memory_entry(
        org_id=run.org_id,
        scope="user",
        scope_id=run.actor_user_id,
        key="preference.language",
        value="Prefers Chinese summaries.",
    )
    await runtime.store.create_todo(
        run_id=run.id,
        title="Search sources",
        status="done",
    )
    await runtime.store.create_artifact(
        org_id=run.org_id,
        workspace_id=run.workspace_id,
        run_id=run.id,
        type="report",
        name="Draft Report",
        uri="/reports/draft.md",
        media_type="text/markdown",
        content="# Draft\nEvidence collected.",
    )

    await runtime.runner.execute_run(run.id)
    events = await runtime.event_store.list_by_run(run.id)
    packet_event = next(event for event in events if event.type == "context.packet.built")

    assert packet_event.visibility == "debug"
    assert packet_event.payload["thread_messages"] == 1
    assert packet_event.payload["todos"] == 1
    assert packet_event.payload["artifacts"] == 1
    assert packet_event.payload["tool_results"] == 0
    assert packet_event.payload["memory"] == 1
    assert packet_event.payload["has_truncated_content"] is False
    assert packet_event.payload["has_dropped_context"] is False
    assert packet_event.payload["budget"]["max_chars"] == 6_000
    assert packet_event.payload["budget"]["used_chars"] > 0
    assert packet_event.payload["budget"]["dropped_thread_messages"] == 0
    assert packet_event.payload["budget"]["dropped_todos"] == 0
    assert packet_event.payload["budget"]["dropped_artifacts"] == 0
    assert packet_event.payload["budget"]["dropped_tool_results"] == 0
    assert packet_event.payload["budget"]["dropped_memory"] == 0
    assert agent_runtime.seen_instructions is not None
    assert "Run context packet:" in agent_runtime.seen_instructions
    assert "Relevant memory:" in agent_runtime.seen_instructions
    assert "user:preference.language = Prefers Chinese summaries." in agent_runtime.seen_instructions
    assert "Context budget:" in agent_runtime.seen_instructions
    assert "- user: Use APAC as the scope." in agent_runtime.seen_instructions
    assert "- [done] Search sources" in agent_runtime.seen_instructions
    assert "- report Draft Report (/reports/draft.md): # Draft\nEvidence collected." in agent_runtime.seen_instructions
