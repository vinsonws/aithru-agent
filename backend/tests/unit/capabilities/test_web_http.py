import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from threading import Thread

import pytest

from aithru_agent.capabilities.web import WebToolInvocation
from aithru_agent.capabilities.web_http import ControlledHTTPWebExecutor


class StaticHandler(BaseHTTPRequestHandler):
    body = b"hello from aithru"
    media_type = "text/plain; charset=utf-8"

    def do_GET(self) -> None:
        if self.path.startswith("/search"):
            query = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
            body = json.dumps(
                {
                    "results": [
                        {
                            "title": f"Aithru result for {query}",
                            "url": "https://example.com/aithru",
                            "snippet": "Controlled search result.",
                            "source": "local-test-search",
                            "published_at": "2026-06-18",
                        },
                        {
                            "title": "Extra result",
                            "url": "https://example.com/extra",
                            "snippet": "Should be trimmed by max_results.",
                        },
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
        yield f"http://127.0.0.1:{server.server_port}/report.txt"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.asyncio
async def test_controlled_http_web_executor_fetches_allowed_url(http_server: str) -> None:
    executor = ControlledHTTPWebExecutor(
        allowed_hosts=["127.0.0.1"],
        timeout_ms=1_000,
        max_fetch_bytes=100_000,
    )

    result = await executor.execute(_invocation("fetch", {"url": http_server}))

    assert result.status == "completed"
    assert result.output == {
        "url": http_server,
        "status_code": 200,
        "media_type": "text/plain; charset=utf-8",
        "content": "hello from aithru",
        "truncated": False,
    }
    assert result.redaction == "partial"


@pytest.mark.asyncio
async def test_controlled_http_web_executor_denies_disallowed_hosts() -> None:
    executor = ControlledHTTPWebExecutor(
        allowed_hosts=["allowed.example"],
        timeout_ms=1_000,
        max_fetch_bytes=100_000,
    )

    result = await executor.execute(_invocation("fetch", {"url": "https://example.com"}))

    assert result.status == "denied"
    assert result.error == {"message": "Host is not allowed for web.fetch: example.com"}


@pytest.mark.asyncio
async def test_controlled_http_web_executor_truncates_to_request_limit(http_server: str) -> None:
    executor = ControlledHTTPWebExecutor(
        allowed_hosts=["127.0.0.1"],
        timeout_ms=1_000,
        max_fetch_bytes=100_000,
    )

    result = await executor.execute(_invocation("fetch", {"url": http_server, "max_bytes": 5}))

    assert result.status == "completed"
    assert result.output["content"] == "hello"
    assert result.output["truncated"] is True


@pytest.mark.asyncio
async def test_controlled_http_web_executor_does_not_fake_search() -> None:
    executor = ControlledHTTPWebExecutor(
        allowed_hosts=["127.0.0.1"],
        timeout_ms=1_000,
        max_fetch_bytes=100_000,
    )

    result = await executor.execute(_invocation("search", {"query": "aithru"}))

    assert result.status == "failed"
    assert result.error == {"message": "Web search executor is not configured"}


@pytest.mark.asyncio
async def test_controlled_http_web_executor_searches_configured_json_endpoint(
    http_server: str,
) -> None:
    search_endpoint = http_server.replace("/report.txt", "/search")
    executor = ControlledHTTPWebExecutor(
        allowed_hosts=["127.0.0.1"],
        timeout_ms=1_000,
        max_fetch_bytes=100_000,
        search_endpoint_url=search_endpoint,
    )

    result = await executor.execute(
        _invocation("search", {"query": "aithru", "max_results": 1})
    )

    assert result.status == "completed"
    assert result.output == {
        "query": "aithru",
        "results": [
            {
                "title": "Aithru result for aithru",
                "url": "https://example.com/aithru",
                "snippet": "Controlled search result.",
                "source": "local-test-search",
                "published_at": "2026-06-18",
            }
        ],
    }
    assert result.redaction == "partial"


def test_controlled_http_web_executor_rejects_unallowlisted_search_endpoint() -> None:
    with pytest.raises(ValueError, match="search endpoint host"):
        ControlledHTTPWebExecutor(
            allowed_hosts=["allowed.example"],
            timeout_ms=1_000,
            max_fetch_bytes=100_000,
            search_endpoint_url="https://search.example.com/api",
        )


def _invocation(action: str, input: object) -> WebToolInvocation:
    return WebToolInvocation(
        tool_call_id="toolcall_1",
        external_tool_name=f"web.{action}",
        action=action,
        input=input,
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
    )
