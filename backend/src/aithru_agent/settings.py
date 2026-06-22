import json
import os
from pathlib import Path
from typing import Literal

from pydantic import (
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from aithru_agent.capabilities.mcp import MCPServerSpec
from aithru_agent.capabilities.web import MAX_WEB_FETCH_BYTES
from aithru_agent.capabilities.workflow import WorkflowCapabilitySpec
from aithru_agent.domain.base import AithruBaseModel

AgentDriverKind = Literal["pydantic_ai"]
AgentPersistenceBackend = Literal["memory", "sqlite"]
AgentWebExecutorKind = Literal["unavailable", "http"]
AgentWebSearchExecutorKind = Literal["unavailable", "http_json"]
AgentMCPExecutorKind = Literal["unavailable", "http_json"]
AgentWorkflowCapabilityExecutorKind = Literal["unavailable", "http_json"]


class AgentExternalToolsSettings(AithruBaseModel):
    web_enabled: bool = False
    web_executor: AgentWebExecutorKind = "unavailable"
    web_search_executor: AgentWebSearchExecutorKind = "unavailable"
    web_search_endpoint_url: str | None = None
    web_allowed_hosts: list[str] = Field(default_factory=list)
    web_timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    web_max_fetch_bytes: int = Field(default=100_000, ge=1, le=MAX_WEB_FETCH_BYTES)
    mcp_executor: AgentMCPExecutorKind = "unavailable"
    mcp_allowed_hosts: list[str] = Field(default_factory=list)
    mcp_timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    mcp_max_response_bytes: int = Field(default=100_000, ge=1, le=1_000_000)
    mcp_servers: list[MCPServerSpec] = Field(default_factory=list)

    @field_validator("web_allowed_hosts")
    @classmethod
    def _web_allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_host(host) for host in value]
        if len(set(hosts)) != len(hosts):
            raise ValueError("web allowed hosts must be unique")
        return hosts

    @field_validator("mcp_allowed_hosts")
    @classmethod
    def _mcp_allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_host(host, label="mcp allowed hosts") for host in value]
        if len(set(hosts)) != len(hosts):
            raise ValueError("mcp allowed hosts must be unique")
        return hosts

    @field_validator("mcp_servers")
    @classmethod
    def _mcp_server_keys_must_be_unique(
        cls,
        value: list[MCPServerSpec],
    ) -> list[MCPServerSpec]:
        keys = [server.key for server in value if server.enabled]
        if len(set(keys)) != len(keys):
            raise ValueError("MCP server keys must be unique")
        return value

    @model_validator(mode="after")
    def _validate_web_executor_settings(self) -> "AgentExternalToolsSettings":
        if self.web_executor == "http" and not self.web_enabled:
            raise ValueError("web_enabled must be true when web_executor is http")
        if self.web_search_executor == "http_json" and not self.web_enabled:
            raise ValueError("web_enabled must be true when web_search_executor is http_json")
        if self.web_executor == "http" and not self.web_allowed_hosts:
            raise ValueError("web allowed hosts are required for http executor")
        if self.web_search_executor == "http_json" and not self.web_search_endpoint_url:
            raise ValueError("web search endpoint is required for http_json executor")
        if self.web_search_executor == "http_json" and not self.web_allowed_hosts:
            raise ValueError("web allowed hosts are required for http_json executor")
        if self.web_search_endpoint_url is not None:
            endpoint = self.web_search_endpoint_url.strip()
            if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
                raise ValueError("web search endpoint must use http or https")
            endpoint_host = _url_host(endpoint)
            if not _host_allowed(endpoint_host, self.web_allowed_hosts):
                raise ValueError(f"web search endpoint host is not allowed: {endpoint_host}")
            self.web_search_endpoint_url = endpoint
        if self.mcp_executor == "http_json":
            enabled_servers = [server for server in self.mcp_servers if server.enabled]
            if not enabled_servers:
                raise ValueError("mcp servers are required when mcp_executor is http_json")
            if not self.mcp_allowed_hosts:
                raise ValueError("mcp allowed hosts are required when mcp_executor is http_json")
            for server in enabled_servers:
                endpoint = _mcp_server_endpoint_url(server)
                endpoint_host = _url_host(endpoint, label="MCP server endpoint")
                if not _host_allowed(endpoint_host, self.mcp_allowed_hosts):
                    raise ValueError(f"MCP server endpoint host is not allowed: {endpoint_host}")
        return self


class AgentWorkflowCapabilitiesSettings(AithruBaseModel):
    executor: AgentWorkflowCapabilityExecutorKind = "unavailable"
    endpoint_url: str | None = None
    allowed_hosts: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    max_response_bytes: int = Field(default=100_000, ge=1, le=1_000_000)
    capabilities: list[WorkflowCapabilitySpec] = Field(default_factory=list)

    @field_validator("allowed_hosts")
    @classmethod
    def _allowed_hosts_must_be_explicit(cls, value: list[str]) -> list[str]:
        hosts = [_normalize_host(host, label="workflow capability allowed hosts") for host in value]
        if len(set(hosts)) != len(hosts):
            raise ValueError("workflow capability allowed hosts must be unique")
        return hosts

    @field_validator("capabilities")
    @classmethod
    def _capabilities_must_be_unique(
        cls,
        value: list[WorkflowCapabilitySpec],
    ) -> list[WorkflowCapabilitySpec]:
        keys = [capability.key for capability in value]
        tool_names = [capability.tool_name for capability in value]
        if len(set(keys)) != len(keys):
            raise ValueError("workflow capability keys must be unique")
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("workflow capability tool names must be unique")
        return value

    @model_validator(mode="after")
    def _validate_workflow_capability_settings(
        self,
    ) -> "AgentWorkflowCapabilitiesSettings":
        if self.executor == "http_json":
            if not self.capabilities:
                raise ValueError("workflow capabilities are required when executor is http_json")
            if not self.endpoint_url:
                raise ValueError(
                    "workflow capability endpoint is required when executor is http_json"
                )
            if not self.allowed_hosts:
                raise ValueError(
                    "workflow capability allowed hosts are required when executor is http_json"
                )
        if self.endpoint_url is not None:
            endpoint = self.endpoint_url.strip()
            if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
                raise ValueError("workflow capability endpoint must use http or https")
            endpoint_host = _url_host(endpoint, label="workflow capability endpoint")
            if not _host_allowed(endpoint_host, self.allowed_hosts):
                raise ValueError(
                    f"workflow capability endpoint host is not allowed: {endpoint_host}"
                )
            self.endpoint_url = endpoint
        return self


class AgentProcessorSettings(AithruBaseModel):
    clarification_enabled: bool = True
    clarification_min_goal_words: int = Field(default=4, ge=1, le=20)
    title_generation_enabled: bool = True
    title_max_words: int = Field(default=6, ge=1, le=12)
    summarization_enabled: bool = True
    summarization_min_message_count: int = Field(default=6, ge=1, le=100)
    memory_extraction_enabled: bool = True


class AgentSettings(AithruBaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    driver: AgentDriverKind = "pydantic_ai"
    persistence_backend: AgentPersistenceBackend = "memory"
    sqlite_path: str = ".aithru/agent.sqlite"
    model: str | None = None
    instructions: str = "You are Aithru Agent. Use controlled tools only."
    test_model_output: str = "Done."
    api_token: str | None = None
    api_scopes: list[str] = Field(default_factory=lambda: ["*"])
    external_tools: AgentExternalToolsSettings = Field(
        default_factory=AgentExternalToolsSettings
    )
    workflow_capabilities: AgentWorkflowCapabilitiesSettings = Field(
        default_factory=AgentWorkflowCapabilitiesSettings
    )
    processors: AgentProcessorSettings = Field(default_factory=AgentProcessorSettings)

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("model cannot be blank")
        return stripped

    @field_validator("instructions", "test_model_output")
    @classmethod
    def _validate_required_string(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("string setting cannot be blank")
        return stripped

    @field_validator("api_token")
    @classmethod
    def _validate_api_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("api_token cannot be blank")
        return stripped

    @field_validator("sqlite_path")
    @classmethod
    def _validate_sqlite_path(cls, value: str) -> str:
        path = value.strip()
        if not path:
            raise ValueError("sqlite_path cannot be blank")
        if Path(path).name in {"", ".", ".."}:
            raise ValueError("sqlite_path must point to a file")
        return path

    @field_validator("api_scopes")
    @classmethod
    def _validate_api_scopes(cls, value: list[str]) -> list[str]:
        scopes = [scope.strip() for scope in value]
        if any(not scope for scope in scopes):
            raise ValueError("api_scopes cannot contain blank scopes")
        return scopes or ["*"]

    @model_validator(mode="after")
    def _validate_sqlite_settings(self) -> "AgentSettings":
        if self.persistence_backend == "sqlite" and not self.sqlite_path:
            raise ValueError("sqlite_path is required for sqlite persistence")
        return self

    @classmethod
    def from_env(cls) -> "AgentSettings":
        driver = os.getenv("AITHRU_AGENT_DRIVER", "pydantic_ai")
        if driver == "scripted":
            raise ValueError(
                "The scripted driver has been removed; use AITHRU_AGENT_MODEL=test "
                "for deterministic tests"
            )
        return cls(
            driver=driver,
            persistence_backend=os.getenv("AITHRU_AGENT_PERSISTENCE_BACKEND", "memory"),
            sqlite_path=os.getenv("AITHRU_AGENT_SQLITE_PATH", ".aithru/agent.sqlite"),
            model=os.getenv("AITHRU_AGENT_MODEL"),
            instructions=os.getenv(
                "AITHRU_AGENT_INSTRUCTIONS",
                "You are Aithru Agent. Use controlled tools only.",
            ),
            test_model_output=os.getenv("AITHRU_AGENT_TEST_MODEL_OUTPUT", "Done."),
            api_token=os.getenv("AITHRU_AGENT_API_TOKEN"),
            api_scopes=_split_scopes(os.getenv("AITHRU_AGENT_API_SCOPES")),
            external_tools=AgentExternalToolsSettings(
                web_enabled=_env_bool(
                    os.getenv("AITHRU_AGENT_EXTERNAL_WEB_ENABLED"),
                    name="AITHRU_AGENT_EXTERNAL_WEB_ENABLED",
                ),
                web_executor=os.getenv(
                    "AITHRU_AGENT_EXTERNAL_WEB_EXECUTOR",
                    "unavailable",
                ),
                web_search_executor=os.getenv(
                    "AITHRU_AGENT_EXTERNAL_WEB_SEARCH_EXECUTOR",
                    "unavailable",
                ),
                web_search_endpoint_url=os.getenv(
                    "AITHRU_AGENT_EXTERNAL_WEB_SEARCH_ENDPOINT_URL"
                ),
                web_allowed_hosts=_split_csv(
                    os.getenv("AITHRU_AGENT_EXTERNAL_WEB_ALLOWED_HOSTS"),
                    name="AITHRU_AGENT_EXTERNAL_WEB_ALLOWED_HOSTS",
                ),
                web_timeout_ms=_env_int(
                    os.getenv("AITHRU_AGENT_EXTERNAL_WEB_TIMEOUT_MS"),
                    default=5_000,
                    name="AITHRU_AGENT_EXTERNAL_WEB_TIMEOUT_MS",
                ),
                web_max_fetch_bytes=_env_int(
                    os.getenv("AITHRU_AGENT_EXTERNAL_WEB_MAX_FETCH_BYTES"),
                    default=100_000,
                    name="AITHRU_AGENT_EXTERNAL_WEB_MAX_FETCH_BYTES",
                ),
                mcp_executor=os.getenv(
                    "AITHRU_AGENT_EXTERNAL_MCP_EXECUTOR",
                    "unavailable",
                ),
                mcp_allowed_hosts=_split_csv(
                    os.getenv("AITHRU_AGENT_EXTERNAL_MCP_ALLOWED_HOSTS"),
                    name="AITHRU_AGENT_EXTERNAL_MCP_ALLOWED_HOSTS",
                ),
                mcp_timeout_ms=_env_int(
                    os.getenv("AITHRU_AGENT_EXTERNAL_MCP_TIMEOUT_MS"),
                    default=5_000,
                    name="AITHRU_AGENT_EXTERNAL_MCP_TIMEOUT_MS",
                ),
                mcp_max_response_bytes=_env_int(
                    os.getenv("AITHRU_AGENT_EXTERNAL_MCP_MAX_RESPONSE_BYTES"),
                    default=100_000,
                    name="AITHRU_AGENT_EXTERNAL_MCP_MAX_RESPONSE_BYTES",
                ),
                mcp_servers=_parse_mcp_servers_json(
                    os.getenv("AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON")
                ),
            ),
            workflow_capabilities=AgentWorkflowCapabilitiesSettings(
                executor=os.getenv(
                    "AITHRU_AGENT_WORKFLOW_CAPABILITY_EXECUTOR",
                    "unavailable",
                ),
                endpoint_url=os.getenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_ENDPOINT_URL"),
                allowed_hosts=_split_csv(
                    os.getenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_ALLOWED_HOSTS"),
                    name="AITHRU_AGENT_WORKFLOW_CAPABILITY_ALLOWED_HOSTS",
                ),
                timeout_ms=_env_int(
                    os.getenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_TIMEOUT_MS"),
                    default=5_000,
                    name="AITHRU_AGENT_WORKFLOW_CAPABILITY_TIMEOUT_MS",
                ),
                max_response_bytes=_env_int(
                    os.getenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_MAX_RESPONSE_BYTES"),
                    default=100_000,
                    name="AITHRU_AGENT_WORKFLOW_CAPABILITY_MAX_RESPONSE_BYTES",
                ),
                capabilities=_parse_workflow_capabilities_json(
                    os.getenv("AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON")
                ),
            ),
            processors=AgentProcessorSettings(
                clarification_enabled=_env_bool_default(
                    os.getenv("AITHRU_AGENT_PROCESSOR_CLARIFICATION_ENABLED"),
                    default=True,
                    name="AITHRU_AGENT_PROCESSOR_CLARIFICATION_ENABLED",
                ),
                clarification_min_goal_words=_env_int(
                    os.getenv("AITHRU_AGENT_PROCESSOR_CLARIFICATION_MIN_GOAL_WORDS"),
                    default=4,
                    name="AITHRU_AGENT_PROCESSOR_CLARIFICATION_MIN_GOAL_WORDS",
                ),
                title_generation_enabled=_env_bool_default(
                    os.getenv("AITHRU_AGENT_PROCESSOR_TITLE_GENERATION_ENABLED"),
                    default=True,
                    name="AITHRU_AGENT_PROCESSOR_TITLE_GENERATION_ENABLED",
                ),
                title_max_words=_env_int(
                    os.getenv("AITHRU_AGENT_PROCESSOR_TITLE_MAX_WORDS"),
                    default=6,
                    name="AITHRU_AGENT_PROCESSOR_TITLE_MAX_WORDS",
                ),
                summarization_enabled=_env_bool_default(
                    os.getenv("AITHRU_AGENT_PROCESSOR_SUMMARIZATION_ENABLED"),
                    default=True,
                    name="AITHRU_AGENT_PROCESSOR_SUMMARIZATION_ENABLED",
                ),
                summarization_min_message_count=_env_int(
                    os.getenv("AITHRU_AGENT_PROCESSOR_SUMMARIZATION_MIN_MESSAGE_COUNT"),
                    default=6,
                    name="AITHRU_AGENT_PROCESSOR_SUMMARIZATION_MIN_MESSAGE_COUNT",
                ),
                memory_extraction_enabled=_env_bool_default(
                    os.getenv("AITHRU_AGENT_PROCESSOR_MEMORY_EXTRACTION_ENABLED"),
                    default=True,
                    name="AITHRU_AGENT_PROCESSOR_MEMORY_EXTRACTION_ENABLED",
                ),
            ),
        )


def _split_scopes(raw: str | None) -> list[str]:
    if raw is None:
        return ["*"]
    scopes = [scope.strip() for scope in raw.split(",")]
    if any(not scope for scope in scopes):
        raise ValueError("AITHRU_AGENT_API_SCOPES contains a blank scope")
    return scopes or ["*"]


def _env_bool(raw: str | None, *, name: str) -> bool:
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_bool_default(raw: str | None, *, default: bool, name: str) -> bool:
    if raw is None:
        return default
    return _env_bool(raw, name=name)


def _env_int(raw: str | None, *, default: int, name: str) -> int:
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _split_csv(raw: str | None, *, name: str) -> list[str]:
    if raw is None or not raw.strip():
        return []
    values = [value.strip() for value in raw.split(",")]
    if any(not value for value in values):
        raise ValueError(f"{name} contains a blank value")
    return values


def _parse_mcp_servers_json(raw: str | None) -> list[MCPServerSpec]:
    if raw is None or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON must be valid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON must be a JSON array")
    try:
        return [MCPServerSpec.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise ValueError(f"AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON is invalid: {exc}") from exc


def _parse_workflow_capabilities_json(raw: str | None) -> list[WorkflowCapabilitySpec]:
    if raw is None or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON must be valid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON must be a JSON array")
    try:
        return [WorkflowCapabilitySpec.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise ValueError(f"AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON is invalid: {exc}") from exc


def _normalize_host(value: str, *, label: str = "web allowed hosts") -> str:
    host = value.strip().lower().rstrip(".")
    if not host:
        raise ValueError(f"{label} cannot contain blank values")
    if any(char.isspace() for char in host) or "/" in host or ":" in host or "*" in host:
        raise ValueError(
            f"{label} must be host names without schemes, ports, or wildcards"
        )
    return host


def _url_host(value: str, *, label: str = "web search endpoint") -> str:
    from urllib.parse import urlsplit

    host = urlsplit(value).hostname
    if host is None:
        raise ValueError(f"{label} must include a host")
    return host.lower().rstrip(".")


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _mcp_server_endpoint_url(server: MCPServerSpec) -> str:
    metadata = server.metadata or {}
    value = metadata.get("endpoint_url")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"MCP server endpoint is required for server: {server.key}")
    endpoint = value.strip()
    if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
        raise ValueError("MCP server endpoint must use http or https")
    metadata["endpoint_url"] = endpoint
    server.metadata = metadata
    return endpoint
