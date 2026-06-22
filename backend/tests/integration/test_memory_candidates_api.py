import pytest
from httpx import ASGITransport, AsyncClient

from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
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
