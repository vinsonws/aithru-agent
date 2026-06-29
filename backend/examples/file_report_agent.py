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


class FileReportRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg
        bridge = PydanticAIToolBridge(deps=deps)
        await bridge.call_tool(
            ToolContext("todo_read_files"),
            "todo.create",
            {"title": "Read files", "status": "running"},
        )
        await bridge.call_tool(
            ToolContext("write_notes"),
            "workspace.write_file",
            {"path": "/inputs/notes.md", "content": "# Notes\nImportant input.\n"},
        )
        await bridge.call_tool(
            ToolContext("read_notes"),
            "workspace.read_file",
            {"path": "/inputs/notes.md"},
        )
        await bridge.call_tool(
            ToolContext("write_report"),
            "workspace.write_file",
            {"path": "/reports/report.md", "content": "# Report\nImportant input.\n"},
        )
        await bridge.call_tool(
            ToolContext("present_report"),
            "presentation.present",
            {"resources": [{"kind": "workspace_file", "path": "/reports/report.md"}]},
        )
        return AgentRuntimeResult(content="Created /reports/report.md")


async def main() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        agent_runtime=FileReportRuntime(),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Analyze workspace files and create a report.",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)
    files = await runtime.store.list_workspace_files(run.workspace_id)
    report_files = [file for file in files if file.path.startswith("/reports/")]
    report_path = report_files[0].path if report_files else "<none>"
    presentations = [event for event in events if event.type == "presentation.created"]

    print(f"Run id: {run.id}")
    print(f"Run status: {run.status.value}")
    print(f"Report path: {report_path}")
    print(f"Workspace files: {', '.join(file.path for file in files)}")
    print(f"Presentations: {len(presentations)}")
    print(f"Events: {len(events)}")
    print(f"Trace span kinds: {', '.join(sorted({span.kind for span in spans}))}")


if __name__ == "__main__":
    asyncio.run(main())
