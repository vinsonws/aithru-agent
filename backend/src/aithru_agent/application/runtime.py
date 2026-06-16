from dataclasses import dataclass

from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.harness import AgentHarnessDriver
from aithru_agent.harness.drivers.pydantic_ai import PydanticAIHarnessDriver
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
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
    driver: AgentHarnessDriver | None = None,
    policy: ToolPolicy | None = None,
    settings: AgentSettings | None = None,
    skill_resolver: AgentSkillResolver | None = None,
) -> AgentRuntime:
    resolved_settings = settings or AgentSettings.from_env()
    store = InMemoryAgentStore()
    event_store = InMemoryAgentEventStore()
    event_writer = AgentEventWriter(event_store)
    capability_router = AithruCapabilityRouter(
        adapters=[
            WorkspaceLocalTool(store),
            TodoLocalTool(store),
            ArtifactLocalTool(store),
        ],
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )
    resolved_skill_resolver = skill_resolver or EmptySkillResolver()
    runner = AgentWorkerRunner(
        store=store,
        event_writer=event_writer,
        capability_router=capability_router,
        driver=driver or _create_driver(resolved_settings),
        skill_resolver=resolved_skill_resolver,
    )
    run_queue = InProcessRunQueue()
    worker = AgentWorkerService(runner=runner, queue=run_queue)
    return AgentRuntime(
        store=store,
        event_store=event_store,
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
