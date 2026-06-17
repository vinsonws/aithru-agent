import pytest

from aithru_agent.settings import AgentSettings


def test_default_driver_is_pydantic_ai() -> None:
    settings = AgentSettings()

    assert settings.driver == "pydantic_ai"


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
    monkeypatch.setenv("AITHRU_AGENT_API_TOKEN", "secret-token")
    monkeypatch.setenv("AITHRU_AGENT_API_SCOPES", "agent.workspace.read, agent.memory.read")

    settings = AgentSettings.from_env()

    assert settings.driver == "pydantic_ai"
    assert settings.model == "test"
    assert settings.test_model_output == "configured"
    assert settings.instructions == "Use controlled tools only."
    assert settings.persistence_backend == "sqlite"
    assert settings.sqlite_path == "/tmp/aithru-agent.sqlite"
    assert settings.api_token == "secret-token"
    assert settings.api_scopes == ["agent.workspace.read", "agent.memory.read"]
