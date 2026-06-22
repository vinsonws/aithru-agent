import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import Field, ValidationError, field_validator, model_validator

from aithru_agent.domain.base import AithruBaseModel

from .workflow import (
    WorkflowCapabilityInvocation,
    WorkflowCapabilityProvider,
    WorkflowCapabilityResult,
    WorkflowCapabilitySpec,
)


class ControlledHTTPWorkflowCapabilityProviderConfig(AithruBaseModel):
    capabilities: list[WorkflowCapabilitySpec]
    endpoint_url: str
    allowed_hosts: list[str]
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_response_bytes: int = Field(default=100_000, ge=1, le=1_000_000)

    @field_validator("capabilities")
    @classmethod
    def _capabilities_must_be_unique(
        cls,
        value: list[WorkflowCapabilitySpec],
    ) -> list[WorkflowCapabilitySpec]:
        if not value:
            raise ValueError("workflow capabilities are required for HTTP execution")
        keys = [capability.key for capability in value]
        tool_names = [capability.tool_name for capability in value]
        if len(set(keys)) != len(keys):
            raise ValueError("workflow capability keys must be unique")
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("workflow capability tool names must be unique")
        return value

    @field_validator("endpoint_url")
    @classmethod
    def _endpoint_must_be_http(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint:
            raise ValueError("workflow capability endpoint cannot be blank")
        if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
            raise ValueError("workflow capability endpoint must use http or https")
        if _request_host(endpoint) is None:
            raise ValueError("workflow capability endpoint must include a host")
        return endpoint

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_allowed_host(host) for host in value]
        if not hosts:
            raise ValueError("workflow capability allowed hosts are required")
        if len(set(hosts)) != len(hosts):
            raise ValueError("workflow capability allowed hosts must be unique")
        return hosts

    @model_validator(mode="after")
    def _endpoint_host_must_be_allowed(
        self,
    ) -> "ControlledHTTPWorkflowCapabilityProviderConfig":
        host = _request_host(self.endpoint_url)
        if not _host_allowed(host, self.allowed_hosts):
            raise ValueError(f"workflow capability endpoint host is not allowed: {host}")
        return self


class ControlledHTTPWorkflowCapabilityProvider(WorkflowCapabilityProvider):
    def __init__(
        self,
        *,
        capabilities: list[WorkflowCapabilitySpec],
        endpoint_url: str,
        allowed_hosts: list[str],
        timeout_ms: int = 5_000,
        max_response_bytes: int = 100_000,
    ) -> None:
        self._config = ControlledHTTPWorkflowCapabilityProviderConfig(
            capabilities=capabilities,
            endpoint_url=endpoint_url,
            allowed_hosts=allowed_hosts,
            timeout_ms=timeout_ms,
            max_response_bytes=max_response_bytes,
        )

    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return self._config.capabilities

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        try:
            return await asyncio.to_thread(self._post, invocation)
        except HTTPError as exc:
            return WorkflowCapabilityResult(
                status="failed",
                error={"message": f"HTTP workflow capability call failed with status {exc.code}"},
                redaction="partial",
            )
        except URLError as exc:
            return WorkflowCapabilityResult(
                status="failed",
                error={"message": f"HTTP workflow capability call failed: {exc.reason}"},
                redaction="partial",
            )
        except TimeoutError:
            return WorkflowCapabilityResult(
                status="failed",
                error={"message": "HTTP workflow capability call timed out"},
                redaction="partial",
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return WorkflowCapabilityResult(
                status="failed",
                error={"message": f"HTTP workflow capability response was invalid: {exc}"},
                redaction="partial",
            )

    def _post(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        data = json.dumps(invocation.model_dump(mode="json")).encode("utf-8")
        request = Request(
            self._config.endpoint_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Aithru-Agent/0.1 controlled-workflow-capability",
            },
            method="POST",
        )
        with urlopen(request, timeout=self._config.timeout_ms / 1000) as response:
            content = response.read(self._config.max_response_bytes + 1)
            if len(content) > self._config.max_response_bytes:
                raise ValueError("workflow capability response exceeded maximum size")
            payload = json.loads(content.decode("utf-8", errors="replace"))
            return WorkflowCapabilityResult.model_validate(payload)


def _request_host(url: str) -> str:
    host = urlsplit(url).hostname
    if host is None:
        raise ValueError("workflow capability endpoint must include a host")
    return host.lower().rstrip(".")


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _normalize_allowed_host(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host:
        raise ValueError("workflow capability allowed hosts cannot contain blank values")
    if any(char.isspace() for char in host) or "/" in host or ":" in host or "*" in host:
        raise ValueError(
            "workflow capability allowed hosts must be host names without schemes, ports, or wildcards"
        )
    return host
