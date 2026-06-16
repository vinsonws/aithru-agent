from aithru_agent.settings import AgentSettings


def test_settings_load_driver_model_and_instructions_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AITHRU_AGENT_DRIVER", "pydantic_ai")
    monkeypatch.setenv("AITHRU_AGENT_MODEL", "test")
    monkeypatch.setenv("AITHRU_AGENT_TEST_MODEL_OUTPUT", "configured")
    monkeypatch.setenv("AITHRU_AGENT_INSTRUCTIONS", "Use controlled tools only.")
    monkeypatch.setenv("AITHRU_AGENT_PERSISTENCE_BACKEND", "sqlite")
    monkeypatch.setenv("AITHRU_AGENT_SQLITE_PATH", "/tmp/aithru-agent.sqlite")

    settings = AgentSettings.from_env()

    assert settings.driver == "pydantic_ai"
    assert settings.model == "test"
    assert settings.test_model_output == "configured"
    assert settings.instructions == "Use controlled tools only."
    assert settings.persistence_backend == "sqlite"
    assert settings.sqlite_path == "/tmp/aithru-agent.sqlite"
