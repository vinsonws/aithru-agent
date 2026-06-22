from typing import Any

from aithru_agent.domain import (
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDescriptor,
    AgentToolKind,
    AgentToolRiskLevel,
    WorkbenchWorkflowDraft,
)
from aithru_agent.persistence.protocols import AgentStore

from ..descriptors import AgentRunContext


WORKBENCH_WORKFLOW_DRAFT_MEDIA_TYPE = "application/vnd.aithru.workbench.workflow-draft+json"


class WorkbenchLocalTool:
    def __init__(self, store: AgentStore) -> None:
        self._store = store

    def list_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name="workbench.workflow_draft.create",
                kind=AgentToolKind.LOCAL_TOOL,
                description="Create a non-executable Workbench workflow draft artifact for human review.",
                input_schema={
                    "type": "object",
                    "required": ["title", "summary", "suggested_steps"],
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "suggested_steps": {"type": "array", "items": {"type": "string"}},
                        "required_inputs": {"type": "array", "items": {"type": "string"}},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "open_questions": {"type": "array", "items": {"type": "string"}},
                        "handoff_notes": {"type": "string"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=AgentToolRiskLevel.WRITE,
                required_scopes=["agent.artifact.write", "agent.workbench.write"],
                approval_policy="on_risk",
            )
        ]

    async def execute(
        self,
        request: AgentToolCallRequest,
        context: AgentRunContext,
    ) -> AgentToolCallResult:
        if request.tool_name != "workbench.workflow_draft.create":
            return AgentToolCallResult(
                status="denied",
                error={"message": f"Unknown Workbench tool: {request.tool_name}"},
                redaction="none",
            )

        input_data = _input_dict(request.input)
        draft = WorkbenchWorkflowDraft(
            title=input_data["title"],
            summary=input_data["summary"],
            source_run_id=context.run_id,
            source_workspace_id=context.workspace_id,
            source_thread_id=context.thread_id,
            suggested_steps=_optional_string_list(input_data.get("suggested_steps")) or [],
            required_inputs=_optional_string_list(input_data.get("required_inputs")) or [],
            risks=_optional_string_list(input_data.get("risks")) or [],
            open_questions=_optional_string_list(input_data.get("open_questions")) or [],
            handoff_notes=_optional_string(input_data.get("handoff_notes")),
        )
        artifact = await self._store.create_artifact(
            org_id=context.org_id,
            workspace_id=context.workspace_id,
            run_id=context.run_id,
            type="workflow_draft",
            name=f"Workbench workflow draft: {draft.title}",
            media_type=WORKBENCH_WORKFLOW_DRAFT_MEDIA_TYPE,
            content=draft.model_dump(mode="json"),
            metadata={
                "workbench": {
                    "draft": True,
                    "draft_kind": draft.draft_kind,
                    "executable": False,
                    "source": "workbench.workflow_draft.create",
                }
            },
        )
        return AgentToolCallResult(
            status="completed",
            output=artifact.model_dump(mode="json"),
            redaction="none",
        )


def _input_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Tool input must be an object")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Workbench draft string fields must be strings")
    return value


def _optional_string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("Workbench draft list fields must be string arrays")
    return value
