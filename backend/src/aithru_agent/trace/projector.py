from typing import cast

from aithru_agent.stream import AgentStreamEvent

from .spans import AgentTraceSpan, AgentTraceSpanKind, AgentTraceSpanStatus


def project_trace_spans(events: list[AgentStreamEvent]) -> list[AgentTraceSpan]:
    spans: dict[str, AgentTraceSpan] = {}
    sorted_events = sorted(events, key=lambda event: event.sequence)

    for event in sorted_events:
        if event.type == "run.created":
            spans[f"run:{event.run_id}"] = _start_span(event, "run", "run")
            continue
        if event.type in {"run.completed", "run.failed", "run.cancelled"}:
            status: AgentTraceSpanStatus = (
                "completed"
                if event.type == "run.completed"
                else "cancelled"
                if event.type == "run.cancelled"
                else "failed"
            )
            _finish_span(spans, f"run:{event.run_id}", event, status)
            if status == "failed":
                _finish_open_span(spans, f"model:{event.run_id}", event, "failed")
            continue

        if event.type == "model.started":
            spans[f"model:{event.run_id}"] = _start_span(event, "model", "model")
            continue
        if event.type in {"model.completed", "model.failed"}:
            _finish_span(
                spans,
                f"model:{event.run_id}",
                event,
                "completed" if event.type == "model.completed" else "failed",
            )
            continue

        if event.type == "message.created":
            message_id = _payload_value(event, "message_id", "messageId") or f"{event.sequence}"
            role = _payload_value(event, "role") or "message"
            spans[f"message:{message_id}"] = _start_span(
                event,
                "message",
                str(role),
                refs={"message_id": message_id, "role": role},
            )
            continue
        if event.type in {"message.completed", "message.failed"}:
            message_id = _payload_value(event, "message_id", "messageId")
            if message_id:
                _finish_span(
                    spans,
                    f"message:{message_id}",
                    event,
                    "completed" if event.type == "message.completed" else "failed",
                )
            continue

        if event.type == "tool.started":
            tool_call_id = _payload_value(event, "tool_call_id", "toolCallId") or f"{event.sequence}"
            tool_name = _payload_value(event, "tool_name", "toolName") or "tool"
            spans[f"tool:{tool_call_id}"] = _start_span(
                event,
                "tool",
                str(tool_name),
                refs={"tool_call_id": tool_call_id},
            )
            continue
        if event.type in {"tool.completed", "tool.failed", "tool.denied"}:
            tool_call_id = _payload_value(event, "tool_call_id", "toolCallId")
            if tool_call_id:
                _finish_span(
                    spans,
                    f"tool:{tool_call_id}",
                    event,
                    "completed" if event.type == "tool.completed" else "failed",
                )
            continue

        if event.type == "approval.requested":
            approval_id = _payload_value(event, "approval_id", "approvalId") or f"{event.sequence}"
            spans[f"approval:{approval_id}"] = _start_span(
                event,
                "approval",
                "approval",
                refs={"approval_id": approval_id},
            )
            continue
        if event.type in {"approval.resolved", "approval.expired"}:
            approval_id = _payload_value(event, "approval_id", "approvalId")
            if approval_id:
                _finish_span(
                    spans,
                    f"approval:{approval_id}",
                    event,
                    "completed" if event.type == "approval.resolved" else "failed",
                )
            continue

        if event.type == "todo.created":
            todo_id = _payload_value(event, "todo_id", "todoId", "id") or f"{event.sequence}"
            title = _payload_value(event, "title") or "todo"
            status = _payload_value(event, "status")
            spans[f"todo:{todo_id}"] = _start_span(
                event,
                "todo",
                str(title),
                refs={"todo_id": todo_id, "status": status} if status else {"todo_id": todo_id},
            )
            if status in {"done", "blocked", "cancelled"}:
                _finish_span(spans, f"todo:{todo_id}", event, _todo_span_status(status))
            continue
        if event.type in {"todo.updated", "todo.completed", "todo.blocked", "todo.cancelled"}:
            todo_id = _payload_value(event, "todo_id", "todoId", "id")
            if todo_id:
                span_id = f"todo:{todo_id}"
                existing = spans.get(span_id)
                status_value = _payload_value(event, "status") or _todo_status_from_event_type(event.type)
                if existing:
                    spans[span_id] = existing.model_copy(
                        update={
                            "name": str(_payload_value(event, "title") or existing.name),
                            "refs": {"todo_id": todo_id, "status": status_value},
                        }
                    )
                else:
                    spans[span_id] = _start_span(
                        event,
                        "todo",
                        str(_payload_value(event, "title") or "todo"),
                        refs={"todo_id": todo_id, "status": status_value},
                    )
                if status_value in {"done", "blocked", "cancelled"}:
                    _finish_span(spans, span_id, event, _todo_span_status(status_value))
            continue

        if event.type == "subagent.started":
            subagent_run_id = _payload_value(event, "subagent_run_id", "subagentRunId") or f"{event.sequence}"
            child_run_id = _payload_value(event, "child_run_id", "childRunId")
            name = _payload_value(event, "name") or "subagent"
            refs = {"subagent_run_id": subagent_run_id}
            if child_run_id:
                refs["child_run_id"] = child_run_id
            span_id = f"subagent:{subagent_run_id}"
            spans[span_id] = _start_span(
                event,
                "subagent",
                str(name),
                refs=refs,
            )
            continue
        if event.type in {"subagent.completed", "subagent.failed"}:
            subagent_run_id = _payload_value(event, "subagent_run_id", "subagentRunId")
            if subagent_run_id:
                status = (
                    "cancelled"
                    if _payload_value(event, "status") == "cancelled"
                    else "completed"
                    if event.type == "subagent.completed"
                    else "failed"
                )
                _finish_span(
                    spans,
                    f"subagent:{subagent_run_id}",
                    event,
                    status,
                )
            continue

        if event.type == "sandbox.started":
            sandbox_run_id = _payload_value(event, "sandbox_run_id", "sandboxRunId") or f"{event.sequence}"
            language = _payload_value(event, "language") or "sandbox"
            span_id = f"sandbox:{sandbox_run_id}"
            spans[span_id] = _start_span(
                event,
                "sandbox",
                str(language),
                refs={"language": language},
            )
            continue
        if event.type in {"sandbox.completed", "sandbox.failed"}:
            sandbox_run_id = _payload_value(event, "sandbox_run_id", "sandboxRunId")
            if sandbox_run_id:
                _finish_span(
                    spans,
                    f"sandbox:{sandbox_run_id}",
                    event,
                    "completed" if event.type == "sandbox.completed" else "failed",
                )
            continue

        if event.type.startswith("workspace.file."):
            path = _payload_value(event, "path")
            span_id = f"workspace:{event.run_id}:{event.sequence}"
            spans[span_id] = _start_span(
                event,
                "workspace",
                event.type,
                refs={"path": path} if path else None,
            )
            _finish_span(spans, span_id, event, "completed")
            continue

        if event.type in {"artifact.created", "artifact.updated", "artifact.finalized"}:
            artifact_id = _payload_value(event, "artifact_id", "artifactId", "id") or f"{event.sequence}"
            span_id = f"artifact:{artifact_id}"
            spans[span_id] = _start_span(
                event,
                "artifact",
                event.type,
                refs={"artifact_id": artifact_id},
            )
            _finish_span(spans, span_id, event, "completed")

        if event.type in {"memory.read", "memory.written", "memory.skipped"}:
            span_id = f"memory:{event.run_id}:{event.sequence}"
            refs = {
                key: value
                for key, value in {
                    "operation": _payload_value(event, "operation"),
                    "memory_scope": _payload_value(event, "memory_scope", "memoryScope", "scope"),
                    "count": _payload_value(event, "count"),
                }.items()
                if value is not None
            }
            spans[span_id] = _start_span(
                event,
                "memory",
                event.type,
                refs=refs or None,
            )
            _finish_span(
                spans,
                span_id,
                event,
                "failed" if event.type == "memory.skipped" else "completed",
            )

    return list(spans.values())


def _start_span(
    event: AgentStreamEvent,
    kind: str,
    name: str,
    refs: dict | None = None,
) -> AgentTraceSpan:
    return AgentTraceSpan(
        id=f"{kind}:{event.run_id}" if kind in {"run", "model"} else "",
        run_id=event.run_id,
        kind=cast(AgentTraceSpanKind, kind),
        name=name,
        status="running",
        start_sequence=event.sequence,
        started_at=event.timestamp,
        refs=refs,
    )


def _finish_span(
    spans: dict[str, AgentTraceSpan],
    span_id: str,
    event: AgentStreamEvent,
    status: AgentTraceSpanStatus,
) -> None:
    span = spans.get(span_id)
    if not span:
        return
    spans[span_id] = span.model_copy(
        update={
            "id": span_id,
            "status": status,
            "end_sequence": event.sequence,
            "ended_at": event.timestamp,
        }
    )


def _finish_open_span(
    spans: dict[str, AgentTraceSpan],
    span_id: str,
    event: AgentStreamEvent,
    status: AgentTraceSpanStatus,
) -> None:
    span = spans.get(span_id)
    if span and span.status == "running":
        _finish_span(spans, span_id, event, status)


def _payload_value(event: AgentStreamEvent, *keys: str) -> object | None:
    if not isinstance(event.payload, dict):
        return None
    for key in keys:
        if key in event.payload:
            return event.payload[key]
    return None


def _todo_status_from_event_type(event_type: str) -> str | None:
    match event_type:
        case "todo.completed":
            return "done"
        case "todo.blocked":
            return "blocked"
        case "todo.cancelled":
            return "cancelled"
        case _:
            return None


def _todo_span_status(status: object) -> AgentTraceSpanStatus:
    match status:
        case "done":
            return "completed"
        case "cancelled":
            return "cancelled"
        case "blocked":
            return "failed"
        case _:
            return "running"
