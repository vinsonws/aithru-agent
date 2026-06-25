"""Package store abstraction and implementations."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from aithru_agent.domain import AgentSkillConfiguration
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.persistence.sqlite.store import SQLiteConnection
from aithru_agent.skills.packages import (
    SkillPackage,
    parse_skill_md_frontmatter,
    parse_skill_package,
    render_skill_md,
)
from aithru_agent.skills.registry import (
    SkillRegistryConflictError,
    SkillRegistryNotFoundError,
    SkillRegistryReadOnlyError,
)


class SkillActor(AithruBaseModel):
    org_id: str
    actor_user_id: str


class SkillPackagePatch(AithruBaseModel):
    name: str | None = None
    description: str | None = None
    body: str | None = None
    skill_md: str | None = None
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    allowed_subagents: list[str] | None = None
    workspace_policy: object | None = None
    memory_policy: object | None = None
    sandbox_policy: object | None = None
    approval_policy: object | None = None
    input_schema: dict[str, object] | None = None
    output_schema: dict[str, object] | None = None
    enabled: bool | None = None


class SkillPackageStore(Protocol):
    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        raise NotImplementedError

    def list_packages(self, actor: SkillActor) -> list[SkillPackage]:
        raise NotImplementedError

    def get_visible_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        raise NotImplementedError

    def get_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        raise NotImplementedError

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        raise NotImplementedError

    def update_user_package(
        self,
        actor: SkillActor,
        key: str,
        patch: SkillPackagePatch,
    ) -> SkillPackage:
        raise NotImplementedError

    def set_user_enabled(self, actor: SkillActor, key: str, enabled: bool) -> SkillPackage:
        raise NotImplementedError


class BuiltinSkillPackageStore:
    def __init__(self, packages: list[SkillPackage] | None = None) -> None:
        self._packages = {pkg.key: pkg for pkg in (packages or [])}

    def set_packages(self, packages: list[SkillPackage]) -> None:
        self._packages = {pkg.key: pkg for pkg in packages}

    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        return [pkg for pkg in self._packages.values() if pkg.enabled]

    def list_packages(self, actor: SkillActor) -> list[SkillPackage]:
        return list(self._packages.values())

    def get_visible_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        pkg = self.get_package(actor, key)
        if pkg is not None and pkg.enabled:
            return pkg
        return None

    def get_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        del actor
        package = self._packages.get(key)
        if package is not None:
            return package
        for candidate in self._packages.values():
            if candidate.id == key:
                return candidate
        return None

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        raise SkillRegistryReadOnlyError("Built-in store is read-only")

    def update_user_package(
        self,
        actor: SkillActor,
        key: str,
        patch: SkillPackagePatch,
    ) -> SkillPackage:
        raise SkillRegistryReadOnlyError("Built-in store is read-only")

    def set_user_enabled(self, actor: SkillActor, key: str, enabled: bool) -> SkillPackage:
        raise SkillRegistryReadOnlyError("Built-in store is read-only")


class InMemoryUserSkillPackageStore:
    def __init__(self) -> None:
        self._packages: dict[tuple[str, str, str], SkillPackage] = {}

    def _key(self, actor: SkillActor, pkg: SkillPackage) -> tuple[str, str, str]:
        return (actor.org_id, pkg.owner_user_id or "", pkg.key)

    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        return [
            pkg
            for (org_id, owner_id, _), pkg in self._packages.items()
            if org_id == actor.org_id
            and owner_id == actor.actor_user_id
            and pkg.enabled
        ]

    def list_packages(self, actor: SkillActor) -> list[SkillPackage]:
        return [
            pkg
            for (org_id, owner_id, _), pkg in self._packages.items()
            if org_id == actor.org_id and owner_id == actor.actor_user_id
        ]

    def get_visible_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        pkg = self.get_package(actor, key)
        if pkg is not None and pkg.enabled:
            return pkg
        return None

    def get_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        for package in self.list_packages(actor):
            if key in {package.key, package.id}:
                return package
        return None

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        _validate_user_package_actor(actor, package)
        store_key = self._key(actor, package)
        if store_key in self._packages:
            raise SkillRegistryConflictError(f"Skill package already exists: {package.key}")
        self._packages[store_key] = package
        return package

    def update_user_package(
        self,
        actor: SkillActor,
        key: str,
        patch: SkillPackagePatch,
    ) -> SkillPackage:
        existing = self.get_package(actor, key)
        if existing is None:
            raise SkillRegistryNotFoundError(f"User skill package not found: {key}")
        now = _utc_now()
        updated = _apply_patch(existing, patch, now)
        self._packages[(updated.org_id, updated.owner_user_id or "", updated.key)] = updated
        return updated

    def set_user_enabled(self, actor: SkillActor, key: str, enabled: bool) -> SkillPackage:
        existing = self.get_package(actor, key)
        if existing is None:
            raise SkillRegistryNotFoundError(f"User skill package not found: {key}")
        now = _utc_now()
        updated = existing.model_copy(update={"enabled": enabled, "updated_at": now})
        self._packages[(updated.org_id, updated.owner_user_id or "", updated.key)] = updated
        return updated


class SQLiteUserSkillPackageStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db = SQLiteConnection(db_path)

    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        return [package for package in self.list_packages(actor) if package.enabled]

    def list_packages(self, actor: SkillActor) -> list[SkillPackage]:
        rows = self._db.query_all(
            """
            SELECT payload
            FROM agent_documents
            WHERE kind = ?
            ORDER BY id
            """,
            (_USER_PACKAGE_KIND,),
        )
        packages = [SkillPackage.model_validate_json(row["payload"]) for row in rows]
        return [
            package
            for package in packages
            if package.org_id == actor.org_id and package.owner_user_id == actor.actor_user_id
        ]

    def get_visible_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        package = self.get_package(actor, key)
        if package is not None and package.enabled:
            return package
        return None

    def get_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        package = self._get_by_doc_id(_doc_id(actor.org_id, actor.actor_user_id, key))
        if package is not None:
            return package
        for candidate in self.list_packages(actor):
            if key in {candidate.key, candidate.id}:
                return candidate
        return None

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        _validate_user_package_actor(actor, package)
        if self.get_package(actor, package.key) is not None:
            raise SkillRegistryConflictError(f"Skill package already exists: {package.key}")
        self._save(package)
        return package

    def update_user_package(
        self,
        actor: SkillActor,
        key: str,
        patch: SkillPackagePatch,
    ) -> SkillPackage:
        existing = self.get_package(actor, key)
        if existing is None:
            raise SkillRegistryNotFoundError(f"User skill package not found: {key}")
        updated = _apply_patch(existing, patch, _utc_now())
        self._save(updated)
        return updated

    def set_user_enabled(self, actor: SkillActor, key: str, enabled: bool) -> SkillPackage:
        existing = self.get_package(actor, key)
        if existing is None:
            raise SkillRegistryNotFoundError(f"User skill package not found: {key}")
        updated = existing.model_copy(update={"enabled": enabled, "updated_at": _utc_now()})
        self._save(updated)
        return updated

    def _get_by_doc_id(self, id: str) -> SkillPackage | None:
        row = self._db.query_one(
            """
            SELECT payload
            FROM agent_documents
            WHERE kind = ? AND id = ?
            """,
            (_USER_PACKAGE_KIND, id),
        )
        return SkillPackage.model_validate_json(row["payload"]) if row else None

    def _save(self, package: SkillPackage) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO agent_documents (kind, id, payload)
            VALUES (?, ?, ?)
            """,
            (
                _USER_PACKAGE_KIND,
                _doc_id(package.org_id, package.owner_user_id or "", package.key),
                package.model_dump_json(),
            ),
        )


class CompositeSkillPackageStore:
    def __init__(
        self,
        builtin: BuiltinSkillPackageStore | None = None,
        users: InMemoryUserSkillPackageStore | SQLiteUserSkillPackageStore | None = None,
    ) -> None:
        self._builtin = builtin or BuiltinSkillPackageStore()
        self._users = users or InMemoryUserSkillPackageStore()

    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        packages = [
            *self._builtin.list_visible_packages(actor),
            *self._users.list_visible_packages(actor),
        ]
        return sorted(packages, key=lambda pkg: (pkg.source, pkg.key))

    def list_packages(self, actor: SkillActor) -> list[SkillPackage]:
        packages = [
            *self._builtin.list_packages(actor),
            *self._users.list_packages(actor),
        ]
        return sorted(packages, key=lambda pkg: (pkg.source, pkg.key))

    def get_visible_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        pkg = self._builtin.get_visible_package(actor, key)
        if pkg is not None:
            return pkg
        return self._users.get_visible_package(actor, key)

    def get_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        package = self._builtin.get_package(actor, key)
        if package is not None:
            return package
        return self._users.get_package(actor, key)

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        if self._builtin.get_visible_package(actor, package.key) is not None:
            raise SkillRegistryConflictError(f"Skill package already exists: {package.key}")
        return self._users.save_user_package(actor, package)

    def update_user_package(
        self,
        actor: SkillActor,
        key: str,
        patch: SkillPackagePatch,
    ) -> SkillPackage:
        existing = self._builtin.get_visible_package(actor, key)
        if existing is not None:
            raise SkillRegistryNotFoundError(f"No user skill package with key: {key}")
        return self._users.update_user_package(actor, key, patch)

    def set_user_enabled(self, actor: SkillActor, key: str, enabled: bool) -> SkillPackage:
        existing = self._builtin.get_visible_package(actor, key)
        if existing is not None:
            raise SkillRegistryReadOnlyError(f"Built-in skill package is read-only: {key}")
        return self._users.set_user_enabled(actor, key, enabled)


def _apply_patch(existing: SkillPackage, patch: SkillPackagePatch, now: str) -> SkillPackage:
    skill_md = patch.skill_md or _patched_skill_md(existing, patch)
    policy = AgentSkillConfiguration(
        instructions=existing.policy.instructions,
        when_to_use=existing.policy.when_to_use,
        allowed_tools=patch.allowed_tools
        if patch.allowed_tools is not None
        else existing.policy.allowed_tools,
        denied_tools=patch.denied_tools
        if patch.denied_tools is not None
        else existing.policy.denied_tools,
        allowed_subagents=patch.allowed_subagents
        if patch.allowed_subagents is not None
        else existing.policy.allowed_subagents,
        workspace_policy=patch.workspace_policy
        if patch.workspace_policy is not None
        else existing.policy.workspace_policy,
        memory_policy=patch.memory_policy
        if patch.memory_policy is not None
        else existing.policy.memory_policy,
        sandbox_policy=patch.sandbox_policy
        if patch.sandbox_policy is not None
        else existing.policy.sandbox_policy,
        approval_policy=patch.approval_policy
        if patch.approval_policy is not None
        else existing.policy.approval_policy,
        input_schema=patch.input_schema if patch.input_schema is not None else existing.policy.input_schema,
        output_schema=patch.output_schema
        if patch.output_schema is not None
        else existing.policy.output_schema,
    )
    reparsed = parse_skill_package(
        key=existing.key,
        org_id=existing.org_id,
        owner_user_id=existing.owner_user_id,
        source=existing.source,
        skill_md=skill_md,
        policy=policy,
        id=existing.id,
        version=existing.version,
        status=existing.status,
        enabled=existing.enabled,
        read_only=existing.read_only,
        created_at=existing.created_at,
        updated_at=now,
    )
    if patch.enabled is not None:
        return reparsed.model_copy(update={"enabled": patch.enabled})
    return reparsed


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


_USER_PACKAGE_KIND = "skill_package_user"


def _doc_id(org_id: str, actor_user_id: str, key: str) -> str:
    return f"{org_id}:{actor_user_id}:{key}"


def _validate_user_package_actor(actor: SkillActor, package: SkillPackage) -> None:
    if package.org_id != actor.org_id or package.owner_user_id != actor.actor_user_id:
        raise SkillRegistryConflictError("User skill package owner does not match request actor")


def _patched_skill_md(existing: SkillPackage, patch: SkillPackagePatch) -> str:
    if patch.name is None and patch.description is None and patch.body is None:
        return existing.skill_md
    _, existing_body = parse_skill_md_frontmatter(existing.skill_md)
    return render_skill_md(
        name=patch.name if patch.name is not None else existing.metadata.name,
        description=patch.description
        if patch.description is not None
        else existing.metadata.description,
        body=patch.body if patch.body is not None else existing_body.strip(),
    )
