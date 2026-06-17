from typing import Any


def map_run_usage(usage: object) -> dict[str, int]:
    input_tokens = _int_attr(usage, "input_tokens")
    output_tokens = _int_attr(usage, "output_tokens")
    total_tokens = _int_attr(usage, "total_tokens")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens if total_tokens else input_tokens + output_tokens,
        "requests": _int_attr(usage, "requests"),
    }


def _int_attr(value: Any, name: str) -> int:
    raw = getattr(value, name, 0)
    if callable(raw):
        raw = raw()
    return int(raw or 0)
