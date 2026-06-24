import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.settings import AgentSettings


def model_profile_payload(*, key: str = "fast", org_id: str = "org_1") -> dict:
    return {
        "org_id": org_id,
        "key": key,
        "name": "Fast profile",
        "provider": "openai",
        "model": "openai:gpt-4.1-mini",
        "enabled": True,
        "capabilities": {"vision": True, "thinking": True},
        "cost_policy": {
            "input_cost_per_million_tokens_usd": 0.15,
            "output_cost_per_million_tokens_usd": 0.6,
            "max_run_cost_usd": 0.5,
        },
        "selection_policy": {
            "required_scopes": ["agent.model.fast"],
            "max_total_tokens": 2_000,
        },
    }


@pytest.mark.asyncio
async def test_model_profile_api_manages_profiles_and_openapi_contracts() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/api/model-profiles",
            json=model_profile_payload(),
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        assert create_response.status_code == 201
        created = create_response.json()

        list_response = await client.get(
            "/api/model-profiles",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        detail_response = await client.get(
            "/api/model-profiles/fast",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        org_2_detail_response = await client.get(
            "/api/model-profiles/fast",
            headers={"X-Aithru-Org-Id": "org_2"},
        )
        conflict_response = await client.get(
            "/api/model-profiles",
            params={"org_id": "org_2"},
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        patch_response = await client.patch(
            "/api/model-profiles/fast",
            json={"name": "Fast profile v2", "provider": "custom"},
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        disable_response = await client.post(
            "/api/model-profiles/fast/disable",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        enable_response = await client.post(
            "/api/model-profiles/fast/enable",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        openapi = (await client.get("/openapi.json")).json()

    assert created["id"].startswith("model_profile_")
    assert created["capabilities"] == {"vision": True, "thinking": True}
    assert list_response.json()[0]["key"] == "fast"
    assert detail_response.json()["model"] == "openai:gpt-4.1-mini"
    assert org_2_detail_response.status_code == 404
    assert conflict_response.status_code == 403
    assert patch_response.json()["name"] == "Fast profile v2"
    assert patch_response.json()["provider"] == "custom"
    assert disable_response.json()["enabled"] is False
    assert enable_response.json()["enabled"] is True
    assert "AgentModelProfileEntry" in openapi["components"]["schemas"]
    assert "CreateModelProfileRequest" in openapi["components"]["schemas"]
    assert "/api/model-profiles" in openapi["paths"]


@pytest.mark.asyncio
async def test_model_profile_api_saves_write_only_api_key_without_returning_secret() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)
    payload = model_profile_payload()
    payload["auth_secret"] = {"write_only_value": "sk-super-secret-model-key"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/api/model-profiles",
            json=payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        assert create_response.status_code == 201
        list_response = await client.get(
            "/api/model-profiles",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        detail_response = await client.get(
            "/api/model-profiles/fast",
            headers={"X-Aithru-Org-Id": "org_1"},
        )

    expected_secret = {
        "has_secret": True,
        "secret_ref": "secret://model-profiles/org_1/fast/api-key",
        "redacted": True,
    }
    assert create_response.json()["auth_secret"] == expected_secret
    assert list_response.json()[0]["auth_secret"] == expected_secret
    assert detail_response.json()["auth_secret"] == expected_secret
    assert "sk-super-secret-model-key" not in create_response.text
    assert "sk-super-secret-model-key" not in list_response.text
    assert runtime.secret_store.get_secret(expected_secret["secret_ref"]) == (
        "sk-super-secret-model-key"
    )


@pytest.mark.asyncio
async def test_model_profile_api_rejects_invalid_secret_ref() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)
    payload = model_profile_payload()
    payload["auth_secret"] = {"secret_ref": "not-a-secret-ref"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/model-profiles",
            json=payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )

    assert response.status_code == 422
    assert "secret://" in response.json()["detail"]


@pytest.mark.asyncio
async def test_model_profile_api_avoids_concatenated_org_key_id_collisions() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_payload = model_profile_payload(key="c", org_id="a_b")
        second_payload = model_profile_payload(key="b_c", org_id="a")
        first = await client.post(
            "/api/model-profiles",
            json=first_payload,
            headers={"X-Aithru-Org-Id": "a_b"},
        )
        second = await client.post(
            "/api/model-profiles",
            json=second_payload,
            headers={"X-Aithru-Org-Id": "a"},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_run_creation_selects_model_profile_and_applies_policy_defaults() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/model-profiles",
            json=model_profile_payload(),
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        run_response = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Use managed model",
                "scopes": ["agent.model.fast"],
                "harness_options": {"model_profile_key": "fast"},
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )

    assert run_response.status_code == 201
    harness_options = run_response.json()["harness_options"]
    assert harness_options["model_profile_key"] == "fast"
    assert harness_options["model"] == "openai:gpt-4.1-mini"
    assert harness_options["model_capabilities"] == {"vision": True, "thinking": True}
    assert harness_options["budget_policy"]["max_total_tokens"] == 2_000
    assert harness_options["model_cost_policy"]["input_cost_per_million_tokens_usd"] == 0.15
    assert harness_options["model_cost_policy"]["output_cost_per_million_tokens_usd"] == 0.6
    assert harness_options["model_cost_policy"]["max_cost_usd"] == 0.5


@pytest.mark.asyncio
async def test_run_creation_rejects_model_profile_policy_violations() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/model-profiles",
            json=model_profile_payload(),
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        no_scope = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "No scope",
                "scopes": ["agent.workspace.read"],
                "harness_options": {"model_profile_key": "fast"},
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        wildcard_scope = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Wildcard scope",
                "scopes": ["*"],
                "harness_options": {"model_profile_key": "fast"},
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        raw_model = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Raw model",
                "harness_options": {"model": "openai:gpt-4.1"},
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        default_model = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Default model",
                "harness_options": {"model": "test"},
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        token_over = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Too many tokens",
                "scopes": ["agent.model.fast"],
                "harness_options": {
                    "model_profile_key": "fast",
                    "budget_policy": {"max_total_tokens": 2_001},
                },
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        cost_over = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Too much cost",
                "scopes": ["agent.model.fast"],
                "harness_options": {
                    "model_profile_key": "fast",
                    "model_cost_policy": {"max_cost_usd": 0.51},
                },
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        model_conflict = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Wrong model",
                "scopes": ["agent.model.fast"],
                "harness_options": {
                    "model_profile_key": "fast",
                    "model": "openai:gpt-4.1",
                },
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )

        limited_profile = model_profile_payload(key="limited")
        limited_profile["capabilities"] = {"vision": False, "thinking": False}
        limited_profile["selection_policy"]["required_scopes"] = ["agent.model.limited"]
        await client.post(
            "/api/model-profiles",
            json=limited_profile,
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        vision_denied = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Need vision",
                "scopes": ["agent.model.limited"],
                "harness_options": {
                    "model_profile_key": "limited",
                    "model_capabilities": {"vision": True},
                },
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        thinking_denied = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Need thinking",
                "scopes": ["agent.model.limited"],
                "harness_options": {
                    "model_profile_key": "limited",
                    "model_reasoning_effort": "medium",
                },
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )
        await client.post(
            "/api/model-profiles/fast/disable",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        disabled = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Disabled",
                "scopes": ["agent.model.fast"],
                "harness_options": {"model_profile_key": "fast"},
            },
            headers={"X-Aithru-Org-Id": "org_1", "X-Aithru-User-Id": "user_1"},
        )

    assert no_scope.status_code == 403
    assert wildcard_scope.status_code == 201
    assert raw_model.status_code == 403
    assert default_model.status_code == 201
    assert token_over.status_code == 403
    assert cost_over.status_code == 403
    assert model_conflict.status_code == 409
    assert vision_denied.status_code == 403
    assert thinking_denied.status_code == 403
    assert disabled.status_code == 403


@pytest.mark.asyncio
async def test_model_profile_api_persists_profiles_in_sqlite_mode(tmp_path) -> None:
    db_path = tmp_path / "agent.sqlite"
    settings = AgentSettings(
        model="test",
        persistence_backend="sqlite",
        sqlite_path=str(db_path),
    )
    app = create_app(create_agent_runtime(settings=settings))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/api/model-profiles",
            json=model_profile_payload(),
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        assert create_response.status_code == 201

    reloaded_app = create_app(create_agent_runtime(settings=settings))
    async with AsyncClient(
        transport=ASGITransport(app=reloaded_app),
        base_url="http://test",
    ) as client:
        detail_response = await client.get(
            "/api/model-profiles/fast",
            headers={"X-Aithru-Org-Id": "org_1"},
        )

    assert detail_response.status_code == 200
    assert detail_response.json()["model"] == "openai:gpt-4.1-mini"


@pytest.mark.asyncio
async def test_model_profile_api_persists_write_only_api_key_in_sqlite_mode(tmp_path) -> None:
    db_path = tmp_path / "agent.sqlite"
    settings = AgentSettings(
        model="test",
        persistence_backend="sqlite",
        sqlite_path=str(db_path),
    )
    runtime = create_agent_runtime(settings=settings)
    app = create_app(runtime)
    payload = model_profile_payload()
    payload["auth_secret"] = {"write_only_value": "sk-sqlite-secret-model-key"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post(
            "/api/model-profiles",
            json=payload,
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        assert create_response.status_code == 201

    reloaded_runtime = create_agent_runtime(settings=settings)
    reloaded_app = create_app(reloaded_runtime)
    async with AsyncClient(
        transport=ASGITransport(app=reloaded_app),
        base_url="http://test",
    ) as client:
        detail_response = await client.get(
            "/api/model-profiles/fast",
            headers={"X-Aithru-Org-Id": "org_1"},
        )

    secret_ref = detail_response.json()["auth_secret"]["secret_ref"]
    assert detail_response.status_code == 200
    assert "sk-sqlite-secret-model-key" not in detail_response.text
    assert reloaded_runtime.secret_store.get_secret(secret_ref) == "sk-sqlite-secret-model-key"
