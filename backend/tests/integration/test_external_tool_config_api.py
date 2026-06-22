import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings


def mcp_config_payload(*, key: str = "search", org_id: str = "org_1") -> dict:
    return {
        "org_id": org_id,
        "key": key,
        "provider_kind": "mcp",
        "name": "Search MCP",
        "enabled": True,
        "mcp": {
            "server_key": key,
            "name": "Search Tools",
            "endpoint": {
                "url": "https://mcp.example.com/rpc",
                "allowed_hosts": ["mcp.example.com"],
                "timeout_ms": 1_000,
                "max_response_bytes": 100_000,
                "auth_secret": {
                    "secret_ref": f"secret://external-tools/{org_id}/{key}/endpoint-auth"
                },
            },
            "tools": [
                {
                    "name": "query",
                    "description": "Search an indexed corpus.",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "risk_level": "read",
                    "required_scopes": ["agent.external.mcp.search.query"],
                    "approval_policy": "never",
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_external_tool_config_api_manages_mcp_config_without_returning_secret() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/api/external-tools/configs",
            json=mcp_config_payload(),
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_admin"},
        )
        assert create_response.status_code == 201
        created = create_response.json()

        assert created["org_id"] == "org_1"
        assert created["key"] == "search"
        assert created["provider_kind"] == "mcp"
        assert created["enabled"] is True
        assert created["activation_status"] == "pending_runtime_reload"
        assert created["mcp"]["endpoint"]["auth_secret"] == {
            "has_secret": True,
            "secret_ref": "secret://external-tools/org_1/search/endpoint-auth",
            "redacted": True,
        }
        assert created["audit"][-1]["action"] == "created"
        assert created["audit"][-1]["actor_user_id"] == "user_admin"

        listed = (
            await client.get(
                "/api/external-tools/configs",
                headers={"X-Aithru-Org-Id": "org_1"},
            )
        ).json()
        assert [item["key"] for item in listed] == ["search"]

        detail = (
            await client.get(
                "/api/external-tools/configs/search",
                headers={"X-Aithru-Org-Id": "org_1"},
            )
        ).json()
        assert detail["mcp"]["tools"][0]["name"] == "query"

        patch_response = await client.patch(
            "/api/external-tools/configs/search",
            json={"name": "Search MCP v2"},
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_owner"},
        )
        assert patch_response.status_code == 200
        patched = patch_response.json()
        assert patched["name"] == "Search MCP v2"
        assert [event["action"] for event in patched["audit"]] == ["created", "updated"]
        assert patched["updated_by"] == "user_owner"


@pytest.mark.asyncio
async def test_external_tool_config_api_rejects_invalid_allowed_hosts_and_endpoints() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        wildcard_payload = mcp_config_payload()
        wildcard_payload["mcp"]["endpoint"]["allowed_hosts"] = ["*.example.com"]
        wildcard_response = await client.post(
            "/api/external-tools/configs",
            json=wildcard_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        disallowed_payload = mcp_config_payload(key="search2")
        disallowed_payload["mcp"]["endpoint"]["url"] = "https://evil.example.com/rpc"
        disallowed_payload["mcp"]["endpoint"]["allowed_hosts"] = ["mcp.example.com"]
        disallowed_response = await client.post(
            "/api/external-tools/configs",
            json=disallowed_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        blank_scope_payload = mcp_config_payload(key="search3")
        blank_scope_payload["mcp"]["tools"][0]["required_scopes"] = [" "]
        blank_scope_response = await client.post(
            "/api/external-tools/configs",
            json=blank_scope_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        credential_url_payload = mcp_config_payload(key="search4")
        credential_url_payload["mcp"]["endpoint"]["url"] = (
            "https://user:pass@mcp.example.com/rpc"
        )
        credential_url_response = await client.post(
            "/api/external-tools/configs",
            json=credential_url_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        assert wildcard_response.status_code == 422
        assert disallowed_response.status_code == 422
        assert blank_scope_response.status_code == 422
        assert credential_url_response.status_code == 422
        assert "pass" not in credential_url_response.text
        assert (await client.get("/api/external-tools/configs")).json() == []


@pytest.mark.asyncio
async def test_external_tool_config_api_rejects_raw_or_unsupported_secret_inputs() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_ref_payload = mcp_config_payload(key="rawref")
        raw_ref_payload["mcp"]["endpoint"]["auth_secret"] = {
            "secret_ref": "plain-token-value"
        }
        raw_ref_response = await client.post(
            "/api/external-tools/configs",
            json=raw_ref_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        write_only_payload = mcp_config_payload(key="writeonly")
        write_only_payload["mcp"]["endpoint"]["auth_secret"] = {
            "write_only_value": "super-secret-token"
        }
        write_only_response = await client.post(
            "/api/external-tools/configs",
            json=write_only_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        assert raw_ref_response.status_code == 422
        assert "plain-token-value" not in raw_ref_response.text
        assert write_only_response.status_code == 422
        assert "super-secret-token" not in write_only_response.text
        assert (await client.get("/api/external-tools/configs")).json() == []


@pytest.mark.asyncio
async def test_external_tool_config_api_rejects_unsafe_tool_policy_and_schema() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dangerous_payload = mcp_config_payload(key="dangerous")
        dangerous_payload["mcp"]["tools"][0]["risk_level"] = "dangerous"
        dangerous_payload["mcp"]["tools"][0]["approval_policy"] = "never"
        dangerous_response = await client.post(
            "/api/external-tools/configs",
            json=dangerous_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        invalid_schema_payload = mcp_config_payload(key="schema")
        invalid_schema_payload["mcp"]["tools"][0]["input_schema"] = {
            "type": "object",
            "properties": "not-an-object",
        }
        invalid_schema_response = await client.post(
            "/api/external-tools/configs",
            json=invalid_schema_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        assert dangerous_response.status_code == 422
        assert invalid_schema_response.status_code == 422
        assert (await client.get("/api/external-tools/configs")).json() == []


@pytest.mark.asyncio
async def test_external_tool_config_api_enable_disable_and_reset_cache_are_audited() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/external-tools/configs",
            json=mcp_config_payload(),
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "creator"},
        )

        disable_response = await client.post(
            "/api/external-tools/configs/search/disable",
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "operator"},
        )
        enable_response = await client.post(
            "/api/external-tools/configs/search/enable",
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "operator"},
        )
        reset_response = await client.post(
            "/api/external-tools/configs/search/reset-cache",
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "operator"},
        )

        assert disable_response.status_code == 200
        disabled = disable_response.json()
        assert disabled["action"] == "disabled"
        assert disabled["config"]["enabled"] is False
        assert disabled["audit_event"]["actor_user_id"] == "operator"

        assert enable_response.status_code == 200
        enabled = enable_response.json()
        assert enabled["action"] == "enabled"
        assert enabled["config"]["enabled"] is True
        assert enabled["config"]["activation_status"] == "pending_runtime_reload"

        assert reset_response.status_code == 200
        reset = reset_response.json()
        assert reset["action"] == "reset_cache"
        assert reset["cache_status"]["status"] == "empty"
        assert reset["cache_status"]["last_reset_at"] == reset["reset_at"]
        assert reset["audit_event"]["actor_user_id"] == "operator"
        assert [event["action"] for event in reset["config"]["audit"]] == [
            "created",
            "disabled",
            "enabled",
            "reset_cache",
        ]


@pytest.mark.asyncio
async def test_external_tool_config_api_isolates_configs_by_org() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        org_1_payload = mcp_config_payload(key="search", org_id="org_1")
        org_2_payload = mcp_config_payload(key="search", org_id="org_2")

        await client.post(
            "/api/external-tools/configs",
            json=org_1_payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        await client.post(
            "/api/external-tools/configs",
            json=org_2_payload,
            headers={"X-Aithru-Org-Id": "org_2"},
        )

        org_1_list = (
            await client.get(
                "/api/external-tools/configs",
                headers={"X-Aithru-Org-Id": "org_1"},
            )
        ).json()
        org_2_detail = (
            await client.get(
                "/api/external-tools/configs/search",
                headers={"X-Aithru-Org-Id": "org_2"},
            )
        ).json()
        conflict_response = await client.get(
            "/api/external-tools/configs",
            params={"org_id": "org_2"},
            headers={"X-Aithru-Org-Id": "org_1"},
        )

        assert [item["org_id"] for item in org_1_list] == ["org_1"]
        assert org_2_detail["org_id"] == "org_2"
        assert conflict_response.status_code == 403


@pytest.mark.asyncio
async def test_external_tool_config_api_openapi_exposes_typed_contracts() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi = (await client.get("/openapi.json")).json()

    schemas = openapi["components"]["schemas"]
    assert "AgentExternalToolConfigEntry" in schemas
    assert "AgentExternalToolSecretStatus" in schemas
    assert "CreateExternalToolConfigRequest" in schemas
    assert "UpdateExternalToolConfigRequest" in schemas
    assert schemas["ExternalToolSecretInput"]["properties"]["write_only_value"][
        "writeOnly"
    ] is True
    assert "/api/external-tools/configs" in openapi["paths"]
    assert "/api/external-tools/configs/{config_id_or_key}" in openapi["paths"]
    assert "/api/external-tools/configs/{config_id_or_key}/enable" in openapi["paths"]
    assert "/api/external-tools/configs/{config_id_or_key}/disable" in openapi["paths"]
    assert "/api/external-tools/configs/{config_id_or_key}/reset-cache" in openapi["paths"]


@pytest.mark.asyncio
async def test_external_tool_config_api_persists_configs_in_sqlite_mode(tmp_path) -> None:
    db_path = tmp_path / "agent.sqlite"
    settings = AgentSettings(
        model="test",
        persistence_backend="sqlite",
        sqlite_path=str(db_path),
    )
    app = create_app(create_agent_runtime(settings=settings))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/api/external-tools/configs",
            json=mcp_config_payload(),
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        assert create_response.status_code == 201

    reloaded_app = create_app(create_agent_runtime(settings=settings))
    async with AsyncClient(
        transport=ASGITransport(app=reloaded_app),
        base_url="http://test",
    ) as client:
        detail_response = await client.get(
            "/api/external-tools/configs/search",
            headers={"X-Aithru-Org-Id": "org_1"},
        )

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["key"] == "search"
    assert detail["mcp"]["endpoint"]["auth_secret"]["has_secret"] is True
