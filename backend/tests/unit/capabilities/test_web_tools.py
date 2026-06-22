import pytest
from pydantic import ValidationError

from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter, ExternalToolAdapter, ToolPolicy
from aithru_agent.capabilities.web import (
    WebFetchRequest,
    WebFetchResult,
    WebSearchItem,
    WebSearchRequest,
    WebSearchResult,
    WebToolExecutor,
    WebToolInvocation,
    WebToolProvider,
    WebToolResult,
)
from aithru_agent.domain import AgentToolCallRequest


class FakeWebExecutor:
    def __init__(self) -> None:
        self.invocations: list[WebToolInvocation] = []

    async def execute(self, invocation: WebToolInvocation) -> WebToolResult:
        self.invocations.append(invocation)
        if invocation.action == "search":
            request = WebSearchRequest.model_validate(invocation.input)
            return WebToolResult(
                status="completed",
                output=WebSearchResult(
                    query=request.query,
                    results=[
                        WebSearchItem(
                            title="Aithru",
                            url="https://example.com/aithru",
                            snippet="Aithru result",
                        )
                    ],
                ).model_dump(mode="json"),
                redaction="partial",
            )
        request = WebFetchRequest.model_validate(invocation.input)
        return WebToolResult(
            status="completed",
            output=WebFetchResult(
                url=request.url,
                status_code=200,
                media_type="text/html",
                content="<h1>Aithru</h1>",
                truncated=False,
            ).model_dump(mode="json"),
            redaction="partial",
        )


def test_web_search_and_fetch_contracts_are_pydantic_validated() -> None:
    search = WebSearchRequest(query="aithru agent", max_results=3, recency_days=7)
    item = WebSearchItem(title="Aithru", url="https://example.com/aithru", snippet="Result")
    search_result = WebSearchResult(query=search.query, results=[item])
    fetch = WebFetchRequest(url="https://example.com/aithru", max_bytes=16_000, extract_text=True)
    fetch_result = WebFetchResult(
        url=fetch.url,
        status_code=200,
        media_type="text/html",
        content="Aithru",
        truncated=False,
    )

    assert search.model_dump(mode="json") == {
        "query": "aithru agent",
        "max_results": 3,
        "recency_days": 7,
    }
    assert search_result.model_dump(mode="json") == {
        "query": "aithru agent",
        "results": [
            {
                "title": "Aithru",
                "url": "https://example.com/aithru",
                "snippet": "Result",
                "source": None,
                "published_at": None,
            }
        ],
    }
    assert fetch_result.model_dump(mode="json") == {
        "url": "https://example.com/aithru",
        "status_code": 200,
        "media_type": "text/html",
        "content": "Aithru",
        "truncated": False,
    }


@pytest.mark.parametrize(
    "model, kwargs",
    [
        (WebSearchRequest, {"query": " "}),
        (WebSearchRequest, {"query": "x", "max_results": 0}),
        (WebSearchRequest, {"query": "x", "max_results": 51}),
        (WebSearchRequest, {"query": "x", "recency_days": 0}),
        (WebFetchRequest, {"url": "ftp://example.com"}),
        (WebFetchRequest, {"url": "https://example.com", "max_bytes": 0}),
    ],
)
def test_web_contracts_reject_invalid_values(model, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_web_tool_provider_maps_search_and_fetch_to_external_specs() -> None:
    provider = WebToolProvider(executor=FakeWebExecutor())

    specs = provider.list_tools()
    by_name = {spec.name: spec for spec in specs}

    assert by_name["web.search"].provider == "web"
    assert by_name["web.search"].risk_level == "read"
    assert by_name["web.search"].required_scopes == ["agent.external.web.search"]
    assert by_name["web.search"].failure_policy == "return_recoverable"
    assert by_name["web.search"].metadata == {"action": "search"}
    assert by_name["web.fetch"].provider == "web"
    assert by_name["web.fetch"].required_scopes == ["agent.external.web.fetch"]
    assert by_name["web.fetch"].failure_policy == "return_recoverable"
    assert by_name["web.fetch"].metadata == {"action": "fetch"}


@pytest.mark.asyncio
async def test_web_tool_provider_executes_search_and_fetch_through_executor() -> None:
    executor = FakeWebExecutor()
    provider = WebToolProvider(executor=executor)

    search = await provider.execute(
        provider.external_invocation(
            tool_call_id="toolcall_1",
            external_tool_name="web.search",
            input={"query": "aithru", "max_results": 1},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
        )
    )
    fetch = await provider.execute(
        provider.external_invocation(
            tool_call_id="toolcall_2",
            external_tool_name="web.fetch",
            input={"url": "https://example.com/aithru"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
        )
    )

    assert search.status == "completed"
    assert search.output["results"][0]["url"] == "https://example.com/aithru"
    assert fetch.status == "completed"
    assert fetch.output["content"] == "<h1>Aithru</h1>"
    assert [invocation.action for invocation in executor.invocations] == ["search", "fetch"]
    assert executor.invocations[0].run_id == "run_1"


@pytest.mark.asyncio
async def test_web_tool_provider_denies_unknown_or_invalid_calls_before_executor() -> None:
    executor = FakeWebExecutor()
    provider = WebToolProvider(executor=executor)

    unknown = await provider.execute(
        provider.external_invocation(
            tool_call_id="toolcall_1",
            external_tool_name="web.unknown",
            input={"query": "aithru"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
        )
    )
    invalid = await provider.execute(
        provider.external_invocation(
            tool_call_id="toolcall_2",
            external_tool_name="web.fetch",
            input={"url": "ftp://example.com"},
            run_id="run_1",
            org_id="org_1",
            actor_user_id="user_1",
            workspace_id="workspace_1",
        )
    )

    assert unknown.status == "denied"
    assert unknown.error == {"message": "Unknown web tool: web.unknown"}
    assert invalid.status == "denied"
    assert "Invalid web tool input" in invalid.error["message"]
    assert executor.invocations == []


@pytest.mark.asyncio
async def test_web_provider_tools_remain_scope_skill_and_approval_controlled() -> None:
    provider = WebToolProvider(executor=FakeWebExecutor())
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
        update={"scopes": ["agent.external.web.search", "agent.external.web.fetch"]}
    )
    skill_context = scoped_context.model_copy(update={"allowed_tools": ["web.search"]})

    assert await router.list_tools(base_context) == []
    assert [tool.name for tool in await router.list_tools(skill_context)] == ["web.search"]
    prepared = await approval_router.prepare_tool_call(
        AgentToolCallRequest(
            id="toolcall_1",
            tool_name="web.search",
            input={"query": "aithru"},
            requested_by="model",
        ),
        skill_context,
    )

    assert prepared.status == "waiting_approval"
