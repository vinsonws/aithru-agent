"""Tests for skill package stores."""

import pytest

from aithru_agent.domain import AgentSkillConfiguration, AgentSkillRegistrySource
from aithru_agent.skills.package_store import (
    BuiltinSkillPackageStore,
    CompositeSkillPackageStore,
    InMemoryUserSkillPackageStore,
    SQLiteUserSkillPackageStore,
    SkillActor,
    SkillPackagePatch,
    SkillRegistryConflictError,
    SkillRegistryNotFoundError,
    SkillRegistryReadOnlyError,
)
from aithru_agent.skills.packages import SkillPackage, parse_skill_package


def _package(
    key: str,
    source: str = "builtin",
    owner_user_id: str | None = None,
) -> SkillPackage:
    return parse_skill_package(
        key=key,
        org_id="org_1",
        owner_user_id=owner_user_id,
        source=AgentSkillRegistrySource(source),
        skill_md=f"""---
name: {key.capitalize().replace('-', ' ')}
description: Test {key} skill.
---

{key} body.
""",
        policy=AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]),
    )


def _actor(org_id: str, user_id: str) -> SkillActor:
    return SkillActor(org_id=org_id, actor_user_id=user_id)


def test_user_package_keys_cannot_collide_with_builtin_keys() -> None:
    builtin = BuiltinSkillPackageStore([_package(key="deep-research", source="builtin")])
    users = InMemoryUserSkillPackageStore()
    store = CompositeSkillPackageStore(builtin=builtin, users=users)

    with pytest.raises(SkillRegistryConflictError, match="deep-research"):
        store.save_user_package(
            actor=_actor("org_1", "user_1"),
            package=_package(key="deep-research", source="user", owner_user_id="user_1"),
        )


def test_user_packages_are_visible_only_to_the_owner() -> None:
    users = InMemoryUserSkillPackageStore()
    users.save_user_package(
        actor=_actor("org_1", "user_1"),
        package=_package(key="file-report", source="user", owner_user_id="user_1"),
    )

    assert [pkg.key for pkg in users.list_visible_packages(_actor("org_1", "user_1"))] == [
        "file-report"
    ]
    assert users.list_visible_packages(_actor("org_1", "user_2")) == []


def test_composite_store_lists_builtin_and_user_packages() -> None:
    builtin = BuiltinSkillPackageStore([
        _package(key="builtin-one", source="builtin"),
        _package(key="builtin-two", source="builtin"),
    ])
    users = InMemoryUserSkillPackageStore()
    users.save_user_package(
        actor=_actor("org_1", "user_1"),
        package=_package(key="user-one", source="user", owner_user_id="user_1"),
    )
    store = CompositeSkillPackageStore(builtin=builtin, users=users)

    visible = store.list_visible_packages(_actor("org_1", "user_1"))

    assert [pkg.key for pkg in visible] == ["builtin-one", "builtin-two", "user-one"]


def test_builtin_store_rejects_save_and_update() -> None:
    store = BuiltinSkillPackageStore()
    actor = _actor("org_1", "user_1")
    pkg = _package(key="test", source="builtin")

    with pytest.raises(SkillRegistryReadOnlyError):
        store.save_user_package(actor, pkg)
    with pytest.raises(SkillRegistryReadOnlyError):
        store.update_user_package(actor, "test", SkillPackagePatch(name="x"))
    with pytest.raises(SkillRegistryReadOnlyError):
        store.set_user_enabled(actor, "test", True)


def test_user_store_get_visible_package_scoped_to_owner() -> None:
    users = InMemoryUserSkillPackageStore()
    pkg = _package(key="my-skill", source="user", owner_user_id="user_1")
    users.save_user_package(actor=_actor("org_1", "user_1"), package=pkg)

    assert users.get_visible_package(_actor("org_1", "user_1"), "my-skill") is not None
    assert users.get_visible_package(_actor("org_1", "user_2"), "my-skill") is None


def test_user_store_rejects_duplicate_owner_key() -> None:
    users = InMemoryUserSkillPackageStore()
    actor = _actor("org_1", "user_1")
    users.save_user_package(actor=actor, package=_package(key="my-skill", source="user", owner_user_id="user_1"))

    with pytest.raises(SkillRegistryConflictError, match="my-skill"):
        users.save_user_package(
            actor=actor,
            package=_package(key="my-skill", source="user", owner_user_id="user_1"),
        )


def test_user_store_update_user_package_updates_metadata_body_and_policy() -> None:
    users = InMemoryUserSkillPackageStore()
    actor = _actor("org_1", "user_1")
    users.save_user_package(
        actor=actor,
        package=_package(key="my-skill", source="user", owner_user_id="user_1"),
    )

    updated = users.update_user_package(
        actor=actor,
        key="my-skill",
        patch=SkillPackagePatch(
            skill_md="""---
name: New Name
description: New description.
---

# New Body
""",
            allowed_tools=["presentation.present"],
            denied_tools=["workspace.write_file"],
            allowed_subagents=["reviewer"],
        ),
    )

    assert updated.metadata.name == "New Name"
    assert updated.metadata.description == "New description."
    assert updated.instructions == "# New Body"
    assert updated.policy.instructions == "# New Body"
    assert updated.policy.allowed_tools == ["presentation.present"]
    assert updated.policy.denied_tools == ["workspace.write_file"]
    assert updated.policy.allowed_subagents == ["reviewer"]


def test_user_store_update_user_package_not_found() -> None:
    users = InMemoryUserSkillPackageStore()

    with pytest.raises(SkillRegistryNotFoundError, match="missing"):
        users.update_user_package(
            actor=_actor("org_1", "user_1"),
            key="missing",
            patch=SkillPackagePatch(name="New"),
        )


def test_user_store_set_user_enabled() -> None:
    users = InMemoryUserSkillPackageStore()
    pkg = _package(key="my-skill", source="user", owner_user_id="user_1")
    users.save_user_package(actor=_actor("org_1", "user_1"), package=pkg)

    updated = users.set_user_enabled(_actor("org_1", "user_1"), "my-skill", False)

    assert updated.enabled is False
    assert users.get_visible_package(_actor("org_1", "user_1"), "my-skill") is None


def test_composite_get_visible_package_checks_builtin_first() -> None:
    builtin = BuiltinSkillPackageStore([_package(key="builtin-one", source="builtin")])
    users = InMemoryUserSkillPackageStore()
    store = CompositeSkillPackageStore(builtin=builtin, users=users)

    pkg = store.get_visible_package(_actor("org_1", "user_1"), "builtin-one")
    assert pkg is not None
    assert pkg.source == AgentSkillRegistrySource.BUILTIN


def test_sqlite_user_skill_package_store_persists_user_packages(tmp_path) -> None:
    db_path = tmp_path / "agent.sqlite"
    actor = _actor("org_1", "user_1")
    store = SQLiteUserSkillPackageStore(db_path)
    store.save_user_package(
        actor=actor,
        package=_package(key="my-skill", source="user", owner_user_id="user_1"),
    )

    reloaded = SQLiteUserSkillPackageStore(db_path)
    package = reloaded.get_visible_package(actor, "my-skill")

    assert package is not None
    assert package.key == "my-skill"
    assert package.owner_user_id == "user_1"
