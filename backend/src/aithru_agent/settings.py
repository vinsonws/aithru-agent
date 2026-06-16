import os
from dataclasses import dataclass
from typing import Literal, cast


AgentDriverKind = Literal["scripted", "pydantic_ai"]


@dataclass(frozen=True)
class AgentSettings:
    driver: AgentDriverKind = "scripted"
    model: str | None = None
    instructions: str = "You are Aithru Agent. Use controlled tools only."
    test_model_output: str = "Done."

    @classmethod
    def from_env(cls) -> "AgentSettings":
        driver = os.getenv("AITHRU_AGENT_DRIVER", cls.driver)
        if driver not in {"scripted", "pydantic_ai"}:
            raise ValueError(f"Unsupported AITHRU_AGENT_DRIVER: {driver}")
        return cls(
            driver=cast(AgentDriverKind, driver),
            model=os.getenv("AITHRU_AGENT_MODEL"),
            instructions=os.getenv("AITHRU_AGENT_INSTRUCTIONS", cls.instructions),
            test_model_output=os.getenv("AITHRU_AGENT_TEST_MODEL_OUTPUT", cls.test_model_output),
        )
