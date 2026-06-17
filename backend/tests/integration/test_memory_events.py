import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from tests.utils.step_runtime import Step, StepAgentRuntime
from aithru_agent.trace import project_trace_spans


@pytest.mark.asyncio
async def test_memory_tools_emit_events_and_trace() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "memory.remember",
                    {
                        "scope": "user",
                        "key": "preference.language",
                        "value": "Chinese",
                    },
                ),
                Step.tool("memory.search", {"query": "Chinese"}),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Remember and search memory.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    spans = project_trace_spans(events)

    assert run.status == AgentRunStatus.COMPLETED
    assert "memory.written" in event_types
    assert "memory.read" in event_types
    assert {span.kind for span in spans} >= {"memory"}
