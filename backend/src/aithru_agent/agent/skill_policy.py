"""Skill policy composition: derive effective tool policy from loaded skills."""

from collections.abc import Sequence

from pydantic_ai import RunContext

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.capabilities import AgentRunContext
from aithru_agent.skills.packages import SkillPackage

_MEMORY_READ_TOOLS = {"memory.search"}
_MEMORY_WRITE_TOOLS = {"memory.remember"}
_WORKSPACE_READ_TOOLS = {"workspace.list_files", "workspace.read_file", "workspace.view_image"}
_WORKSPACE_WRITE_TOOLS = {"workspace.write_file", "workspace.patch_file", "workspace.delete_file"}
_SANDBOX_TOOLS = {
    "sandbox.list_files",
    "sandbox.read_file",
    "sandbox.diff",
    "sandbox.write_file",
    "sandbox.patch_file",
    "sandbox.delete_file",
    "sandbox.promote_file",
    "sandbox.run_python",
}
_SUBAGENT_TOOLS = {"subagent.delegate", "task"}


def active_skill_keys(ctx: RunContext[PydanticAgentDeps]) -> list[str]:
    """Return ordered unique active skill keys from explicit and loaded capabilities."""
    keys: list[str] = []
    explicit = ctx.deps.explicit_skill_key
    if explicit:
        keys.append(explicit)
    for capability_id in sorted(ctx.loaded_capability_ids):
        if capability_id.startswith("skill:"):
            keys.append(capability_id.removeprefix("skill:"))
    return list(dict.fromkeys(keys))


def effective_run_context(ctx: RunContext[PydanticAgentDeps]) -> AgentRunContext:
    """Derive the effective run context by merging skill policies.

    Combines the base run context with policies from all currently active
    (explicit + loaded) skill packages.
    """
    packages = [
        ctx.deps.visible_skill_packages[key]
        for key in active_skill_keys(ctx)
        if key in ctx.deps.visible_skill_packages
    ]
    return compose_skill_run_context(ctx.deps.run_context, packages)


def compose_skill_run_context(
    base: AgentRunContext,
    packages: Sequence[SkillPackage],
) -> AgentRunContext:
    """Merge base context with skill policies conservatively."""
    if not packages:
        return base

    allowed_tools = _compose_allowed_tools(
        base.allowed_tools,
        [pkg.policy for pkg in packages],
    )
    denied_tools: set[str] = set()
    denied_tools.update(base.denied_tools)
    for pkg in packages:
        denied_tools.update(pkg.policy.denied_tools)
        denied_tools.update(_policy_denied_tools(pkg))
    if allowed_tools is not None:
        allowed_tools = [tool for tool in allowed_tools if tool not in denied_tools]

    return base.model_copy(
        update={
            "allowed_tools": allowed_tools,
            "denied_tools": sorted(denied_tools),
            "allowed_subagents": _compose_allowed_subagents(
                base.allowed_subagents,
                packages,
            ),
            "workspace_allowed_paths": _compose_workspace_paths(
                base.workspace_allowed_paths,
                packages,
            ),
            "sandbox_policy": _compose_sandbox_policy(
                base.sandbox_policy,
                packages,
            ),
            "require_approval_for_risk": _compose_approval_risks(
                base.require_approval_for_risk,
                packages,
            ),
        }
    )


def _compose_allowed_tools(
    base_allowed: list[str] | None,
    policies: Sequence[object],
) -> list[str] | None:
    """Intersect allowlists from all active skills. None means no restriction."""
    sets: list[set[str]] = []
    for policy in policies:
        allowed = getattr(policy, "allowed_tools", None)
        if allowed:
            sets.append(set(allowed))
    if not sets:
        return base_allowed
    intersection = set.intersection(*sets) if len(sets) > 1 else sets[0]
    if base_allowed is not None:
        intersection &= set(base_allowed)
    return sorted(intersection) if intersection else []


def _compose_allowed_subagents(
    base_allowed: list[str] | None,
    packages: Sequence[SkillPackage],
) -> list[str]:
    """Intersect subagent allowlists from skill packages."""
    if not packages:
        return base_allowed or []
    sets: list[set[str]] = [set(pkg.policy.allowed_subagents) for pkg in packages if pkg.policy.allowed_subagents]
    if not sets:
        return base_allowed or []
    intersection = set.intersection(*sets) if len(sets) > 1 else sets[0]
    if base_allowed is not None:
        intersection &= set(base_allowed)
    return sorted(intersection)


def _compose_workspace_paths(
    base_paths: list[str] | None,
    packages: Sequence[SkillPackage],
) -> list[str] | None:
    """Take the strictest: only paths allowed by ALL active skill policies."""
    sets: list[set[str]] = []
    for pkg in packages:
        policy = pkg.policy.workspace_policy
        if policy and policy.allowed_paths:
            sets.append(set(policy.allowed_paths))
    if not sets:
        return base_paths
    intersection = set.intersection(*sets) if len(sets) > 1 else sets[0]
    if base_paths is not None:
        intersection &= set(base_paths)
    return sorted(intersection) if intersection else []


def _compose_sandbox_policy(
    base_policy: object | None,
    packages: Sequence[SkillPackage],
) -> object | None:
    """Sandbox is enabled only if ALL active skills agree on enabled=true."""
    if not packages:
        return base_policy
    for pkg in packages:
        sp = pkg.policy.sandbox_policy
        if sp is not None and sp.enabled:
            return sp
    return None


def _compose_approval_risks(
    base_risks: list[str],
    packages: Sequence[SkillPackage],
) -> list[str]:
    """Union of approval risks across all active skills."""
    all_risks = set(base_risks)
    for pkg in packages:
        ap = pkg.policy.approval_policy
        if ap and ap.require_approval_for_risk:
            all_risks.update(ap.require_approval_for_risk)
    return list(all_risks)


def _policy_denied_tools(package: SkillPackage) -> set[str]:
    policy = package.policy
    denied: set[str] = set()
    if policy.memory_policy is not None:
        if not policy.memory_policy.read:
            denied.update(_MEMORY_READ_TOOLS)
        if not policy.memory_policy.write:
            denied.update(_MEMORY_WRITE_TOOLS)
    if policy.workspace_policy is not None:
        if not policy.workspace_policy.read:
            denied.update(_WORKSPACE_READ_TOOLS)
        if not policy.workspace_policy.write:
            denied.update(_WORKSPACE_WRITE_TOOLS)
    if policy.sandbox_policy is None or not policy.sandbox_policy.enabled:
        denied.update(_SANDBOX_TOOLS)
    if not policy.allowed_subagents:
        denied.update(_SUBAGENT_TOOLS)
    return denied
