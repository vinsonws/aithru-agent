from dataclasses import dataclass

from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    MemoryLocalTool,
    TodoLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.harness import AgentHarnessDriver
from aithru_agent.harness.drivers.pydantic_ai import PydanticAIHarnessDriver
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.settings import AgentSettings
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker import AgentWorkerRunner, AgentWorkerService, InProcessRunQueue


@dataclass
class AgentRuntime:
    store: AgentStore
    event_store: AgentEventStore
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    runner: AgentWorkerRunner
    run_queue: InProcessRunQueue
    worker: AgentWorkerService
    skill_resolver: AgentSkillResolver


def create_agent_runtime(
    *,
    store: AgentStore | None = None,
    event_store: AgentEventStore | None = None,
    driver: AgentHarnessDriver | None = None,
    policy: ToolPolicy | None = None,
    settings: AgentSettings | None = None,
    skill_resolver: AgentSkillResolver | None = None,
) -> AgentRuntime:
    resolved_settings = settings or AgentSettings.from_env()
    resolved_store = store or _create_store(resolved_settings)
    resolved_event_store = event_store or _create_event_store(resolved_settings)
    event_writer = AgentEventWriter(resolved_event_store)
    capability_router = AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(resolved_store),
            TodoLocalTool(resolved_store),
            ArtifactLocalTool(resolved_store),
            MemoryLocalTool(resolved_store),
        ],
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )
    resolved_skill_resolver = skill_resolver or EmptySkillResolver()
    runner = AgentWorkerRunner(
        store=resolved_store,
        event_writer=event_writer,
        capability_router=capability_router,
        driver=driver or _create_driver(resolved_settings),
        skill_resolver=resolved_skill_resolver,
    )
    run_queue = InProcessRunQueue()
    worker = AgentWorkerService(runner=runner, queue=run_queue)
    return AgentRuntime(
        store=resolved_store,
        event_store=resolved_event_store,
        event_writer=event_writer,
        capability_router=capability_router,
        runner=runner,
        run_queue=run_queue,
        worker=worker,
        skill_resolver=resolved_skill_resolver,
    )


def _create_driver(settings: AgentSettings) -> AgentHarnessDriver:
    if settings.driver == "pydantic_ai":
        model: object | str | None
        if settings.model == "test":
            from pydantic_ai.models.test import TestModel

            model = TestModel(call_tools=[], custom_output_text=settings.test_model_output)
        else:
            model = settings.model
        return PydanticAIHarnessDriver(model=model, instructions=settings.instructions)
    return ScriptedHarnessDriver([])


def _create_store(settings: AgentSettings) -> AgentStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentStore(settings.sqlite_path)
    return InMemoryAgentStore()


def _create_event_store(settings: AgentSettings) -> AgentEventStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentEventStore(settings.sqlite_path)
    return InMemoryAgentEventStore()
