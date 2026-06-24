from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
import hashlib
from pathlib import Path
from typing import Protocol, TypeVar

from aithru_agent.domain import (
    AgentModelProfileDefinition,
    AgentModelProfileEnablementResult,
    AgentModelProfileEntry,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.persistence.sqlite.store import SQLiteConnection


ModelT = TypeVar("ModelT", bound=AithruBaseModel)


class ModelProfileError(ValueError):
    pass


class ModelProfileConflictError(ModelProfileError):
    pass


class ModelProfileNotFoundError(ModelProfileError):
    pass


class AgentModelProfileRegistry(Protocol):
    def create_profile(
        self,
        profile: AgentModelProfileDefinition,
    ) -> AgentModelProfileEntry:
        ...

    def list_profiles(self, org_id: str) -> list[AgentModelProfileEntry]:
        ...

    def get_profile(
        self,
        org_id: str,
        profile_id_or_key: str,
    ) -> AgentModelProfileEntry | None:
        ...

    def update_profile(
        self,
        org_id: str,
        profile_id_or_key: str,
        updates: dict[str, object],
    ) -> AgentModelProfileEntry:
        ...

    def set_enabled(
        self,
        org_id: str,
        profile_id_or_key: str,
        enabled: bool,
    ) -> AgentModelProfileEnablementResult:
        ...


class InMemoryModelProfileRegistry:
    def __init__(
        self,
        *,
        seed_profiles: Iterable[AgentModelProfileDefinition] = (),
    ) -> None:
        self._entries: dict[str, AgentModelProfileEntry] = {}
        for profile in seed_profiles:
            entry = _entry_from_profile(profile)
            self._entries[entry.id] = entry

    def create_profile(
        self,
        profile: AgentModelProfileDefinition,
    ) -> AgentModelProfileEntry:
        entry = _entry_from_profile(profile)
        _ensure_available(entry, self._entries.values())
        self._entries[entry.id] = entry
        return entry

    def list_profiles(self, org_id: str) -> list[AgentModelProfileEntry]:
        return sorted(
            [entry for entry in self._entries.values() if entry.org_id == org_id],
            key=lambda entry: (entry.key, entry.id),
        )

    def get_profile(
        self,
        org_id: str,
        profile_id_or_key: str,
    ) -> AgentModelProfileEntry | None:
        for entry in self._entries.values():
            if entry.org_id == org_id and profile_id_or_key in {entry.id, entry.key}:
                return entry
        return None

    def update_profile(
        self,
        org_id: str,
        profile_id_or_key: str,
        updates: dict[str, object],
    ) -> AgentModelProfileEntry:
        entry = self.get_profile(org_id, profile_id_or_key)
        if entry is None:
            raise ModelProfileNotFoundError(f"Model profile not found: {profile_id_or_key}")
        updated = _updated_entry(entry, updates)
        self._entries[updated.id] = updated
        return updated

    def set_enabled(
        self,
        org_id: str,
        profile_id_or_key: str,
        enabled: bool,
    ) -> AgentModelProfileEnablementResult:
        updated = self.update_profile(org_id, profile_id_or_key, {"enabled": enabled})
        return _enablement_result(updated)


class SQLiteModelProfileRegistry:
    def __init__(
        self,
        db_path: str | Path,
        *,
        seed_profiles: Iterable[AgentModelProfileDefinition] = (),
    ) -> None:
        self._db = SQLiteConnection(db_path)
        for profile in seed_profiles:
            entry = _entry_from_profile(profile)
            existing = self.get_profile(entry.org_id, entry.key)
            if existing is None:
                self._save_entry(entry)

    def create_profile(
        self,
        profile: AgentModelProfileDefinition,
    ) -> AgentModelProfileEntry:
        entry = _entry_from_profile(profile)
        _ensure_available(entry, self._list_all_entries())
        self._insert_entry(entry)
        return entry

    def list_profiles(self, org_id: str) -> list[AgentModelProfileEntry]:
        return sorted(
            [entry for entry in self._list_all_entries() if entry.org_id == org_id],
            key=lambda entry: (entry.key, entry.id),
        )

    def get_profile(
        self,
        org_id: str,
        profile_id_or_key: str,
    ) -> AgentModelProfileEntry | None:
        entry = self._get_entry_by_id(profile_id_or_key)
        if entry is not None and entry.org_id == org_id:
            return entry
        for entry in self._list_all_entries():
            if entry.org_id == org_id and entry.key == profile_id_or_key:
                return entry
        return None

    def update_profile(
        self,
        org_id: str,
        profile_id_or_key: str,
        updates: dict[str, object],
    ) -> AgentModelProfileEntry:
        entry = self.get_profile(org_id, profile_id_or_key)
        if entry is None:
            raise ModelProfileNotFoundError(f"Model profile not found: {profile_id_or_key}")
        updated = _updated_entry(entry, updates)
        self._save_entry(updated)
        return updated

    def set_enabled(
        self,
        org_id: str,
        profile_id_or_key: str,
        enabled: bool,
    ) -> AgentModelProfileEnablementResult:
        updated = self.update_profile(org_id, profile_id_or_key, {"enabled": enabled})
        return _enablement_result(updated)

    def _save_entry(self, entry: AgentModelProfileEntry) -> None:
        _save_doc(self._db, "model_profile_entry", entry.id, entry)

    def _insert_entry(self, entry: AgentModelProfileEntry) -> None:
        _insert_doc(self._db, "model_profile_entry", entry.id, entry)

    def _get_entry_by_id(self, entry_id: str) -> AgentModelProfileEntry | None:
        return _get_doc(self._db, "model_profile_entry", entry_id, AgentModelProfileEntry)

    def _list_all_entries(self) -> list[AgentModelProfileEntry]:
        return _list_docs(self._db, "model_profile_entry", AgentModelProfileEntry)


def _entry_from_profile(profile: AgentModelProfileDefinition) -> AgentModelProfileEntry:
    now = _utc_now()
    return AgentModelProfileEntry(
        **profile.model_dump(mode="python"),
        id=_profile_id(profile.org_id, profile.key),
        created_at=now,
        updated_at=now,
    )


def _updated_entry(
    entry: AgentModelProfileEntry,
    updates: dict[str, object],
) -> AgentModelProfileEntry:
    allowed = {
        "name",
        "provider",
        "model",
        "enabled",
        "capabilities",
        "cost_policy",
        "selection_policy",
        "auth_secret",
        "metadata",
    }
    unexpected = set(updates) - allowed
    if unexpected:
        raise ModelProfileError(f"Unsupported model profile update field: {sorted(unexpected)[0]}")
    payload = entry.model_dump(mode="python")
    payload.update(updates)
    payload["updated_at"] = _utc_now()
    return AgentModelProfileEntry.model_validate(payload)


def _ensure_available(
    entry: AgentModelProfileEntry,
    existing_entries: Iterable[AgentModelProfileEntry],
) -> None:
    for existing in existing_entries:
        if existing.id == entry.id:
            raise ModelProfileConflictError(f"Model profile already exists: {entry.id}")
        if existing.org_id == entry.org_id and existing.key == entry.key:
            raise ModelProfileConflictError(f"Model profile already exists: {entry.key}")


def _enablement_result(entry: AgentModelProfileEntry) -> AgentModelProfileEnablementResult:
    return AgentModelProfileEnablementResult(
        id=entry.id,
        org_id=entry.org_id,
        key=entry.key,
        enabled=entry.enabled,
        profile=entry,
    )


def _profile_id(org_id: str, key: str) -> str:
    digest = hashlib.sha256(f"{org_id}\0{key}".encode("utf-8")).hexdigest()[:20]
    return f"model_profile_{digest}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _save_doc(
    db: SQLiteConnection,
    kind: str,
    id: str,
    model: AithruBaseModel,
) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO agent_documents (kind, id, payload)
        VALUES (?, ?, ?)
        """,
        (kind, id, model.model_dump_json()),
    )


def _insert_doc(
    db: SQLiteConnection,
    kind: str,
    id: str,
    model: AithruBaseModel,
) -> None:
    try:
        db.execute(
            """
            INSERT INTO agent_documents (kind, id, payload)
            VALUES (?, ?, ?)
            """,
            (kind, id, model.model_dump_json()),
        )
    except sqlite3.IntegrityError as err:
        raise ModelProfileConflictError(f"Model profile already exists: {id}") from err


def _get_doc(
    db: SQLiteConnection,
    kind: str,
    id: str,
    model_type: type[ModelT],
) -> ModelT | None:
    row = db.query_one(
        """
        SELECT payload
        FROM agent_documents
        WHERE kind = ? AND id = ?
        """,
        (kind, id),
    )
    return model_type.model_validate_json(row["payload"]) if row else None


def _list_docs(
    db: SQLiteConnection,
    kind: str,
    model_type: type[ModelT],
) -> list[ModelT]:
    rows = db.query_all(
        """
        SELECT payload
        FROM agent_documents
        WHERE kind = ?
        ORDER BY id
        """,
        (kind,),
    )
    return [model_type.model_validate_json(row["payload"]) for row in rows]
