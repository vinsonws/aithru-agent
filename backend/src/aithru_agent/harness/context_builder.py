from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentRun, AgentSkill

_SANDBOX_TOOLS = {
    "sandbox.list_files",
    "sandbox.read_file",
    "sandbox.diff",
    "sandbox.write_file",
    "sandbox.patch_file",
    "sandbox.delete_file",
    "sandbox.run_python",
}


class ContextBuilder:
    def build(self, run: AgentRun, scopes: list[str], skill: AgentSkill | None = None) -> AgentRunContext:
        harness_options = getattr(run, "harness_options", None)
        return AgentRunContext(
            run_id=run.id,
            org_id=run.org_id,
            actor_user_id=run.actor_user_id,
            workspace_id=run.workspace_id,
            thread_id=run.thread_id,
            skill_id=run.skill_id,
            scopes=scopes,
            allowed_tools=_allowed_tools_for_skill(skill) if skill else None,
            denied_tools=_denied_tools_for_skill(skill) if skill else [],
            allowed_subagents=skill.allowed_subagents if skill else None,
            workspace_allowed_paths=(
                skill.workspace_policy.allowed_paths
                if skill and skill.workspace_policy
                else None
            ),
            sandbox_policy=(
                skill.sandbox_policy
                if skill and skill.sandbox_policy and skill.sandbox_policy.enabled
                else None
            ),
            require_approval_for_risk=(
                skill.approval_policy.require_approval_for_risk
                if skill and skill.approval_policy
                else []
            ),
            model_vision_enabled=(
                bool(harness_options.model_capabilities.vision)
                if harness_options and harness_options.model_capabilities
                else False
            ),
        )


def _allowed_tools_for_skill(skill: AgentSkill) -> list[str] | None:
    if not skill.allowed_tools:
        return None
    tools = list(skill.allowed_tools)
    if skill.denied_tools:
        denied = set(skill.denied_tools)
        tools = [tool for tool in tools if tool not in denied]
    if not (skill.sandbox_policy and skill.sandbox_policy.enabled):
        tools = [tool for tool in tools if not tool.startswith("sandbox.")]
    if skill.memory_policy:
        if not skill.memory_policy.read:
            tools = [tool for tool in tools if tool != "memory.search"]
        if not skill.memory_policy.write:
            tools = [tool for tool in tools if tool != "memory.remember"]
    if skill.workspace_policy:
        if not skill.workspace_policy.read:
            tools = [
                tool
                for tool in tools
                if tool not in {"workspace.list_files", "workspace.read_file", "workspace.view_image"}
            ]
        if not skill.workspace_policy.write:
            tools = [
                tool
                for tool in tools
                if tool not in {"workspace.write_file", "workspace.delete_file"}
            ]
    if not skill.allowed_subagents:
        tools = [tool for tool in tools if tool not in {"subagent.delegate", "task"}]
    return tools


def _denied_tools_for_skill(skill: AgentSkill) -> list[str]:
    denied = set(skill.denied_tools)
    denied.update(_policy_denied_tools(skill))
    return sorted(denied)


def _policy_denied_tools(skill: AgentSkill) -> set[str]:
    denied: set[str] = set()
    if skill.memory_policy:
        if not skill.memory_policy.read:
            denied.add("memory.search")
        if not skill.memory_policy.write:
            denied.add("memory.remember")
    if skill.workspace_policy:
        if not skill.workspace_policy.read:
            denied.update({"workspace.list_files", "workspace.read_file", "workspace.view_image"})
        if not skill.workspace_policy.write:
            denied.update({"workspace.write_file", "workspace.patch_file", "workspace.delete_file"})
    if not (skill.sandbox_policy and skill.sandbox_policy.enabled):
        denied.update(_SANDBOX_TOOLS)
    if not skill.allowed_subagents:
        denied.update({"subagent.delegate", "task"})
    return denied
