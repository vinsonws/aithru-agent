from __future__ import annotations

import re


REDACTED_VALUE = "[REDACTED]"
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|token|password|passwd|secret|authorization)\s*[:=]\s*([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]+")


def sanitize_memory_text(value: str) -> str:
    redacted = _BEARER_TOKEN.sub(f"Bearer {REDACTED_VALUE}", value)
    redacted = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}={REDACTED_VALUE}", redacted)
    return redacted


def contains_no_memory_marker(value: str, markers: list[str]) -> bool:
    normalized = value.lower()
    return any(marker.lower() in normalized for marker in markers)
