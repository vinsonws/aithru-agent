import pytest
from pydantic_ai.models.test import TestModel

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ToolPolicy
from aithru_agent.domain import (
    AgentMemoryEntry,
    AgentMemoryPolicy,
    AgentMessage,
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
from aithru_agent.harness.drivers.pydantic_ai.driver import PydanticAIHarnessDriver
from aithru_agent.persistence.memory.store import InMemoryAgentStore
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


class RecordingInstructionsPydanticDriver(PydanticAIHarnessDriver):
    def __init__(self) -> None:
        super().__init__(model=TestModel(custom_output_text="done"))
        self.seen_memory_entries: list[AgentMemoryEntry] | None = None
        self.seen_thread_messages: list[AgentMessage] | None = None
        self.seen_workspace_files: list[AgentWorkspaceFile] | None = None

    def instructions_for_run(
        self,
        skill: AgentSkill | None = None,
        *,
        memory_entries: list[AgentMemoryEntry] | None = None,
        thread_messages: list[AgentMessage] | None = None,
        workspace_files: list[AgentWorkspaceFile] | None = None,
    ) -> str:
        self.seen_memory_entries = memory_entries
        self.seen_thread_messages = thread_messages
        self.seen_workspace_files = workspace_files
        return super().instructions_for_run(
            skill,
            memory_entries=memory_entries,
            thread_messages=thread_messages,
            workspace_files=workspace_files,
        )


@pytest.mark.asyncio
async def test_pydantic_ai_driver_streams_text_steps_from_test_model() -> None:
    driver = PydanticAIHarnessDriver(model=TestModel(custom_output_text="done"))

    steps = await driver.run("Say done")

    assert [step.type for step in steps] == ["message", "message", "finish"]
    assert "".join(step.text or "" for step in steps) == "done"


@pytest.mark.asyncio
async def test_pydantic_ai_driver_routes_model_tool_calls_through_aithru_bridge() -> None:
    runtime = create_agent_runtime(
        driver=PydanticAIHarnessDriver(
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
async def test_pydantic_ai_driver_exposes_descriptor_input_schema_to_model() -> None:
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
        driver=PydanticAIHarnessDriver(
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
async def test_pydantic_ai_driver_fails_run_when_tool_execution_fails() -> None:
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
        driver=PydanticAIHarnessDriver(
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
async def test_pydantic_ai_driver_pauses_when_tool_requires_approval() -> None:
    runtime = create_agent_runtime(
        driver=PydanticAIHarnessDriver(
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
async def test_pydantic_ai_driver_loads_skill_memory_entries() -> None:
    driver = RecordingInstructionsPydanticDriver()
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
    runtime = create_agent_runtime(
        driver=driver,
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

    assert driver.seen_memory_entries is not None
    assert [entry.key for entry in driver.seen_memory_entries] == ["preference.language"]


@pytest.mark.asyncio
async def test_pydantic_ai_driver_loads_workspace_file_summary() -> None:
    driver = RecordingInstructionsPydanticDriver()
    runtime = create_agent_runtime(driver=driver)
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

    assert driver.seen_workspace_files is not None
    assert [file.path for file in driver.seen_workspace_files] == ["/data/notes.md"]


@pytest.mark.asyncio
async def test_pydantic_ai_driver_respects_workspace_read_policy_for_file_summary() -> None:
    driver = RecordingInstructionsPydanticDriver()
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
    runtime = create_agent_runtime(
        driver=driver,
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

    assert driver.seen_workspace_files == []


@pytest.mark.asyncio
async def test_pydantic_ai_driver_loads_thread_message_summary() -> None:
    driver = RecordingInstructionsPydanticDriver()
    runtime = create_agent_runtime(driver=driver)
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
        goal="Write a report.",
        scopes=["*"],
        thread_id=thread.id,
    )

    await runtime.runner.execute_run(run.id)

    assert driver.seen_thread_messages is not None
    assert [message.content for message in driver.seen_thread_messages] == [
        "Remember that reports should be concise."
    ]
