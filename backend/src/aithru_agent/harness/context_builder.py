from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentRun, AgentSkill


class ContextBuilder:
    def build(self, run: AgentRun, scopes: list[str], skill: AgentSkill | None = None) -> AgentRunContext:
        return AgentRunContext(
            run_id=run.id,
            org_id=run.org_id,
            actor_user_id=run.actor_user_id,
            workspace_id=run.workspace_id,
            thread_id=run.thread_id,
            skill_id=run.skill_id,
            scopes=scopes,
            allowed_tools=_allowed_tools_for_skill(skill) if skill else None,
        )


def _allowed_tools_for_skill(skill: AgentSkill) -> list[str]:
    tools = list(skill.allowed_tools)
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
                if tool not in {"workspace.list_files", "workspace.read_file"}
            ]
        if not skill.workspace_policy.write:
            tools = [
                tool
                for tool in tools
                if tool not in {"workspace.write_file", "workspace.delete_file"}
            ]
    if not skill.allowed_subagents:
        tools = [tool for tool in tools if tool != "subagent.delegate"]
    return tools
