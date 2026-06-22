from typing import Any

from aithru_agent.domain.governance import AgentRedactedPayload

from .events import AgentStreamRedaction


REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_KEY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "session",
    "token",
}


def redact_stream_payload(payload: Any) -> tuple[Any, AgentStreamRedaction]:
    receipt = redact_stream_payload_with_receipt(payload)
    return receipt.payload, AgentStreamRedaction(receipt.redaction)


def redact_stream_payload_with_receipt(payload: Any) -> AgentRedactedPayload:
    redacted, redacted_paths = _redact_value(payload)
    redaction = AgentStreamRedaction.PARTIAL if redacted_paths else AgentStreamRedaction.NONE
    return AgentRedactedPayload(
        payload=redacted,
        redaction=redaction.value,
        redacted_paths=redacted_paths,
    )


def combine_redaction(
    explicit: AgentStreamRedaction | str,
    detected: AgentStreamRedaction | str,
) -> AgentStreamRedaction:
    explicit_level = AgentStreamRedaction(explicit)
    detected_level = AgentStreamRedaction(detected)
    if AgentStreamRedaction.FULL in {explicit_level, detected_level}:
        return AgentStreamRedaction.FULL
    if AgentStreamRedaction.PARTIAL in {explicit_level, detected_level}:
        return AgentStreamRedaction.PARTIAL
    return AgentStreamRedaction.NONE


def _redact_value(value: Any, path: str = "") -> tuple[Any, list[str]]:
    if isinstance(value, dict):
        redacted_paths: list[str] = []
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            child_path = _join_path(path, str(key))
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_VALUE
                redacted_paths.append(child_path)
                continue
            redacted_item, item_paths = _redact_value(item, child_path)
            redacted[key] = redacted_item
            redacted_paths.extend(item_paths)
        return redacted, redacted_paths

    if isinstance(value, list):
        redacted_paths: list[str] = []
        redacted_items: list[Any] = []
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            redacted_item, item_paths = _redact_value(item, child_path)
            redacted_items.append(redacted_item)
            redacted_paths.extend(item_paths)
        return redacted_items, redacted_paths

    if isinstance(value, tuple):
        redacted_items, redacted_paths = _redact_value(list(value), path)
        return tuple(redacted_items), redacted_paths

    return value, []


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.lower().replace("-", "_").replace(" ", "_")
    return (
        normalized in _SENSITIVE_KEY_NAMES
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
    )


def _join_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key
