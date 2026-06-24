import asyncio

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings
from aithru_agent.trace import project_trace_spans


class ToolContext:
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = False


class DeepResearchDemoRuntime(AgentRuntime):
    async def run(self, goal: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del goal
        bridge = PydanticAIToolBridge(deps=deps)
        await deps.event_writer.write(
            run_id=deps.run.id,
            thread_id=deps.run.thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": "msg_1", "role": "assistant"},
        )
        await bridge.call_tool(
            ToolContext("research_plan"),
            "research.create_plan",
            {
                "query": "aithru deerflow parity",
                "objective": "Check backend parity for controlled research work.",
            },
        )
        await bridge.call_tool(
            ToolContext("research_report"),
            "research.create_report",
            {
                "title": "Aithru Deep Research",
                "query": "aithru deerflow parity",
                "summary": "Aithru Agent can plan research and create cited report artifacts.",
                "sources": [
                    {
                        "title": "Aithru Agent Harness",
                        "url": "https://example.com/aithru-agent",
                        "snippet": (
                            "Aithru Agent routes real actions through controlled "
                            "capabilities and records traceable artifacts."
                        ),
                        "source": "example",
                    }
                ],
            },
        )
        return AgentRuntimeResult(content="Created research report.")


async def main() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=DeepResearchDemoRuntime(),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Research Aithru Agent backend parity.",
        scopes=["*"],
        skill_id="deep-research",
    )
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)
    todos = await runtime.store.list_todos(run.id)
    artifacts = await runtime.store.list_artifacts(run_id=run.id)
    report_artifact = artifacts[0] if artifacts else None

    print(f"Run id: {run.id}")
    print(f"Run status: {run.status.value}")
    print(f"Todos: {len(todos)}")
    if report_artifact is not None:
        print(f"Report artifact: {report_artifact.name} ({report_artifact.uri})")
    else:
        print("Report artifact: <none>")
    print(f"Events: {len(events)}")
    print(f"Trace span kinds: {', '.join(sorted({span.kind for span in spans}))}")


if __name__ == "__main__":
    asyncio.run(main())
