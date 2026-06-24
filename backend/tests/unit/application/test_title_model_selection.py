from pydantic_ai.models.test import TestModel

from aithru_agent.application.runtime import _resolve_title_model_for_run
from aithru_agent.domain import (
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunSource,
    AgentRunStatus,
)
from aithru_agent.settings import AgentSettings


def test_title_model_prefers_run_model_over_global_default() -> None:
    run = _make_run(
        harness_options=AgentRunHarnessOptions(model="run-selected-model"),
    )

    model = _resolve_title_model_for_run(
        run,
        settings=AgentSettings(model="test", test_model_output="Done"),
        model_profile_resolver=lambda org_id, key: None,
        profile_model_factory=lambda profile: profile.model,
    )

    assert model == "run-selected-model"


def test_title_model_uses_global_default_when_run_has_no_model() -> None:
    model = _resolve_title_model_for_run(
        _make_run(),
        settings=AgentSettings(model="test", test_model_output="Fallback Title"),
        model_profile_resolver=lambda org_id, key: None,
        profile_model_factory=lambda profile: profile.model,
    )

    assert isinstance(model, TestModel)


def _make_run(
    *,
    harness_options: AgentRunHarnessOptions | None = None,
) -> AgentRun:
    return AgentRun(
        id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        source=AgentRunSource.CHAT,
        thread_id="thread_1",
        workspace_id="ws_1",
        task_msg="Create a useful title",
        scopes=["*"],
        harness_options=harness_options,
        status=AgentRunStatus.COMPLETED,
        started_at="2026-06-24T00:00:00Z",
    )
