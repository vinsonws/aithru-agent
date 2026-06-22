import asyncio
import json
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pydantic import Field, ValidationError, field_validator, model_validator

from aithru_agent.domain.base import AithruBaseModel

from .web import (
    MAX_WEB_FETCH_BYTES,
    WebFetchRequest,
    WebFetchResult,
    WebSearchItem,
    WebSearchRequest,
    WebSearchResult,
    WebToolInvocation,
    WebToolResult,
)


class ControlledHTTPSearchResponse(AithruBaseModel):
    results: list[WebSearchItem]


class ControlledHTTPWebExecutorConfig(AithruBaseModel):
    allowed_hosts: list[str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_fetch_bytes: int = Field(default=100_000, ge=1, le=MAX_WEB_FETCH_BYTES)
    fetch_enabled: bool = True
    search_endpoint_url: str | None = None

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_allowed_host(host) for host in value]
        if not hosts:
            raise ValueError("allowed hosts are required for HTTP web execution")
        if len(set(hosts)) != len(hosts):
            raise ValueError("allowed hosts must be unique")
        return hosts

    @field_validator("search_endpoint_url")
    @classmethod
    def _search_endpoint_must_be_http(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("search endpoint must use http or https")
        if _request_host(url) is None:
            raise ValueError("search endpoint must include a host")
        return url

    @model_validator(mode="after")
    def _search_endpoint_host_must_be_allowed(self) -> "ControlledHTTPWebExecutorConfig":
        if self.search_endpoint_url is None:
            return self
        host = _request_host(self.search_endpoint_url)
        if not _host_allowed(host, self.allowed_hosts):
            raise ValueError(f"search endpoint host is not allowed: {host}")
        return self


class ControlledHTTPWebExecutor:
    def __init__(
        self,
        *,
        allowed_hosts: list[str],
        timeout_ms: int = 5_000,
        max_fetch_bytes: int = 100_000,
        fetch_enabled: bool = True,
        search_endpoint_url: str | None = None,
    ) -> None:
        self._config = ControlledHTTPWebExecutorConfig(
            allowed_hosts=allowed_hosts,
            timeout_ms=timeout_ms,
            max_fetch_bytes=max_fetch_bytes,
            fetch_enabled=fetch_enabled,
            search_endpoint_url=search_endpoint_url,
        )

    async def execute(self, invocation: WebToolInvocation) -> WebToolResult:
        if invocation.action == "search":
            if self._config.search_endpoint_url is not None:
                return await self._execute_search(invocation)
            return WebToolResult(
                status="failed",
                error={"message": "Web search executor is not configured"},
                redaction="none",
            )
        if not self._config.fetch_enabled:
            return WebToolResult(
                status="failed",
                error={"message": "Web fetch executor is not configured"},
                redaction="none",
            )
        request = WebFetchRequest.model_validate(invocation.input)
        host = _request_host(request.url)
        if not _host_allowed(host, self._config.allowed_hosts):
            return WebToolResult(
                status="denied",
                error={"message": f"Host is not allowed for web.fetch: {host}"},
                redaction="none",
            )
        try:
            result = await asyncio.to_thread(self._fetch, request)
        except HTTPError as exc:
            return WebToolResult(
                status="failed",
                error={"message": f"HTTP fetch failed with status {exc.code}"},
                redaction="partial",
            )
        except URLError as exc:
            return WebToolResult(
                status="failed",
                error={"message": f"HTTP fetch failed: {exc.reason}"},
                redaction="partial",
            )
        except TimeoutError:
            return WebToolResult(
                status="failed",
                error={"message": "HTTP fetch timed out"},
                redaction="partial",
            )
        return WebToolResult(
            status="completed",
            output=result.model_dump(mode="json"),
            redaction="partial",
        )

    async def _execute_search(self, invocation: WebToolInvocation) -> WebToolResult:
        request = WebSearchRequest.model_validate(invocation.input)
        try:
            result = await asyncio.to_thread(self._search, request)
        except HTTPError as exc:
            return WebToolResult(
                status="failed",
                error={"message": f"HTTP search failed with status {exc.code}"},
                redaction="partial",
            )
        except URLError as exc:
            return WebToolResult(
                status="failed",
                error={"message": f"HTTP search failed: {exc.reason}"},
                redaction="partial",
            )
        except TimeoutError:
            return WebToolResult(
                status="failed",
                error={"message": "HTTP search timed out"},
                redaction="partial",
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return WebToolResult(
                status="failed",
                error={"message": f"HTTP search response was invalid: {exc}"},
                redaction="partial",
            )
        return WebToolResult(
            status="completed",
            output=result.model_dump(mode="json"),
            redaction="partial",
        )

    def _fetch(self, request: WebFetchRequest) -> WebFetchResult:
        max_bytes = min(request.max_bytes, self._config.max_fetch_bytes)
        http_request = Request(
            request.url,
            headers={"User-Agent": "Aithru-Agent/0.1 controlled-web-fetch"},
            method="GET",
        )
        with urlopen(http_request, timeout=self._config.timeout_ms / 1000) as response:
            content = response.read(max_bytes + 1)
            truncated = len(content) > max_bytes
            if truncated:
                content = content[:max_bytes]
            media_type = response.headers.get("Content-Type")
            return WebFetchResult(
                url=request.url,
                status_code=response.status,
                media_type=media_type,
                content=_decode_content(content, response.headers),
                truncated=truncated,
            )

    def _search(self, request: WebSearchRequest) -> WebSearchResult:
        endpoint_url = self._config.search_endpoint_url
        if endpoint_url is None:
            raise ValueError("search endpoint is not configured")
        http_request = Request(
            _search_url(endpoint_url, request),
            headers={"User-Agent": "Aithru-Agent/0.1 controlled-web-search"},
            method="GET",
        )
        with urlopen(http_request, timeout=self._config.timeout_ms / 1000) as response:
            content = response.read(self._config.max_fetch_bytes + 1)
            if len(content) > self._config.max_fetch_bytes:
                raise ValueError("search response exceeded maximum size")
            payload = json.loads(_decode_content(content, response.headers))
            search_response = ControlledHTTPSearchResponse.model_validate(payload)
            return WebSearchResult(
                query=request.query,
                results=search_response.results[: request.max_results],
            )


def _decode_content(content: bytes, headers: Message) -> str:
    charset = headers.get_content_charset() or "utf-8"
    return content.decode(charset, errors="replace")


def _search_url(endpoint_url: str, request: WebSearchRequest) -> str:
    parsed = urlsplit(endpoint_url)
    query_params = [
        *parse_qsl(parsed.query, keep_blank_values=True),
        ("q", request.query),
        ("max_results", str(request.max_results)),
    ]
    if request.recency_days is not None:
        query_params.append(("recency_days", str(request.recency_days)))
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query_params),
            parsed.fragment,
        )
    )


def _request_host(url: str) -> str:
    host = urlsplit(url).hostname
    if host is None:
        raise ValueError("url must include a host")
    return host.lower().rstrip(".")


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _normalize_allowed_host(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host:
        raise ValueError("allowed hosts cannot contain blank values")
    if any(char.isspace() for char in host) or "/" in host or ":" in host or "*" in host:
        raise ValueError("allowed hosts must be host names without schemes, ports, or wildcards")
    return host
