from aithru_agent.domain import (
    AgentModelCapabilities,
    AgentModelProfileEntry,
    AgentModelProviderKind,
)
from aithru_agent.model_profiles.factory import _model_settings


def test_model_profile_factory_reads_generation_settings_from_metadata() -> None:
    profile = AgentModelProfileEntry(
        org_id="org_1",
        key="custom-minimax-m2-7",
        name="MiniMax M2.7 Local",
        provider=AgentModelProviderKind.CUSTOM,
        model="custom:MiniMax-M2.7",
        metadata={
            "base_url": "http://192.168.1.175:8000/v1",
            "stream_usage": True,
            "max_tokens": 98304,
            "temperature": 1.0,
            "top_p": 0.95,
        },
        id="model_profile_1",
        created_at="2026-06-23T00:00:00Z",
        updated_at="2026-06-23T00:00:00Z",
    )

    assert _model_settings(profile) == {
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 98304,
        "extra_body": {"stream_options": {"include_usage": True}},
    }


def test_model_profile_factory_does_not_enable_thinking_from_capability() -> None:
    profile = AgentModelProfileEntry(
        org_id="org_1",
        key="custom-deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        provider=AgentModelProviderKind.CUSTOM,
        model="custom:deepseek-v4-flash",
        capabilities=AgentModelCapabilities(thinking=True),
        metadata={"base_url": "https://api.deepseek.com/v1"},
        id="model_profile_1",
        created_at="2026-06-23T00:00:00Z",
        updated_at="2026-06-23T00:00:00Z",
    )

    assert _model_settings(profile) is None
