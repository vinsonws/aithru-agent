from aithru_agent.agent import AgentRuntime, PydanticAgentDeps, RunPausedForApproval
from aithru_agent.agent.runtime import (
    PYDANTIC_APPROVAL_LEGACY_METADATA_HISTORY,
    PYDANTIC_APPROVAL_METADATA_HISTORY,
)
from aithru_agent.capabilities import AithruCapabilityRouter
from aithru_agent.domain import (
    AgentApprovalDecision,
    AgentRun,
    AgentRunHarnessOptions,
    AgentRunResult,
    AgentRunSource,
    AgentRunStatus,
    AgentSkill,
    AgentSubagentRunStatus,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import ContextBuilder
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter


class AgentWorkerRunner:
    def __init__(
        self,
        *,
        store: AgentStore,
        event_writer: AgentEventWriter,
        capability_router: AithruCapabilityRouter,
        agent_runtime: AgentRuntime | None = None,
        skill_resolver: AgentSkillResolver | None = None,
    ) -> None:
        self._store = store
        self._event_writer = event_writer
        self._capability_router = capability_router
        self._agent_runtime = agent_runtime or AgentRuntime()
        self._skill_resolver = skill_resolver or EmptySkillResolver()
        self._context_builder = ContextBuilder()

    async def start_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        goal: str,
        scopes: list[str],
        harness_options: AgentRunHarnessOptions | None = None,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        run = await self.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            goal=goal,
            scopes=scopes,
            harness_options=harness_options,
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

    async def execute_run(self, run_id: str) -> AgentRun:
        claimed = await self._store.claim_run(run_id)
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
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.started",
            source={"kind": "model"},
            payload={},
        )

        deps = self._build_deps(run, skill)
        try:
            result = await self._agent_runtime.run(run.goal, deps)
            if result.pending_approval is not None:
                return await self._get_existing_run(run.id)
            return await self._complete_run(run, thread_id, "msg_1", [result.content])
        except RunPausedForApproval:
            return await self._get_existing_run(run.id)
        except AgentError as exc:
            if exc.code == "RUN_PAUSED_FOR_APPROVAL":
                return await self._get_existing_run(run.id)
            return await self._fail_run(run, thread_id, exc)
        except Exception as exc:
            return await self._fail_run(run, thread_id, exc)

    def _build_deps(self, run: AgentRun, skill: AgentSkill | None) -> PydanticAgentDeps:
        return PydanticAgentDeps(
            run=run,
            run_context=self._context_builder.build(run, run.scopes, skill),
            event_writer=self._event_writer,
            capability_router=self._capability_router,
            store=self._store,
            skill=skill,
        )

    async def _get_existing_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        return run

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

    async def claim_run(self, run_id: str) -> AgentRun | None:
        return await self._store.claim_run(run_id)

    async def claim_next_queued_run(self) -> AgentRun | None:
        return await self._store.claim_next_queued_run()

    async def resume_run(
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

        deps = self._build_deps(resumed, skill)
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
            return await self._complete_run(resumed, run.thread_id, "msg_1", [result.content])
        except RunPausedForApproval:
            return await self._get_existing_run(run_id)
        except AgentError as exc:
            if exc.code == "RUN_PAUSED_FOR_APPROVAL":
                return await self._get_existing_run(run_id)
            return await self._fail_run(resumed, run.thread_id, exc)
        except Exception as exc:
            return await self._fail_run(resumed, run.thread_id, exc)

    async def _complete_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        message_id: str,
        final_content: list[str],
    ) -> AgentRun:
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
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.completed",
            source={"kind": "harness"},
            payload={"status": "completed", "result": result.model_dump(mode="json")},
        )
        await self._emit_parent_subagent_completed(run, content)
        return run

    async def _fail_run(
        self,
        run: AgentRun,
        thread_id: str | None,
        error: Exception,
    ) -> AgentRun:
        error_payload = _error_payload(error)
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.failed",
            source={"kind": "model"},
            payload={"error": error_payload},
        )
        failed = await self._store.update_run(
            run.id,
            status=AgentRunStatus.FAILED,
            completed_at=_event_completed_at_marker(),
            current_approval_id=None,
            error=error_payload,
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.failed",
            source={"kind": "harness"},
            payload={"status": "failed", "error": error_payload},
        )
        await self._emit_parent_subagent_failed(failed, error_payload)
        return failed

    async def _emit_parent_subagent_completed(self, run: AgentRun, result: str) -> None:
        if run.source != AgentRunSource.DELEGATED_TASK:
            return
        subagent_runs = await self._store.list_subagent_runs(child_run_id=run.id)
        for subagent_run in subagent_runs:
            completed = await self._store.update_subagent_run(
                subagent_run.id,
                status=AgentSubagentRunStatus.COMPLETED,
                result=result,
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
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.cancelled",
            source={"kind": "harness"},
            payload={"status": "cancelled"},
        )
        await self._emit_parent_subagent_cancelled(cancelled)
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


_TERMINAL_RUN_STATUSES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
}
