import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings
from aithru_agent.trace import project_trace_spans


class ControlledResearchHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/search"):
            query = self._query_value()
            evidence_url = f"http://{self.headers['Host']}/evidence.txt"
            body = json.dumps(
                {
                    "results": [
                        {
                            "title": f"Local Aithru evidence for {query}",
                            "url": evidence_url,
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

    def _query_value(self) -> str:
        from urllib.parse import parse_qs, urlsplit

        return parse_qs(urlsplit(self.path).query).get("q", [""])[0]

    def _send(self, status: int, body: bytes, media_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def controlled_web_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledResearchHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


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


class RecoverableWebFailureResearchRuntime(AgentRuntime):
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
                "query": "aithru recoverable web failure",
                "objective": "Continue to a degraded report when search fails.",
            },
        )
        search = await bridge.call_tool(
            ToolContext("web_search"),
            "web.search",
            {"query": "aithru recoverable web failure", "max_results": 1},
        )
        assert search["status"] == "failed"
        assert search["recoverable"] is True
        await bridge.call_tool(
            ToolContext("research_report"),
            "research.create_report",
            {
                "title": "Aithru Recoverable Web Failure",
                "query": "aithru recoverable web failure",
            },
        )
        return AgentRuntimeResult(content="Created degraded research report.")


@pytest.mark.asyncio
async def test_deep_research_uses_controlled_web_search_fetch_and_report(
    controlled_web_server: str,
) -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={
                "web_enabled": True,
                "web_executor": "http",
                "web_search_executor": "http_json",
                "web_search_endpoint_url": f"{controlled_web_server}/search",
                "web_allowed_hosts": ["127.0.0.1"],
            },
        ),
        agent_runtime=ControlledWebResearchRuntime(),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Research with controlled web tools.",
        scopes=["*"],
        skill_id="deep-research",
    )
    artifacts = await runtime.store.list_artifacts(run_id=run.id)
    todos = await runtime.store.list_todos(run.id)
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)

    assert run.status.value == "completed"
    assert len(artifacts) == 1
    assert artifacts[0].name == "Aithru Controlled Web Research"
    assert artifacts[0].metadata["evidence_count"] == 1
    assert artifacts[0].metadata["source_input_count"] == 1
    assert artifacts[0].metadata["duplicate_source_count"] == 0
    assert artifacts[0].metadata["quality_summary"] == {"high": 1, "medium": 0, "low": 0}
    assert "Controlled fetch evidence from Aithru local HTTP provider." in str(
        artifacts[0].content
    )
    assert "| # | Source | Quality | Evidence |" in str(artifacts[0].content)
    assert "| 1 | [Local Aithru evidence for aithru controlled web research]" in str(
        artifacts[0].content
    )
    assert "| high |" in str(artifacts[0].content)
    assert "web.search.completed" in [event.type for event in events]
    assert "web.fetch.completed" in [event.type for event in events]
    assert {todo.title: todo.status.value for todo in todos} == {
        "Search sources": "done",
        "Fetch and review sources": "done",
        "Synthesize findings": "done",
        "Create research report": "done",
    }
    assert sum(event.type == "todo.updated" for event in events) == 4
    assert {span.kind for span in spans} >= {
        "run",
        "model",
        "tool",
        "todo",
        "web",
        "artifact",
    }
    assert {span.name for span in spans if span.kind == "web"} == {"web.search", "web.fetch"}


@pytest.mark.asyncio
async def test_deep_research_can_continue_after_recoverable_web_failure() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={"web_enabled": True},
        ),
        agent_runtime=RecoverableWebFailureResearchRuntime(),
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        goal="Research with recoverable web failure.",
        scopes=["*"],
        skill_id="deep-research",
    )
    artifacts = await runtime.store.list_artifacts(run_id=run.id)
    todos = await runtime.store.list_todos(run.id)
    events = await runtime.event_store.list_by_run(run.id)
    spans = project_trace_spans(events)

    assert run.status.value == "completed"
    assert len(artifacts) == 1
    assert artifacts[0].metadata["report_status"] == "insufficient_evidence"
    assert artifacts[0].metadata["source_count"] == 0
    assert artifacts[0].metadata["limitation_count"] == 1
    assert "Research source search was blocked before report creation." in str(
        artifacts[0].content
    )
    assert {todo.title: todo.status.value for todo in todos} == {
        "Search sources": "blocked",
        "Fetch and review sources": "pending",
        "Synthesize findings": "done",
        "Create research report": "done",
    }
    assert "web.search.failed" in [event.type for event in events]
    assert events[-1].type == "run.completed"
    assert [span.status for span in spans if span.kind == "web"] == ["failed"]


def test_controlled_web_research_example_script_runs_successfully() -> None:
    backend_root = Path(__file__).parents[2]
    script = backend_root / "examples" / "controlled_web_research_agent.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=backend_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Run status: completed" in completed.stdout
    assert "Todos done: 4" in completed.stdout
    assert "Evidence rows: 1" in completed.stdout
    assert "Quality summary: high=1 medium=0 low=0" in completed.stdout
    assert "Web events: web.fetch.completed, web.search.completed" in completed.stdout
    assert "Report artifact: Aithru Controlled Web Research" in completed.stdout
    assert "Trace span kinds:" in completed.stdout
