import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Self

from pydantic import Field, model_validator

from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain import AgentRun, AgentRunHarnessOptions, AgentRunRetryPolicy

from .queue import InProcessRunQueue
from .runner import AgentWorkerRunner


class AgentWorkerHeartbeatPolicy(AithruBaseModel):
    enabled: bool = True
    interval_seconds: float | None = Field(default=None, gt=0)
    min_interval_seconds: float = Field(default=1.0, gt=0)
    max_interval_seconds: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def _max_interval_must_cover_min_interval(self) -> Self:
        if self.max_interval_seconds < self.min_interval_seconds:
            raise ValueError("max_interval_seconds must be greater than or equal to min_interval_seconds")
        if self.interval_seconds is not None and not (
            self.min_interval_seconds <= self.interval_seconds <= self.max_interval_seconds
        ):
            raise ValueError("interval_seconds must be between min_interval_seconds and max_interval_seconds")
        return self

    def interval_for_lease(self, lease_seconds: int) -> float:
        if not self.enabled:
            return 0.0
        if self.interval_seconds is not None:
            return self.interval_seconds
        lease_interval = max(float(lease_seconds), 0.0) / 3.0
        return max(self.min_interval_seconds, min(self.max_interval_seconds, lease_interval))


class AgentWorkerLoopPolicy(AithruBaseModel):
    poll_interval_seconds: float = Field(default=1.0, gt=0)
    idle_timeout_seconds: float | None = Field(default=None, gt=0)


@dataclass
class AgentWorkerService:
    runner: AgentWorkerRunner
    queue: InProcessRunQueue
    worker_id: str = "worker"
    lease_seconds: int = 300
    heartbeat_policy: AgentWorkerHeartbeatPolicy = field(default_factory=AgentWorkerHeartbeatPolicy)

    async def submit_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        goal: str,
        scopes: list[str],
        harness_options: AgentRunHarnessOptions | None = None,
        retry_policy: AgentRunRetryPolicy | None = None,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        run = await self.runner.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            goal=goal,
            scopes=scopes,
            harness_options=harness_options,
            retry_policy=retry_policy,
            thread_id=thread_id,
            skill_id=skill_id,
        )
        self.queue.enqueue(run.id)
        return run

    async def work_once(self) -> AgentRun | None:
        queued = self.queue.pop()
        if queued is not None:
            claimed = await self.runner.claim_run(
                queued.run_id,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if claimed is not None:
                return await self._execute_claimed_run(claimed.id)
        claimed = await self.runner.claim_next_queued_run(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if claimed is None:
            return await self.runner.recover_next_paused_run(
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
        return await self._execute_claimed_run(claimed.id)

    async def resume_waiting_input(self, run_id: str) -> AgentRun:
        run = await self.runner.resume_after_input(run_id)
        self.queue.enqueue(run.id)
        return run

    async def renew_claim(self, run_id: str) -> AgentRun | None:
        return await self.runner.renew_run_claim(
            run_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )

    async def _execute_claimed_run(self, run_id: str) -> AgentRun:
        if not self.heartbeat_policy.enabled:
            return await self.runner.execute_claimed_run(run_id)
        heartbeat_task = asyncio.create_task(self._renew_claim_until_cancelled(run_id))
        try:
            return await self.runner.execute_claimed_run(run_id)
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _renew_claim_until_cancelled(self, run_id: str) -> None:
        interval = self.heartbeat_policy.interval_for_lease(self.lease_seconds)
        if interval <= 0:
            return
        while True:
            await asyncio.sleep(interval)
            try:
                await self.renew_claim(run_id)
            except Exception:
                continue

    async def drain(self, *, limit: int | None = None) -> list[AgentRun]:
        completed: list[AgentRun] = []
        while limit is None or len(completed) < limit:
            run = await self.work_once()
            if run is None:
                break
            completed.append(run)
        return completed

    async def run_loop(
        self,
        *,
        policy: AgentWorkerLoopPolicy | None = None,
        limit: int | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> list[AgentRun]:
        if limit is not None and limit <= 0:
            return []
        resolved_policy = policy or AgentWorkerLoopPolicy()
        processed: list[AgentRun] = []
        idle_started_at: float | None = None
        loop = asyncio.get_running_loop()
        while limit is None or len(processed) < limit:
            if stop_event is not None and stop_event.is_set():
                break
            run = await self.work_once()
            if run is not None:
                processed.append(run)
                idle_started_at = None
                continue
            now = loop.time()
            if idle_started_at is None:
                idle_started_at = now
            sleep_seconds = _next_idle_sleep_seconds(
                policy=resolved_policy,
                idle_elapsed_seconds=now - idle_started_at,
            )
            if sleep_seconds is None:
                break
            if stop_event is not None:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
                except TimeoutError:
                    pass
            else:
                await asyncio.sleep(sleep_seconds)
        return processed


def _next_idle_sleep_seconds(
    *,
    policy: AgentWorkerLoopPolicy,
    idle_elapsed_seconds: float,
) -> float | None:
    if policy.idle_timeout_seconds is None:
        return policy.poll_interval_seconds
    remaining = policy.idle_timeout_seconds - idle_elapsed_seconds
    if remaining <= 0:
        return None
    return min(policy.poll_interval_seconds, remaining)
