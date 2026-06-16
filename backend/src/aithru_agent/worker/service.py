from dataclasses import dataclass

from aithru_agent.domain import AgentRun

from .queue import InProcessRunQueue
from .runner import AgentWorkerRunner


@dataclass
class AgentWorkerService:
    runner: AgentWorkerRunner
    queue: InProcessRunQueue

    async def submit_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        goal: str,
        scopes: list[str],
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        run = await self.runner.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            goal=goal,
            scopes=scopes,
            thread_id=thread_id,
            skill_id=skill_id,
        )
        self.queue.enqueue(run.id)
        return run

    async def work_once(self) -> AgentRun | None:
        queued = self.queue.pop()
        if queued is not None:
            claimed = await self.runner.claim_run(queued.run_id)
            if claimed is not None:
                return await self.runner.execute_claimed_run(claimed.id)
        claimed = await self.runner.claim_next_queued_run()
        if claimed is None:
            return None
        return await self.runner.execute_claimed_run(claimed.id)

    async def drain(self, *, limit: int | None = None) -> list[AgentRun]:
        completed: list[AgentRun] = []
        while limit is None or len(completed) < limit:
            run = await self.work_once()
            if run is None:
                break
            completed.append(run)
        return completed
