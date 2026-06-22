import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import Field, ValidationError, field_validator, model_validator

from aithru_agent.domain.base import AithruBaseModel

from .mcp import MCPToolExecutor, MCPToolInvocation, MCPToolResult


class ControlledHTTPMCPToolExecutorConfig(AithruBaseModel):
    allowed_hosts: list[str]
    server_endpoints: dict[str, str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_response_bytes: int = Field(default=100_000, ge=1, le=1_000_000)

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_allowed_host(host) for host in value]
        if not hosts:
            raise ValueError("mcp allowed hosts are required for HTTP MCP execution")
        if len(set(hosts)) != len(hosts):
            raise ValueError("mcp allowed hosts must be unique")
        return hosts

    @field_validator("server_endpoints")
    @classmethod
    def _server_endpoints_must_be_http(cls, value: dict[str, str]) -> dict[str, str]:
        endpoints: dict[str, str] = {}
        for server_key, endpoint_url in value.items():
            key = server_key.strip()
            if not key:
                raise ValueError("MCP server endpoint key cannot be blank")
            url = endpoint_url.strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                raise ValueError("MCP server endpoint must use http or https")
            if _request_host(url) is None:
                raise ValueError("MCP server endpoint must include a host")
            endpoints[key] = url
        return endpoints

    @model_validator(mode="after")
    def _server_endpoint_hosts_must_be_allowed(self) -> "ControlledHTTPMCPToolExecutorConfig":
        for endpoint_url in self.server_endpoints.values():
            host = _request_host(endpoint_url)
            if not _host_allowed(host, self.allowed_hosts):
                raise ValueError(f"MCP server endpoint host is not allowed: {host}")
        return self


class ControlledHTTPMCPToolExecutor(MCPToolExecutor):
    def __init__(
        self,
        *,
        allowed_hosts: list[str],
        server_endpoints: dict[str, str],
        timeout_ms: int = 5_000,
        max_response_bytes: int = 100_000,
    ) -> None:
        self._config = ControlledHTTPMCPToolExecutorConfig(
            allowed_hosts=allowed_hosts,
            server_endpoints=server_endpoints,
            timeout_ms=timeout_ms,
            max_response_bytes=max_response_bytes,
        )

    async def execute(self, invocation: MCPToolInvocation) -> MCPToolResult:
        endpoint_url = self._config.server_endpoints.get(invocation.server_key)
        if endpoint_url is None:
            return MCPToolResult(
                status="denied",
                error={"message": f"MCP server endpoint is not configured: {invocation.server_key}"},
                redaction="none",
            )
        try:
            return await asyncio.to_thread(self._post, endpoint_url, invocation)
        except HTTPError as exc:
            return MCPToolResult(
                status="failed",
                error={"message": f"HTTP MCP call failed with status {exc.code}"},
                redaction="partial",
            )
        except URLError as exc:
            return MCPToolResult(
                status="failed",
                error={"message": f"HTTP MCP call failed: {exc.reason}"},
                redaction="partial",
            )
        except TimeoutError:
            return MCPToolResult(
                status="failed",
                error={"message": "HTTP MCP call timed out"},
                redaction="partial",
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return MCPToolResult(
                status="failed",
                error={"message": f"HTTP MCP response was invalid: {exc}"},
                redaction="partial",
            )

    def _post(self, endpoint_url: str, invocation: MCPToolInvocation) -> MCPToolResult:
        data = json.dumps(invocation.model_dump(mode="json")).encode("utf-8")
        request = Request(
            endpoint_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Aithru-Agent/0.1 controlled-mcp",
            },
            method="POST",
        )
        with urlopen(request, timeout=self._config.timeout_ms / 1000) as response:
            content = response.read(self._config.max_response_bytes + 1)
            if len(content) > self._config.max_response_bytes:
                raise ValueError("MCP response exceeded maximum size")
            payload = json.loads(content.decode("utf-8", errors="replace"))
            return MCPToolResult.model_validate(payload)


def _request_host(url: str) -> str:
    host = urlsplit(url).hostname
    if host is None:
        raise ValueError("MCP server endpoint must include a host")
    return host.lower().rstrip(".")


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _normalize_allowed_host(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host:
        raise ValueError("mcp allowed hosts cannot contain blank values")
    if any(char.isspace() for char in host) or "/" in host or ":" in host or "*" in host:
        raise ValueError("mcp allowed hosts must be host names without schemes, ports, or wildcards")
    return host
