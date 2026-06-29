from pydantic import ValidationError

from aithru_agent.domain import (
    AgentTodoStatus,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
)
from aithru_agent.domain.research import (
    ResearchLimitation,
    ResearchPlanRequest,
    ResearchReportRequest,
    build_research_plan,
    build_research_report,
    research_limitation_for_blocked_todo_title,
    research_report_uri,
)
from aithru_agent.persistence.protocols import AgentStore

from ..descriptors import AgentRunContext


class ResearchLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="research.create_plan",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Create runtime Agent todos for a research task.",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "objective": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["section_id", "title", "question"],
                                "properties": {
                                    "section_id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "question": {"type": "string"},
                                    "priority": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"],
                                    },
                                },
                            },
                        },
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["phase", "title"],
                                "properties": {
                                    "phase": {
                                        "type": "string",
                                        "enum": ["search", "fetch", "synthesize", "report", "custom"],
                                    },
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.research.write", "agent.todo.write"],
                approval_policy="never",
            ),
            AgentToolDescriptor(
                name="research.create_report",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Create an evidence-backed markdown research report workspace file.",
                input_schema={
                    "type": "object",
                    "required": ["title", "query"],
                    "properties": {
                        "title": {"type": "string"},
                        "query": {"type": "string"},
                        "summary": {"type": "string"},
                        "name": {"type": "string"},
                        "uri": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["section_id", "title", "question"],
                                "properties": {
                                    "section_id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "question": {"type": "string"},
                                    "priority": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"],
                                    },
                                },
                            },
                        },
                        "limitations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["code", "severity", "message"],
                                "properties": {
                                    "code": {"type": "string"},
                                    "severity": {
                                        "type": "string",
                                        "enum": ["info", "warning", "error"],
                                    },
                                    "message": {"type": "string"},
                                    "source_url": {"type": "string"},
                                },
                            },
                        },
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["title", "url"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "url": {"type": "string"},
                                    "snippet": {"type": "string"},
                                    "content": {"type": "string"},
                                    "source": {"type": "string"},
                                    "published_at": {"type": "string"},
                                    "section_id": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.SAFE,
                required_scopes=["agent.research.write", "agent.workspace.write"],
                approval_policy="never",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name == "research.create_plan":
            return await self._create_plan(request, context)
        if request.tool_name == "research.create_report":
            return await self._create_report(request, context)
        return AgentToolCallResult(
            status="denied",
            error={"message": f"Unknown research tool: {request.tool_name}"},
            redaction="none",
        )

    async def _create_plan(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        try:
            plan_request = ResearchPlanRequest.model_validate(request.input)
        except ValidationError as exc:
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Invalid research plan input: {exc}"},
                redaction="none",
            )
        plan = build_research_plan(plan_request)
        todos = [
            await self._store.create_todo(
                run_id=context.run_id,
                title=step.title,
                description=step.description,
                status="pending",
                created_by="agent",
            )
            for step in plan.steps
        ]
        return AgentToolCallResult(
            status="completed",
            output={
                "plan": plan.model_dump(mode="json"),
                "todos": [todo.model_dump(mode="json") for todo in todos],
            },
            redaction="none",
        )

    async def _create_report(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        report_input = await self._report_input_with_runtime_limitations(
            request.input,
            run_id=context.run_id,
        )
        try:
            report_request = ResearchReportRequest.model_validate(report_input)
        except ValidationError as exc:
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Invalid research report input: {exc}"},
                redaction="none",
            )
        report = build_research_report(report_request)
        input_data = report_input if isinstance(report_input, dict) else {}
        path = str(input_data.get("uri") or research_report_uri(report.title))
        file = await self._store.write_workspace_file(
            workspace_id=context.workspace_id,
            path=path,
            content=report.markdown,
            media_type="text/markdown",
        )
        return AgentToolCallResult(
            status="completed",
            output={
                "report": report.model_dump(mode="json"),
                "workspace_file": file.model_dump(mode="json"),
                "path": file.path,
                "media_type": file.media_type,
                "size": file.size,
            },
            redaction="none",
        )

    async def _report_input_with_runtime_limitations(
        self,
        input_data: object,
        *,
        run_id: str,
    ) -> object:
        if not isinstance(input_data, dict):
            return input_data
        if input_data.get("limitations"):
            return input_data
        limitations = await self._limitations_from_blocked_research_todos(run_id)
        if not limitations:
            return input_data
        return {
            **input_data,
            "limitations": [limitation.model_dump(mode="json") for limitation in limitations],
        }

    async def _limitations_from_blocked_research_todos(
        self,
        run_id: str,
    ) -> list[ResearchLimitation]:
        limitations: list[ResearchLimitation] = []
        for todo in await self._store.list_todos(run_id):
            if todo.status != AgentTodoStatus.BLOCKED:
                continue
            limitation = research_limitation_for_blocked_todo_title(todo.title)
            if limitation is not None:
                limitations.append(limitation)
        return limitations
