import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.domain import AgentMemoryCandidateApprovalResult
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from tests.utils.step_runtime import Step, StepAgentRuntime


@pytest.mark.asyncio
async def test_memory_candidates_api_lists_and_approves_pending_candidate() -> None:
    runtime = create_agent_runtime(
        agent_runtime=_runtime_with_output("Remember that the user prefers concise summaries.")
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Capture a deterministic memory candidate from output",
                    "scopes": ["agent.memory.write"],
                },
            )
        ).json()
        await runtime.worker.drain()

        pending = (await client.get("/api/memory-candidates")).json()
        memory_before = (await client.get("/api/memory")).json()
        approved_response = await client.post(
            f"/api/memory-candidates/memcand_{run['id']}/approve"
        )
        approved = approved_response.json()
        memory_after = (await client.get("/api/memory")).json()
        repeat_approve = await client.post(
            f"/api/memory-candidates/memcand_{run['id']}/approve"
        )

    assert memory_before == []
    assert len(pending) == 1
    assert pending[0]["id"] == f"memcand_{run['id']}"
    assert pending[0]["status"] == "pending"
    assert pending[0]["scope"] == "user"
    assert pending[0]["scope_id"] == "user_1"
    assert pending[0]["value"] == "Remember that the user prefers concise summaries."
    assert approved_response.status_code == 200
    assert approved["candidate"]["status"] == "approved"
    assert approved["candidate"]["resolved_at"] is not None
    assert approved["memory_entry"]["scope"] == "user"
    assert approved["memory_entry"]["scope_id"] == "user_1"
    assert approved["memory_entry"]["key"] == f"run_{run['id']}_outcome"
    assert approved["memory_entry"]["value"] == "Remember that the user prefers concise summaries."
    assert approved["memory_entry"]["source"] == "memory_candidate"
    assert approved["memory_entry"]["owner"] == "user_1"
    assert approved["memory_entry"]["confidence"] == 0.6
    assert len(memory_after) == 1
    assert memory_after[0]["id"] == approved["memory_entry"]["id"]
    assert repeat_approve.status_code == 409
    assert repeat_approve.json()["detail"] == "Memory candidate is already resolved"


@pytest.mark.asyncio
async def test_memory_candidates_api_rejects_pending_candidate() -> None:
    runtime = create_agent_runtime(
        agent_runtime=_runtime_with_output("Keep follow-up actions in a short checklist.")
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Capture a rejectable deterministic memory candidate",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()

        rejected_response = await client.post(
            f"/api/memory-candidates/memcand_{run['id']}/reject"
        )
        rejected = rejected_response.json()
        memory_after = (await client.get("/api/memory")).json()
        approve_after_reject = await client.post(
            f"/api/memory-candidates/memcand_{run['id']}/approve"
        )

    assert rejected_response.status_code == 200
    assert rejected["id"] == f"memcand_{run['id']}"
    assert rejected["status"] == "rejected"
    assert rejected["resolved_at"] is not None
    assert memory_after == []
    assert approve_after_reject.status_code == 409
    assert approve_after_reject.json()["detail"] == "Memory candidate is already resolved"


@pytest.mark.asyncio
async def test_memory_candidates_api_concurrent_approve_allows_one_winner() -> None:
    store = _GatedApprovalStore(parties=2)
    runtime = create_agent_runtime(
        store=store,
        agent_runtime=_runtime_with_output("Store one copy of this approval race memory."),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Capture a deterministic memory candidate for approve race",
                    "scopes": ["agent.memory.write"],
                },
            )
        ).json()
        await runtime.worker.drain()

        responses = await asyncio.gather(
            client.post(f"/api/memory-candidates/memcand_{run['id']}/approve"),
            client.post(f"/api/memory-candidates/memcand_{run['id']}/approve"),
        )
        memory_after = await client.get("/api/memory")
        candidate_after = (
            await client.get(
                "/api/memory-candidates",
                params={"run_id": run["id"]},
            )
        ).json()

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 409]
    assert len(memory_after.json()) == 1
    assert len(candidate_after) == 1
    assert candidate_after[0]["status"] == "approved"


@pytest.mark.asyncio
async def test_memory_candidates_api_concurrent_approve_reject_allows_one_winner() -> None:
    store = _PausedApprovalStore()
    runtime = create_agent_runtime(
        store=store,
        agent_runtime=_runtime_with_output("Do not persist this if rejection wins."),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Capture a deterministic memory candidate for reject race",
                    "scopes": ["agent.memory.write"],
                },
            )
        ).json()
        await runtime.worker.drain()

        approve_task = asyncio.create_task(
            client.post(f"/api/memory-candidates/memcand_{run['id']}/approve")
        )
        await asyncio.wait_for(store.approval_entered.wait(), timeout=1)

        reject_response = await client.post(
            f"/api/memory-candidates/memcand_{run['id']}/reject"
        )
        store.resume_approval.set()
        approve_response = await approve_task

        memory_after = await client.get("/api/memory")
        candidate_after = (
            await client.get(
                "/api/memory-candidates",
                params={"run_id": run["id"]},
            )
        ).json()

    statuses = sorted([approve_response.status_code, reject_response.status_code])
    assert statuses == [200, 409]
    assert reject_response.status_code == 200
    assert approve_response.status_code == 409
    assert memory_after.json() == []
    assert len(candidate_after) == 1
    assert candidate_after[0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_memory_candidates_api_blocks_cross_org_visibility() -> None:
    runtime = create_agent_runtime(
        agent_runtime=_runtime_with_output("Only org one should see this candidate.")
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "goal": "Capture org scoped candidate visibility behavior",
                    "scopes": ["agent.memory.write"],
                },
            )
        ).json()
        await runtime.worker.drain()

        hidden_list = (
            await client.get(
                "/api/memory-candidates",
                headers={"X-Aithru-Org-Id": "org_2"},
            )
        ).json()
        hidden_approve = await client.post(
            f"/api/memory-candidates/memcand_{run['id']}/approve",
            headers={"X-Aithru-Org-Id": "org_2"},
        )

    assert hidden_list == []
    assert hidden_approve.status_code == 404
    assert hidden_approve.json()["detail"] == "Memory candidate not found"


def _runtime_with_output(output: str) -> StepAgentRuntime:
    return StepAgentRuntime([Step.message(output), Step.finish()])


class _AsyncGate:
    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._count = 0
        self._open = asyncio.Event()

    async def wait(self) -> None:
        self._count += 1
        if self._count >= self._parties:
            self._open.set()
        await asyncio.wait_for(self._open.wait(), timeout=1)


class _GatedApprovalStore(InMemoryAgentStore):
    def __init__(self, *, parties: int) -> None:
        super().__init__()
        self._gate = _AsyncGate(parties)

    async def create_memory_entry(self, **kwargs):
        await self._gate.wait()
        return await super().create_memory_entry(**kwargs)

    async def approve_memory_candidate(self, *args, **kwargs) -> AgentMemoryCandidateApprovalResult:
        await self._gate.wait()
        return await super().approve_memory_candidate(*args, **kwargs)


class _PausedApprovalStore(InMemoryAgentStore):
    def __init__(self) -> None:
        super().__init__()
        self.approval_entered = asyncio.Event()
        self.resume_approval = asyncio.Event()

    async def create_memory_entry(self, **kwargs):
        self.approval_entered.set()
        await asyncio.wait_for(self.resume_approval.wait(), timeout=1)
        return await super().create_memory_entry(**kwargs)

    async def approve_memory_candidate(self, *args, **kwargs) -> AgentMemoryCandidateApprovalResult:
        self.approval_entered.set()
        await asyncio.wait_for(self.resume_approval.wait(), timeout=1)
        return await super().approve_memory_candidate(*args, **kwargs)
