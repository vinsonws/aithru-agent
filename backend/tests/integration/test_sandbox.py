import pytest

from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentRunStatus
from tests.utils.step_runtime import Step, StepAgentRuntime
from aithru_agent.trace import project_trace_spans


@pytest.mark.asyncio
async def test_sandbox_run_python_emits_events_and_trace() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {
                        "code": "print('rows', len(input_data['rows']))\nresult = sum(input_data['rows'])",
                        "input": {"rows": [1, 2, 3]},
                        "timeout_ms": 1000,
                    },
                ),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Process numbers",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    event_types = [event.type for event in events]
    tool_completed = next(event for event in events if event.type == "tool.completed")
    spans = project_trace_spans(events)
    sandbox_span = next(span for span in spans if span.kind == "sandbox")

    assert run.status == AgentRunStatus.COMPLETED
    assert event_types.index("sandbox.started") < event_types.index("sandbox.stdout")
    assert event_types.index("sandbox.stdout") < event_types.index("sandbox.completed")
    assert event_types.index("sandbox.completed") < event_types.index("tool.completed")
    assert tool_completed.payload["output"]["result"] == 6
    assert tool_completed.payload["output"]["stdout"] == "rows 3\n"
    assert sandbox_span.status == "completed"
    assert sandbox_span.refs == {"language": "python"}


@pytest.mark.asyncio
async def test_sandbox_run_python_rejects_imports() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {"code": "import os\nresult = os.listdir('/')"},
                ),
                Step.finish(),
            ]
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Try unsafe code",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    sandbox_failed = next(event for event in events if event.type == "sandbox.failed")
    spans = project_trace_spans(events)
    sandbox_span = next(span for span in spans if span.kind == "sandbox")

    assert run.status == AgentRunStatus.FAILED
    assert "import statements are not allowed" in sandbox_failed.payload["error"]["message"]
    assert sandbox_span.status == "failed"
