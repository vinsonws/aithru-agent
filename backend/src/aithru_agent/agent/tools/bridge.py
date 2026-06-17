"""Bridge Pydantic AI tool calls through the Aithru capability router."""

from typing import Any

from pydantic_ai import RunContext

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentToolCallRequest
from aithru_agent.domain.errors import AgentError


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
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "reason": prepared.reason},
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
                },
            )
            raise AgentError(
                "TOOL_APPROVAL_NOT_DEFERRED",
                "Tool required approval but was not deferred by Pydantic AI; check tool.requires_approval setup",
            )

        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
        )
        result = await self._capability_router.execute_tool_call(request, self._run_context)
        await self._emit_domain_event(tool_call_id, tool_name, result.output)
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.completed" if result.status == "completed" else "tool.failed",
            source={"kind": "tool"},
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": result.status,
                "output": result.output,
                "error": result.error,
            },
        )
        if result.status != "completed":
            raise AgentError("TOOL_FAILED", _tool_result_error_message(result.error))
        return result.output

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
        elif tool_name == "artifact.create":
            await self._event_writer.write(
                run_id=self._run.id,
                thread_id=self._run.thread_id,
                type="artifact.created",
                source={"kind": "artifact"},
                payload=output,
            )
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


def _tool_result_error_message(error: dict | None) -> str:
    if not error:
        return "Tool failed"
    message = error.get("message")
    return str(message) if message else "Tool failed"
