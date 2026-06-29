import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from aithru_agent.capabilities import AgentRunContext
from aithru_agent.capabilities.external import ExternalToolInvocation, ExternalToolResult, ExternalToolSpec
from aithru_agent.capabilities.workflow import (
    WorkflowCapabilityInvocation,
    WorkflowCapabilityResult,
    WorkflowCapabilitySpec,
)
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentExternalRunRef, AgentRunStatus, AgentToolCallRequest
from aithru_agent.settings import AgentSettings


class FakeExternalProvider:
    def list_tools(self) -> list[ExternalToolSpec]:
        return [
            ExternalToolSpec(
                name="external.echo",
                description="Echo input.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="read",
                required_scopes=["agent.external.echo"],
                approval_policy="never",
                provider="fake",
            )
        ]

    async def execute(self, invocation: ExternalToolInvocation) -> ExternalToolResult:
        return ExternalToolResult(status="completed", output=invocation.input, redaction="none")


class FakeWorkflowCapabilityProvider:
    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return [
            WorkflowCapabilitySpec(
                key="report_review",
                tool_name="workflow.report_review",
                description="Run report review in Workbench.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="write",
                required_scopes=["workflow.capability.report_review.invoke"],
                approval_policy="never",
            )
        ]

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        return WorkflowCapabilityResult(
            status="completed",
            output={"capability_key": invocation.capability_key, "input": invocation.input},
            redaction="none",
            external_run=AgentExternalRunRef(
                kind="workflow_capability",
                capability_key=invocation.capability_key,
                capability_run_id="caprun_runtime_1",
                status="completed",
                correlation_id=invocation.correlation_id,
            ),
        )


class StaticHandler(BaseHTTPRequestHandler):
    body = b"runtime fetch"
    media_type = "text/plain; charset=utf-8"

    def do_POST(self) -> None:
        if self.path.startswith("/capability-runs"):
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            body = json.dumps(
                {
                    "status": "completed",
                    "output": {
                        "capability_key": payload["capability_key"],
                        "workspace_path": payload["input"]["workspace_path"],
                        "run_id": payload["run_id"],
                    },
                    "redaction": "partial",
                    "external_run": {
                        "kind": "workflow_capability",
                        "capability_key": payload["capability_key"],
                        "capability_run_id": "caprun_runtime_http_1",
                        "status": "completed",
                        "correlation_id": payload["correlation_id"],
                        "approval_id": None,
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/mcp"):
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            body = json.dumps(
                {
                    "status": "completed",
                    "output": {
                        "tool": payload["tool_name"],
                        "query": payload["input"]["query"],
                        "run_id": payload["run_id"],
                    },
                    "redaction": "partial",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/search"):
            query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
            body = json.dumps(
                {
                    "results": [
                        {
                            "title": f"Runtime search for {query}",
                            "url": "https://example.com/runtime-search",
                            "snippet": "Runtime search result.",
                        }
                    ]
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", self.media_type)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def http_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), StaticHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/runtime.txt"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.asyncio
async def test_runtime_uses_configured_pydantic_ai_driver_without_injected_driver() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            driver="pydantic_ai",
            model="test",
            test_model_output="configured",
            instructions="Answer concisely.",
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Return configured output",
        scopes=["*"],
    )
    events = await runtime.event_store.list_by_run(run.id)
    completed_message = next(event for event in events if event.type == "message.completed")

    assert completed_message.payload["content"] == "configured"


def test_runtime_installs_builtin_research_skill_when_no_resolver_is_injected() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))

    skill = runtime.skill_resolver.resolve("deep-research")

    assert skill is not None
    assert skill.id == "skill_deep_research"
    assert "research.create_report" in skill.allowed_tools


@pytest.mark.asyncio
async def test_runtime_resolves_run_model_override_from_settings() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            driver="pydantic_ai",
            model="test",
            test_model_output="run model",
        )
    )

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Return run model output",
        scopes=["*"],
        harness_options={"model": "test"},
    )
    events = await runtime.event_store.list_by_run(run.id)
    completed_message = next(event for event in events if event.type == "message.completed")

    assert completed_message.payload["content"] == "run model"


@pytest.mark.asyncio
async def test_runtime_uses_configured_sqlite_persistence(tmp_path) -> None:
    settings = AgentSettings(
        model="test",
        persistence_backend="sqlite",
        sqlite_path=str(tmp_path / "agent.sqlite"),
    )
    runtime = create_agent_runtime(settings=settings)

    queued = await runtime.worker.submit_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="Persist via settings",
        scopes=["*"],
    )
    await runtime.worker.drain()

    reopened = create_agent_runtime(settings=settings)
    persisted = await reopened.store.get_run(queued.id)
    events = await reopened.event_store.list_by_run(queued.id)

    assert persisted is not None
    assert persisted.status == AgentRunStatus.COMPLETED
    assert [event.type for event in events][-1] == "run.completed"


@pytest.mark.asyncio
async def test_runtime_installs_external_tool_providers_only_when_injected() -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.external.echo"],
    )
    default_runtime = create_agent_runtime(settings=AgentSettings(model="test"))

    injected_runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        external_tool_providers=[FakeExternalProvider()],
    )

    assert [
        tool.name for tool in await default_runtime.capability_router.list_tools(context)
    ].count("external.echo") == 0
    assert [
        tool.name for tool in await injected_runtime.capability_router.list_tools(context)
    ].count("external.echo") == 1


@pytest.mark.asyncio
async def test_runtime_installs_workflow_capabilities_only_when_injected() -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["workflow.capability.report_review.invoke"],
    )
    default_runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    injected_runtime = create_agent_runtime(
        settings=AgentSettings(model="test"),
        workflow_capability_providers=[FakeWorkflowCapabilityProvider()],
    )

    default_tools = [
        tool.name for tool in await default_runtime.capability_router.list_tools(context)
    ]
    injected_tools = [
        tool.name for tool in await injected_runtime.capability_router.list_tools(context)
    ]
    result = await injected_runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="workflow.report_review",
            input={"workspace_path": "/reports/report.md"},
            requested_by="model",
        ),
        context,
    )

    assert "workflow.report_review" not in default_tools
    assert "workflow.report_review" in injected_tools
    assert result.status == "completed"
    assert result.output == {
        "capability_key": "report_review",
            "input": {"workspace_path": "/reports/report.md"},
    }
    assert result.external_run == AgentExternalRunRef(
        kind="workflow_capability",
        capability_key="report_review",
        capability_run_id="caprun_runtime_1",
        status="completed",
        correlation_id="run_1:toolcall_1",
    )


@pytest.mark.asyncio
async def test_runtime_installs_configured_web_tools_only_when_enabled() -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.external.web.search", "agent.external.web.fetch"],
    )
    default_runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    web_runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={"web_enabled": True},
        )
    )

    default_tool_names = [
        tool.name for tool in await default_runtime.capability_router.list_tools(context)
    ]
    web_tool_names = [
        tool.name for tool in await web_runtime.capability_router.list_tools(context)
    ]
    result = await web_runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="web.search",
            input={"query": "aithru"},
            requested_by="model",
        ),
        context,
    )

    assert "web.search" not in default_tool_names
    assert {"web.search", "web.fetch"}.issubset(set(web_tool_names))
    assert result.status == "failed"
    assert result.error == {"message": "Web tool executor is not configured"}


@pytest.mark.asyncio
async def test_runtime_configured_http_web_fetch_executes_through_router(http_server: str) -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.external.web.fetch"],
    )
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={
                "web_enabled": True,
                "web_executor": "http",
                "web_allowed_hosts": ["127.0.0.1"],
            },
        )
    )

    result = await runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="web.fetch",
            input={"url": http_server},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["content"] == "runtime fetch"
    assert result.output["url"] == http_server


@pytest.mark.asyncio
async def test_runtime_configured_http_json_search_executes_through_router(http_server: str) -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.external.web.search"],
    )
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={
                "web_enabled": True,
                "web_search_executor": "http_json",
                "web_search_endpoint_url": http_server.replace("/runtime.txt", "/search"),
                "web_allowed_hosts": ["127.0.0.1"],
            },
        )
    )

    result = await runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="web.search",
            input={"query": "aithru", "max_results": 1},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output["query"] == "aithru"
    assert result.output["results"][0]["title"] == "Runtime search for aithru"


@pytest.mark.asyncio
async def test_runtime_installs_configured_mcp_catalog_with_safe_executor() -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.external.mcp.search.query"],
    )
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={
                "mcp_servers": [
                    {
                        "key": "search",
                        "tools": [
                            {
                                "name": "query",
                                "description": "Search documents.",
                                "risk_level": "read",
                                "approval_policy": "on_risk",
                            }
                        ],
                    }
                ]
            },
        )
    )

    tool_names = [
        tool.name for tool in await runtime.capability_router.list_tools(context)
    ]
    result = await runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="mcp.search.query",
            input={"query": "aithru"},
            requested_by="model",
        ),
        context,
    )

    assert tool_names == ["mcp.search.query"]
    assert result.status == "failed"
    assert result.error == {"message": "MCP-like tool executor is not configured"}


@pytest.mark.asyncio
async def test_runtime_configured_http_json_mcp_executes_through_router(
    http_server: str,
) -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.external.mcp.search.query"],
    )
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            external_tools={
                "mcp_executor": "http_json",
                "mcp_allowed_hosts": ["127.0.0.1"],
                "mcp_servers": [
                    {
                        "key": "search",
                        "metadata": {
                            "endpoint_url": http_server.replace("/runtime.txt", "/mcp")
                        },
                        "tools": [
                            {
                                "name": "query",
                                "description": "Search documents.",
                                "risk_level": "read",
                                "approval_policy": "never",
                            }
                        ],
                    }
                ],
            },
        )
    )

    result = await runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="mcp.search.query",
            input={"query": "aithru"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output == {
        "tool": "query",
        "query": "aithru",
        "run_id": "run_1",
    }
    assert result.redaction == "partial"


@pytest.mark.asyncio
async def test_runtime_configured_http_json_workflow_capability_executes_through_router(
    http_server: str,
) -> None:
    context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["workflow.capability.report_review.invoke"],
    )
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            workflow_capabilities={
                "executor": "http_json",
                "endpoint_url": http_server.replace("/runtime.txt", "/capability-runs"),
                "allowed_hosts": ["127.0.0.1"],
                "capabilities": [
                    {
                        "key": "report_review",
                        "tool_name": "workflow.report_review",
                        "description": "Run report review in Workbench.",
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"},
                        "risk_level": "write",
                        "required_scopes": ["workflow.capability.report_review.invoke"],
                        "approval_policy": "never",
                    }
                ],
            },
        )
    )

    result = await runtime.capability_router.execute_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="workflow.report_review",
            input={"workspace_path": "/reports/report.md"},
            requested_by="model",
        ),
        context,
    )

    assert result.status == "completed"
    assert result.output == {
        "capability_key": "report_review",
        "workspace_path": "/reports/report.md",
        "run_id": "run_1",
    }
    assert result.redaction == "partial"
    assert result.external_run == AgentExternalRunRef(
        kind="workflow_capability",
        capability_key="report_review",
        capability_run_id="caprun_runtime_http_1",
        status="completed",
        correlation_id="run_1:toolcall_1",
    )


@pytest.mark.asyncio
async def test_runtime_installs_workbench_draft_tool_behind_scopes() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    base_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=["agent.workspace.write"],
    )
    scoped_context = base_context.model_copy(
        update={"scopes": ["agent.workspace.write", "agent.workbench.write"]}
    )

    assert "workbench.workflow_draft.create" not in [
        tool.name for tool in await runtime.capability_router.list_tools(base_context)
    ]
    assert "workbench.workflow_draft.create" in [
        tool.name for tool in await runtime.capability_router.list_tools(scoped_context)
    ]
