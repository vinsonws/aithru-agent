from dataclasses import dataclass

from aithru_agent.capabilities import AithruCapabilityRouter, ToolPolicy
from aithru_agent.capabilities.local_tools import ArtifactLocalTool, TodoLocalTool, WorkspaceLocalTool
from aithru_agent.harness import AgentHarnessDriver
from aithru_agent.harness.drivers.scripted import ScriptedHarnessDriver
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker import AgentWorkerRunner


@dataclass
class AgentRuntime:
    store: InMemoryAgentStore
    event_store: InMemoryAgentEventStore
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    runner: AgentWorkerRunner


def create_agent_runtime(
    *,
    driver: AgentHarnessDriver | None = None,
    policy: ToolPolicy | None = None,
) -> AgentRuntime:
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
    runner = AgentWorkerRunner(
        store=store,
        event_writer=event_writer,
        capability_router=capability_router,
        driver=driver or ScriptedHarnessDriver([]),
    )
    return AgentRuntime(
        store=store,
        event_store=event_store,
        event_writer=event_writer,
        capability_router=capability_router,
        runner=runner,
    )

