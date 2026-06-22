import asyncio
from typing import Literal

from pydantic import Field

from aithru_agent.agent import (
    AgentRuntime,
    PydanticAgentDeps,
    RunPausedForApproval,
    RunPausedForExternalApproval,
    RunPausedForExternalRun,
    RunPausedForInput,
    RunPausedForSubagent,
)
from aithru_agent.agent.runtime import (
    PYDANTIC_APPROVAL_LEGACY_METADATA_HISTORY,
    PYDANTIC_APPROVAL_METADATA_HISTORY,
)
from aithru_agent.capabilities import AithruCapabilityRouter
from aithru_agent.domain import (
    AgentApprovalDecision,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunRetryPolicy,
    AgentRunRetryState,
    AgentRunResult,
    AgentRunSource,
    AgentRunStatus,
    AgentSkill,
    AgentSubagentRunStatus,
)
from aithru_agent.domain.base import AithruBaseModel
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import ContextBuilder, ContextPacketBuilder
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.runtime.processors import AgentRuntimeProcessorRunner
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter
from aithru_agent.worker.recovery import RunRecoveryDecision, decide_run_recovery
from aithru_agent.worker.subagent_result import build_subagent_result_summary


ExternalRunTerminalStatus = Literal["completed", "failed", "cancelled"]


class ExternalRunTerminalEvent(AithruBaseModel):
    capability_run_id: str
    status: ExternalRunTerminalStatus
    source_sequence: int = Field(ge=0)


class AgentWorkerRunner:
    def __init__(
        self,
        *,
        store: AgentStore,
        event_writer: AgentEventWriter,
        capability_router: AithruCapabilityRouter,
        event_store: AgentEventStore | None = None,
        agent_runtime: AgentRuntime | None = None,
        skill_resolver: AgentSkillResolver | None = None,
        processor_runner: AgentRuntimeProcessorRunner | None = None,
    ) -> None:
        self._store = store
        self._event_writer = event_writer
        self._event_store = event_store
        self._capability_router = capability_router
        self._agent_runtime = agent_runtime or AgentRuntime()
        self._skill_resolver = skill_resolver or EmptySkillResolver()
        self._processor_runner = processor_runner or AgentRuntimeProcessorRunner()
        self._context_builder = ContextBuilder()
        self._context_packet_builder = ContextPacketBuilder()

    async def start_run(
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
        run = await self.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            goal=goal,
            scopes=scopes,
            harness_options=harness_options,
            retry_policy=retry_policy,
            thread_id=thread_id,
            skill_id=skill_id,
        )
        return await self.execute_run(run.id)

    async def create_run(
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
        if thread_id:
            thread = await self._store.get_thread(thread_id)
            if thread is None or thread.org_id != org_id or thread.owner_user_id != actor_user_id:
                raise AgentError("NOT_FOUND", f"Thread not found: {thread_id}")
        self._resolve_run_skill(org_id=org_id, skill_id=skill_id)
        workspace = await self._store.create_workspace(org_id=org_id, thread_id=thread_id)
        run = await self._store.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            source="api",
            goal=goal,
            workspace_id=workspace.id,
            scopes=scopes,
            harness_options=harness_options,
            retry_policy=retry_policy,
            thread_id=thread_id,
            skill_id=skill_id,
        )

        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.created",
            source={"kind": "harness"},
            payload={"status": "queued", "workspace_id": workspace.id},
        )
        return run

    async def execute_run(
        self,
        run_id: str,
        *,
        worker_id: str = "worker",
        lease_seconds: int = 300,
    ) -> AgentRun:
        claimed = await self.claim_run(
            run_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if claimed is None:
            existing = await self._store.get_run(run_id)
            if existing is None:
                raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
            raise AgentError("BAD_REQUEST", f"Run is not queued: {run_id}")
        return await self.execute_claimed_run(claimed.id)

    async def execute_claimed_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.RUNNING:
            raise AgentError("BAD_REQUEST", f"Run is not claimed: {run_id}")

        thread_id = run.thread_id
        try:
            skill = self._resolve_run_skill(org_id=run.org_id, skill_id=run.skill_id)
        except AgentError as exc:
            return await self._fail_run(run, thread_id, exc)

        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.started",
            source={"kind": "harness"},
            payload={"status": "running"},
        )
        decision = await self._processor_runner.before_model(
            run=run,
            store=self._store,
            event_writer=self._event_writer,
            event_store=self._event_store,
            skill=skill,
        )
        if decision.paused_run is not None:
            return decision.paused_run
        if decision.replaced_run is not None:
            run = decision.replaced_run
            thread_id = run.thread_id
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.started",
            source={"kind": "model"},
            payload={},
        )

        deps = await self._build_deps(run, skill)
        try:
            result = await self._agent_runtime.run(run.goal, deps)
            if result.pending_approval is not None:
                return await self._get_existing_run(run.id)
            return await self._complete_run(run, thread_id, "msg_1", [result.content], skill=skill)
        except RunPausedForApproval:
            return await self._get_existing_run(run.id)
        except RunPausedForExternalApproval:
            return await self._get_existing_run(run.id)
        except RunPausedForExternalRun:
            return await self._get_existing_run(run.id)
        except RunPausedForInput:
            return await self._get_existing_run(run.id)
        except RunPausedForSubagent:
            return await self._get_existing_run(run.id)
        except AgentError as exc:
            if exc.code in {
                "RUN_PAUSED_FOR_APPROVAL",
                "RUN_PAUSED_FOR_EXTERNAL_APPROVAL",
                "RUN_PAUSED_FOR_EXTERNAL_RUN",
                "RUN_PAUSED_FOR_INPUT",
                "RUN_PAUSED_FOR_SUBAGENT",
            }:
                return await self._get_existing_run(run.id)
            return await self._fail_run(run, thread_id, exc, skill=skill)
        except Exception as exc:
            return await self._retry_or_fail_run(run, thread_id, exc, skill=skill)

    async def _build_deps(self, run: AgentRun, skill: AgentSkill | None) -> PydanticAgentDeps:
        context_packet = await self._context_packet_builder.build(
            run,
            self._store,
            event_store=self._event_store,
        )
        if context_packet.has_context:
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="context.packet.built",
                source={"kind": "harness"},
                visibility="debug",
                payload=context_packet.event_payload(),
            )
        return PydanticAgentDeps(
            run=run,
            run_context=self._context_builder.build(run, run.scopes, skill),
            event_writer=self._event_writer,
            capability_router=self._capability_router,
            store=self._store,
            skill=skill,
            context_packet=context_packet,
        )

    async def _get_existing_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        return run

    async def execute_child_run_for_task(self, child_run_id: str, subagent_run_id: str) -> str:
        subagent_run = await self._store.get_subagent_run(subagent_run_id)
        if subagent_run is None or subagent_run.child_run_id != child_run_id:
            raise AgentError("NOT_FOUND", f"Subagent run not found: {subagent_run_id}")
        parent = await self._store.get_run(subagent_run.parent_run_id)
        if parent is None:
            raise AgentError("NOT_FOUND", f"Parent run not found: {subagent_run.parent_run_id}")

        await self._store.update_run(parent.id, status=AgentRunStatus.WAITING_SUBAGENT)
        await self._event_writer.write(
            run_id=parent.id,
            thread_id=parent.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_subagent",
                "subagent_run_id": subagent_run.id,
                "child_run_id": child_run_id,
            },
        )
        child = await self.execute_run(child_run_id)
        if child.status == AgentRunStatus.COMPLETED and child.result is not None and child.result.content is not None:
            await self.resume_after_subagent(
                parent.id,
                subagent_run_id=subagent_run.id,
                child_run_id=child_run_id,
            )
            return child.result.content
        if child.status in {
            AgentRunStatus.QUEUED,
            AgentRunStatus.RUNNING,
            AgentRunStatus.WAITING_APPROVAL,
            AgentRunStatus.WAITING_INPUT,
            AgentRunStatus.WAITING_SUBAGENT,
            AgentRunStatus.WAITING_EXTERNAL_RUN,
        }:
            raise RunPausedForSubagent(parent.id, subagent_run.id, child_run_id)
        if child.status == AgentRunStatus.CANCELLED:
            raise AgentError("SUBAGENT_CANCELLED", "Subagent child run was cancelled")
        if child.status == AgentRunStatus.FAILED:
            raise AgentError("SUBAGENT_FAILED", "Subagent child run did not complete")
        raise AgentError("SUBAGENT_FAILED", "Subagent child run did not complete")

    async def join_run(
        self,
        run_id: str,
        *,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.05,
    ) -> AgentRun:
        interval = max(0.01, poll_interval_seconds)
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout_seconds)
        while True:
            run = await self._store.get_run(run_id)
            if run is None:
                raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
            if run.status in _TERMINAL_RUN_STATUSES:
                return run
            if asyncio.get_running_loop().time() >= deadline:
                raise AgentError("RUN_JOIN_TIMEOUT", f"Run did not finish before timeout: {run_id}")
            await asyncio.sleep(interval)

    async def resume_after_subagent(
        self,
        parent_run_id: str,
        *,
        subagent_run_id: str,
        child_run_id: str,
    ) -> AgentRun:
        parent = await self._store.update_run(parent_run_id, status=AgentRunStatus.RUNNING)
        await self._event_writer.write(
            run_id=parent.id,
            thread_id=parent.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={
                "status": "running",
                "subagent_run_id": subagent_run_id,
                "child_run_id": child_run_id,
            },
        )
        return parent

    async def resume_after_input(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.WAITING_INPUT:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for input: {run_id}")
        resumed = await self._store.update_run(run_id, status=AgentRunStatus.QUEUED)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={"status": "queued", "resume_reason": "input_received"},
        )
        return resumed

    def _resolve_run_skill(
        self,
        *,
        org_id: str,
        skill_id: str | None,
    ) -> AgentSkill | None:
        if skill_id is None:
            return None
        skill = self._skill_resolver.resolve(skill_id)
        if skill is None or skill.org_id != org_id:
            raise AgentError("SKILL_NOT_FOUND", f"Skill not found: {skill_id}")
        return skill

    async def find_next_queued_run(self) -> AgentRun | None:
        for run in await self._store.list_runs():
            if run.status == AgentRunStatus.QUEUED:
                return run
        return None

    async def claim_run(
        self,
        run_id: str,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        previous = await self._store.get_run(run_id)
        claimed = await self._store.claim_run(
            run_id,
            worker_id=worker_id,
            claimed_at=claimed_at,
            lease_seconds=lease_seconds,
        )
        if claimed is not None:
            await self._write_claim_reclaimed_event(previous, claimed)
        return claimed

    async def claim_next_queued_run(
        self,
        *,
        worker_id: str = "worker",
        claimed_at: str | None = None,
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        previous_runs = {run.id: run for run in await self._store.list_runs()}
        claimed = await self._store.claim_next_queued_run(
            worker_id=worker_id,
            claimed_at=claimed_at,
            lease_seconds=lease_seconds,
        )
        if claimed is not None:
            await self._write_claim_reclaimed_event(previous_runs.get(claimed.id), claimed)
        return claimed

    async def renew_run_claim(
        self,
        run_id: str,
        *,
        worker_id: str = "worker",
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        return await self._store.renew_run_claim(
            run_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    async def _write_claim_reclaimed_event(
        self,
        previous: AgentRun | None,
        claimed: AgentRun,
    ) -> None:
        if previous is None or previous.status != AgentRunStatus.RUNNING:
            return
        if previous.claim is None or claimed.claim is None:
            return
        if claimed.claim.attempt <= previous.claim.attempt:
            return
        await self._event_writer.write(
            run_id=claimed.id,
            thread_id=claimed.thread_id,
            type="run.claim.reclaimed",
            source={"kind": "harness"},
            visibility="audit",
            payload={
                "previous_worker_id": previous.claim.worker_id,
                "worker_id": claimed.claim.worker_id,
                "attempt": claimed.claim.attempt,
                "previous_lease_expires_at": previous.claim.lease_expires_at,
            },
        )

    async def recover_next_paused_run(
        self,
        *,
        worker_id: str = "worker",
        lease_seconds: int = 300,
    ) -> AgentRun | None:
        for run in await self._store.list_runs():
            decision = await self._recovery_decision_for_run(run)
            if decision.action == "resume_input":
                queued = await self.resume_after_input(run.id)
                claimed = await self.claim_run(
                    queued.id,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )
                if claimed is None:
                    return await self._get_existing_run(queued.id)
                return await self.execute_claimed_run(claimed.id)
            if decision.action == "resume_approval" and decision.approval_id and decision.approval_decision:
                return await self.resume_after_approval(
                    run.id,
                    approval_id=decision.approval_id,
                    decision=decision.approval_decision,
                )
            if (
                decision.action == "resume_subagent"
                and decision.subagent_run_id
                and decision.child_run_id
                and (decision.child_result is not None or decision.child_artifacts)
            ):
                return await self.resume_after_completed_subagent(run.id, decision=decision)
            if decision.action == "fail_subagent":
                return await self.fail_after_subagent(run.id, decision=decision)
        return None

    async def _recovery_decision_for_run(self, run: AgentRun) -> RunRecoveryDecision:
        events = await self._event_store.list_by_run(run.id) if self._event_store else []
        subagents = await self._store.list_subagent_runs(parent_run_id=run.id)
        child_runs = [
            child
            for child in [
                await self._store.get_run(subagent.child_run_id)
                for subagent in subagents
            ]
            if child is not None
        ]
        child_artifacts = []
        for child in child_runs:
            child_artifacts.extend(await self._store.list_artifacts(run_id=child.id))
        return decide_run_recovery(
            run=run,
            events=events,
            approvals=await self._store.list_approvals(),
            subagents=subagents,
            child_runs=child_runs,
            child_artifacts=child_artifacts,
        )

    async def resume_run(
        self,
        run_id: str,
        *,
        approval_id: str,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentRun:
        return await self.resume_after_approval(
            run_id,
            approval_id=approval_id,
            decision=decision,
            comment=comment,
        )

    async def resume_after_approval(
        self,
        run_id: str,
        *,
        approval_id: str,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.WAITING_APPROVAL:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for approval: {run_id}")

        approval = await self._store.get_approval(approval_id)
        if approval is None or approval.run_id != run_id:
            raise AgentError("RUN_NOT_RESUMABLE", f"Approval not found: {approval_id}")

        resolved = await self._store.resolve_approval(
            approval_id,
            decision=decision,
            comment=comment,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="approval.resolved",
            source={"kind": "approval"},
            payload={
                "approval_id": approval_id,
                "tool_call_id": approval.tool_call_id,
                "tool_name": approval.tool_name,
                "decision": _approval_decision_value(resolved.decision or decision),
                "comment": comment,
            },
        )

        if str(decision) == AgentApprovalDecision.REJECTED.value:
            failed = await self._store.update_run(
                run_id,
                status=AgentRunStatus.FAILED,
                current_approval_id=None,
                error={"message": "Approval rejected"},
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": approval.tool_call_id,
                    "tool_name": approval.tool_name,
                    "reason": comment,
                },
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="run.failed",
                source={"kind": "harness"},
                payload={"status": "failed", "error": {"message": "Approval rejected"}},
            )
            await self._after_terminal(failed)
            return failed

        try:
            skill = self._resolve_run_skill(org_id=run.org_id, skill_id=run.skill_id)
        except AgentError as exc:
            return await self._fail_run(run, run.thread_id, exc)

        resumed = await self._store.update_run(run_id, status=AgentRunStatus.RUNNING, current_approval_id=None)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={"status": "running"},
        )

        metadata = approval.metadata or {}
        persisted_history = metadata.get(PYDANTIC_APPROVAL_METADATA_HISTORY) or metadata.get(
            PYDANTIC_APPROVAL_LEGACY_METADATA_HISTORY
        )
        if persisted_history is not None and not isinstance(persisted_history, str):
            persisted_history = None

        deps = await self._build_deps(resumed, skill)
        try:
            result = await self._agent_runtime.resume_approval(
                run_id=run_id,
                approval_id=approval_id,
                approved=True,
                deps=deps,
                persisted_message_history=persisted_history,
                persisted_tool_call_id=approval.tool_call_id,
            )
            if result.pending_approval is not None:
                return await self._get_existing_run(run_id)
            return await self._complete_run(
                resumed,
                run.thread_id,
                "msg_1",
                [result.content],
                skill=skill,
            )
        except RunPausedForApproval:
            return await self._get_existing_run(run_id)
        except RunPausedForExternalApproval:
            return await self._get_existing_run(run_id)
        except RunPausedForExternalRun:
            return await self._get_existing_run(run_id)
        except RunPausedForInput:
            return await self._get_existing_run(run_id)
        except RunPausedForSubagent:
            return await self._get_existing_run(run_id)
        except AgentError as exc:
            if exc.code in {
                "RUN_PAUSED_FOR_APPROVAL",
                "RUN_PAUSED_FOR_EXTERNAL_APPROVAL",
                "RUN_PAUSED_FOR_EXTERNAL_RUN",
                "RUN_PAUSED_FOR_INPUT",
                "RUN_PAUSED_FOR_SUBAGENT",
            }:
                return await self._get_existing_run(run_id)
            return await self._fail_run(resumed, run.thread_id, exc, skill=skill)
        except Exception as exc:
            return await self._fail_run(resumed, run.thread_id, exc, skill=skill)

    async def resume_after_external_approval(
        self,
        run_id: str,
        *,
        approval_id: str,
        capability_run_id: str | None = None,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.WAITING_APPROVAL:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for approval: {run_id}")
        external = run.current_external_approval
        if external is None:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for external approval: {run_id}")
        if external.approval_id != approval_id:
            raise AgentError("RUN_NOT_RESUMABLE", f"External approval not found: {approval_id}")
        if capability_run_id is not None and external.capability_run_id != capability_run_id:
            raise AgentError("RUN_NOT_RESUMABLE", f"External capability run not found: {capability_run_id}")

        decision_value = _approval_decision_value(decision)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="external_approval.resolved",
            source={"kind": "workflow"},
            payload={
                "kind": external.kind,
                "capability_key": external.capability_key,
                "capability_run_id": external.capability_run_id,
                "approval_id": external.approval_id,
                "tool_call_id": external.tool_call_id,
                "tool_name": external.tool_name,
                "decision": decision_value,
                "comment": comment,
            },
        )

        if decision_value == AgentApprovalDecision.REJECTED.value:
            error = {"message": "External workflow approval rejected"}
            failed = await self._store.update_run(
                run_id,
                status=AgentRunStatus.FAILED,
                completed_at=_event_completed_at_marker(),
                current_approval_id=None,
                current_external_approval=None,
                current_external_run=None,
                error=error,
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="external_run.failed",
                source={"kind": "workflow"},
                payload={
                    "kind": external.kind,
                    "tool_call_id": external.tool_call_id,
                    "tool_name": external.tool_name,
                    "capability_key": external.capability_key,
                    "capability_run_id": external.capability_run_id,
                    "status": "failed",
                    "correlation_id": external.correlation_id,
                    "approval_id": external.approval_id,
                    "error": error,
                },
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="run.failed",
                source={"kind": "harness"},
                payload={"status": "failed", "error": error},
            )
            await self._after_terminal(failed)
            return failed

        resumed = await self._store.update_run(
            run_id,
            status=AgentRunStatus.QUEUED,
            current_approval_id=None,
            current_external_approval=None,
            current_external_run=None,
            error=None,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={"status": "queued", "resume_reason": "external_approval_resolved"},
        )
        return resumed

    async def resume_after_external_run(
        self,
        run_id: str,
        *,
        capability_run_id: str,
        status: str,
        output: object | None = None,
        error: dict | None = None,
        comment: str | None = None,
    ) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.WAITING_EXTERNAL_RUN:
            terminal = await self._find_terminal_external_run_event(
                run_id,
                capability_run_id=capability_run_id,
            )
            if terminal is not None:
                if terminal.status == status:
                    return run
                raise AgentError(
                    "EXTERNAL_RUN_ALREADY_RESOLVED",
                    (
                        f"External capability run {capability_run_id} already "
                        f"resolved as {terminal.status}; received {status}"
                    ),
                )
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for an external run: {run_id}")
        external = run.current_external_run
        if external is None:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for an external run: {run_id}")
        if external.capability_run_id != capability_run_id:
            raise AgentError("RUN_NOT_RESUMABLE", f"External capability run not found: {capability_run_id}")

        if status == "completed":
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="external_run.completed",
                source={"kind": "workflow"},
                payload={
                    "kind": external.kind,
                    "capability_key": external.capability_key,
                    "capability_run_id": external.capability_run_id,
                    "tool_call_id": external.tool_call_id,
                    "tool_name": external.tool_name,
                    "status": "completed",
                    "correlation_id": external.correlation_id,
                    "output": output,
                    "comment": comment,
                },
            )
            resumed = await self._store.update_run(
                run_id,
                status=AgentRunStatus.QUEUED,
                current_approval_id=None,
                current_external_approval=None,
                current_external_run=None,
                error=None,
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="run.resumed",
                source={"kind": "harness"},
                payload={"status": "queued", "resume_reason": "external_run_completed"},
            )
            return resumed

        if status == "failed":
            error_payload = error or {"message": "External workflow capability run failed"}
            failed = await self._store.update_run(
                run_id,
                status=AgentRunStatus.FAILED,
                completed_at=_event_completed_at_marker(),
                current_approval_id=None,
                current_external_approval=None,
                current_external_run=None,
                error=error_payload,
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="external_run.failed",
                source={"kind": "workflow"},
                payload={
                    "kind": external.kind,
                    "capability_key": external.capability_key,
                    "capability_run_id": external.capability_run_id,
                    "tool_call_id": external.tool_call_id,
                    "tool_name": external.tool_name,
                    "status": "failed",
                    "correlation_id": external.correlation_id,
                    "error": error_payload,
                    "comment": comment,
                },
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="run.failed",
                source={"kind": "harness"},
                payload={"status": "failed", "error": error_payload},
            )
            await self._after_terminal(failed)
            return failed

        if status == "cancelled":
            cancelled = await self._store.update_run(
                run_id,
                status=AgentRunStatus.CANCELLED,
                completed_at=_event_completed_at_marker(),
                current_approval_id=None,
                current_external_approval=None,
                current_external_run=None,
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="external_run.cancelled",
                source={"kind": "workflow"},
                payload={
                    "kind": external.kind,
                    "capability_key": external.capability_key,
                    "capability_run_id": external.capability_run_id,
                    "tool_call_id": external.tool_call_id,
                    "tool_name": external.tool_name,
                    "status": "cancelled",
                    "correlation_id": external.correlation_id,
                    "comment": comment,
                },
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=run.thread_id,
                type="run.cancelled",
                source={"kind": "harness"},
                payload={"status": "cancelled"},
            )
            await self._after_terminal(cancelled)
            return cancelled

        raise AgentError("BAD_REQUEST", f"Unsupported external run status: {status}")

    async def _find_terminal_external_run_event(
        self,
        run_id: str,
        *,
        capability_run_id: str,
    ) -> ExternalRunTerminalEvent | None:
        if self._event_store is None:
            return None
        latest: ExternalRunTerminalEvent | None = None
        for event in await self._event_store.list_by_run(run_id):
            status = _external_run_terminal_status(event.type)
            if status is None:
                continue
            payload = event.payload if isinstance(event.payload, dict) else {}
            event_capability_run_id = payload.get("capability_run_id")
            if event_capability_run_id != capability_run_id:
                continue
            latest = ExternalRunTerminalEvent(
                capability_run_id=capability_run_id,
                status=status,
                source_sequence=event.sequence,
            )
        return latest

    async def resume_after_completed_subagent(
        self,
        run_id: str,
        *,
        decision: RunRecoveryDecision,
    ) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.WAITING_SUBAGENT:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for a subagent: {run_id}")
        if (
            not decision.subagent_run_id
            or not decision.child_run_id
            or (
                decision.child_result is None
                and not decision.child_artifacts
                and not (decision.child_result_summary and decision.child_result_summary.has_output)
            )
        ):
            raise AgentError("RUN_NOT_RESUMABLE", f"Subagent result is not recoverable: {run_id}")

        try:
            skill = self._resolve_run_skill(org_id=run.org_id, skill_id=run.skill_id)
        except AgentError as exc:
            return await self._fail_run(run, run.thread_id, exc)

        resumed = await self.resume_after_subagent(
            run.id,
            subagent_run_id=decision.subagent_run_id,
            child_run_id=decision.child_run_id,
        )
        if decision.child_result_summary is not None:
            await self._store.update_subagent_run(
                decision.subagent_run_id,
                status=AgentSubagentRunStatus.COMPLETED,
                result=decision.child_result,
                result_summary=decision.child_result_summary,
                completed_at=_event_completed_at_marker(),
            )
        deps = await self._build_deps(resumed, skill)
        try:
            result = await self._agent_runtime.resume_subagent(
                run_id=run_id,
                subagent_run_id=decision.subagent_run_id,
                child_run_id=decision.child_run_id,
                child_result=decision.child_result,
                child_artifacts=decision.child_artifacts,
                deps=deps,
            )
            if result.pending_approval is not None:
                return await self._get_existing_run(run_id)
            return await self._complete_run(
                resumed,
                run.thread_id,
                "msg_1",
                [result.content],
                skill=skill,
            )
        except RunPausedForApproval:
            return await self._get_existing_run(run_id)
        except RunPausedForExternalApproval:
            return await self._get_existing_run(run_id)
        except RunPausedForExternalRun:
            return await self._get_existing_run(run_id)
        except RunPausedForInput:
            return await self._get_existing_run(run_id)
        except RunPausedForSubagent:
            return await self._get_existing_run(run_id)
        except AgentError as exc:
            if exc.code in {
                "RUN_PAUSED_FOR_APPROVAL",
                "RUN_PAUSED_FOR_EXTERNAL_APPROVAL",
                "RUN_PAUSED_FOR_EXTERNAL_RUN",
                "RUN_PAUSED_FOR_INPUT",
                "RUN_PAUSED_FOR_SUBAGENT",
            }:
                return await self._get_existing_run(run_id)
            return await self._fail_run(resumed, run.thread_id, exc, skill=skill)
        except Exception as exc:
            return await self._fail_run(resumed, run.thread_id, exc, skill=skill)

    async def fail_after_subagent(
        self,
        run_id: str,
        *,
        decision: RunRecoveryDecision,
    ) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.WAITING_SUBAGENT:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for a subagent: {run_id}")
        detail = decision.detail
        if decision.child_status:
            detail = f"{detail} Child status: {decision.child_status}."
        return await self._fail_run(
            run,
            run.thread_id,
            AgentError("SUBAGENT_FAILED", detail),
        )

    async def _complete_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        message_id: str,
        final_content: list[str],
        *,
        skill: AgentSkill | None = None,
    ) -> AgentRun:
        latest = await self._store.get_run(run.id)
        if latest is not None and latest.status == AgentRunStatus.CANCELLED:
            return latest
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.completed",
            source={"kind": "model"},
            payload={},
        )
        content = "".join(final_content)
        persisted_message_id = None
        if thread_id and content:
            message = await self._store.append_message(
                thread_id=thread_id,
                role="assistant",
                content=content,
                run_id=run.id,
            )
            persisted_message_id = message.id
        message_payload = {"message_id": message_id, "content": content}
        if persisted_message_id:
            message_payload["thread_message_id"] = persisted_message_id
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="message.completed",
            source={"kind": "harness"},
            payload=message_payload,
        )
        artifacts = await self._store.list_artifacts(run_id=run.id)
        result = AgentRunResult(
            content=content or None,
            artifact_ids=[artifact.id for artifact in artifacts],
            message_id=message_id,
            thread_message_id=persisted_message_id,
        )
        run = await self._store.update_run(
            run.id,
            status=AgentRunStatus.COMPLETED,
            completed_at=_event_completed_at_marker(),
            result=result,
            current_external_run=None,
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.completed",
            source={"kind": "harness"},
            payload={"status": "completed", "result": result.model_dump(mode="json")},
        )
        await self._emit_parent_subagent_completed(run, content)
        await self._after_terminal(run, skill=skill)
        return run

    async def _fail_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        error: Exception,
        retry_state: AgentRunRetryState | None = None,
        *,
        skill: AgentSkill | None = None,
    ) -> AgentRun:
        latest = await self._store.get_run(run.id)
        if latest is not None and latest.status == AgentRunStatus.CANCELLED:
            return latest
        error_payload = _error_payload(error)
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.failed",
            source={"kind": "model"},
            payload={"error": error_payload},
        )
        updates: dict[str, object] = {
            "status": AgentRunStatus.FAILED,
            "completed_at": _event_completed_at_marker(),
            "current_approval_id": None,
            "current_external_approval": None,
            "current_external_run": None,
            "error": error_payload,
        }
        if retry_state is not None:
            updates["retry_state"] = retry_state
        failed = await self._store.update_run(run.id, **updates)
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.failed",
            source={"kind": "harness"},
            payload={"status": "failed", "error": error_payload},
        )
        await self._emit_parent_subagent_failed(failed, error_payload)
        await self._after_terminal(failed, skill=skill)
        return failed

    async def _retry_or_fail_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        error: Exception,
        *,
        skill: AgentSkill | None = None,
    ) -> AgentRun:
        latest = await self._store.get_run(run.id)
        if latest is not None and latest.status == AgentRunStatus.CANCELLED:
            return latest
        current = latest or run
        policy = current.retry_policy or AgentRunRetryPolicy()
        error_payload = _error_payload(error)
        failure_attempt = (current.retry_state.attempt if current.retry_state else 0) + 1
        retry_state = AgentRunRetryState(
            attempt=failure_attempt,
            next_retry_at=None,
            last_error=error_payload,
        )
        if not policy.can_retry_after_failure(failure_attempt):
            if current.retry_policy is not None:
                await self._event_writer.write(
                    run_id=current.id,
                    thread_id=thread_id,
                    type="run.retry.exhausted",
                    source={"kind": "harness"},
                    payload={
                        "attempt": failure_attempt,
                        "max_attempts": policy.max_attempts,
                        "error": error_payload,
                    },
                )
            return await self._fail_run(current, thread_id, error, retry_state=retry_state, skill=skill)

        failed_at = current.claim.claimed_at if current.claim else None
        retry_state = AgentRunRetryState(
            attempt=failure_attempt,
            next_retry_at=policy.next_retry_at(
                failure_attempt=failure_attempt,
                failed_at=failed_at,
            ),
            last_error=error_payload,
        )
        await self._event_writer.write(
            run_id=current.id,
            thread_id=thread_id,
            type="model.failed",
            source={"kind": "model"},
            payload={"error": error_payload, "retry": {"attempt": failure_attempt}},
        )
        scheduled = await self._store.update_run(
            current.id,
            status=AgentRunStatus.QUEUED,
            current_approval_id=None,
            current_external_approval=None,
            current_external_run=None,
            retry_state=retry_state,
            error=None,
        )
        await self._event_writer.write(
            run_id=current.id,
            thread_id=thread_id,
            type="run.retry.scheduled",
            source={"kind": "harness"},
            payload={
                "status": "queued",
                "attempt": failure_attempt,
                "max_attempts": policy.max_attempts,
                "next_retry_at": retry_state.next_retry_at,
                "error": error_payload,
            },
        )
        return scheduled

    async def _after_terminal(
        self,
        run: AgentRun,
        *,
        skill: AgentSkill | None = None,
    ) -> None:
        await self._processor_runner.after_terminal(
            run=run,
            store=self._store,
            event_writer=self._event_writer,
            event_store=self._event_store,
            skill=skill,
            terminal_status=run.status,
        )

    async def _emit_parent_subagent_completed(self, run: AgentRun, result: str) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        child_artifacts = await self._store.list_artifacts(run_id=run.id)
        result_summary = build_subagent_result_summary(run, child_artifacts)
        for subagent_run in subagent_runs:
            completed = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.COMPLETED,
                result=result,
                result_summary=result_summary,
                completed_at=_event_completed_at_marker(),
            )
            parent = await self._store.get_run(completed.parent_run_id)
            await self._event_writer.write(
                run_id=completed.parent_run_id,
                thread_id=parent.thread_id if parent else None,
                type="subagent.completed",
                source={"kind": "subagent", "id": completed.id, "name": completed.name},
                payload={
                    "subagent_run_id": completed.id,
                    "child_run_id": completed.child_run_id,
                    "name": completed.name,
                    "task": completed.task,
                    "spec_key": completed.spec_key,
                    "status": completed.status.value,
                    "result": result,
                    "result_summary": result_summary.model_dump(mode="json"),
                },
            )

    async def _emit_parent_subagent_failed(self, run: AgentRun, error: dict[str, str]) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        for subagent_run in subagent_runs:
            failed = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.FAILED,
                error=error,
                completed_at=_event_completed_at_marker(),
            )
            parent = await self._store.get_run(failed.parent_run_id)
            await self._event_writer.write(
                run_id=failed.parent_run_id,
                thread_id=parent.thread_id if parent else None,
                type="subagent.failed",
                source={"kind": "subagent", "id": failed.id, "name": failed.name},
                payload={
                    "subagent_run_id": failed.id,
                    "child_run_id": failed.child_run_id,
                    "name": failed.name,
                    "task": failed.task,
                    "spec_key": failed.spec_key,
                    "status": failed.status.value,
                    "error": error,
                },
            )

    async def cancel_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if not run:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status in _TERMINAL_RUN_STATUSES:
            raise AgentError("BAD_REQUEST", f"Run is already terminal: {run.status.value}")
        cancelled = await self._store.update_run(
            run_id,
            status=AgentRunStatus.CANCELLED,
            completed_at=_event_completed_at_marker(),
            current_approval_id=None,
            current_external_approval=None,
            current_external_run=None,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.cancelled",
            source={"kind": "harness"},
            payload={"status": "cancelled"},
        )
        await self._emit_parent_subagent_cancelled(cancelled)
        await self._after_terminal(cancelled)
        return cancelled

    async def _emit_parent_subagent_cancelled(self, run: AgentRun) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        for subagent_run in subagent_runs:
            cancelled = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.CANCELLED,
                error={"message": "Subagent child run cancelled"},
                completed_at=_event_completed_at_marker(),
            )
            parent = await self._store.get_run(cancelled.parent_run_id)
            await self._event_writer.write(
                run_id=cancelled.parent_run_id,
                thread_id=parent.thread_id if parent else None,
                type="subagent.failed",
                source={"kind": "subagent", "id": cancelled.id, "name": cancelled.name},
                payload={
                    "subagent_run_id": cancelled.id,
                    "child_run_id": cancelled.child_run_id,
                    "name": cancelled.name,
                    "task": cancelled.task,
                    "spec_key": cancelled.spec_key,
                    "status": cancelled.status.value,
                    "error": cancelled.error,
                },
            )


def _event_completed_at_marker() -> str:
    from aithru_agent.persistence.memory.store import utc_now

    return utc_now()


def _error_payload(error: Exception) -> dict[str, str]:
    if isinstance(error, AgentError):
        return {"code": error.code, "message": error.message}
    return {"message": str(error)}


def _approval_decision_value(decision: AgentApprovalDecision | str) -> str:
    return decision.value if isinstance(decision, AgentApprovalDecision) else str(decision)


def _external_run_terminal_status(event_type: str) -> ExternalRunTerminalStatus | None:
    if event_type == "external_run.completed":
        return "completed"
    if event_type == "external_run.failed":
        return "failed"
    if event_type == "external_run.cancelled":
        return "cancelled"
    return None


_TERMINAL_RUN_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
}
