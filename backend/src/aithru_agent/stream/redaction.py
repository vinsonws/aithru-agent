from typing import Any

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
    redacted, changed = _redact_value(payload)
    return redacted, AgentStreamRedaction.PARTIAL if changed else AgentStreamRedaction.NONE


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


def _redact_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        changed = False
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_VALUE
                changed = True
                continue
            redacted_item, item_changed = _redact_value(item)
            redacted[key] = redacted_item
            changed = changed or item_changed
        return redacted, changed

    if isinstance(value, list):
        changed = False
        redacted_items: list[Any] = []
        for item in value:
            redacted_item, item_changed = _redact_value(item)
            redacted_items.append(redacted_item)
            changed = changed or item_changed
        return redacted_items, changed

    if isinstance(value, tuple):
        redacted_items, changed = _redact_value(list(value))
        return tuple(redacted_items), changed

    return value, False


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
