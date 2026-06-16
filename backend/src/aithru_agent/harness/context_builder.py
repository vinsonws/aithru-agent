from aithru_agent.capabilities import AgentRunContext
from aithru_agent.domain import AgentRun


class ContextBuilder:
    def build(self, run: AgentRun, scopes: list[str]) -> AgentRunContext:
        return AgentRunContext(
            run_id=run.id,
            org_id=run.org_id,
            actor_user_id=run.actor_user_id,
            workspace_id=run.workspace_id,
            thread_id=run.thread_id,
            skill_id=run.skill_id,
            scopes=scopes,
        )

