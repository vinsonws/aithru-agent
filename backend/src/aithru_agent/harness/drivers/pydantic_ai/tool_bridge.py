from typing import Any

from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter
from aithru_agent.domain import AgentRun, AgentToolCallRequest
from aithru_agent.stream import AgentEventWriter


class PydanticAIToolBridge:
    def __init__(
        self,
        *,
        run: AgentRun,
        run_context: AgentRunContext,
        event_writer: AgentEventWriter,
        capability_router: AithruCapabilityRouter,
    ) -> None:
        self._run = run
        self._run_context = run_context
        self._event_writer = event_writer
        self._capability_router = capability_router

    async def call_tool(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        tool_input: dict[str, Any] | None = None,
    ) -> object:
        request = AgentToolCallRequest(
            id=tool_call_id,
            tool_name=tool_name,
            input=tool_input or {},
            requested_by="model",
        )
        await self._event_writer.write(
            run_id=self._run.id,
            thread_id=self._run.thread_id,
            type="tool.proposed",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "input": tool_input or {}},
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
                type="approval.requested",
                source={"kind": "approval"},
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "output": prepared.output},
            )
            return {"status": "waiting_approval", "output": prepared.output}

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

