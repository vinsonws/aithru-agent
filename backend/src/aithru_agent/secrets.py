from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.persistence.sqlite.store import SQLiteConnection


class AgentSecretStore(Protocol):
    def set_secret(self, secret_ref: str, value: str) -> None:
        ...

    def get_secret(self, secret_ref: str) -> str | None:
        ...


class InMemorySecretStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set_secret(self, secret_ref: str, value: str) -> None:
        _validate_secret_ref(secret_ref)
        self._values[secret_ref] = value

    def get_secret(self, secret_ref: str) -> str | None:
        _validate_secret_ref(secret_ref)
        return self._values.get(secret_ref)


class SQLiteSecretStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db = SQLiteConnection(db_path)
        self._fernet = Fernet(_load_or_create_secret_key(_secret_key_path(db_path)))

    def set_secret(self, secret_ref: str, value: str) -> None:
        _validate_secret_ref(secret_ref)
        encrypted_value = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
        existing = self._get_record(secret_ref)
        now = _utc_now()
        record = AgentSecretRecord(
            secret_ref=secret_ref,
            encrypted_value=encrypted_value,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._save_record(record)

    def get_secret(self, secret_ref: str) -> str | None:
        _validate_secret_ref(secret_ref)
        record = self._get_record(secret_ref)
        if record is None:
            return None
        return self._fernet.decrypt(record.encrypted_value.encode("ascii")).decode("utf-8")

    def _get_record(self, secret_ref: str) -> "AgentSecretRecord | None":
        row = self._db.query_one(
            """
            SELECT payload
            FROM agent_documents
            WHERE kind = ? AND id = ?
            """,
            ("secret_record", secret_ref),
        )
        return AgentSecretRecord.model_validate_json(row["payload"]) if row else None

    def _save_record(self, record: "AgentSecretRecord") -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO agent_documents (kind, id, payload)
            VALUES (?, ?, ?)
            """,
            ("secret_record", record.secret_ref, record.model_dump_json()),
        )


class AgentSecretRecord(AithruBaseModel):
    secret_ref: str
    encrypted_value: str
    created_at: str
    updated_at: str


def model_profile_api_key_secret_ref(*, org_id: str, key: str) -> str:
    return f"secret://model-profiles/{org_id}/{key}/api-key"


def _validate_secret_ref(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "secret" or not parts.netloc:
        raise ValueError("secret_ref must be a secret:// reference")
    if parts.username is not None or parts.password is not None:
        raise ValueError("secret_ref cannot include user info")
    if parts.query or parts.fragment:
        raise ValueError("secret_ref cannot include query or fragment values")


def _secret_key_path(db_path: str | Path) -> Path:
    path = Path(db_path)
    return path.with_name(f"{path.stem}.secrets.key")


def _load_or_create_secret_key(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return path.read_bytes().strip()
    with os.fdopen(fd, "wb") as file:
        file.write(key)
    return key


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
