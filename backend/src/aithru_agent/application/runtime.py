from dataclasses import dataclass

from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime as NativeAgentRuntime
from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    MemoryLocalTool,
    SandboxLocalTool,
    SubagentLocalTool,
    TodoLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.settings import AgentSettings
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker import AgentWorkerRunner, AgentWorkerService, InProcessRunQueue


@dataclass
class AgentApplication:
    settings: AgentSettings
    store: AgentStore
    event_store: AgentEventStore
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    runner: AgentWorkerRunner
    run_queue: InProcessRunQueue
    worker: AgentWorkerService
    skill_resolver: AgentSkillResolver
    agent_runtime: NativeAgentRuntime


AgentRuntime = AgentApplication


def create_agent_application(
    *,
    store: AgentStore | None = None,
    event_store: AgentEventStore | None = None,
    agent_runtime: NativeAgentRuntime | None = None,
    policy: ToolPolicy | None = None,
    settings: AgentSettings | None = None,
    skill_resolver: AgentSkillResolver | None = None,
) -> AgentApplication:
    resolved_settings = settings or AgentSettings.from_env()
    resolved_store = store or _create_store(resolved_settings)
    resolved_event_store = event_store or _create_event_store(resolved_settings)
    event_writer = AgentEventWriter(resolved_event_store)
    resolved_skill_resolver = skill_resolver or EmptySkillResolver()
    subagent_tool = SubagentLocalTool(resolved_store, event_writer, resolved_skill_resolver)
    capability_router = AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(resolved_store),
            TodoLocalTool(resolved_store),
            ArtifactLocalTool(resolved_store),
            MemoryLocalTool(resolved_store),
            subagent_tool,
            SandboxLocalTool(event_writer),
        ],
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )
    resolved_agent_runtime = agent_runtime or _create_native_agent_runtime(resolved_settings)
    runner = AgentWorkerRunner(
        store=resolved_store,
        event_writer=event_writer,
        capability_router=capability_router,
        agent_runtime=resolved_agent_runtime,
        skill_resolver=resolved_skill_resolver,
    )
    subagent_tool.set_task_runner(runner.execute_child_run_for_task)
    run_queue = InProcessRunQueue()
    worker = AgentWorkerService(runner=runner, queue=run_queue)
    return AgentApplication(
        settings=resolved_settings,
        store=resolved_store,
        event_store=resolved_event_store,
        event_writer=event_writer,
        capability_router=capability_router,
        runner=runner,
        run_queue=run_queue,
        worker=worker,
        skill_resolver=resolved_skill_resolver,
        agent_runtime=resolved_agent_runtime,
    )


create_agent_runtime = create_agent_application


def _create_native_agent_runtime(settings: AgentSettings) -> NativeAgentRuntime:
    if settings.model == "test":
        model: object | str = TestModel(
            call_tools=[],
            custom_output_text=settings.test_model_output,
        )
    elif settings.model:
        model = settings.model
    else:
        raise ValueError(
            "AITHRU_AGENT_MODEL is required for the Pydantic AI runtime. "
            "Use AITHRU_AGENT_MODEL=test only for tests or local deterministic development."
        )

    return NativeAgentRuntime(
        model=model,
        model_factory=lambda model_name: (
            TestModel(call_tools=[], custom_output_text=settings.test_model_output)
            if model_name == "test"
            else model_name
        ),
        instructions=settings.instructions,
    )


def _create_store(settings: AgentSettings) -> AgentStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentStore(settings.sqlite_path)
    return InMemoryAgentStore()


def _create_event_store(settings: AgentSettings) -> AgentEventStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentEventStore(settings.sqlite_path)
    return InMemoryAgentEventStore()
