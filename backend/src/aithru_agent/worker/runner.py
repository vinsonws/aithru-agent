from aithru_agent.capabilities import AgentRunContext, AithruCapabilityRouter
from aithru_agent.domain import AgentRun, AgentRunStatus, AgentToolCallRequest
from aithru_agent.domain.errors import AgentError
from aithru_agent.harness import AgentHarnessDriver, ContextBuilder
from aithru_agent.persistence.memory.store import InMemoryAgentStore
from aithru_agent.stream import AgentEventWriter


class AgentWorkerRunner:
    def __init__(
        self,
        *,
        store: InMemoryAgentStore,
        event_writer: AgentEventWriter,
        capability_router: AithruCapabilityRouter,
        driver: AgentHarnessDriver,
    ) -> None:
        self._store = store
        self._event_writer = event_writer
        self._capability_router = capability_router
        self._driver = driver
        self._context_builder = ContextBuilder()
        self._tool_counter = 0

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
        workspace = await self._store.create_workspace(org_id=org_id, thread_id=thread_id)
        run = await self._store.create_run(
            org_id=org_id,
            actor_user_id=actor_user_id,
            source="api",
            goal=goal,
            workspace_id=workspace.id,
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
        run = await self._store.update_run(run.id, status=AgentRunStatus.RUNNING)
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

        context = self._context_builder.build(run, scopes)
        final_content: list[str] = []
        for step in await self._driver.run():
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
                await self._execute_tool_step(run, context, step.tool_call.name, step.tool_call.input)
            elif step.type == "finish":
                break

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
        tool_name: str,
        tool_input: dict,
    ) -> None:
        self._tool_counter += 1
        tool_call_id = f"toolcall_{self._tool_counter}"
        request = AgentToolCallRequest(
            id=tool_call_id,
            tool_name=tool_name,
            input=tool_input,
            requested_by="model",
        )
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="tool.proposed",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
        )
        prepared = await self._capability_router.prepare_tool_call(request, context)
        if prepared.status == "denied":
            await self._event_writer.write(
                run_id=run.id,
                thread_id=run.thread_id,
                type="tool.denied",
                source={"kind": "tool"},
                payload={"tool_call_id": tool_call_id, "tool_name": tool_name, "reason": prepared.reason},
            )
            return
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
            type="tool.started",
            source={"kind": "tool"},
            payload={"tool_call_id": tool_call_id, "tool_name": tool_name},
        )
        result = await self._capability_router.execute_tool_call(request, context)
        await self._emit_domain_tool_event(run, tool_call_id, tool_name, result.output)
        await self._event_writer.write(
            run_id=run.id,
            thread_id=run.thread_id,
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

