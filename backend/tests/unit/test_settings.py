import json

import pytest

from aithru_agent.settings import (
    AgentExternalToolsSettings,
    AgentProcessorSettings,
    AgentSettings,
    AgentWorkflowCapabilitiesSettings,
)


def test_default_driver_is_pydantic_ai() -> None:
    settings = AgentSettings()

    assert settings.driver == "pydantic_ai"


def test_settings_is_pydantic_model() -> None:
    settings = AgentSettings()

    assert settings.model_dump()["driver"] == "pydantic_ai"


def test_processor_settings_default_to_deterministic_summarization_enabled() -> None:
    settings = AgentSettings()

    assert isinstance(settings.processors, AgentProcessorSettings)
    assert settings.processors.clarification_enabled is True
    assert settings.processors.title_generation_enabled is True
    assert settings.processors.title_max_words == 6
    assert settings.processors.summarization_enabled is True
    assert settings.processors.summarization_min_message_count == 6
    assert settings.processors.memory_extraction_enabled is True


def test_processor_settings_parse_title_generation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_PROCESSOR_TITLE_GENERATION_ENABLED", "false")
    monkeypatch.setenv("AITHRU_AGENT_PROCESSOR_TITLE_MAX_WORDS", "4")
    monkeypatch.setenv("AITHRU_AGENT_PROCESSOR_MEMORY_EXTRACTION_ENABLED", "false")

    settings = AgentSettings.from_env()

    assert settings.processors.title_generation_enabled is False
    assert settings.processors.title_max_words == 4
    assert settings.processors.memory_extraction_enabled is False


def test_external_tool_settings_are_pydantic_validated() -> None:
    settings = AgentSettings(
        external_tools={
            "web_enabled": True,
            "web_executor": "http",
            "web_search_executor": "http_json",
            "web_search_endpoint_url": "https://Search.Example.com/api/search",
            "web_allowed_hosts": ["Example.com"],
            "web_timeout_ms": 1_000,
            "web_max_fetch_bytes": 32_000,
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
            ],
        }
    )

    assert isinstance(settings.external_tools, AgentExternalToolsSettings)
    assert settings.external_tools.web_enabled is True
    assert settings.external_tools.web_executor == "http"
    assert settings.external_tools.web_search_executor == "http_json"
    assert settings.external_tools.web_search_endpoint_url == "https://Search.Example.com/api/search"
    assert settings.external_tools.web_allowed_hosts == ["example.com"]
    assert settings.external_tools.web_timeout_ms == 1_000
    assert settings.external_tools.web_max_fetch_bytes == 32_000
    assert settings.external_tools.mcp_servers[0].key == "search"
    assert settings.model_dump()["external_tools"]["mcp_servers"][0]["tools"][0]["name"] == "query"


def test_http_web_executor_requires_allowed_hosts() -> None:
    with pytest.raises(ValueError, match="allowed hosts"):
        AgentSettings(
            external_tools={
                "web_enabled": True,
                "web_executor": "http",
            }
        )


def test_http_json_search_executor_requires_endpoint() -> None:
    with pytest.raises(ValueError, match="search endpoint"):
        AgentSettings(
            external_tools={
                "web_enabled": True,
                "web_search_executor": "http_json",
                "web_allowed_hosts": ["example.com"],
            }
        )


def test_http_json_search_endpoint_must_be_allowlisted() -> None:
    with pytest.raises(ValueError, match="search endpoint host"):
        AgentSettings(
            external_tools={
                "web_enabled": True,
                "web_search_executor": "http_json",
                "web_search_endpoint_url": "https://search.example.com/api",
                "web_allowed_hosts": ["allowed.example"],
            }
        )


def test_external_tool_settings_reject_invalid_mcp_catalog() -> None:
    with pytest.raises(ValueError, match="MCP server key"):
        AgentSettings(
            external_tools={
                "mcp_servers": [
                    {
                        "key": "bad key",
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
            }
        )


def test_http_json_mcp_executor_requires_server_endpoint_and_allowed_hosts() -> None:
    mcp_server = {
        "key": "search",
        "metadata": {"endpoint_url": "http://127.0.0.1:9999/mcp"},
        "tools": [
            {
                "name": "query",
                "description": "Search documents.",
                "risk_level": "read",
                "approval_policy": "on_risk",
            }
        ],
    }

    with pytest.raises(ValueError, match="mcp allowed hosts"):
        AgentSettings(
            external_tools={
                "mcp_executor": "http_json",
                "mcp_servers": [mcp_server],
            }
        )

    with pytest.raises(ValueError, match="MCP server endpoint"):
        AgentSettings(
            external_tools={
                "mcp_executor": "http_json",
                "mcp_allowed_hosts": ["127.0.0.1"],
                "mcp_servers": [{**mcp_server, "metadata": None}],
            }
        )

    with pytest.raises(ValueError, match="MCP server endpoint host"):
        AgentSettings(
            external_tools={
                "mcp_executor": "http_json",
                "mcp_allowed_hosts": ["allowed.example"],
                "mcp_servers": [mcp_server],
            }
        )

    settings = AgentSettings(
        external_tools={
            "mcp_executor": "http_json",
            "mcp_allowed_hosts": ["127.0.0.1"],
            "mcp_timeout_ms": 1_000,
            "mcp_max_response_bytes": 64_000,
            "mcp_servers": [mcp_server],
        }
    )

    assert settings.external_tools.mcp_executor == "http_json"
    assert settings.external_tools.mcp_allowed_hosts == ["127.0.0.1"]
    assert settings.external_tools.mcp_timeout_ms == 1_000
    assert settings.external_tools.mcp_max_response_bytes == 64_000


def test_http_json_workflow_capability_requires_endpoint_catalog_and_allowed_hosts() -> None:
    capability = {
        "key": "report_review",
        "tool_name": "workflow.report_review",
        "description": "Run report review in Workbench.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "risk_level": "write",
        "required_scopes": ["workflow.capability.report_review.invoke"],
        "approval_policy": "never",
    }

    with pytest.raises(ValueError, match="workflow capabilities"):
        AgentSettings(
            workflow_capabilities={
                "executor": "http_json",
                "endpoint_url": "http://127.0.0.1:9999/capability-runs",
                "allowed_hosts": ["127.0.0.1"],
            }
        )

    with pytest.raises(ValueError, match="workflow capability endpoint"):
        AgentSettings(
            workflow_capabilities={
                "executor": "http_json",
                "allowed_hosts": ["127.0.0.1"],
                "capabilities": [capability],
            }
        )

    with pytest.raises(ValueError, match="workflow capability allowed hosts"):
        AgentSettings(
            workflow_capabilities={
                "executor": "http_json",
                "endpoint_url": "http://127.0.0.1:9999/capability-runs",
                "capabilities": [capability],
            }
        )

    with pytest.raises(ValueError, match="workflow capability endpoint host"):
        AgentSettings(
            workflow_capabilities={
                "executor": "http_json",
                "endpoint_url": "http://127.0.0.1:9999/capability-runs",
                "allowed_hosts": ["allowed.example"],
                "capabilities": [capability],
            }
        )

    settings = AgentSettings(
        workflow_capabilities={
            "executor": "http_json",
            "endpoint_url": "http://127.0.0.1:9999/capability-runs",
            "allowed_hosts": ["127.0.0.1"],
            "timeout_ms": 1_000,
            "max_response_bytes": 64_000,
            "capabilities": [capability],
        }
    )

    assert isinstance(settings.workflow_capabilities, AgentWorkflowCapabilitiesSettings)
    assert settings.workflow_capabilities.executor == "http_json"
    assert settings.workflow_capabilities.endpoint_url == "http://127.0.0.1:9999/capability-runs"
    assert settings.workflow_capabilities.allowed_hosts == ["127.0.0.1"]
    assert settings.workflow_capabilities.timeout_ms == 1_000
    assert settings.workflow_capabilities.max_response_bytes == 64_000
    assert settings.workflow_capabilities.capabilities[0].key == "report_review"


def test_blank_model_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="model"):
        AgentSettings(model=" ")


def test_unsupported_persistence_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="persistence"):
        AgentSettings(persistence_backend="postgres")  # type: ignore[arg-type]


def test_env_api_scopes_rejects_blank_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_API_SCOPES", "agent.workspace.read,,agent.memory.read")

    with pytest.raises(ValueError, match="AITHRU_AGENT_API_SCOPES"):
        AgentSettings.from_env()


def test_env_external_mcp_servers_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON", "{not-json")

    with pytest.raises(ValueError, match="AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON"):
        AgentSettings.from_env()


def test_scripted_driver_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_DRIVER", "scripted")

    with pytest.raises(ValueError, match="scripted driver has been removed"):
        AgentSettings.from_env()


def test_settings_load_driver_model_and_instructions_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_DRIVER", "pydantic_ai")
    monkeypatch.setenv("AITHRU_AGENT_MODEL", "test")
    monkeypatch.setenv("AITHRU_AGENT_TEST_MODEL_OUTPUT", "configured")
    monkeypatch.setenv("AITHRU_AGENT_INSTRUCTIONS", "Use controlled tools only.")
    monkeypatch.setenv("AITHRU_AGENT_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("AITHRU_AGENT_SQLITE_PATH", "/tmp/aithru-agent.sqlite")
    monkeypatch.setenv("AITHRU_AGENT_PROCESSOR_CLARIFICATION_ENABLED", "false")
    monkeypatch.setenv("AITHRU_AGENT_PROCESSOR_SUMMARIZATION_ENABLED", "false")
    monkeypatch.setenv("AITHRU_AGENT_PROCESSOR_SUMMARIZATION_MIN_MESSAGE_COUNT", "12")
    monkeypatch.setenv("AITHRU_AGENT_API_TOKEN", "secret-token")
    monkeypatch.setenv("AITHRU_AGENT_API_SCOPES", "agent.workspace.read, agent.memory.read")
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_WEB_ENABLED", "true")
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_WEB_EXECUTOR", "http")
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_WEB_SEARCH_EXECUTOR", "http_json")
    monkeypatch.setenv(
        "AITHRU_AGENT_EXTERNAL_WEB_SEARCH_ENDPOINT_URL",
        "https://search.example.com/api/search",
    )
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_WEB_ALLOWED_HOSTS", "Example.com, www.example.com")
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_WEB_TIMEOUT_MS", "2500")
    monkeypatch.setenv("AITHRU_AGENT_EXTERNAL_WEB_MAX_FETCH_BYTES", "64000")
    monkeypatch.setenv(
        "AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON",
        json.dumps(
            [
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
        ),
    )
    monkeypatch.setenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_EXECUTOR", "http_json")
    monkeypatch.setenv(
        "AITHRU_AGENT_WORKFLOW_CAPABILITY_ENDPOINT_URL",
        "https://workflow.example.com/api/capability-runs",
    )
    monkeypatch.setenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_ALLOWED_HOSTS", "workflow.example.com")
    monkeypatch.setenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_TIMEOUT_MS", "3500")
    monkeypatch.setenv("AITHRU_AGENT_WORKFLOW_CAPABILITY_MAX_RESPONSE_BYTES", "128000")
    monkeypatch.setenv(
        "AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON",
        json.dumps(
            [
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
            ]
        ),
    )

    settings = AgentSettings.from_env()

    assert settings.driver == "pydantic_ai"
    assert settings.model == "test"
    assert settings.test_model_output == "configured"
    assert settings.instructions == "Use controlled tools only."
    assert settings.persistence_backend == "sqlite"
    assert settings.sqlite_path == "/tmp/aithru-agent.sqlite"
    assert settings.processors.clarification_enabled is False
    assert settings.processors.summarization_enabled is False
    assert settings.processors.summarization_min_message_count == 12
    assert settings.api_token == "secret-token"
    assert settings.api_scopes == ["agent.workspace.read", "agent.memory.read"]
    assert settings.external_tools.web_enabled is True
    assert settings.external_tools.web_executor == "http"
    assert settings.external_tools.web_search_executor == "http_json"
    assert (
        settings.external_tools.web_search_endpoint_url
        == "https://search.example.com/api/search"
    )
    assert settings.external_tools.web_allowed_hosts == ["example.com", "www.example.com"]
    assert settings.external_tools.web_timeout_ms == 2_500
    assert settings.external_tools.web_max_fetch_bytes == 64_000
    assert settings.external_tools.mcp_servers[0].key == "search"
    assert settings.workflow_capabilities.executor == "http_json"
    assert settings.workflow_capabilities.endpoint_url == (
        "https://workflow.example.com/api/capability-runs"
    )
    assert settings.workflow_capabilities.allowed_hosts == ["workflow.example.com"]
    assert settings.workflow_capabilities.timeout_ms == 3_500
    assert settings.workflow_capabilities.max_response_bytes == 128_000
    assert settings.workflow_capabilities.capabilities[0].key == "report_review"
