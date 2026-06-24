import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings
from aithru_agent.trace import project_trace_spans


class ControlledResearchHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/search"):
            query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
            body = json.dumps(
                {
                    "results": [
                        {
                            "title": f"Local Aithru evidence for {query}",
                            "url": f"http://{self.headers['Host']}/evidence.txt",
                            "snippet": "Search result from the controlled local provider.",
                            "source": "local-controlled-search",
                            "published_at": "2026-06-18",
                        }
                    ]
                }
            ).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if self.path == "/evidence.txt":
            self._send(
                200,
                b"Controlled fetch evidence from Aithru local HTTP provider.",
                "text/plain; charset=utf-8",
            )
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes, media_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ToolContext:
    def __init__(self, tool_call_id: str) -> None:
        self.tool_call_id = tool_call_id
        self.run_step = 0
        self.tool_call_approved = False


class ControlledWebResearchRuntime(AgentRuntime):
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
                "query": "aithru controlled web research",
                "objective": "Use controlled search and fetch before report creation.",
            },
        )
        search = await bridge.call_tool(
            ToolContext("web_search"),
            "web.search",
            {"query": "aithru controlled web research", "max_results": 1},
        )
        search_result = search["results"][0]
        fetched = await bridge.call_tool(
            ToolContext("web_fetch"),
            "web.fetch",
            {"url": search_result["url"], "max_bytes": 10_000},
        )
        await bridge.call_tool(
            ToolContext("research_report"),
            "research.create_report",
            {
                "title": "Aithru Controlled Web Research",
                "query": "aithru controlled web research",
                "summary": "Controlled web tools supplied evidence for the report.",
                "sources": [
                    {
                        "title": search_result["title"],
                        "url": search_result["url"],
                        "snippet": search_result["snippet"],
                        "content": fetched["content"],
                        "source": search_result["source"],
                        "published_at": search_result["published_at"],
                    }
                ],
            },
        )
        return AgentRuntimeResult(content="Created controlled-web research report.")


async def run_demo(base_url: str) -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={
                "web_enabled": True,
                "web_executor": "http",
                "web_search_executor": "http_json",
                "web_search_endpoint_url": f"{base_url}/search",
                "web_allowed_hosts": ["127.0.0.1"],
            },
        ),
        agent_runtime=ControlledWebResearchRuntime(),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Research with controlled web tools.",
        scopes=["*"],
        skill_id="deep-research",
    )
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)
    todos = await runtime.store.list_todos(run.id)
    artifacts = await runtime.store.list_artifacts(run_id=run.id)
    report_artifact = artifacts[0] if artifacts else None
    web_events = sorted({event.type for event in events if event.type.startswith("web.")})
    done_todos = sum(1 for todo in todos if todo.status.value == "done")

    print(f"Run id: {run.id}")
    print(f"Run status: {run.status.value}")
    print(f"Todos: {len(todos)}")
    print(f"Todos done: {done_todos}")
    evidence_count = (
        report_artifact.metadata.get("evidence_count")
        if report_artifact is not None and report_artifact.metadata is not None
        else 0
    )
    quality_summary = (
        report_artifact.metadata.get("quality_summary")
        if report_artifact is not None and report_artifact.metadata is not None
        else None
    )
    print(f"Evidence rows: {evidence_count}")
    if isinstance(quality_summary, dict):
        print(
            "Quality summary: "
            f"high={quality_summary.get('high', 0)} "
            f"medium={quality_summary.get('medium', 0)} "
            f"low={quality_summary.get('low', 0)}"
        )
    print(f"Web events: {', '.join(web_events)}")
    if report_artifact is not None:
        print(f"Report artifact: {report_artifact.name} ({report_artifact.uri})")
    else:
        print("Report artifact: <none>")
    print(f"Events: {len(events)}")
    print(f"Trace span kinds: {', '.join(sorted({span.kind for span in spans}))}")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledResearchHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        asyncio.run(run_demo(f"http://127.0.0.1:{server.server_port}"))
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
