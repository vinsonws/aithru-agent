from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter
from dataclasses import dataclass

from aithru_agent.domain import AgentApprovalDecision, AgentRun, AgentRunStatus, AgentToolCallRequest
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import (
    AgentHarnessDriver,
    ContextBuilder,
    HarnessRunDeps,
    HarnessRunPaused,
    HarnessStep,
    HarnessToolCall,
)
from aithru_agent.persistence.protocols import AgentStore
from aithru_agent.skills import AgentSkillResolver, EmptySkillResolver
from aithru_agent.stream import AgentEventWriter


@dataclass
class PendingToolApproval:
    run: AgentRun
    context: AgentRunContext
    request: AgentToolCallRequest
    tool_input: dict
    remaining_steps: list[HarnessStep]
    message_id: str
    final_content: list[str]
    approval_id: str


class AgentWorkerRunner:
    def __init__(
        self,
        *,
        store: AgentStore,
        event_writer: AgentEventWriter,
        capability_router: AithruCapabilityRouter,
        driver: AgentHarnessDriver,
        skill_resolver: AgentSkillResolver | None = None,
    ) -> None:
        self._store = store
        self._event_writer = event_writer
        self._capability_router = capability_router
        self._driver = driver
        self._skill_resolver = skill_resolver or EmptySkillResolver()
        self._context_builder = ContextBuilder()
        self._tool_counter = 0
        self._pending_approvals: dict[str, PendingToolApproval] = {}

    async def start_run(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        goal: str,
        scopes: list[str],
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        run = await self.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            goal=goal,
            scopes=scopes,
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
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> AgentRun:
        workspace = await self._store.create_workspace(org_id=org_id, thread_id=thread_id)
        run = await self._store.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            source="api",
            goal=goal,
            workspace_id=workspace.id,
            scopes=scopes,
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
        run = await self._store.get_run(run_id)
        if run is None:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        if run.status != AgentRunStatus.QUEUED:
            raise AgentError("BAD_REQUEST", f"Run is not queued: {run_id}")

        run = await self._store.update_run(run.id, status=AgentRunStatus.RUNNING)
        thread_id = run.thread_id
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.started",
            source={"kind": "harness"},
            payload={"status": "running"},
        )
        message_id = "msg_1"
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="message.created",
            source={"kind": "harness"},
            payload={"message_id": message_id, "role": "assistant"},
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="model.started",
            source={"kind": "model"},
            payload={},
        )

        skill = self._skill_resolver.resolve(run.skill_id) if run.skill_id else None
        context = self._context_builder.build(run, run.scopes, skill)
        final_content: list[str] = []
        try:
            steps = await self._driver.run(
                run.goal,
                HarnessRunDeps(
                    run=run,
                    run_context=context,
                    event_writer=self._event_writer,
                    capability_router=self._capability_router,
                    store=self._store,
                    skill=skill,
                ),
            )
            for index, step in enumerate(steps):
                if step.type == "message" and step.text is not None:
                    final_content.append(step.text)
                    await self._event_writer.write(
                        run_id=run.id,
                        thread_id=thread_id,
                        type="message.delta",
                        source={"kind": "model"},
                        payload={"message_id": message_id, "delta": step.text},
                    )
                elif step.type == "tool" and step.tool_call is not None:
                    paused = await self._execute_tool_step(
                        run,
                        context,
                        step.tool_call,
                        remaining_steps=steps[index + 1 :],
                        message_id=message_id,
                        final_content=final_content,
                    )
                    if paused:
                        paused_run = await self._store.get_run(run.id)
                        if paused_run is None:
                            raise AgentError("NOT_FOUND", f"Run not found: {run.id}")
                        return paused_run
                elif step.type == "finish":
                    break
        except HarnessRunPaused:
            paused_run = await self._store.get_run(run.id)
            if paused_run is None:
                raise AgentError("NOT_FOUND", f"Run not found: {run.id}")
            return paused_run
        except Exception as exc:
            return await self._fail_run(run, thread_id, exc)

        return await self._complete_run(run, thread_id, message_id, final_content)

    async def find_next_queued_run(self) -> AgentRun | None:
        for run in await self._store.list_runs():
            if run.status == AgentRunStatus.QUEUED:
                return run
        return None

    async def resume_run(
        self,
        run_id: str,
        *,
        approval_id: str,
        decision: AgentApprovalDecision | str,
        comment: str | None = None,
    ) -> AgentRun:
        pending = self._pending_approvals.get(run_id)
        if pending is None:
            return await self._resume_persisted_approval(
                run_id,
                approval_id=approval_id,
                decision=decision,
                comment=comment,
            )
        if pending.approval_id != approval_id:
            raise AgentError("AUTHZ_DENIED", f"Approval id does not match: {approval_id}")

        resolved = await self._store.resolve_approval(
            approval_id,
            decision=decision,
            comment=comment,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=pending.run.thread_id,
            type="approval.resolved",
            source={"kind": "approval"},
            payload={
                "approval_id": approval_id,
                "tool_call_id": pending.request.id,
                "tool_name": pending.request.tool_name,
                "decision": _approval_decision_value(resolved.decision or decision),
                "comment": comment,
            },
        )

        if str(decision) == AgentApprovalDecision.REJECTED.value:
            self._pending_approvals.pop(run_id, None)
            failed = await self._store.update_run(
                run_id,
                status=AgentRunStatus.FAILED,
                error={"message": "Approval rejected"},
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=pending.run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": pending.request.id,
                    "tool_name": pending.request.tool_name,
                    "reason": comment,
                },
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=pending.run.thread_id,
                type="run.failed",
                source={"kind": "harness"},
                payload={"status": "failed", "error": {"message": "Approval rejected"}},
            )
            return failed

        resumed = await self._store.update_run(run_id, status=AgentRunStatus.RUNNING, current_approval_id=None)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=pending.run.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={"status": "running"},
        )
        approved_request = pending.request.model_copy(
            update={"already_approved": True, "requested_by": "harness"}
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=pending.run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": approved_request.id, "tool_name": approved_request.tool_name},
        )
        try:
            result = await self._capability_router.execute_tool_call(approved_request, pending.context)
            await self._emit_domain_tool_event(
                resumed,
                approved_request.id,
                approved_request.tool_name,
                result.output,
            )
            await self._event_writer.write(
                run_id=run_id,
                thread_id=pending.run.thread_id,
                type="tool.completed" if result.status == "completed" else "tool.failed",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": approved_request.id,
                    "tool_name": approved_request.tool_name,
                    "status": result.status,
                    "output": result.output,
                    "error": result.error,
                },
            )
            if result.status != "completed":
                error = AgentError("TOOL_FAILED", _tool_result_error_message(result.error))
                self._pending_approvals.pop(run_id, None)
                return await self._fail_run(resumed, pending.run.thread_id, error)
        except Exception as exc:
            await self._emit_tool_exception(
                resumed,
                approved_request.id,
                approved_request.tool_name,
                exc,
            )
            self._pending_approvals.pop(run_id, None)
            return await self._fail_run(resumed, pending.run.thread_id, exc)
        self._pending_approvals.pop(run_id, None)

        try:
            for step in pending.remaining_steps:
                if step.type == "message" and step.text is not None:
                    pending.final_content.append(step.text)
                    await self._event_writer.write(
                        run_id=run_id,
                        thread_id=pending.run.thread_id,
                        type="message.delta",
                        source={"kind": "model"},
                        payload={"message_id": pending.message_id, "delta": step.text},
                    )
                elif step.type == "tool" and step.tool_call is not None:
                    paused = await self._execute_tool_step(
                        resumed,
                        pending.context,
                        step.tool_call,
                        remaining_steps=[],
                        message_id=pending.message_id,
                        final_content=pending.final_content,
                    )
                    if paused:
                        paused_run = await self._store.get_run(run_id)
                        if paused_run is None:
                            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
                        return paused_run
                elif step.type == "finish":
                    break
        except Exception as exc:
            return await self._fail_run(resumed, pending.run.thread_id, exc)

        return await self._complete_run(
            resumed,
            pending.run.thread_id,
            pending.message_id,
            pending.final_content,
        )

    async def _resume_persisted_approval(
        self,
        run_id: str,
        *,
        approval_id: str,
        decision: AgentApprovalDecision | str,
        comment: str | None,
    ) -> AgentRun:
        approval = await self._store.get_approval(approval_id)
        if approval is None or approval.run_id != run_id:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for approval: {run_id}")
        run = await self._store.get_run(run_id)
        if run is None or run.status != AgentRunStatus.WAITING_APPROVAL:
            raise AgentError("RUN_NOT_RESUMABLE", f"Run is not waiting for approval: {run_id}")

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

        resumed = await self._store.update_run(run_id, status=AgentRunStatus.RUNNING, current_approval_id=None)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.resumed",
            source={"kind": "harness"},
            payload={"status": "running"},
        )
        skill = self._skill_resolver.resolve(run.skill_id) if run.skill_id else None
        context = self._context_builder.build(resumed, resumed.scopes, skill)
        approved_request = AgentToolCallRequest(
            id=approval.tool_call_id,
            tool_name=approval.tool_name,
            input=approval.tool_input or {},
            requested_by="harness",
            already_approved=True,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": approval.tool_call_id, "tool_name": approval.tool_name},
        )
        try:
            result = await self._capability_router.execute_tool_call(approved_request, context)
        except Exception as exc:
            await self._emit_tool_exception(resumed, approval.tool_call_id, approval.tool_name, exc)
            return await self._fail_run(resumed, run.thread_id, exc)

        await self._emit_domain_tool_event(
            resumed,
            approval.tool_call_id,
            approval.tool_name,
            result.output,
        )
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="tool.completed" if result.status == "completed" else "tool.failed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": approval.tool_call_id,
                "tool_name": approval.tool_name,
                "status": result.status,
                "output": result.output,
                "error": result.error,
            },
        )
        if result.status != "completed":
            return await self._fail_run(
                resumed,
                run.thread_id,
                AgentError("TOOL_FAILED", _tool_result_error_message(result.error)),
            )
        return await self._complete_run(resumed, run.thread_id, "msg_1", [])

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
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="message.completed",
            source={"kind": "harness"},
            payload={"message_id": message_id, "content": content},
        )
        run = await self._store.update_run(
            run.id,
            status=AgentRunStatus.COMPLETED,
            completed_at=_event_completed_at_marker(),
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=thread_id,
            type="run.completed",
            source={"kind": "harness"},
            payload={"status": "completed"},
        )
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
        return failed

    async def cancel_run(self, run_id: str) -> AgentRun:
        run = await self._store.get_run(run_id)
        if not run:
            raise AgentError("NOT_FOUND", f"Run not found: {run_id}")
        cancelled = await self._store.update_run(run_id, status=AgentRunStatus.CANCELLED)
        await self._event_writer.write(
            run_id=run_id,
            thread_id=run.thread_id,
            type="run.cancelled",
            source={"kind": "harness"},
            payload={"status": "cancelled"},
        )
        return cancelled

    async def _execute_tool_step(
        self,
        run: AgentRun,
        context: AgentRunContext,
        tool_call: HarnessToolCall,
        *,
        remaining_steps: list[HarnessStep],
        message_id: str,
        final_content: list[str],
    ) -> bool:
        self._tool_counter += 1
        tool_call_id = f"toolcall_{self._tool_counter}"
        request = AgentToolCallRequest(
            id=tool_call_id,
            tool_name=tool_call.name,
            input=tool_call.input,
            requested_by="model",
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="tool.proposed",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_call.name},
        )
        prepared = await self._capability_router.prepare_tool_call(request, context)
        if prepared.status == "denied":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={"tool_call_id": tool_call_id, "tool_name": tool_call.name, "reason": prepared.reason},
            )
            return False
        if prepared.status == "waiting_approval":
            approval = await self._store.create_approval(
                run_id=run.id,
                tool_call_id=tool_call_id,
                tool_name=tool_call.name,
                tool_input=tool_call.input,
            )
            self._pending_approvals[run.id] = PendingToolApproval(
                run=run,
                context=context,
                request=request,
                tool_input=tool_call.input,
                remaining_steps=remaining_steps,
                message_id=message_id,
                final_content=final_content,
                approval_id=approval.id,
            )
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="approval.requested",
                source={"kind": "approval"},
                payload={
                    "approval_id": approval.id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_call.name,
                    "status": "pending",
                    "output": prepared.output,
                },
            )
            await self._store.update_run(
                run.id,
                status=AgentRunStatus.WAITING_APPROVAL,
                current_approval_id=approval.id,
            )
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="run.paused",
                source={"kind": "harness"},
                payload={
                    "status": "waiting_approval",
                    "approval_id": approval.id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_call.name,
                },
            )
            return True
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_call.name},
        )
        try:
            result = await self._capability_router.execute_tool_call(request, context)
        except Exception as exc:
            await self._emit_tool_exception(run, tool_call_id, tool_call.name, exc)
            raise
        await self._emit_domain_tool_event(run, tool_call_id, tool_call.name, result.output)
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="tool.completed" if result.status == "completed" else "tool.failed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_call.name,
                "status": result.status,
                "output": result.output,
                "error": result.error,
            },
        )
        if result.status != "completed":
            raise AgentError("TOOL_FAILED", _tool_result_error_message(result.error))
        return False

    async def _emit_tool_exception(
        self,
        run: AgentRun,
        tool_call_id: str,
        tool_name: str,
        error: Exception,
    ) -> None:
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="tool.failed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "failed",
                "output": None,
                "error": _error_payload(error),
            },
        )

    async def _emit_domain_tool_event(
        self,
        run: AgentRun,
        tool_call_id: str,
        tool_name: str,
        output: object,
    ) -> None:
        if not isinstance(output, dict):
            return
        if tool_name == "todo.create":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="todo.created",
                source={"kind": "harness"},
                payload=output,
            )
        elif tool_name == "todo.update":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="todo.updated",
                source={"kind": "harness"},
                payload=output,
            )
        elif tool_name == "workspace.write_file":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="workspace.file.created",
                source={"kind": "workspace"},
                payload={"tool_call_id": tool_call_id, **output},
            )
        elif tool_name == "workspace.read_file":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="workspace.file.read",
                source={"kind": "workspace"},
                payload={"tool_call_id": tool_call_id, **output},
            )
        elif tool_name == "artifact.create":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="artifact.created",
                source={"kind": "artifact"},
                payload=output,
            )


def _event_completed_at_marker() -> str:
    from aithru_agent.persistence.memory.store import utc_now

    return utc_now()


def _error_payload(error: Exception) -> dict[str, str]:
    if isinstance(error, AgentError):
        return {"code": error.code, "message": error.message}
    return {"message": str(error)}


def _tool_result_error_message(error: dict | None) -> str:
    if not error:
        return "Tool failed"
    message = error.get("message")
    return str(message) if message else "Tool failed"


def _approval_decision_value(decision: AgentApprovalDecision | str) -> str:
    return decision.value if isinstance(decision, AgentApprovalDecision) else str(decision)
