"""Built-in skill packages loaded from disk."""

from pathlib import Path

from aithru_agent.domain import (
    AgentSkill,
    AgentSkillConfiguration,
    AgentSkillStatus,
    AgentWorkspacePolicy,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.skills.package_store import BuiltinSkillPackageStore
from aithru_agent.skills.packages import SkillPackage, parse_skill_package

from aithru_agent.domain import AgentSkillRegistrySource


DEEP_RESEARCH_PACKAGE_POLICY = AgentSkillConfiguration(
    instructions="",
    when_to_use="research, deep research, evidence-backed report, cited web investigation",
    allowed_tools=[
        "research.create_plan",
        "web.search",
        "web.fetch",
        "research.create_report",
        "presentation.present",
    ],
    denied_tools=[],
    allowed_subagents=[],
    workspace_policy=AgentWorkspacePolicy(
        read=True,
        write=True,
        allowed_paths=["/reports", "/workspace", "/outputs"],
    ),
)

_READ_WRITE_WORKSPACE = AgentWorkspacePolicy(
    read=True,
    write=True,
    allowed_paths=["/workspace", "/outputs", "/reports"],
)

_READ_ONLY_WORKSPACE = AgentWorkspacePolicy(
    read=True,
    write=False,
    allowed_paths=["/workspace", "/outputs", "/reports"],
)


def _load_builtin_packages(root: Path) -> list[SkillPackage]:
    packages: list[SkillPackage] = []
    policies = {
        "deep-research": DEEP_RESEARCH_PACKAGE_POLICY,
        "surprise-me": AgentSkillConfiguration(
            instructions="",
            when_to_use="surprise, delight, creative showcase, unexpected",
            allowed_tools=[
                "workspace.read_file",
                "workspace.write_file",
                "presentation.present",
            ],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
        "bootstrap": AgentSkillConfiguration(
            instructions="",
            when_to_use="onboarding, setup, configure, personalize",
            allowed_tools=["workspace.write_file", "presentation.present"],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
        "find-skills": AgentSkillConfiguration(
            instructions="",
            when_to_use="discover, find, search, install skill",
            allowed_tools=["workspace.read_file", "presentation.present"],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_ONLY_WORKSPACE,
        ),
        "skill-creator": AgentSkillConfiguration(
            instructions="",
            when_to_use="create, write, edit, improve skill, packaging",
            allowed_tools=["workspace.read_file", "workspace.write_file", "presentation.present"],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
        "frontend-design": AgentSkillConfiguration(
            instructions="",
            when_to_use="frontend, UI, web, HTML, CSS, component, page, dashboard",
            allowed_tools=[
                "workspace.read_file",
                "workspace.write_file",
                "presentation.present",
            ],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
        "chart-visualization": AgentSkillConfiguration(
            instructions="",
            when_to_use="chart, graph, visualization, plot, data",
            allowed_tools=[
                "workspace.read_file",
                "workspace.write_file",
                "presentation.present",
            ],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
        "web-design-guidelines": AgentSkillConfiguration(
            instructions="",
            when_to_use="UI review, accessibility, design audit, UX",
            allowed_tools=["workspace.read_file", "web.fetch", "presentation.present"],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_ONLY_WORKSPACE,
        ),
        "ppt-generation": AgentSkillConfiguration(
            instructions="",
            when_to_use="presentation, slide, PowerPoint, PPT, PPTX",
            allowed_tools=[
                "workspace.read_file",
                "workspace.write_file",
                "presentation.present",
            ],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
        "data-analysis": AgentSkillConfiguration(
            instructions="",
            when_to_use="Excel, CSV, data, statistics, SQL, DuckDB, analysis",
            allowed_tools=[
                "workspace.read_file",
                "workspace.write_file",
                "presentation.present",
            ],
            denied_tools=[],
            allowed_subagents=[],
            workspace_policy=_READ_WRITE_WORKSPACE,
        ),
    }
    for skill_dir in root.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            continue
        key = skill_dir.name
        content = skill_md_path.read_text(encoding="utf-8")
        policy = policies.get(key, AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]))
        package = parse_skill_package(
            key=key,
            org_id="org_1",
            owner_user_id=None,
            source=AgentSkillRegistrySource.BUILTIN,
            skill_md=content,
            policy=policy,
            read_only=True,
        )
        packages.append(package)
    return packages


class BuiltinPackageResolver:
    """Resolver that loads built-in skill packages from disk and provides AgentSkill views."""

    def __init__(self, packages_root: Path | None = None) -> None:
        root = packages_root or (Path(__file__).parent / "builtin_packages")
        self._packages = _load_builtin_packages(root)
        self._by_key: dict[str, SkillPackage] = {pkg.key: pkg for pkg in self._packages}

    def resolve(self, skill_id_or_key: str) -> AgentSkill | None:
        pkg = self._by_key.get(skill_id_or_key)
        if pkg is None:
            for pkg_candidate in self._packages:
                if pkg_candidate.id == skill_id_or_key:
                    pkg = pkg_candidate
                    break
        if pkg is None:
            return None
        return _package_to_skill(pkg)

    def resolve_for_org(self, org_id: str, skill_id_or_key: str) -> AgentSkill | None:
        skill = self.resolve(skill_id_or_key)
        if skill is None or skill.org_id != org_id:
            return None
        return skill

    def list_skills(self) -> list[AgentSkill]:
        return [_package_to_skill(pkg) for pkg in self._packages]

    def list_packages(self) -> list[SkillPackage]:
        return list(self._packages)

    def get_package(self, key: str) -> SkillPackage | None:
        return self._by_key.get(key)


def _package_to_skill(pkg: SkillPackage) -> AgentSkill:
    from aithru_agent.domain import AgentSkill

    return AgentSkill(
        id=pkg.id,
        org_id=pkg.org_id,
        key=pkg.key,
        name=pkg.metadata.name,
        description=pkg.metadata.description,
        instructions=pkg.instructions,
        when_to_use=pkg.policy.when_to_use or "",
        enabled=pkg.enabled,
        allowed_tools=pkg.policy.allowed_tools,
        denied_tools=pkg.policy.denied_tools,
        allowed_subagents=pkg.policy.allowed_subagents,
        workspace_policy=pkg.policy.workspace_policy,
        memory_policy=pkg.policy.memory_policy,
        sandbox_policy=pkg.policy.sandbox_policy,
        approval_policy=pkg.policy.approval_policy,
        input_schema=pkg.policy.input_schema,
        output_schema=pkg.policy.output_schema,
        version=pkg.version,
        status=pkg.status,
    )


# Compatibility alias
BuiltInResearchSkillResolver = BuiltinPackageResolver
