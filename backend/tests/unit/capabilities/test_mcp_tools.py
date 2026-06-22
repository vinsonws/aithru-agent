import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from pydantic import ValidationError

from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ExternalToolAdapter, ToolPolicy
from aithru_agent.capabilities.mcp import (
    MCPServerSpec,
    MCPToolExecutor,
    MCPToolInvocation,
    MCPToolProvider,
    MCPToolResult,
    MCPToolSpec,
)
from aithru_agent.capabilities.mcp_http import ControlledHTTPMCPToolExecutor
from aithru_agent.domain import AgentToolCallRequest


class MCPHTTPHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        self.__class__.requests.append({"path": self.path, "payload": payload})
        body = json.dumps(
            {
                "status": "completed",
                "output": {
                    "received_tool": payload["tool_name"],
                    "received_query": payload["input"]["query"],
                    "received_run_id": payload["run_id"],
                },
                "redaction": "partial",
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def mcp_http_endpoint() -> str:
    MCPHTTPHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHTTPHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class FakeMCPExecutor:
    def __init__(self) -> None:
        self.invocations: list[MCPToolInvocation] = []

    async def execute(self, invocation: MCPToolInvocation) -> MCPToolResult:
        self.invocations.append(invocation)
        return MCPToolResult(
            status="completed",
            output={
                "server": invocation.server_key,
                "tool": invocation.tool_name,
                "query": invocation.input["query"],
                "run_id": invocation.run_id,
            },
            redaction="partial",
        )


def mcp_server() -> MCPServerSpec:
    return MCPServerSpec(
        key="search",
        name="Search Tools",
        tools=[
            MCPToolSpec(
                name="query",
                description="Search an indexed corpus.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                output_schema={"type": "object"},
                risk_level="read",
                approval_policy="never",
            )
        ],
    )


def test_mcp_server_spec_is_pydantic_validated_catalog() -> None:
    server = mcp_server()

    assert server.model_dump(mode="json") == {
        "key": "search",
        "name": "Search Tools",
        "enabled": True,
        "tools": [
            {
                "name": "query",
                "description": "Search an indexed corpus.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "output_schema": {"type": "object"},
                "risk_level": "read",
                "required_scopes": None,
                "approval_policy": "never",
                "metadata": None,
            }
        ],
        "metadata": None,
    }


@pytest.mark.parametrize(
    "value",
    [
        {"key": " ", "tools": []},
        {"key": "bad key", "tools": []},
        {"key": "search", "tools": [{"name": "bad tool", "description": "x"}]},
        {"key": "search", "tools": [{"name": "query", "description": "x", "input_schema": {"type": "array"}}]},
        {"key": "search", "tools": [{"name": "query", "description": "x", "required_scopes": [" "]}]},
    ],
)
def test_mcp_server_spec_rejects_invalid_catalog_values(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MCPServerSpec.model_validate(value)


def test_mcp_tool_provider_maps_catalog_to_external_tool_specs() -> None:
    provider = MCPToolProvider(servers=[mcp_server()], executor=FakeMCPExecutor())

    specs = provider.list_tools()

    assert specs[0].name == "mcp.search.query"
    assert specs[0].provider == "mcp:search"
    assert specs[0].required_scopes == ["agent.external.mcp.search.query"]
    assert specs[0].metadata == {"server_key": "search", "tool_name": "query"}


@pytest.mark.asyncio
async def test_mcp_tool_provider_executes_through_injected_executor() -> None:
    executor = FakeMCPExecutor()
    provider = MCPToolProvider(servers=[mcp_server()], executor=executor)

    result = await provider.execute(
        invocation=provider.external_invocation(
            tool_call_id="toolcall_1",
            external_tool_name="mcp.search.query",
            input={"query": "aithru"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
            thread_id="thread_1",
            skill_id="skill_1",
        )
    )

    assert result.status == "completed"
    assert result.output == {
        "server": "search",
        "tool": "query",
        "query": "aithru",
        "run_id": "run_1",
    }
    assert result.redaction == "partial"
    assert executor.invocations == [
        MCPToolInvocation(
            tool_call_id="toolcall_1",
            external_tool_name="mcp.search.query",
            server_key="search",
            tool_name="query",
            input={"query": "aithru"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
            thread_id="thread_1",
            skill_id="skill_1",
        )
    ]


@pytest.mark.asyncio
async def test_controlled_http_mcp_executor_posts_invocation_to_allowlisted_endpoint(
    mcp_http_endpoint: str,
) -> None:
    executor = ControlledHTTPMCPToolExecutor(
        allowed_hosts=["127.0.0.1"],
        server_endpoints={"search": mcp_http_endpoint},
        timeout_ms=1_000,
        max_response_bytes=100_000,
    )
    invocation = MCPToolInvocation(
        tool_call_id="toolcall_1",
        external_tool_name="mcp.search.query",
        server_key="search",
        tool_name="query",
        input={"query": "aithru"},
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        thread_id="thread_1",
        skill_id="skill_1",
    )

    result = await executor.execute(invocation)

    assert result.status == "completed"
    assert result.output == {
        "received_tool": "query",
        "received_query": "aithru",
        "received_run_id": "run_1",
    }
    assert result.redaction == "partial"
    assert MCPHTTPHandler.requests == [
        {
            "path": "/mcp",
            "payload": invocation.model_dump(mode="json"),
        }
    ]


@pytest.mark.asyncio
async def test_mcp_tool_provider_denies_unknown_tool() -> None:
    provider = MCPToolProvider(servers=[mcp_server()], executor=FakeMCPExecutor())

    result = await provider.execute(
        invocation=provider.external_invocation(
            tool_call_id="toolcall_1",
            external_tool_name="mcp.search.missing",
            input={"query": "aithru"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
        )
    )

    assert result.status == "denied"
    assert result.error == {"message": "Unknown MCP-like tool: mcp.search.missing"}


@pytest.mark.asyncio
async def test_mcp_provider_tools_remain_scope_skill_and_approval_controlled() -> None:
    provider = MCPToolProvider(servers=[mcp_server()], executor=FakeMCPExecutor())
    adapter = ExternalToolAdapter(provider)
    router = AithruCapabilityRouter(adapters=[adapter])
    approval_router = AithruCapabilityRouter(
        adapters=[adapter],
        policy=ToolPolicy(require_approval_for_risk=["read"]),
    )
    base_context = AgentRunContext(
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        scopes=[],
    )
    scoped_context = base_context.model_copy(
        update={"scopes": ["agent.external.mcp.search.query"]}
    )
    skill_context = scoped_context.model_copy(
        update={"allowed_tools": ["mcp.search.query"]}
    )
    denied_by_skill = scoped_context.model_copy(
        update={"allowed_tools": ["workspace.read_file"]}
    )

    assert await router.list_tools(base_context) == []
    assert await router.list_tools(denied_by_skill) == []
    assert [tool.name for tool in await router.list_tools(skill_context)] == ["mcp.search.query"]
    prepared = await approval_router.prepare_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="mcp.search.query",
            input={"query": "aithru"},
            requested_by="model",
        ),
        skill_context,
    )

    assert prepared.status == "waiting_approval"
