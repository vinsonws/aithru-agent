from aithru_agent.memory.redaction import contains_no_memory_marker, sanitize_memory_text


def test_sanitize_memory_text_redacts_secret_like_values() -> None:
    value = (
        "Use api_key=sk-secret and password: hunter2. "
        "Authorization: Bearer abc.def.ghi should not be stored."
    )

    sanitized = sanitize_memory_text(value)

    assert "sk-secret" not in sanitized
    assert "hunter2" not in sanitized
    assert "abc.def.ghi" not in sanitized
    assert "[REDACTED]" in sanitized


def test_contains_no_memory_marker_is_case_insensitive() -> None:
    assert contains_no_memory_marker(
        "Please DO NOT REMEMBER this.",
        ["do not remember"],
    )
    assert not contains_no_memory_marker(
        "Please remember this preference.",
        ["do not remember"],
    )
