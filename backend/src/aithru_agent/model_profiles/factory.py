from __future__ import annotations

from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings

from aithru_agent.domain import AgentModelProfileEntry, AgentModelProviderKind
from aithru_agent.secrets import AgentSecretStore


def create_model_from_profile(
    profile: AgentModelProfileEntry,
    *,
    secret_store: AgentSecretStore,
    test_model_output: str,
) -> str | object:
    if profile.provider == AgentModelProviderKind.TEST or profile.model == "test":
        return TestModel(call_tools=[], custom_output_text=test_model_output)

    api_key = _profile_api_key(profile, secret_store)
    model_name = _strip_provider_prefix(profile.model, profile.provider)
    base_url = _metadata_string(profile.metadata, "base_url")
    model_settings = _model_settings(profile)

    if profile.provider == AgentModelProviderKind.OPENAI:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(api_key=api_key, base_url=base_url),
            settings=model_settings,
        )

    if profile.provider == AgentModelProviderKind.ANTHROPIC:
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            model_name,
            provider=AnthropicProvider(api_key=api_key, base_url=base_url),
            settings=model_settings,
        )

    if profile.provider == AgentModelProviderKind.CUSTOM and base_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(api_key=api_key, base_url=base_url),
            settings=model_settings,
        )

    return profile.model


def _profile_api_key(
    profile: AgentModelProfileEntry,
    secret_store: AgentSecretStore,
) -> str | None:
    secret_ref = profile.auth_secret.secret_ref if profile.auth_secret else None
    if secret_ref is None:
        return None
    return secret_store.get_secret(secret_ref)


def _strip_provider_prefix(model: str, provider: AgentModelProviderKind) -> str:
    prefix = f"{provider.value}:"
    return model[len(prefix) :] if model.startswith(prefix) else model


def _metadata_string(metadata: dict | None, key: str) -> str | None:
    value = (metadata or {}).get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _model_settings(profile: AgentModelProfileEntry) -> ModelSettings | None:
    metadata = profile.metadata or {}
    settings: ModelSettings = {}

    temperature = _metadata_float(metadata, "temperature")
    if temperature is not None:
        settings["temperature"] = temperature

    top_p = _metadata_float(metadata, "top_p")
    if top_p is not None:
        settings["top_p"] = top_p

    max_tokens = _metadata_int(metadata, "max_tokens")
    if max_tokens is not None:
        settings["max_tokens"] = max_tokens

    if _metadata_bool(metadata, "stream_usage"):
        settings["extra_body"] = {"stream_options": {"include_usage": True}}

    return settings or None


def _metadata_float(metadata: dict, key: str) -> float | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metadata_int(metadata: dict, key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _metadata_bool(metadata: dict, key: str) -> bool:
    value = metadata.get(key)
    return value if isinstance(value, bool) else False
