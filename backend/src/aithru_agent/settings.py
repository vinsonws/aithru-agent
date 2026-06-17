import os
from dataclasses import dataclass, field
from typing import Literal, cast


AgentDriverKind = Literal["pydantic_ai"]
AgentPersistenceBackend = Literal["memory", "sqlite"]


@dataclass(frozen=True)
class AgentSettings:
    driver: AgentDriverKind = "pydantic_ai"
    persistence_backend: AgentPersistenceBackend = "memory"
    sqlite_path: str = ".aithru/agent.sqlite"
    model: str | None = None
    instructions: str = "You are Aithru Agent. Use controlled tools only."
    test_model_output: str = "Done."
    api_token: str | None = None
    api_scopes: list[str] = field(default_factory=lambda: ["*"])

    @classmethod
    def from_env(cls) -> "AgentSettings":
        driver = os.getenv("AITHRU_AGENT_DRIVER", cls.driver)
        if driver == "scripted":
            raise ValueError(
                "The scripted driver has been removed; use AITHRU_AGENT_MODEL=test "
                "for deterministic tests"
            )
        if driver != "pydantic_ai":
            raise ValueError(f"Unsupported AITHRU_AGENT_DRIVER: {driver}")
        persistence_backend = os.getenv("AITHRU_AGENT_PERSISTENCE_BACKEND", cls.persistence_backend)
        if persistence_backend not in {"memory", "sqlite"}:
            raise ValueError(f"Unsupported AITHRU_AGENT_PERSISTENCE_BACKEND: {persistence_backend}")
        return cls(
            driver=cast(AgentDriverKind, driver),
            persistence_backend=cast(AgentPersistenceBackend, persistence_backend),
            sqlite_path=os.getenv("AITHRU_AGENT_SQLITE_PATH", cls.sqlite_path),
            model=os.getenv("AITHRU_AGENT_MODEL"),
            instructions=os.getenv("AITHRU_AGENT_INSTRUCTIONS", cls.instructions),
            test_model_output=os.getenv("AITHRU_AGENT_TEST_MODEL_OUTPUT", cls.test_model_output),
            api_token=os.getenv("AITHRU_AGENT_API_TOKEN"),
            api_scopes=_split_scopes(os.getenv("AITHRU_AGENT_API_SCOPES")),
        )


def _split_scopes(raw: str | None) -> list[str]:
    if raw is None:
        return ["*"]
    scopes = [scope.strip() for scope in raw.split(",") if scope.strip()]
    return scopes or ["*"]
