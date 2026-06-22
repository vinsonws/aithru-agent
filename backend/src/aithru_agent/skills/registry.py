from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from aithru_agent.domain import (
    AgentSkill,
    AgentSkillConfiguration,
    AgentSkillEnablementResult,
    AgentSkillMarketplaceMetadata,
    AgentSkillRegistryEntry,
    AgentSkillRegistrySource,
    AgentSkillStatus,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.persistence.sqlite.store import SQLiteConnection
from aithru_agent.skills.resolver import AgentSkillResolver


class SkillRegistryError(ValueError):
    pass


class SkillRegistryConflictError(SkillRegistryError):
    pass


class SkillRegistryNotFoundError(SkillRegistryError):
    pass


class SkillRegistryReadOnlyError(SkillRegistryError):
    pass


class AgentSkillRegistry(AgentSkillResolver, Protocol):
    def register_skill(
        self,
        skill: AgentSkill,
        *,
        source: AgentSkillRegistrySource = AgentSkillRegistrySource.MANAGED,
        marketplace: AgentSkillMarketplaceMetadata | None = None,
        read_only: bool = False,
    ) -> AgentSkillRegistryEntry:
        ...

    def list_entries(self, org_id: str) -> list[AgentSkillRegistryEntry]:
        ...

    def get_entry(self, org_id: str, entry_id_or_key: str) -> AgentSkillRegistryEntry | None:
        ...

    def update_entry(
        self,
        org_id: str,
        entry_id_or_key: str,
        updates: dict[str, object],
    ) -> AgentSkillRegistryEntry:
        ...

    def set_enabled(
        self,
        org_id: str,
        entry_id_or_key: str,
        enabled: bool,
    ) -> AgentSkillEnablementResult:
        ...


class InMemorySkillRegistry:
    def __init__(
        self,
        *,
        seed_skills: Iterable[AgentSkill] = (),
        seed_source: AgentSkillRegistrySource = AgentSkillRegistrySource.BUILTIN,
        seed_read_only: bool = True,
    ) -> None:
        self._entries: dict[str, AgentSkillRegistryEntry] = {}
        for skill in seed_skills:
            entry = _entry_from_skill(
                skill,
                source=seed_source,
                read_only=seed_read_only,
            )
            self._entries[entry.id] = entry

    def register_skill(
        self,
        skill: AgentSkill,
        *,
        source: AgentSkillRegistrySource = AgentSkillRegistrySource.MANAGED,
        marketplace: AgentSkillMarketplaceMetadata | None = None,
        read_only: bool = False,
    ) -> AgentSkillRegistryEntry:
        entry = _entry_from_skill(
            skill,
            source=source,
            marketplace=marketplace,
            read_only=read_only,
        )
        _validate_managed_configuration(entry.configuration)
        _ensure_available(entry, self._entries.values())
        self._entries[entry.id] = entry
        return entry

    def list_entries(self, org_id: str) -> list[AgentSkillRegistryEntry]:
        return sorted(
            [entry for entry in self._entries.values() if entry.org_id == org_id],
            key=lambda entry: (entry.key, entry.id),
        )

    def get_entry(self, org_id: str, entry_id_or_key: str) -> AgentSkillRegistryEntry | None:
        for entry in self._entries.values():
            if entry.org_id == org_id and entry_id_or_key in {entry.id, entry.key}:
                return entry
        return None

    def update_entry(
        self,
        org_id: str,
        entry_id_or_key: str,
        updates: dict[str, object],
    ) -> AgentSkillRegistryEntry:
        entry = self.get_entry(org_id, entry_id_or_key)
        if entry is None:
            raise SkillRegistryNotFoundError(f"Skill registry entry not found: {entry_id_or_key}")
        updated = _updated_entry(entry, updates)
        self._entries[updated.id] = updated
        return updated

    def set_enabled(
        self,
        org_id: str,
        entry_id_or_key: str,
        enabled: bool,
    ) -> AgentSkillEnablementResult:
        entry = self.get_entry(org_id, entry_id_or_key)
        if entry is None:
            raise SkillRegistryNotFoundError(f"Skill registry entry not found: {entry_id_or_key}")
        updated = _updated_entry(entry, {"enabled": enabled})
        self._entries[updated.id] = updated
        return _enablement_result(updated)

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        for entry in self._entries.values():
            if skill_id_or_key in {entry.id, entry.key} and _is_runtime_visible(entry):
                return entry.to_skill()
        return None

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        entry = self.get_entry(org_id, skill_id_or_key)
        if entry is None or not _is_runtime_visible(entry):
            return None
        return entry.to_skill()

    def list_skills(self) -> list[AgentSkill]:
        return [
            entry.to_skill()
            for entry in sorted(self._entries.values(), key=lambda item: (item.key, item.id))
            if _is_runtime_visible(entry)
        ]


class SQLiteSkillRegistry:
    def __init__(
        self,
        db_path: str | Path,
        *,
        seed_skills: Iterable[AgentSkill] = (),
        seed_source: AgentSkillRegistrySource = AgentSkillRegistrySource.BUILTIN,
        seed_read_only: bool = True,
    ) -> None:
        self._db = SQLiteConnection(db_path)
        for skill in seed_skills:
            entry = _entry_from_skill(
                skill,
                source=seed_source,
                read_only=seed_read_only,
            )
            existing = self.get_entry(entry.org_id, entry.id) or self.get_entry(entry.org_id, entry.key)
            if existing is None:
                self._save_entry(entry)
            elif existing.read_only and entry.read_only:
                self._save_entry(
                    entry.model_copy(
                        update={
                            "created_at": existing.created_at,
                            "updated_at": _utc_now(),
                        }
                    )
                )

    def register_skill(
        self,
        skill: AgentSkill,
        *,
        source: AgentSkillRegistrySource = AgentSkillRegistrySource.MANAGED,
        marketplace: AgentSkillMarketplaceMetadata | None = None,
        read_only: bool = False,
    ) -> AgentSkillRegistryEntry:
        entry = _entry_from_skill(
            skill,
            source=source,
            marketplace=marketplace,
            read_only=read_only,
        )
        _validate_managed_configuration(entry.configuration)
        _ensure_available(entry, self._list_all_entries())
        self._save_entry(entry)
        return entry

    def list_entries(self, org_id: str) -> list[AgentSkillRegistryEntry]:
        return sorted(
            [entry for entry in self._list_all_entries() if entry.org_id == org_id],
            key=lambda entry: (entry.key, entry.id),
        )

    def get_entry(self, org_id: str, entry_id_or_key: str) -> AgentSkillRegistryEntry | None:
        entry = self._get_entry_by_id(entry_id_or_key)
        if entry is not None and entry.org_id == org_id:
            return entry
        for entry in self._list_all_entries():
            if entry.org_id == org_id and entry.key == entry_id_or_key:
                return entry
        return None

    def update_entry(
        self,
        org_id: str,
        entry_id_or_key: str,
        updates: dict[str, object],
    ) -> AgentSkillRegistryEntry:
        entry = self.get_entry(org_id, entry_id_or_key)
        if entry is None:
            raise SkillRegistryNotFoundError(f"Skill registry entry not found: {entry_id_or_key}")
        updated = _updated_entry(entry, updates)
        self._save_entry(updated)
        return updated

    def set_enabled(
        self,
        org_id: str,
        entry_id_or_key: str,
        enabled: bool,
    ) -> AgentSkillEnablementResult:
        entry = self.get_entry(org_id, entry_id_or_key)
        if entry is None:
            raise SkillRegistryNotFoundError(f"Skill registry entry not found: {entry_id_or_key}")
        updated = _updated_entry(entry, {"enabled": enabled})
        self._save_entry(updated)
        return _enablement_result(updated)

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        entry = self._get_entry_by_id(skill_id_or_key)
        if entry is not None and _is_runtime_visible(entry):
            return entry.to_skill()
        for entry in self._list_all_entries():
            if entry.key == skill_id_or_key and _is_runtime_visible(entry):
                return entry.to_skill()
        return None

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        entry = self.get_entry(org_id, skill_id_or_key)
        if entry is None or not _is_runtime_visible(entry):
            return None
        return entry.to_skill()

    def list_skills(self) -> list[AgentSkill]:
        return [
            entry.to_skill()
            for entry in sorted(self._list_all_entries(), key=lambda item: (item.key, item.id))
            if _is_runtime_visible(entry)
        ]

    def _save_entry(self, entry: AgentSkillRegistryEntry) -> None:
        _save_doc(self._db, "skill_registry_entry", entry.id, entry)

    def _get_entry_by_id(self, entry_id: str) -> AgentSkillRegistryEntry | None:
        return _get_doc(self._db, "skill_registry_entry", entry_id, AgentSkillRegistryEntry)

    def _list_all_entries(self) -> list[AgentSkillRegistryEntry]:
        return _list_docs(self._db, "skill_registry_entry", AgentSkillRegistryEntry)


def _entry_from_skill(
    skill: AgentSkill,
    *,
    source: AgentSkillRegistrySource,
    marketplace: AgentSkillMarketplaceMetadata | None = None,
    read_only: bool,
) -> AgentSkillRegistryEntry:
    now = _utc_now()
    return AgentSkillRegistryEntry.from_skill(
        skill,
        source=source,
        marketplace=marketplace,
        read_only=read_only,
        created_at=now,
    )


def _ensure_available(
    entry: AgentSkillRegistryEntry,
    existing_entries: Iterable[AgentSkillRegistryEntry],
) -> None:
    for existing in existing_entries:
        if existing.id == entry.id:
            raise SkillRegistryConflictError(f"Skill registry entry already exists: {entry.id}")
        if existing.org_id != entry.org_id:
            continue
        if existing.key == entry.key:
            raise SkillRegistryConflictError(f"Skill registry entry already exists: {entry.key}")


def _updated_entry(
    entry: AgentSkillRegistryEntry,
    updates: dict[str, object],
) -> AgentSkillRegistryEntry:
    if entry.read_only:
        raise SkillRegistryReadOnlyError(f"Skill registry entry is read-only: {entry.key}")
    allowed = {
        "name",
        "description",
        "version",
        "status",
        "enabled",
        "marketplace",
        "configuration",
    }
    unexpected = set(updates) - allowed
    if unexpected:
        raise SkillRegistryError(f"Unsupported skill registry update field: {sorted(unexpected)[0]}")
    payload = entry.model_dump(mode="python")
    payload.update(updates)
    payload["updated_at"] = _utc_now()
    updated = AgentSkillRegistryEntry.model_validate(payload)
    _validate_managed_configuration(updated.configuration)
    return updated


def _validate_managed_configuration(configuration: AgentSkillConfiguration) -> None:
    sandbox = configuration.sandbox_policy
    if sandbox is None:
        return
    if sandbox.network != "none":
        raise SkillRegistryError("managed sandbox policy supports only network='none'")
    if sandbox.allowed_commands is not None:
        raise SkillRegistryError("managed sandbox policy does not support allowed_commands")
    if sandbox.allowed_packages is not None:
        raise SkillRegistryError("managed sandbox policy does not support allowed_packages")
    if sandbox.allowed_mounts is not None:
        raise SkillRegistryError("managed sandbox policy does not support allowed_mounts")


def _is_runtime_visible(entry: AgentSkillRegistryEntry) -> bool:
    return entry.status == AgentSkillStatus.PUBLISHED and entry.enabled


def _enablement_result(entry: AgentSkillRegistryEntry) -> AgentSkillEnablementResult:
    return AgentSkillEnablementResult(
        id=entry.id,
        org_id=entry.org_id,
        key=entry.key,
        enabled=entry.enabled,
        status=entry.status,
        runtime_visible=_is_runtime_visible(entry),
        entry=entry,
    )


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


def _get_doc(
    db: SQLiteConnection,
    kind: str,
    id: str,
    model_type: type[AgentSkillRegistryEntry],
) -> AgentSkillRegistryEntry | None:
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
    model_type: type[AgentSkillRegistryEntry],
) -> list[AgentSkillRegistryEntry]:
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
