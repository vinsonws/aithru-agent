from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeVar

from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.external_tools import (
    AgentExternalToolActivationStatus,
    AgentExternalToolCacheStatus,
    AgentExternalToolConfigAuditAction,
    AgentExternalToolConfigAuditEvent,
    AgentExternalToolConfigDefinition,
    AgentExternalToolConfigEntry,
    AgentExternalToolConfigOperationResult,
    AgentExternalToolConfigResetResult,
)
from aithru_agent.persistence.sqlite.store import SQLiteConnection


ModelT = TypeVar("ModelT", bound=AithruBaseModel)


class ExternalToolConfigError(ValueError):
    pass


class ExternalToolConfigConflictError(ExternalToolConfigError):
    pass


class ExternalToolConfigNotFoundError(ExternalToolConfigError):
    pass


class AgentExternalToolConfigRegistry(Protocol):
    def create_config(
        self,
        definition: AgentExternalToolConfigDefinition,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigEntry:
        ...

    def list_configs(self, org_id: str) -> list[AgentExternalToolConfigEntry]:
        ...

    def get_config(
        self,
        org_id: str,
        config_id_or_key: str,
    ) -> AgentExternalToolConfigEntry | None:
        ...

    def update_config(
        self,
        org_id: str,
        config_id_or_key: str,
        updates: dict[str, object],
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigEntry:
        ...

    def set_enabled(
        self,
        org_id: str,
        config_id_or_key: str,
        enabled: bool,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigOperationResult:
        ...

    def reset_cache(
        self,
        org_id: str,
        config_id_or_key: str,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigResetResult:
        ...


class InMemoryExternalToolConfigRegistry:
    def __init__(
        self,
        *,
        seed_configs: Iterable[AgentExternalToolConfigEntry] = (),
    ) -> None:
        self._entries: dict[str, AgentExternalToolConfigEntry] = {
            config.id: config for config in seed_configs
        }

    def create_config(
        self,
        definition: AgentExternalToolConfigDefinition,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigEntry:
        entry = _entry_from_definition(definition, actor_user_id=actor_user_id)
        _ensure_available(entry, self._entries.values())
        self._entries[entry.id] = entry
        return entry

    def list_configs(self, org_id: str) -> list[AgentExternalToolConfigEntry]:
        return sorted(
            [entry for entry in self._entries.values() if entry.org_id == org_id],
            key=lambda entry: (entry.key, entry.id),
        )

    def get_config(
        self,
        org_id: str,
        config_id_or_key: str,
    ) -> AgentExternalToolConfigEntry | None:
        for entry in self._entries.values():
            if entry.org_id == org_id and config_id_or_key in {entry.id, entry.key}:
                return entry
        return None

    def update_config(
        self,
        org_id: str,
        config_id_or_key: str,
        updates: dict[str, object],
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigEntry:
        entry = self.get_config(org_id, config_id_or_key)
        if entry is None:
            raise ExternalToolConfigNotFoundError(
                f"External tool config not found: {config_id_or_key}"
            )
        updated, _ = _updated_entry(
            entry,
            updates,
            actor_user_id=actor_user_id,
            action=AgentExternalToolConfigAuditAction.UPDATED,
        )
        self._entries[updated.id] = updated
        return updated

    def set_enabled(
        self,
        org_id: str,
        config_id_or_key: str,
        enabled: bool,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigOperationResult:
        action = (
            AgentExternalToolConfigAuditAction.ENABLED
            if enabled
            else AgentExternalToolConfigAuditAction.DISABLED
        )
        updated, audit_event = self._mutate(
            org_id,
            config_id_or_key,
            {"enabled": enabled},
            actor_user_id=actor_user_id,
            action=action,
        )
        return AgentExternalToolConfigOperationResult(
            action=action,
            config=updated,
            audit_event=audit_event,
        )

    def reset_cache(
        self,
        org_id: str,
        config_id_or_key: str,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigResetResult:
        reset_at = _utc_now()
        updated, audit_event = self._mutate(
            org_id,
            config_id_or_key,
            {"cache_status": AgentExternalToolCacheStatus(last_reset_at=reset_at)},
            actor_user_id=actor_user_id,
            action=AgentExternalToolConfigAuditAction.RESET_CACHE,
            now=reset_at,
        )
        return AgentExternalToolConfigResetResult(
            id=updated.id,
            org_id=updated.org_id,
            key=updated.key,
            reset_at=reset_at,
            activation_status=updated.activation_status,
            cache_status=updated.cache_status,
            audit_event=audit_event,
            config=updated,
        )

    def _mutate(
        self,
        org_id: str,
        config_id_or_key: str,
        updates: dict[str, object],
        *,
        actor_user_id: str,
        action: AgentExternalToolConfigAuditAction,
        now: str | None = None,
    ) -> tuple[AgentExternalToolConfigEntry, AgentExternalToolConfigAuditEvent]:
        entry = self.get_config(org_id, config_id_or_key)
        if entry is None:
            raise ExternalToolConfigNotFoundError(
                f"External tool config not found: {config_id_or_key}"
            )
        updated, audit_event = _updated_entry(
            entry,
            updates,
            actor_user_id=actor_user_id,
            action=action,
            now=now,
        )
        self._entries[updated.id] = updated
        return updated, audit_event


class SQLiteExternalToolConfigRegistry:
    def __init__(self, db_path: str | Path) -> None:
        self._db = SQLiteConnection(db_path)

    def create_config(
        self,
        definition: AgentExternalToolConfigDefinition,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigEntry:
        entry = _entry_from_definition(definition, actor_user_id=actor_user_id)
        _ensure_available(entry, self._list_all_entries())
        self._insert_entry(entry)
        return entry

    def list_configs(self, org_id: str) -> list[AgentExternalToolConfigEntry]:
        return sorted(
            [entry for entry in self._list_all_entries() if entry.org_id == org_id],
            key=lambda entry: (entry.key, entry.id),
        )

    def get_config(
        self,
        org_id: str,
        config_id_or_key: str,
    ) -> AgentExternalToolConfigEntry | None:
        entry = self._get_entry_by_id(config_id_or_key)
        if entry is not None and entry.org_id == org_id:
            return entry
        for entry in self._list_all_entries():
            if entry.org_id == org_id and entry.key == config_id_or_key:
                return entry
        return None

    def update_config(
        self,
        org_id: str,
        config_id_or_key: str,
        updates: dict[str, object],
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigEntry:
        entry = self.get_config(org_id, config_id_or_key)
        if entry is None:
            raise ExternalToolConfigNotFoundError(
                f"External tool config not found: {config_id_or_key}"
            )
        updated, _ = _updated_entry(
            entry,
            updates,
            actor_user_id=actor_user_id,
            action=AgentExternalToolConfigAuditAction.UPDATED,
        )
        self._save_entry(updated)
        return updated

    def set_enabled(
        self,
        org_id: str,
        config_id_or_key: str,
        enabled: bool,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigOperationResult:
        action = (
            AgentExternalToolConfigAuditAction.ENABLED
            if enabled
            else AgentExternalToolConfigAuditAction.DISABLED
        )
        updated, audit_event = self._mutate(
            org_id,
            config_id_or_key,
            {"enabled": enabled},
            actor_user_id=actor_user_id,
            action=action,
        )
        return AgentExternalToolConfigOperationResult(
            action=action,
            config=updated,
            audit_event=audit_event,
        )

    def reset_cache(
        self,
        org_id: str,
        config_id_or_key: str,
        *,
        actor_user_id: str,
    ) -> AgentExternalToolConfigResetResult:
        reset_at = _utc_now()
        updated, audit_event = self._mutate(
            org_id,
            config_id_or_key,
            {"cache_status": AgentExternalToolCacheStatus(last_reset_at=reset_at)},
            actor_user_id=actor_user_id,
            action=AgentExternalToolConfigAuditAction.RESET_CACHE,
            now=reset_at,
        )
        return AgentExternalToolConfigResetResult(
            id=updated.id,
            org_id=updated.org_id,
            key=updated.key,
            reset_at=reset_at,
            activation_status=updated.activation_status,
            cache_status=updated.cache_status,
            audit_event=audit_event,
            config=updated,
        )

    def _mutate(
        self,
        org_id: str,
        config_id_or_key: str,
        updates: dict[str, object],
        *,
        actor_user_id: str,
        action: AgentExternalToolConfigAuditAction,
        now: str | None = None,
    ) -> tuple[AgentExternalToolConfigEntry, AgentExternalToolConfigAuditEvent]:
        entry = self.get_config(org_id, config_id_or_key)
        if entry is None:
            raise ExternalToolConfigNotFoundError(
                f"External tool config not found: {config_id_or_key}"
            )
        updated, audit_event = _updated_entry(
            entry,
            updates,
            actor_user_id=actor_user_id,
            action=action,
            now=now,
        )
        self._save_entry(updated)
        return updated, audit_event

    def _save_entry(self, entry: AgentExternalToolConfigEntry) -> None:
        _save_doc(self._db, "external_tool_config_entry", entry.id, entry)

    def _insert_entry(self, entry: AgentExternalToolConfigEntry) -> None:
        _insert_doc(self._db, "external_tool_config_entry", entry.id, entry)

    def _get_entry_by_id(self, entry_id: str) -> AgentExternalToolConfigEntry | None:
        return _get_doc(
            self._db,
            "external_tool_config_entry",
            entry_id,
            AgentExternalToolConfigEntry,
        )

    def _list_all_entries(self) -> list[AgentExternalToolConfigEntry]:
        return _list_docs(
            self._db,
            "external_tool_config_entry",
            AgentExternalToolConfigEntry,
        )


def _entry_from_definition(
    definition: AgentExternalToolConfigDefinition,
    *,
    actor_user_id: str,
) -> AgentExternalToolConfigEntry:
    now = _utc_now()
    audit_event = AgentExternalToolConfigAuditEvent(
        action=AgentExternalToolConfigAuditAction.CREATED,
        at=now,
        actor_user_id=actor_user_id,
    )
    return AgentExternalToolConfigEntry(
        **definition.model_dump(mode="python"),
        id=_config_id(definition.org_id, definition.key),
        activation_status=AgentExternalToolActivationStatus.PENDING_RUNTIME_RELOAD,
        created_at=now,
        updated_at=now,
        created_by=actor_user_id,
        updated_by=actor_user_id,
        audit=[audit_event],
    )


def _ensure_available(
    entry: AgentExternalToolConfigEntry,
    existing_entries: Iterable[AgentExternalToolConfigEntry],
) -> None:
    for existing in existing_entries:
        if existing.id == entry.id:
            raise ExternalToolConfigConflictError(
                f"External tool config already exists: {entry.id}"
            )
        if existing.org_id != entry.org_id:
            continue
        if existing.key == entry.key:
            raise ExternalToolConfigConflictError(
                f"External tool config already exists: {entry.key}"
            )


def _updated_entry(
    entry: AgentExternalToolConfigEntry,
    updates: dict[str, object],
    *,
    actor_user_id: str,
    action: AgentExternalToolConfigAuditAction,
    now: str | None = None,
) -> tuple[AgentExternalToolConfigEntry, AgentExternalToolConfigAuditEvent]:
    allowed = {
        "name",
        "enabled",
        "mcp",
        "http",
        "web",
        "oauth_status",
        "cache_status",
    }
    unexpected = set(updates) - allowed
    if unexpected:
        raise ExternalToolConfigError(
            f"Unsupported external tool config update field: {sorted(unexpected)[0]}"
        )
    updated_at = now or _utc_now()
    audit_event = AgentExternalToolConfigAuditEvent(
        action=action,
        at=updated_at,
        actor_user_id=actor_user_id,
    )
    payload = entry.model_dump(mode="python")
    payload.update(updates)
    payload["updated_at"] = updated_at
    payload["updated_by"] = actor_user_id
    payload["activation_status"] = AgentExternalToolActivationStatus.PENDING_RUNTIME_RELOAD
    payload["audit"] = [*entry.audit, audit_event]
    return AgentExternalToolConfigEntry.model_validate(payload), audit_event


def _config_id(org_id: str, key: str) -> str:
    return f"external_tool_config_{org_id}_{key}"


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
        raise ExternalToolConfigConflictError(
            f"External tool config already exists: {id}"
        ) from err


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
