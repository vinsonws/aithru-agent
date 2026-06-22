"""Bridge Pydantic AI tool calls through the Aithru capability router."""

from typing import Any

from pydantic_ai import RunContext

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.exceptions import (
    RunPausedForApproval,
    RunPausedForExternalApproval,
    RunPausedForExternalRun,
    RunPausedForInput,
    RunPausedForSubagent,
)
from aithru_agent.domain import (
    AgentAuthorizationDecision,
    AgentCapabilityAuditEvent,
    AgentExternalApprovalRef,
    AgentExternalRunWaitRef,
    AgentRunStatus,
    AgentTodoStatus,
    AgentToolCallRequest,
)
from aithru_agent.domain.errors import AgentError
from aithru_agent.domain.research import (
    ResearchRecoverableToolFailure,
    ResearchTodoProgressOutcome,
    ResearchToolFailure,
    research_limitation_for_tool_failure,
    research_todo_progress_for_tool,
)


class PydanticAIToolBridge:
    """Converts Pydantic AI tool calls into capability-router requests."""

    def __init__(
        self,
        *,
        deps: PydanticAgentDeps,
    ) -> None:
        self._deps = deps
        self._run = deps.run
        self._run_context = deps.run_context
        self._event_writer = deps.event_writer
        self._capability_router = deps.capability_router

    async def call_tool(
        self,
        ctx: RunContext[PydanticAgentDeps],
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> object:
        """Call a tool via the Aithru capability router."""
        await self._raise_if_cancelled()
        tool_call_id = ctx.tool_call_id or f"pydantic:{tool_name}:{ctx.run_step}"
        already_approved = bool(ctx.tool_call_approved)

        request = AgentToolCallRequest(
            id=tool_call_id,
            tool_name=tool_name,
            input=tool_input,
            requested_by="model",
            already_approved=already_approved,
        )

        if not already_approved:
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.proposed",
                source={"kind": "tool"},
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "input": tool_input},
            )

        prepared = await self._capability_router.prepare_tool_call(request, self._run_context)
        if prepared.status == "denied":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "reason": prepared.reason,
                    **_governance_payload(prepared.authorization, prepared.audit),
                },
            )
            return {"status": "denied", "reason": prepared.reason}

        if prepared.status == "waiting_approval":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.failed",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "status": "failed",
                    "error": {
                        "message": "Tool required approval but was not deferred by Pydantic AI",
                    },
                    **_governance_payload(prepared.authorization, prepared.audit),
                },
            )
            raise AgentError(
                "TOOL_APPROVAL_NOT_DEFERRED",
                "Tool required approval but was not deferred by Pydantic AI; check tool.requires_approval setup",
            )

        descriptor = await self._capability_router.get_tool_descriptor(tool_name, self._run_context)
        allow_recoverable_failure = (
            descriptor is not None
            and _failure_policy_value(descriptor.failure_policy) == "return_recoverable"
        )

        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
        )
        try:
            await self._raise_if_cancelled()
            result = await self._capability_router.execute_tool_call(request, self._run_context)
        except (
            RunPausedForApproval,
            RunPausedForExternalApproval,
            RunPausedForExternalRun,
            RunPausedForInput,
            RunPausedForSubagent,
        ):
            raise
        except Exception as exc:
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="tool.failed",
                source={"kind": "tool"},
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "status": "failed",
                    "output": None,
                    "error": _error_payload(exc),
                },
            )
            raise
        recoverable_failure: ResearchRecoverableToolFailure | None = None
        await self._emit_external_run_events(tool_call_id, tool_name, result)
        if result.status == "waiting_approval":
            await self._emit_tool_result_event(tool_call_id, tool_name, result)
            await self._pause_for_external_approval(tool_call_id, tool_name, result)
        if result.status == "running":
            await self._emit_tool_result_event(tool_call_id, tool_name, result)
            await self._pause_for_external_run(tool_call_id, tool_name, result)
        if result.status == "completed":
            await self._emit_domain_event(tool_call_id, tool_name, result.output)
        else:
            recoverable_failure = await self._emit_failed_domain_event(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_input=tool_input,
                error=result.error,
                allow_recoverable=allow_recoverable_failure,
            )
        await self._emit_tool_result_event(tool_call_id, tool_name, result)
        if result.status != "completed":
            if recoverable_failure is not None:
                return _recoverable_failure_payload(recoverable_failure)
            raise AgentError("TOOL_FAILED", _tool_result_error_message(result.error))
        if tool_name == "input.request":
            await self._pause_for_input(tool_call_id, result.output)
        return result.output

    async def _emit_tool_result_event(
        self,
        tool_call_id: str,
        tool_name: str,
        result: object,
    ) -> None:
        status = getattr(result, "status", "failed")
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.completed" if status in {"completed", "waiting_approval", "running"} else "tool.failed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": status,
                "output": getattr(result, "output", None),
                "error": getattr(result, "error", None),
                "external_run": result.external_run.model_dump(mode="json")
                if getattr(result, "external_run", None) is not None
                else None,
                **_governance_payload(
                    getattr(result, "authorization", None),
                    getattr(result, "audit", None),
                ),
            },
        )

    async def _pause_for_external_approval(
        self,
        tool_call_id: str,
        tool_name: str,
        result: object,
    ) -> None:
        external_run = getattr(result, "external_run", None)
        if external_run is None or external_run.approval_id is None:
            raise AgentError(
                "TOOL_FAILED",
                "Workflow capability requested approval without an external approval reference",
            )
        approval_ref = AgentExternalApprovalRef(
            kind=external_run.kind,
            capability_key=external_run.capability_key,
            capability_run_id=external_run.capability_run_id,
            approval_id=external_run.approval_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            correlation_id=external_run.correlation_id,
            status="pending",
        )
        await self._deps.store.update_run(
            self._run.id,
            status=AgentRunStatus.WAITING_APPROVAL,
            current_approval_id=None,
            current_external_approval=approval_ref,
        )
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_approval",
                "approval_kind": "external",
                "current_external_approval": approval_ref.model_dump(mode="json"),
            },
        )
        raise RunPausedForExternalApproval(
            self._run.id,
            external_run.approval_id,
            external_run.capability_run_id,
        )

    async def _pause_for_external_run(
        self,
        tool_call_id: str,
        tool_name: str,
        result: object,
    ) -> None:
        external_run = getattr(result, "external_run", None)
        if external_run is None:
            raise AgentError(
                "TOOL_FAILED",
                "Workflow capability returned a running status without an external run reference",
            )
        run_ref = AgentExternalRunWaitRef(
            kind=external_run.kind,
            capability_key=external_run.capability_key,
            capability_run_id=external_run.capability_run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            correlation_id=external_run.correlation_id,
            status="running",
        )
        await self._deps.store.update_run(
            self._run.id,
            status=AgentRunStatus.WAITING_EXTERNAL_RUN,
            current_approval_id=None,
            current_external_approval=None,
            current_external_run=run_ref,
        )
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={
                "status": "waiting_external_run",
                "current_external_run": run_ref.model_dump(mode="json"),
            },
        )
        raise RunPausedForExternalRun(
            self._run.id,
            external_run.capability_run_id,
        )

    async def _emit_external_run_events(
        self,
        tool_call_id: str,
        tool_name: str,
        result: object,
    ) -> None:
        external_run = getattr(result, "external_run", None)
        if external_run is None:
            return
        payload = {
            "kind": external_run.kind,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "capability_key": external_run.capability_key,
            "capability_run_id": external_run.capability_run_id,
            "status": external_run.status,
            "correlation_id": external_run.correlation_id,
            "approval_id": external_run.approval_id,
        }
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="external_run.created",
            source={"kind": "workflow"},
            payload=payload,
        )
        if external_run.approval_id is not None:
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="external_approval.requested",
                source={"kind": "workflow"},
                payload={
                    "kind": external_run.kind,
                    "capability_run_id": external_run.capability_run_id,
                    "approval_id": external_run.approval_id,
                },
            )
        terminal_type = _external_run_terminal_event_type(external_run.status)
        if terminal_type is None:
            return
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type=terminal_type,
            source={"kind": "workflow"},
            payload=payload,
        )

    async def _raise_if_cancelled(self) -> None:
        latest = await self._deps.store.get_run(self._run.id)
        if latest is not None and latest.status == AgentRunStatus.CANCELLED:
            raise AgentError("RUN_CANCELLED", f"Run is cancelled: {self._run.id}")

    async def _pause_for_input(self, tool_call_id: str, output: object) -> None:
        input_output = output if isinstance(output, dict) else {}
        input_request_id = _string_value(input_output.get("input_request_id")) or tool_call_id
        prompt = _string_value(input_output.get("prompt")) or "Input requested."
        reason = _string_value(input_output.get("reason"))
        payload = {
            "input_request_id": input_request_id,
            "tool_call_id": tool_call_id,
            "prompt": prompt,
            "reason": reason,
        }
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="input.requested",
            source={"kind": "harness"},
            payload=payload,
        )
        await self._deps.store.update_run(self._run.id, status=AgentRunStatus.WAITING_INPUT)
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="run.paused",
            source={"kind": "harness"},
            payload={"status": "waiting_input", **payload},
        )
        raise RunPausedForInput(self._run.id, input_request_id)

    async def _emit_domain_event(self, tool_call_id: str, tool_name: str, output: object) -> None:
        if not isinstance(output, dict):
            return
        if tool_name == "workspace.read_file":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="workspace.file.read",
                source={"kind": "workspace"},
                payload={"tool_call_id": tool_call_id, **output},
            )
        elif tool_name == "workspace.write_file":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="workspace.file.created",
                source={"kind": "workspace"},
                payload={"tool_call_id": tool_call_id, **output},
            )
        elif tool_name == "todo.create":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="todo.created",
                source={"kind": "harness"},
                payload=output,
            )
        elif tool_name == "todo.update":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="todo.updated",
                source={"kind": "harness"},
                payload=output,
            )
        elif tool_name == "research.create_plan":
            todos = output.get("todos")
            if isinstance(todos, list):
                for todo in todos:
                    if isinstance(todo, dict):
                        await self._event_writer.write(
                            run_id=self._run.id,
                            thread_id=self._run.thread_id,
                            type="todo.created",
                            source={"kind": "harness"},
                            payload=todo,
                        )
        elif tool_name == "artifact.create":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="artifact.created",
                source={"kind": "artifact"},
                payload=output,
            )
        elif tool_name == "research.create_report":
            artifact = output.get("artifact")
            if isinstance(artifact, dict):
                await self._event_writer.write(
                    run_id=self._run.id,
                    thread_id=self._run.thread_id,
                    type="artifact.created",
                    source={"kind": "artifact"},
                    payload=artifact,
                )
            await self._emit_research_todo_progress(tool_name)
        elif tool_name == "web.search":
            results = output.get("results")
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="web.search.completed",
                source={"kind": "web"},
                payload={
                    "tool_call_id": tool_call_id,
                    "query": output.get("query"),
                    "result_count": len(results) if isinstance(results, list) else 0,
                    "results": results if isinstance(results, list) else [],
                },
            )
            await self._emit_research_todo_progress(tool_name)
        elif tool_name == "web.fetch":
            content = output.get("content")
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="web.fetch.completed",
                source={"kind": "web"},
                payload={
                    "tool_call_id": tool_call_id,
                    "url": output.get("url"),
                    "status_code": output.get("status_code"),
                    "media_type": output.get("media_type"),
                    "content_length": len(content) if isinstance(content, str) else 0,
                    "truncated": output.get("truncated"),
                },
            )
            await self._emit_research_todo_progress(tool_name)
        elif tool_name == "artifact.finalize":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="artifact.finalized",
                source={"kind": "artifact"},
                payload=output,
            )
        elif tool_name == "memory.search":
            entries = output.get("entries") if isinstance(output.get("entries"), list) else []
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="memory.read",
                source={"kind": "memory"},
                payload={"operation": "read", "count": len(entries)},
            )
        elif tool_name == "memory.remember":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="memory.written",
                source={"kind": "memory"},
                payload={
                    "operation": "write",
                    "memory_id": output.get("id"),
                    "memory_scope": output.get("scope"),
                    "key": output.get("key"),
                },
            )

    async def _emit_failed_domain_event(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        error: dict | None,
        allow_recoverable: bool,
    ) -> ResearchRecoverableToolFailure | None:
        if not allow_recoverable:
            return None
        if tool_name == "web.search":
            error_payload = error or {"message": "Tool failed"}
            limitation = research_limitation_for_tool_failure(
                ResearchToolFailure(
                    tool_name="web.search",
                    query=_string_value(tool_input.get("query")),
                    error_message=_tool_result_error_message(error_payload),
                )
            )
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="web.search.failed",
                source={"kind": "web"},
                payload={
                    "tool_call_id": tool_call_id,
                    "query": tool_input.get("query"),
                    "error": error_payload,
                    "limitation": limitation.model_dump(mode="json"),
                },
            )
            await self._emit_research_todo_progress(tool_name, outcome="failed")
            return ResearchRecoverableToolFailure(
                tool_name="web.search",
                query=_string_value(tool_input.get("query")),
                error=error_payload,
                limitation=limitation,
            )
        elif tool_name == "web.fetch":
            error_payload = error or {"message": "Tool failed"}
            limitation = research_limitation_for_tool_failure(
                ResearchToolFailure(
                    tool_name="web.fetch",
                    url=_string_value(tool_input.get("url")),
                    error_message=_tool_result_error_message(error_payload),
                )
            )
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="web.fetch.failed",
                source={"kind": "web"},
                payload={
                    "tool_call_id": tool_call_id,
                    "url": tool_input.get("url"),
                    "error": error_payload,
                    "limitation": limitation.model_dump(mode="json"),
                },
            )
            await self._emit_research_todo_progress(tool_name, outcome="failed")
            return ResearchRecoverableToolFailure(
                tool_name="web.fetch",
                url=_string_value(tool_input.get("url")),
                error=error_payload,
                limitation=limitation,
            )
        return None

    async def _emit_research_todo_progress(
        self,
        tool_name: str,
        *,
        outcome: ResearchTodoProgressOutcome = "completed",
    ) -> None:
        progress_updates = research_todo_progress_for_tool(tool_name, outcome=outcome)
        if not progress_updates:
            return
        todos = await self._deps.store.list_todos(self._run.id)
        for progress in progress_updates:
            todo = next(
                (
                    candidate
                    for candidate in todos
                    if candidate.title == progress.todo_title
                    and _todo_status_value(candidate.status) != progress.status
                ),
                None,
            )
            if todo is None:
                continue
            updated = await self._deps.store.update_todo(
                todo.id,
                status=AgentTodoStatus(progress.status),
            )
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="todo.updated",
                source={"kind": "harness"},
                payload=updated.model_dump(mode="json"),
            )


def _tool_result_error_message(error: dict | None) -> str:
    if not error:
        return "Tool failed"
    message = error.get("message")
    return str(message) if message else "Tool failed"


def _error_payload(error: Exception) -> dict[str, str]:
    if isinstance(error, AgentError):
        return {"code": error.code, "message": error.message}
    return {"message": str(error)}


def _todo_status_value(status: AgentTodoStatus | str) -> str:
    return status.value if isinstance(status, AgentTodoStatus) else str(status)


def _failure_policy_value(policy: object) -> str:
    value = getattr(policy, "value", policy)
    return str(value)


def _governance_payload(
    authorization: AgentAuthorizationDecision | None,
    audit: AgentCapabilityAuditEvent | None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if authorization is not None:
        payload["authorization_decision"] = authorization.model_dump(mode="json")
    if audit is not None:
        payload["audit"] = audit.model_dump(mode="json", by_alias=True)
    return payload


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _recoverable_failure_payload(failure: ResearchRecoverableToolFailure) -> dict:
    payload = failure.model_dump(mode="json")
    if payload.get("query") is None:
        payload.pop("query", None)
    if payload.get("url") is None:
        payload.pop("url", None)
    return payload


def _external_run_terminal_event_type(status: object) -> str | None:
    match str(status):
        case "completed":
            return "external_run.completed"
        case "failed" | "denied":
            return "external_run.failed"
        case "cancelled":
            return "external_run.cancelled"
        case _:
            return None
