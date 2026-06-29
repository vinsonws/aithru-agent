import asyncio
import base64
import io
import json
import zipfile

import pytest
from pydantic_ai.models.test import TestModel
from httpx import ASGITransport, AsyncClient

from aithru_agent.agent import AgentRuntime, AgentRuntimeResult, PydanticAgentDeps
from aithru_agent.agent.tools import PydanticAIToolBridge
from aithru_agent.api.main import create_app
from aithru_agent.application.runtime import create_agent_runtime
from aithru_agent.capabilities import (
    ToolPolicy,
    WorkflowCapabilityInvocation,
    WorkflowCapabilityResult,
    WorkflowCapabilitySpec,
)
from aithru_agent.domain import (
    AgentArtifactRetentionPolicy,
    AgentExternalRunRef,
    AgentExternalApprovalRef,
    AgentExternalRunWaitRef,
    AgentModelCapabilities,
    AgentRunHarnessOptions,
    MAX_WORKSPACE_IMAGE_BYTES,
    AgentRunStatus,
    AgentSandboxPolicy,
    AgentSkill,
)
from aithru_agent.memory import LongTermMemoryAddResult, LongTermMemorySearchResult
from tests.utils.step_runtime import Step, StepAgentRuntime, ToolContext
from aithru_agent.settings import AgentLongTermMemorySettings, AgentSettings
from aithru_agent.skills import InMemorySkillResolver
from aithru_agent.stream import AgentEventWriter


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def file_report_driver() -> StepAgentRuntime:
    return StepAgentRuntime(
        [
            Step.message("I will write the report.\n"),
            Step.tool("todo.create", {"title": "Write report", "status": "running"}),
            Step.tool(
                "workspace.write_file",
                {"path": "/reports/report.md", "content": "# Report\nDone.\n", "media_type": "text/markdown"},
            ),
            Step.tool(
                "artifact.create",
                {
                    "type": "report",
                    "name": "Report",
                    "uri": "/reports/report.md",
                    "content": {"path": "/reports/report.md"},
                },
            ),
            Step.finish(),
        ]
    )


def recoverable_web_failure_research_driver() -> StepAgentRuntime:
    return StepAgentRuntime(
        [
            Step.message("I will research with controlled web tools.\n"),
            Step.tool(
                "research.create_plan",
                {"query": "aithru snapshot web failure"},
            ),
            Step.tool(
                "web.search",
                {"query": "aithru snapshot web failure", "max_results": 1},
            ),
            Step.tool(
                "research.create_report",
                {
                    "title": "Aithru Snapshot Recovery",
                    "query": "aithru snapshot web failure",
                },
            ),
            Step.finish(),
        ]
    )


def evidence_research_driver() -> StepAgentRuntime:
    return StepAgentRuntime(
        [
            Step.message("I will create an evidence-backed research report.\n"),
            Step.tool(
                "research.create_plan",
                {"query": "aithru evidence ledger"},
            ),
            Step.tool(
                "research.create_report",
                {
                    "title": "Aithru Evidence Ledger",
                    "query": "aithru evidence ledger",
                    "summary": "Collected evidence for the ledger API.",
                    "sources": [
                        {
                            "title": "Aithru Agent",
                            "url": "https://example.com/aithru",
                            "snippet": "Aithru Agent supports evidence-backed work.",
                            "content": "Fetched content for the evidence ledger API.",
                            "source": "example-search",
                            "published_at": "2026-06-19",
                        }
                    ],
                },
            ),
            Step.finish(),
        ]
    )


def section_quality_research_driver() -> StepAgentRuntime:
    return StepAgentRuntime(
        [
            Step.message("I will create a sectioned research report.\n"),
            Step.tool(
                "research.create_plan",
                {
                    "query": "aithru section quality",
                    "sections": [
                        {
                            "section_id": "architecture",
                            "title": "Architecture",
                            "question": "How is the backend structured?",
                            "priority": "high",
                        },
                        {
                            "section_id": "gaps",
                            "title": "Open gaps",
                            "question": "What remains incomplete?",
                            "priority": "medium",
                        },
                    ],
                },
            ),
            Step.tool(
                "research.create_report",
                {
                    "title": "Aithru Section Quality",
                    "query": "aithru section quality",
                    "summary": "Architecture is strong, but gaps need stronger evidence.",
                    "sections": [
                        {
                            "section_id": "architecture",
                            "title": "Architecture",
                            "question": "How is the backend structured?",
                            "priority": "high",
                        },
                        {
                            "section_id": "gaps",
                            "title": "Open gaps",
                            "question": "What remains incomplete?",
                            "priority": "medium",
                        },
                    ],
                    "sources": [
                        {
                            "title": "Aithru Architecture",
                            "url": "https://example.com/aithru-architecture",
                            "snippet": "Architecture evidence.",
                            "content": "Fetched architecture detail.",
                            "source": "example-search",
                            "published_at": "2026-06-19",
                            "section_id": "architecture",
                        },
                        {
                            "title": "Aithru Gaps",
                            "url": "https://example.com/aithru-gaps",
                            "snippet": "Gaps evidence.",
                            "source": "example-search",
                            "section_id": "gaps",
                        },
                    ],
                },
            ),
            Step.finish(),
        ]
    )


def approval_report_runtime() -> AgentRuntime:
    return AgentRuntime(
        model=TestModel(call_tools=["workspace.write_file"], custom_output_text="Report written.")
    )


class InputRequestRuntime(AgentRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg
        self.calls += 1
        if self.calls == 1:
            bridge = PydanticAIToolBridge(deps=deps)
            await bridge.call_tool(
                ToolContext("toolcall_input"),
                "input.request",
                {
                    "prompt": "Which region should I use?",
                    "reason": "The report needs a geographic scope.",
                },
            )
        return AgentRuntimeResult(content="Thanks, I can continue now.")


class ViewImageRuntime(AgentRuntime):
    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg
        await deps.store.write_workspace_file(
            workspace_id=deps.run.workspace_id,
            path="/uploads/chart.png",
            content=b"image-bytes",
            media_type="image/png",
        )
        bridge = PydanticAIToolBridge(deps=deps)
        output = await bridge.call_tool(
            ToolContext("toolcall_view_image"),
            "workspace.view_image",
            {"path": "/uploads/chart.png"},
        )
        assert isinstance(output, dict)
        assert "content_base64" in output
        return AgentRuntimeResult(content="Viewed image.")


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


class RunningWorkflowCapabilityProvider:
    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return [
            WorkflowCapabilitySpec(
                key="report_review",
                tool_name="workflow.report_review",
                description="Run report review in Workbench.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                risk_level="write",
                required_scopes=["workflow.capability.report_review.invoke"],
                approval_policy="never",
            )
        ]

    async def invoke(
        self,
        invocation: WorkflowCapabilityInvocation,
    ) -> WorkflowCapabilityResult:
        return WorkflowCapabilityResult(
            status="running",
            output={"message": "Workflow capability run started."},
            redaction="none",
            external_run=AgentExternalRunRef(
                kind="workflow_capability",
                capability_key=invocation.capability_key,
                capability_run_id="caprun_async_1",
                status="running",
                correlation_id=invocation.correlation_id,
            ),
        )


class ApiMem0Provider:
    async def search(self, *, run, query: str, limit: int):
        del run, query, limit
        return [
            LongTermMemorySearchResult(
                id="mem0_api_1",
                memory="Mem0 remembers concise Chinese summaries.",
                score=0.9,
                metadata={"org_id": "org_1", "actor_user_id": "user_1"},
                created_at="2026-06-25T00:00:00Z",
                updated_at="2026-06-25T00:00:00Z",
            )
        ]

    async def add_messages(self, *, run, messages):
        del run, messages
        return LongTermMemoryAddResult(status="PENDING", event_id="evt_api")

    async def delete_memory(self, *, memory_id: str, org_id: str, actor_user_id: str):
        del memory_id, org_id, actor_user_id
        raise AssertionError("API Mem0 tests must not delete memory")


class AsyncExternalRunRuntime(AgentRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.external_result_summaries: list[str] = []

    async def run(self, task_msg: str, deps: PydanticAgentDeps) -> AgentRuntimeResult:
        del task_msg
        self.calls += 1
        if self.calls == 1:
            bridge = PydanticAIToolBridge(deps=deps)
            await bridge.call_tool(
                ToolContext("toolcall_workflow"),
                "workflow.report_review",
                {"artifact_id": "artifact_1"},
            )

        external_result = next(
            (
                result
                for result in deps.context_packet.tool_results
                if result.source_type == "external_run"
            ),
            None,
        )
        if external_result is None:
            return AgentRuntimeResult(content="No external result context.")
        self.external_result_summaries.append(external_result.summary)
        return AgentRuntimeResult(content=f"External review result: {external_result.summary}")


@pytest.mark.asyncio
async def test_agent_api_threads_runs_events_stream_workspace_and_artifacts() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/api/health")
        thread_response = await client.post(
            "/api/threads",
            json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Work"},
        )
        thread = thread_response.json()
        message_response = await client.post(
            f"/api/threads/{thread['id']}/messages",
            json={"role": "user", "content": "Please write a report"},
        )
        run_response = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "thread_id": thread["id"],
                "task_msg": "Write the report draft",
                "scopes": ["*"],
            },
        )
        run = run_response.json()

        assert run["status"] == "queued"
        await runtime.worker.drain()

        run_detail = (await client.get(f"/api/runs/{run['id']}")).json()
        events = (await client.get(f"/api/runs/{run['id']}/events")).json()
        capability_audit = (await client.get(f"/api/runs/{run['id']}/capability-audit")).json()
        thread_capability_audit = (
            await client.get(f"/api/threads/{thread['id']}/runs/{run['id']}/capability-audit")
        ).json()
        trace = (await client.get(f"/api/runs/{run['id']}/trace")).json()
        stream = await client.get(f"/api/runs/{run['id']}/stream")
        files = (await client.get(f"/api/workspaces/{run['workspace_id']}/files")).json()
        file_content = (
            await client.get(f"/api/workspaces/{run['workspace_id']}/files/reports/report.md")
        ).json()
        await client.put(
            f"/api/workspaces/{run['workspace_id']}/files/reports/second.md",
            json={"content": "first\n", "media_type": "text/markdown"},
        )
        await client.put(
            f"/api/workspaces/{run['workspace_id']}/files/reports/second.md",
            json={"content": "second\n", "media_type": "text/markdown"},
        )
        versions = (
            await client.get(f"/api/workspaces/{run['workspace_id']}/files/reports/second.md/versions")
        ).json()
        workspace_snapshot = (
            await client.get(f"/api/workspaces/{run['workspace_id']}/snapshot")
        ).json()
        workspace_diff = (
            await client.get(
                f"/api/workspaces/{run['workspace_id']}/diff",
                params={"base_version": versions[0]["version"], "target_version": versions[1]["version"]},
            )
        ).json()
        restore = (
            await client.post(
                f"/api/workspaces/{run['workspace_id']}/restore",
                json={"version": versions[0]["version"]},
            )
        ).json()
        restored_file_content = (
            await client.get(f"/api/workspaces/{run['workspace_id']}/files/reports/second.md")
        ).json()
        promoted_response = await client.post(
            f"/api/workspaces/{run['workspace_id']}/files/reports/second.md/promote",
            json={
                "name": "Second report",
                "type": "report",
                "run_id": run["id"],
                "retention": {
                    "mode": "expires_at",
                    "expires_at": "2026-07-01T00:00:00Z",
                },
                "metadata": {"kind": "promoted"},
            },
        )
        promoted = promoted_response.json()
        artifacts = (await client.get("/api/artifacts", params={"run_id": run["id"]})).json()
        artifact_content = await client.get(f"/api/artifacts/{artifacts[0]['id']}/content")
        promoted_content = await client.get(f"/api/artifacts/{promoted['artifact']['id']}/content")
        export_bundle = (await client.get(f"/api/runs/{run['id']}/export")).json()
        export_artifact_response = await client.post(
            f"/api/runs/{run['id']}/export/artifact",
            json={
                "retention": {"mode": "retained"},
                "metadata": {"kind": "audit"},
            },
        )
        export_artifact = export_artifact_response.json()
        export_artifact_content = await client.get(
            f"/api/artifacts/{export_artifact['artifact']['id']}/content"
        )
        export_artifact_download_info = (
            await client.get(f"/api/artifacts/{export_artifact['artifact']['id']}/download-info")
        ).json()
        export_artifact_download = await client.get(
            f"/api/artifacts/{export_artifact['artifact']['id']}/download"
        )

    assert health.json() == {"ok": True, "service": "aithru-agent-backend"}
    assert thread_response.status_code == 201
    assert message_response.status_code == 201
    assert run_response.status_code == 201
    assert run_detail["status"] == "completed"
    assert run_detail["result"]["content"] == "I will write the report.\n"
    assert run_detail["summary"]["health"] == "completed"
    assert run_detail["summary"]["needs_attention"] is False
    assert run_detail["summary"]["research_status"] == "none"
    assert run_detail["summary"]["research_degraded"] is False
    assert [event["type"] for event in events][-1] == "run.completed"
    assert events[-1]["payload"]["result"]["artifact_ids"] == [artifacts[0]["id"]]
    assert capability_audit == thread_capability_audit
    assert capability_audit["run_id"] == run["id"]
    assert capability_audit["count"] == 3
    assert [entry["source_event_type"] for entry in capability_audit["entries"]] == [
        "tool.completed",
        "tool.completed",
        "tool.completed",
    ]
    assert [entry["audit"]["tool_name"] for entry in capability_audit["entries"]] == [
        "todo.create",
        "workspace.write_file",
        "artifact.create",
    ]
    assert capability_audit["entries"][1]["audit"]["authorization_decision"]["status"] == "allowed"
    assert "authorization" not in capability_audit["entries"][1]["audit"]
    assert {span["kind"] for span in trace} >= {"run", "model", "tool", "workspace", "artifact"}
    assert next(span for span in trace if span["kind"] == "run")["status"] == "completed"
    assert "event: run.completed" in stream.text
    assert files[0]["path"] == "/reports/report.md"
    assert file_content["content"] == "# Report\nDone.\n"
    assert [version["file_version"] for version in versions] == [1, 2]
    assert workspace_snapshot["file_count"] == 2
    assert "/reports/second.md" in [file["path"] for file in workspace_snapshot["files"]]
    assert [(change["path"], change["operation"]) for change in workspace_diff["changes"]] == [
        ("/reports/second.md", "modified")
    ]
    assert restore["restored_count"] == 1
    assert next(
        change for change in restore["changes"] if change["path"] == "/reports/second.md"
    )["operation"] == "restored"
    assert restored_file_content["content"] == "first\n"
    assert promoted_response.status_code == 201
    assert promoted["artifact"]["type"] == "report"
    assert promoted["artifact"]["name"] == "Second report"
    assert promoted["artifact"]["retention"]["mode"] == "expires_at"
    assert promoted["artifact"]["metadata"]["kind"] == "promoted"
    assert promoted["artifact"]["metadata"]["source"] == "workspace_file"
    assert promoted["path"] == "/reports/second.md"
    assert artifacts[0]["type"] == "report"
    assert artifact_content.status_code == 200
    assert artifact_content.text == "# Report\nDone.\n"
    assert artifact_content.headers["content-type"].startswith("text/markdown")
    assert promoted_content.status_code == 200
    assert promoted_content.text == "first\n"
    assert export_bundle["schema_version"] == "run_export.v1"
    assert export_bundle["run"]["id"] == run["id"]
    assert export_bundle["summary"]["run_id"] == run["id"]
    assert export_bundle["summary"]["status"] == "completed"
    assert export_bundle["summary"]["event_count"] == len(export_bundle["events"])
    assert export_bundle["summary"]["trace_span_count"] == len(export_bundle["trace"])
    assert export_bundle["summary"]["artifact_count"] == len(export_bundle["artifacts"])
    assert export_bundle["summary"]["workspace_file_count"] == export_bundle["workspace_snapshot"]["file_count"]
    assert {artifact["id"] for artifact in export_bundle["artifacts"]} == {artifact["id"] for artifact in artifacts}
    assert "/reports/second.md" in [
        file["path"] for file in export_bundle["workspace_snapshot"]["files"]
    ]
    assert export_artifact_response.status_code == 201
    assert export_artifact["schema_version"] == "run_export.v1"
    assert export_artifact["path"] == f"/exports/runs/{run['id']}.export.json"
    assert export_artifact["artifact"]["type"] == "json"
    assert export_artifact["artifact"]["media_type"] == "application/json"
    assert export_artifact["artifact"]["uri"] == export_artifact["path"]
    assert export_artifact["artifact"]["content"] == {"path": export_artifact["path"]}
    assert export_artifact["artifact"]["metadata"]["source"] == "run_export"
    assert export_artifact["artifact"]["metadata"]["kind"] == "audit"
    assert export_artifact["artifact"]["retention"]["mode"] == "retained"
    assert export_artifact["workspace_file"]["path"] == export_artifact["path"]
    assert export_artifact["workspace_file"]["media_type"] == "application/json"
    assert export_artifact["export_summary"]["run_id"] == run["id"]
    assert export_artifact_content.status_code == 200
    assert export_artifact_content.headers["content-type"].startswith("application/json")
    archived_bundle = json.loads(export_artifact_content.text)
    assert archived_bundle["schema_version"] == "run_export.v1"
    assert archived_bundle["run"]["id"] == run["id"]
    assert archived_bundle["summary"]["artifact_count"] == len(artifacts)
    assert export_artifact_download_info == {
        "artifact_id": export_artifact["artifact"]["id"],
        "filename": f"Run_{run['id']}_export.json",
        "media_type": "application/json",
        "content_length": len(export_artifact_content.text.encode("utf-8")),
        "disposition": "attachment",
        "source_path": export_artifact["path"],
    }
    assert export_artifact_download.status_code == 200
    assert export_artifact_download.headers["content-type"].startswith("application/json")
    assert export_artifact_download.headers["content-disposition"] == (
        f'attachment; filename="Run_{run["id"]}_export.json"'
    )
    assert json.loads(export_artifact_download.text)["run"]["id"] == run["id"]


@pytest.mark.asyncio
async def test_agent_api_views_workspace_images_and_persists_message_attachments() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    image_bytes = b"\x89PNG\r\nimage"
    image_base64 = base64.b64encode(image_bytes).decode("ascii")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Vision"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Inspect the attached image",
                    "scopes": ["agent.workspace.read"],
                },
            )
        ).json()
        upload = (
            await client.post(
                f"/api/workspaces/{run['workspace_id']}/uploads",
                json={
                    "path": "/uploads/chart.png",
                    "content_base64": image_base64,
                    "media_type": "image/png",
                },
            )
        ).json()
        view_response = await client.get(
            f"/api/workspaces/{run['workspace_id']}/images/uploads/chart.png/view"
        )
        attachment = {
            "kind": "workspace_image",
            "workspace_id": run["workspace_id"],
            "path": "/uploads/chart.png",
            "media_type": "image/png",
            "size": len(image_bytes),
            "content_hash": upload["file"]["content_hash"],
        }
        message_response = await client.post(
            f"/api/threads/{thread['id']}/messages",
            json={
                "role": "user",
                "content": "What does this chart show?",
                "attachments": [attachment],
            },
        )
        messages = (
            await client.get(f"/api/threads/{thread['id']}/messages")
        ).json()

    assert view_response.status_code == 200
    assert view_response.json() == {
        "workspace_id": run["workspace_id"],
        "path": "/uploads/chart.png",
        "media_type": "image/png",
        "size": len(image_bytes),
        "content_hash": upload["file"]["content_hash"],
        "content_encoding": "base64",
        "content_base64": image_base64,
    }
    assert message_response.status_code == 201
    assert message_response.json()["attachments"] == [attachment]
    assert messages[-1]["attachments"] == [attachment]
    assert "content_base64" not in message_response.json()["attachments"][0]


@pytest.mark.asyncio
async def test_agent_api_rejects_invalid_image_views_and_message_attachments() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    user_a_headers = {
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    user_b_headers = {
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }
    text_base64 = base64.b64encode(b"plain text").decode("ascii")
    oversized_base64 = base64.b64encode(b"x" * (MAX_WORKSPACE_IMAGE_BYTES + 1)).decode("ascii")
    image_base64 = base64.b64encode(b"image").decode("ascii")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_thread = (
            await client.post(
                "/api/threads",
                headers=user_a_headers,
                json={"title": "User A"},
            )
        ).json()
        user_a_run = (
            await client.post(
                f"/api/threads/{user_a_thread['id']}/runs",
                headers=user_a_headers,
                json={"task_msg": "Inspect image", "scopes": ["agent.workspace.read"]},
            )
        ).json()
        await client.post(
            f"/api/workspaces/{user_a_run['workspace_id']}/uploads",
            headers=user_a_headers,
            json={
                "path": "/uploads/notes.txt",
                "content_base64": text_base64,
                "media_type": "text/plain",
            },
        )
        await client.post(
            f"/api/workspaces/{user_a_run['workspace_id']}/uploads",
            headers=user_a_headers,
            json={
                "path": "/uploads/large.png",
                "content_base64": oversized_base64,
                "media_type": "image/png",
            },
        )
        user_b_thread = (
            await client.post(
                "/api/threads",
                headers=user_b_headers,
                json={"title": "User B"},
            )
        ).json()
        user_b_run = (
            await client.post(
                f"/api/threads/{user_b_thread['id']}/runs",
                headers=user_b_headers,
                json={"task_msg": "Inspect image", "scopes": ["agent.workspace.read"]},
            )
        ).json()
        await client.post(
            f"/api/workspaces/{user_b_run['workspace_id']}/uploads",
            headers=user_b_headers,
            json={
                "path": "/uploads/hidden.png",
                "content_base64": image_base64,
                "media_type": "image/png",
            },
        )

        missing_view = await client.get(
            f"/api/workspaces/{user_a_run['workspace_id']}/images/uploads/missing.png/view",
            headers=user_a_headers,
        )
        non_image_view = await client.get(
            f"/api/workspaces/{user_a_run['workspace_id']}/images/uploads/notes.txt/view",
            headers=user_a_headers,
        )
        oversized_view = await client.get(
            f"/api/workspaces/{user_a_run['workspace_id']}/images/uploads/large.png/view",
            headers=user_a_headers,
        )
        hidden_view = await client.get(
            f"/api/workspaces/{user_b_run['workspace_id']}/images/uploads/hidden.png/view",
            headers=user_a_headers,
        )
        non_image_attachment = await client.post(
            f"/api/threads/{user_a_thread['id']}/messages",
            headers=user_a_headers,
            json={
                "role": "user",
                "content": "Attach text as image",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": user_a_run["workspace_id"],
                        "path": "/uploads/notes.txt",
                        "media_type": "image/png",
                        "size": len(b"plain text"),
                    }
                ],
            },
        )
        oversized_attachment = await client.post(
            f"/api/threads/{user_a_thread['id']}/messages",
            headers=user_a_headers,
            json={
                "role": "user",
                "content": "Attach large image",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": user_a_run["workspace_id"],
                        "path": "/uploads/large.png",
                        "media_type": "image/png",
                        "size": 1,
                    }
                ],
            },
        )
        missing_attachment = await client.post(
            f"/api/threads/{user_a_thread['id']}/messages",
            headers=user_a_headers,
            json={
                "role": "user",
                "content": "Attach missing image",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": user_a_run["workspace_id"],
                        "path": "/uploads/missing.png",
                        "media_type": "image/png",
                        "size": 1,
                    }
                ],
            },
        )
        hidden_attachment = await client.post(
            f"/api/threads/{user_a_thread['id']}/messages",
            headers=user_a_headers,
            json={
                "role": "user",
                "content": "Attach hidden image",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": user_b_run["workspace_id"],
                        "path": "/uploads/hidden.png",
                        "media_type": "image/png",
                        "size": len(b"image"),
                    }
                ],
            },
        )

    assert missing_view.status_code == 404
    assert non_image_view.status_code == 415
    assert oversized_view.status_code == 413
    assert hidden_view.status_code == 404
    assert non_image_attachment.status_code == 415
    assert oversized_attachment.status_code == 413
    assert missing_attachment.status_code == 404
    assert hidden_attachment.status_code == 404


@pytest.mark.asyncio
async def test_agent_api_rejects_cross_thread_workspace_image_attachments() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    headers = {
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    image_bytes = b"image"
    image_base64 = base64.b64encode(image_bytes).decode("ascii")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        target_thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Target thread"},
            )
        ).json()
        other_thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Other thread"},
            )
        ).json()
        other_run = (
            await client.post(
                f"/api/threads/{other_thread['id']}/runs",
                headers=headers,
                json={"task_msg": "Inspect image", "scopes": ["agent.workspace.read"]},
            )
        ).json()
        other_upload = (
            await client.post(
                f"/api/workspaces/{other_run['workspace_id']}/uploads",
                headers=headers,
                json={
                    "path": "/uploads/other-thread.png",
                    "content_base64": image_base64,
                    "media_type": "image/png",
                },
            )
        ).json()
        run_workspace = await runtime.store.create_workspace(
            org_id="org_1",
            run_id=other_run["id"],
        )
        run_scoped_file = await runtime.store.write_workspace_file(
            workspace_id=run_workspace.id,
            path="/uploads/run-scoped.png",
            content=image_bytes,
            media_type="image/png",
        )

        thread_scoped_attachment = await client.post(
            f"/api/threads/{target_thread['id']}/messages",
            headers=headers,
            json={
                "role": "user",
                "content": "Attach from another thread workspace",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": other_run["workspace_id"],
                        "path": "/uploads/other-thread.png",
                        "media_type": "image/png",
                        "size": len(image_bytes),
                        "content_hash": other_upload["file"]["content_hash"],
                    }
                ],
            },
        )
        run_scoped_attachment = await client.post(
            f"/api/threads/{target_thread['id']}/messages",
            headers=headers,
            json={
                "role": "user",
                "content": "Attach from another thread run workspace",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": run_workspace.id,
                        "path": "/uploads/run-scoped.png",
                        "media_type": "image/png",
                        "size": len(image_bytes),
                        "content_hash": run_scoped_file.content_hash,
                    }
                ],
            },
        )

    assert thread_scoped_attachment.status_code == 404
    assert thread_scoped_attachment.json()["detail"] == "Workspace not found"
    assert run_scoped_attachment.status_code == 404
    assert run_scoped_attachment.json()["detail"] == "Workspace not found"


@pytest.mark.asyncio
async def test_agent_api_rejects_zero_byte_workspace_images_by_size() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    headers = {
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Blank image"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=headers,
                json={"task_msg": "Inspect image", "scopes": ["agent.workspace.read"]},
            )
        ).json()
        blank = await runtime.store.write_workspace_file(
            workspace_id=run["workspace_id"],
            path="/uploads/blank.png",
            content=b"",
            media_type="image/png",
        )

        view_response = await client.get(
            f"/api/workspaces/{run['workspace_id']}/images/uploads/blank.png/view",
            headers=headers,
        )
        attachment_response = await client.post(
            f"/api/threads/{thread['id']}/messages",
            headers=headers,
            json={
                "role": "user",
                "content": "Attach blank image",
                "attachments": [
                    {
                        "kind": "workspace_image",
                        "workspace_id": run["workspace_id"],
                        "path": "/uploads/blank.png",
                        "media_type": "image/png",
                        "size": 0,
                        "content_hash": blank.content_hash,
                    }
                ],
            },
        )

    assert view_response.status_code == 409
    assert "greater than 0" in view_response.json()["detail"]
    assert attachment_response.status_code == 422
    assert "greater than 0" in attachment_response.text


@pytest.mark.asyncio
async def test_agent_api_views_workspace_images_with_normalized_image_path() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    headers = {
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    image_bytes = b"\x89PNG\r\nimage"
    image_base64 = base64.b64encode(image_bytes).decode("ascii")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Normalized image path"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=headers,
                json={"task_msg": "Inspect image", "scopes": ["agent.workspace.read"]},
            )
        ).json()
        written = await runtime.store.write_workspace_file(
            workspace_id=run["workspace_id"],
            path="/chart.png",
            content=image_bytes,
            media_type="image/png",
        )

        view_response = await client.get(
            f"/api/workspaces/{run['workspace_id']}/images/uploads%5C..%5Cchart.png/view",
            headers=headers,
        )

    assert view_response.status_code == 200
    assert view_response.json() == {
        "workspace_id": run["workspace_id"],
        "path": "/chart.png",
        "media_type": "image/png",
        "size": len(image_bytes),
        "content_hash": written.content_hash,
        "content_encoding": "base64",
        "content_base64": image_base64,
    }


def test_agent_api_openapi_includes_workspace_image_view_contract() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    schema = app.openapi()
    image_view = schema["paths"]["/api/workspaces/{workspace_id}/images/{path}/view"]["get"]

    assert image_view["operationId"].startswith("view_workspace_image")
    assert (
        image_view["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentWorkspaceImageViewResult"
    )


@pytest.mark.asyncio
async def test_workspace_view_image_tool_events_do_not_store_base64_content() -> None:
    runtime = create_agent_runtime(agent_runtime=ViewImageRuntime())

    run = await runtime.runner.start_run(
        org_id="org_1",
        actor_user_id="user_1",
        task_msg="View image",
        scopes=["agent.workspace.read", "agent.workspace.write"],
        harness_options=AgentRunHarnessOptions(
            model_capabilities=AgentModelCapabilities(vision=True)
        ),
    )
    events = await runtime.event_store.list_by_run(run.id)
    completed = next(
        event
        for event in events
        if event.type == "tool.completed" and event.payload["tool_name"] == "workspace.view_image"
    )

    assert completed.payload["output"]["path"] == "/uploads/chart.png"
    assert completed.payload["output"]["media_type"] == "image/png"
    assert "content_base64" not in completed.payload["output"]


@pytest.mark.asyncio
async def test_agent_api_follow_stream_waits_for_new_run_events() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Write report", "scopes": ["*"]},
            )
        ).json()
        stream_task = asyncio.create_task(
            client.get(
                f"/api/runs/{run['id']}/stream",
                params={
                    "after_sequence": 1,
                    "follow": True,
                    "poll_interval_seconds": 0.01,
                    "timeout_seconds": 2,
                },
            )
        )
        await asyncio.sleep(0.05)
        assert not stream_task.done()
        await runtime.worker.drain()
        stream = await stream_task

    assert stream.status_code == 200
    assert "event: run.started" in stream.text
    assert "event: run.completed" in stream.text


@pytest.mark.asyncio
async def test_agent_api_requires_bearer_token_when_configured() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/api/health")
        missing = await client.post(
            "/api/threads",
            json={"org_id": "org_1", "owner_user_id": "user_1"},
        )
        wrong = await client.post(
            "/api/threads",
            headers={"Authorization": "Bearer wrong"},
            json={"org_id": "org_1", "owner_user_id": "user_1"},
        )
        authorized = await client.post(
            "/api/threads",
            headers={"Authorization": "Bearer secret-token"},
            json={"org_id": "org_1", "owner_user_id": "user_1"},
        )

    assert health.status_code == 200
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"] == "Unauthorized"
    assert wrong.json()["detail"] == "Unauthorized"
    assert authorized.status_code == 201


@pytest.mark.asyncio
async def test_agent_api_binds_run_scopes_to_configured_token_scopes() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(
            api_token="secret-token",
            api_scopes=["agent.workspace.read"],
        ),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inherited = await client.post(
            "/api/runs",
            headers={"Authorization": "Bearer secret-token"},
            json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Read only"},
        )
        escalated = await client.post(
            "/api/runs",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Escalate",
                "scopes": ["*"],
            },
        )
        runs = (await client.get(
            "/api/runs",
            headers={"Authorization": "Bearer secret-token"},
        )).json()

    assert inherited.status_code == 201
    assert inherited.json()["scopes"] == ["agent.workspace.read"]
    assert escalated.status_code == 403
    assert escalated.json()["detail"] == "Requested scopes exceed API token scopes"
    assert [run["task_msg"] for run in runs] == ["Read only"]


@pytest.mark.asyncio
async def test_agent_api_binds_run_identity_to_trusted_headers() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_from_header",
        "X-Aithru-User-Id": "user_from_header",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inherited = await client.post(
            "/api/runs",
            headers=headers,
            json={"task_msg": "Use trusted identity"},
        )
        conflicting = await client.post(
            "/api/runs",
            headers=headers,
            json={
                "org_id": "org_from_body",
                "actor_user_id": "user_from_header",
                "task_msg": "Conflict",
            },
        )
        runs = (await client.get("/api/runs", headers=headers)).json()

    assert inherited.status_code == 201
    assert inherited.json()["org_id"] == "org_from_header"
    assert inherited.json()["actor_user_id"] == "user_from_header"
    assert conflicting.status_code == 403
    assert conflicting.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [run["task_msg"] for run in runs] == ["Use trusted identity"]


@pytest.mark.asyncio
async def test_agent_api_persists_run_harness_options() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Use run config",
                    "harness_options": {
                        "model": "test",
                        "instructions": "Answer with terse bullets.",
                    },
                },
            )
        ).json()
        fetched = (await client.get(f"/api/runs/{created['id']}")).json()

    assert created["harness_options"] == {
        "model": "test",
        "instructions": "Answer with terse bullets.",
    }
    assert fetched["harness_options"] == created["harness_options"]


@pytest.mark.asyncio
async def test_agent_api_binds_thread_identity_to_trusted_headers() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_from_header",
        "X-Aithru-User-Id": "user_from_header",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        inherited = await client.post(
            "/api/threads",
            headers=headers,
            json={"title": "Trusted"},
        )
        conflicting = await client.post(
            "/api/threads",
            headers=headers,
            json={"org_id": "org_from_header", "owner_user_id": "user_from_body"},
        )
        threads = (await client.get("/api/threads", headers=headers)).json()

    assert inherited.status_code == 201
    assert inherited.json()["org_id"] == "org_from_header"
    assert inherited.json()["owner_user_id"] == "user_from_header"
    assert conflicting.status_code == 403
    assert conflicting.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [thread["title"] for thread in threads] == ["Trusted"]


@pytest.mark.asyncio
async def test_agent_api_filters_threads_by_trusted_identity_headers() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_thread = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "User A"})
        ).json()
        user_b_thread = (
            await client.post("/api/threads", headers=user_b_headers, json={"title": "User B"})
        ).json()
        user_a_threads = (await client.get("/api/threads", headers=user_a_headers)).json()
        hidden_thread = await client.get(f"/api/threads/{user_b_thread['id']}", headers=user_a_headers)
        hidden_messages = await client.get(
            f"/api/threads/{user_b_thread['id']}/messages",
            headers=user_a_headers,
        )
        hidden_append = await client.post(
            f"/api/threads/{user_b_thread['id']}/messages",
            headers=user_a_headers,
            json={"role": "user", "content": "should not write"},
        )
        visible_thread = await client.get(f"/api/threads/{user_a_thread['id']}", headers=user_a_headers)

    assert [thread["id"] for thread in user_a_threads] == [user_a_thread["id"]]
    assert hidden_thread.status_code == 404
    assert hidden_thread.json()["detail"] == "Thread not found"
    assert hidden_messages.status_code == 404
    assert hidden_messages.json()["detail"] == "Thread not found"
    assert hidden_append.status_code == 404
    assert hidden_append.json()["detail"] == "Thread not found"
    assert visible_thread.status_code == 200
    assert visible_thread.json()["id"] == user_a_thread["id"]


@pytest.mark.asyncio
async def test_agent_api_updates_thread_lifecycle_with_pydantic_request() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "Draft"})
        ).json()
        renamed = await client.patch(
            f"/api/threads/{thread['id']}",
            headers=user_a_headers,
            json={"title": "Research archive"},
        )
        cleared = await client.patch(
            f"/api/threads/{thread['id']}",
            headers=user_a_headers,
            json={"title": None},
        )
        archived = await client.patch(
            f"/api/threads/{thread['id']}",
            headers=user_a_headers,
            json={"status": "archived"},
        )
        empty_patch = await client.patch(
            f"/api/threads/{thread['id']}",
            headers=user_a_headers,
            json={},
        )
        hidden_patch = await client.patch(
            f"/api/threads/{thread['id']}",
            headers=user_b_headers,
            json={"title": "Should not update"},
        )
        fetched = await client.get(f"/api/threads/{thread['id']}", headers=user_a_headers)

    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Research archive"
    assert renamed.json()["updated_at"] >= renamed.json()["created_at"]
    assert cleared.status_code == 200
    assert cleared.json()["title"] is None
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["title"] is None
    assert empty_patch.status_code == 422
    assert hidden_patch.status_code == 404
    assert hidden_patch.json()["detail"] == "Thread not found"
    assert fetched.json()["status"] == "archived"
    assert fetched.json()["title"] is None


@pytest.mark.asyncio
async def test_agent_api_filters_paginates_and_orders_threads() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alpha = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "Alpha"})
        ).json()
        beta = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "Beta"})
        ).json()
        archived = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "Archive"})
        ).json()
        await client.patch(
            f"/api/threads/{archived['id']}",
            headers=user_a_headers,
            json={"status": "archived"},
        )
        await client.post("/api/threads", headers=user_b_headers, json={"title": "Hidden"})

        active = (
            await client.get("/api/threads", headers=user_a_headers, params={"status": "active"})
        ).json()
        archived_threads = (
            await client.get("/api/threads", headers=user_a_headers, params={"status": "archived"})
        ).json()
        page_response = await client.get(
            "/api/threads",
            headers=user_a_headers,
            params={
                "status": "active",
                "include_meta": True,
                "order_by": "title",
                "order_direction": "desc",
                "limit": 1,
                "offset": 1,
            },
        )
        invalid_status = await client.get(
            "/api/threads",
            headers=user_a_headers,
            params={"status": "deleted"},
        )

    assert [thread["id"] for thread in active] == [alpha["id"], beta["id"]]
    assert [thread["id"] for thread in archived_threads] == [archived["id"]]
    assert invalid_status.status_code == 422
    assert page_response.status_code == 200
    page = page_response.json()
    assert [thread["id"] for thread in page["items"]] == [alpha["id"]]
    assert page["total"] == 2
    assert page["count"] == 1
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert page["order_by"] == "title"
    assert page["order_direction"] == "desc"
    assert page["status_counts"] == {"active": 2, "archived": 1}


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_summary_for_sidebar() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "Research"})
        ).json()
        await client.post(
            f"/api/threads/{thread['id']}/messages",
            headers=user_a_headers,
            json={"role": "user", "content": "Please research Aithru Agent."},
        )
        latest_content = "Latest update: " + ("context " * 40)
        latest_message = (
            await client.post(
                f"/api/threads/{thread['id']}/messages",
                headers=user_a_headers,
                json={"role": "assistant", "content": latest_content},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=user_a_headers,
                json={"task_msg": "Research Aithru", "scopes": ["*"]},
            )
        ).json()
        running = await runtime.store.claim_run(run["id"])
        assert running is not None
        paused = await runtime.store.update_run(running.id, status=AgentRunStatus.WAITING_INPUT)
        summary_response = await client.get(
            f"/api/threads/{thread['id']}/summary",
            headers=user_a_headers,
        )
        hidden_response = await client.get(
            f"/api/threads/{thread['id']}/summary",
            headers=user_b_headers,
        )

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["thread_id"] == thread["id"]
    assert summary["message_count"] == 2
    assert summary["run_count"] == 1
    assert summary["active_run_count"] == 1
    assert summary["waiting_input_run_count"] == 1
    assert summary["latest_message"]["message_id"] == latest_message["id"]
    assert summary["latest_message"]["role"] == "assistant"
    assert summary["latest_message"]["content_preview"].startswith("Latest update:")
    assert summary["latest_message"]["truncated"] is True
    assert len(summary["latest_message"]["content_preview"]) == 160
    assert summary["latest_run"] == {
        "run_id": paused.id,
        "status": "waiting_input",
        "task_msg": "Research Aithru",
        "started_at": paused.started_at,
        "completed_at": None,
    }
    assert summary["last_activity_at"] >= latest_message["created_at"]
    assert hidden_response.status_code == 404
    assert hidden_response.json()["detail"] == "Thread not found"


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_workbench_for_deerflow_like_frontend() -> None:
    runtime = create_agent_runtime(
        agent_runtime=evidence_research_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post("/api/threads", headers=user_a_headers, json={"title": "Evidence"})
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=user_a_headers,
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Open a DeerFlow-like thread workbench",
                    "scopes": ["*"],
                    "skill_id": "skill_deep_research",
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(
            f"/api/threads/{thread['id']}/workbench",
            headers=user_a_headers,
        )
        selected_response = await client.get(
            f"/api/threads/{thread['id']}/workbench",
            headers=user_a_headers,
            params={"selected_run_id": run["id"], "run_limit": 1},
        )
        hidden_response = await client.get(
            f"/api/threads/{thread['id']}/workbench",
            headers=user_b_headers,
        )

    assert response.status_code == 200
    workbench = response.json()
    assert workbench["thread"]["id"] == thread["id"]
    assert workbench["summary"]["thread_id"] == thread["id"]
    assert workbench["summary"]["run_count"] == 1
    assert workbench["summary"]["latest_run"]["run_id"] == run["id"]
    assert workbench["selected_run_id"] == run["id"]
    assert [item["run"]["id"] for item in workbench["runs"]] == [run["id"]]
    assert workbench["runs"][0]["summary"]["research_status"] == "complete"
    assert workbench["runs"][0]["summary"]["research_degraded"] is False
    selected_run = workbench["selected_run"]
    assert selected_run["run"]["id"] == run["id"]
    assert selected_run["summary"] == workbench["runs"][0]["summary"]
    assert selected_run["research_evidence"]["status"] == "complete"
    assert selected_run["research_evidence"]["counts"]["evidence_count"] == 1
    assert selected_run["research_review"]["status"] == "pass"
    assert selected_run["research_continuation"]["status"] == "ready"
    assert selected_run["events"]
    assert selected_run["artifacts"]
    assert selected_response.status_code == 200
    assert selected_response.json()["selected_run_id"] == run["id"]
    assert hidden_response.status_code == 404
    assert hidden_response.json()["detail"] == "Thread not found"


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_dashboard_for_queue_views() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(
            model="test",
            api_token="secret-token",
            external_tools={"web_enabled": True},
        ),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        degraded_thread = (
            await client.post(
                "/api/threads",
                headers=user_a_headers,
                json={"title": "Recovery"},
            )
        ).json()
        empty_thread = (
            await client.post(
                "/api/threads",
                headers=user_a_headers,
                json={"title": "Empty"},
            )
        ).json()
        hidden_thread = (
            await client.post(
                "/api/threads",
                headers=user_b_headers,
                json={"title": "Hidden"},
            )
        ).json()
        degraded_run = (
            await client.post(
                f"/api/threads/{degraded_thread['id']}/runs",
                headers=user_a_headers,
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Recover degraded research report",
                    "scopes": ["*"],
                    "skill_id": "skill_deep_research",
                },
            )
        ).json()
        await runtime.worker.drain()
        dashboard_response = await client.get(
            "/api/threads/dashboard",
            headers=user_a_headers,
            params={"order_by": "needs_attention", "order_direction": "desc"},
        )
        attention_response = await client.get(
            "/api/threads/dashboard",
            headers=user_a_headers,
            params={"needs_attention": True},
        )
        degraded_response = await client.get(
            "/api/threads/dashboard",
            headers=user_a_headers,
            params={"research_degraded": True},
        )
        page_response = await client.get(
            "/api/threads/dashboard",
            headers=user_a_headers,
            params={"limit": 1},
        )
        hidden_dashboard_response = await client.get(
            "/api/threads/dashboard",
            headers=user_b_headers,
        )

    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["total"] == 2
    assert dashboard["count"] == 2
    assert dashboard["status_counts"] == {"active": 2}
    assert dashboard["needs_attention_count"] == 1
    assert dashboard["research_degraded_count"] == 1
    assert dashboard["action_hint_count"] == 4
    assert dashboard["high_priority_action_hint_count"] == 2
    assert [item["thread"]["id"] for item in dashboard["items"]] == [
        degraded_thread["id"],
        empty_thread["id"],
    ]
    degraded_item = dashboard["items"][0]
    empty_item = dashboard["items"][1]
    assert degraded_item["summary"]["thread_id"] == degraded_thread["id"]
    assert degraded_item["summary"]["latest_run"]["run_id"] == degraded_run["id"]
    assert degraded_item["latest_run"]["run"]["id"] == degraded_run["id"]
    assert degraded_item["latest_run"]["summary"]["research_status"] == "insufficient_evidence"
    assert degraded_item["needs_attention"] is True
    assert degraded_item["attention_reasons"] == ["health_degraded"]
    assert degraded_item["research_status"] == "insufficient_evidence"
    assert degraded_item["research_degraded"] is True
    assert degraded_item["last_activity_at"] == degraded_item["summary"]["last_activity_at"]
    assert degraded_item["action_count"] == 4
    assert degraded_item["high_priority_action_count"] == 2
    assert [action["kind"] for action in degraded_item["action_hints"]] == [
        "continue_research",
        "continue_research",
        "continue_research",
        "continue_research",
    ]
    assert [action["label"] for action in degraded_item["action_hints"]] == [
        "Collect more evidence sources",
        "Retry controlled web search",
        "Address research limitations",
        "Regenerate the research report",
    ]
    assert [action["source"] for action in degraded_item["action_hints"]] == [
        "research_continuation",
        "research_continuation",
        "research_continuation",
        "research_continuation",
    ]
    assert [action["priority"] for action in degraded_item["action_hints"]] == [
        "high",
        "high",
        "medium",
        "medium",
    ]
    assert {
        action["path"] for action in degraded_item["action_hints"]
    } == {f"/api/runs/{degraded_run['id']}/research/continue"}
    assert degraded_item["action_hints"][0]["related_action_id"] == "collect_more_sources"
    assert degraded_item["action_hints"][0]["suggested_tool_names"] == [
        "web.search",
        "web.fetch",
    ]
    assert empty_item["thread"]["id"] == empty_thread["id"]
    assert empty_item["summary"]["run_count"] == 0
    assert empty_item["latest_run"] is None
    assert empty_item["needs_attention"] is False
    assert empty_item["attention_reasons"] == []
    assert empty_item["research_status"] == "none"
    assert empty_item["research_degraded"] is False
    assert empty_item["action_hints"] == []
    assert empty_item["action_count"] == 0
    assert empty_item["high_priority_action_count"] == 0
    assert [item["thread"]["id"] for item in attention_response.json()["items"]] == [
        degraded_thread["id"]
    ]
    assert [item["thread"]["id"] for item in degraded_response.json()["items"]] == [
        degraded_thread["id"]
    ]
    page = page_response.json()
    assert page["total"] == 2
    assert page["count"] == 1
    assert page["limit"] == 1
    assert [item["thread"]["id"] for item in page["items"]] == [degraded_thread["id"]]
    hidden_dashboard = hidden_dashboard_response.json()
    assert hidden_dashboard["total"] == 1
    assert [item["thread"]["id"] for item in hidden_dashboard["items"]] == [
        hidden_thread["id"]
    ]


@pytest.mark.asyncio
async def test_agent_api_thread_dashboard_exposes_waiting_input_action_hint() -> None:
    input_runtime = InputRequestRuntime()
    runtime = create_agent_runtime(
        agent_runtime=input_runtime,
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Input"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=headers,
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Ask for missing input",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        dashboard_response = await client.get("/api/threads/dashboard", headers=headers)

    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["total"] == 1
    assert dashboard["action_hint_count"] == 1
    assert dashboard["high_priority_action_hint_count"] == 1
    row = dashboard["items"][0]
    assert row["thread"]["id"] == thread["id"]
    assert row["latest_run"]["run"]["id"] == run["id"]
    assert row["needs_attention"] is True
    assert row["attention_reasons"] == ["health_waiting_input"]
    assert row["action_count"] == 1
    assert row["high_priority_action_count"] == 1
    assert row["action_hints"] == [
        {
            "action_id": f"{run['id']}:resume:input:toolcall_input",
            "kind": "answer_input",
            "source": "resume",
            "priority": "high",
            "label": "Answer input request",
            "reason": "Which region should I use?",
            "run_id": run["id"],
            "method": "POST",
            "path": f"/api/runs/{run['id']}/input",
            "thread_path": f"/api/threads/{thread['id']}/runs/{run['id']}/input",
            "related_action_id": "toolcall_input",
            "target_section_ids": [],
            "suggested_tool_names": [],
            "workspace_path": None,
        }
    ]


@pytest.mark.asyncio
async def test_agent_api_thread_workbench_exposes_waiting_input_action_hint() -> None:
    input_runtime = InputRequestRuntime()
    runtime = create_agent_runtime(
        agent_runtime=input_runtime,
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Input workbench"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=headers,
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Ask for missing input in workbench",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        workbench_response = await client.get(
            f"/api/threads/{thread['id']}/workbench",
            headers=headers,
        )

    assert workbench_response.status_code == 200
    workbench = workbench_response.json()
    assert workbench["thread"]["id"] == thread["id"]
    assert workbench["selected_run_id"] == run["id"]
    assert [item["run"]["id"] for item in workbench["runs"]] == [run["id"]]
    run_card = workbench["runs"][0]
    assert run_card["summary"]["health"] == "waiting_input"
    assert run_card["summary"]["needs_attention"] is True
    assert run_card["action_count"] == 1
    assert run_card["high_priority_action_count"] == 1
    assert run_card["action_hints"] == [
        {
            "action_id": f"{run['id']}:resume:input:toolcall_input",
            "kind": "answer_input",
            "source": "resume",
            "priority": "high",
            "label": "Answer input request",
            "reason": "Which region should I use?",
            "run_id": run["id"],
            "method": "POST",
            "path": f"/api/runs/{run['id']}/input",
            "thread_path": f"/api/threads/{thread['id']}/runs/{run['id']}/input",
            "related_action_id": "toolcall_input",
            "target_section_ids": [],
            "suggested_tool_names": [],
            "workspace_path": None,
        }
    ]


@pytest.mark.asyncio
async def test_agent_api_thread_action_hint_input_path_resolves_and_clears_hints() -> None:
    input_runtime = InputRequestRuntime()
    runtime = create_agent_runtime(
        agent_runtime=input_runtime,
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_1",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                headers=headers,
                json={"title": "Input loop"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                headers=headers,
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Resolve input hint request",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        dashboard_before = (
            await client.get("/api/threads/dashboard", headers=headers)
        ).json()
        workbench_before = (
            await client.get(
                f"/api/threads/{thread['id']}/workbench",
                headers=headers,
            )
        ).json()
        dashboard_hint = dashboard_before["items"][0]["action_hints"][0]
        workbench_hint = workbench_before["runs"][0]["action_hints"][0]

        input_response = await client.post(
            dashboard_hint["thread_path"],
            headers=headers,
            json={"content": "Use APAC."},
        )
        queued = (await client.get(f"/api/runs/{run['id']}", headers=headers)).json()
        await runtime.worker.drain()
        completed = (await client.get(f"/api/runs/{run['id']}", headers=headers)).json()
        dashboard_after = (
            await client.get("/api/threads/dashboard", headers=headers)
        ).json()
        workbench_after = (
            await client.get(
                f"/api/threads/{thread['id']}/workbench",
                headers=headers,
            )
        ).json()

    assert dashboard_before["items"][0]["action_count"] == 1
    assert workbench_before["runs"][0]["action_count"] == 1
    assert dashboard_hint == workbench_hint
    assert dashboard_hint["kind"] == "answer_input"
    assert dashboard_hint["path"] == f"/api/runs/{run['id']}/input"
    assert dashboard_hint["thread_path"] == (
        f"/api/threads/{thread['id']}/runs/{run['id']}/input"
    )

    assert input_response.status_code == 201
    assert input_response.json()["content"] == "Use APAC."
    assert queued["status"] == "queued"
    assert completed["status"] == "completed"
    assert completed["summary"]["needs_attention"] is False

    dashboard_row = dashboard_after["items"][0]
    assert dashboard_after["action_hint_count"] == 0
    assert dashboard_after["high_priority_action_hint_count"] == 0
    assert dashboard_row["action_count"] == 0
    assert dashboard_row["high_priority_action_count"] == 0
    assert dashboard_row["action_hints"] == []

    workbench_run = workbench_after["runs"][0]
    assert workbench_after["selected_run"]["resume"]["kind"] == "input"
    assert workbench_after["selected_run"]["resume"]["resumable"] is False
    assert workbench_after["selected_run"]["resume"]["input_received"] is True
    assert workbench_after["selected_run"]["resume"]["input_message_id"] == (
        input_response.json()["id"]
    )
    assert workbench_run["action_count"] == 0
    assert workbench_run["high_priority_action_count"] == 0
    assert workbench_run["action_hints"] == []


@pytest.mark.asyncio
async def test_agent_api_filters_runs_by_trusted_identity_headers() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/runs", headers=user_a_headers, json={"task_msg": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/runs", headers=user_b_headers, json={"task_msg": "User B"})
        ).json()
        user_a_runs = (await client.get("/api/runs", headers=user_a_headers)).json()
        hidden_run = await client.get(f"/api/runs/{user_b_run['id']}", headers=user_a_headers)
        hidden_events = await client.get(f"/api/runs/{user_b_run['id']}/events", headers=user_a_headers)
        visible_run = await client.get(f"/api/runs/{user_a_run['id']}", headers=user_a_headers)

    assert [run["id"] for run in user_a_runs] == [user_a_run["id"]]
    assert hidden_run.status_code == 404
    assert hidden_run.json()["detail"] == "Run not found"
    assert hidden_events.status_code == 404
    assert hidden_events.json()["detail"] == "Run not found"
    assert visible_run.status_code == 200
    assert visible_run.json()["id"] == user_a_run["id"]


@pytest.mark.asyncio
async def test_agent_api_rejects_run_with_thread_outside_trusted_identity() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_b_thread = (
            await client.post("/api/threads", headers=user_b_headers, json={"title": "User B"})
        ).json()
        response = await client.post(
            "/api/runs",
            headers=user_a_headers,
            json={"thread_id": user_b_thread["id"], "task_msg": "Attach elsewhere"},
        )
        runs = (await client.get("/api/runs", headers=user_a_headers)).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_filters_approvals_by_trusted_run_identity() -> None:
    runtime = create_agent_runtime(
        agent_runtime=approval_report_runtime(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/runs", headers=user_a_headers, json={"task_msg": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/runs", headers=user_b_headers, json={"task_msg": "User B"})
        ).json()
        await runtime.worker.drain()
        user_a_run = (await client.get(f"/api/runs/{user_a_run['id']}", headers=user_a_headers)).json()
        user_b_run = (await client.get(f"/api/runs/{user_b_run['id']}", headers=user_b_headers)).json()
        user_a_approvals = (await client.get("/api/approvals", headers=user_a_headers)).json()
        visible_approval = await client.get(
            f"/api/approvals/{user_a_run['current_approval_id']}",
            headers=user_a_headers,
        )
        hidden_approval = await client.get(
            f"/api/approvals/{user_b_run['current_approval_id']}",
            headers=user_a_headers,
        )
        hidden_resolve = await client.post(
            f"/api/approvals/{user_b_run['current_approval_id']}/resolve",
            headers=user_a_headers,
            json={"decision": "approved"},
        )

    assert [approval["id"] for approval in user_a_approvals] == [user_a_run["current_approval_id"]]
    assert visible_approval.status_code == 200
    assert visible_approval.json()["id"] == user_a_run["current_approval_id"]
    assert hidden_approval.status_code == 404
    assert hidden_approval.json()["detail"] == "Approval not found"
    assert hidden_resolve.status_code == 404
    assert hidden_resolve.json()["detail"] == "Approval not found"


@pytest.mark.asyncio
async def test_agent_api_filters_artifacts_by_trusted_run_identity() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/runs", headers=user_a_headers, json={"task_msg": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/runs", headers=user_b_headers, json={"task_msg": "User B"})
        ).json()
        await runtime.worker.drain()
        user_a_artifacts = (await client.get("/api/artifacts", headers=user_a_headers)).json()
        user_b_artifacts = (
            await client.get(
                "/api/artifacts",
                headers=user_b_headers,
                params={"run_id": user_b_run["id"]},
            )
        ).json()
        hidden_artifact = await client.get(
            f"/api/artifacts/{user_b_artifacts[0]['id']}",
            headers=user_a_headers,
        )
        hidden_run_artifacts = await client.get(
            "/api/artifacts",
            headers=user_a_headers,
            params={"run_id": user_b_run["id"]},
        )
        visible_artifact = await client.get(
            f"/api/artifacts/{user_a_artifacts[0]['id']}",
            headers=user_a_headers,
        )

    assert [artifact["run_id"] for artifact in user_a_artifacts] == [user_a_run["id"]]
    assert hidden_artifact.status_code == 404
    assert hidden_artifact.json()["detail"] == "Artifact not found"
    assert hidden_run_artifacts.status_code == 404
    assert hidden_run_artifacts.json()["detail"] == "Run not found"
    assert visible_artifact.status_code == 200
    assert visible_artifact.json()["id"] == user_a_artifacts[0]["id"]


@pytest.mark.asyncio
async def test_agent_api_serves_active_artifact_content_as_attachment() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    workspace = await runtime.store.create_workspace(org_id="org_1")
    await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        path="/pages/report.html",
        content="<h1>Report</h1>",
        media_type="text/html",
    )
    artifact = await runtime.store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=None,
        type="file",
        name="Report HTML",
        media_type="text/html",
        uri="/pages/report.html",
        content={"path": "/pages/report.html"},
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/artifacts/{artifact.id}/content")

    assert response.status_code == 200
    assert response.text == "<h1>Report</h1>"
    assert response.headers["content-type"].startswith("text/html")
    assert "content-disposition" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" not in response.headers.get("content-security-policy", "")  # CSP uses sandbox directive sparingly
    assert "default-src" in response.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_agent_api_infers_inline_html_artifact_media_type_from_name() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    workspace = await runtime.store.create_workspace(org_id="org_1")
    artifact = await runtime.store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=None,
        type="file",
        name="index.html",
        content="<main>Hello</main>",
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        content_response = await client.get(f"/api/artifacts/{artifact.id}/content")
        download_info = (
            await client.get(f"/api/artifacts/{artifact.id}/download-info")
        ).json()

    assert content_response.status_code == 200
    assert content_response.headers["content-type"].startswith("text/html")
    assert content_response.headers["x-content-type-options"] == "nosniff"
    assert download_info["filename"] == "index.html"
    assert download_info["media_type"] == "text/html"


@pytest.mark.asyncio
async def test_agent_api_filters_paginates_and_orders_artifacts() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    workspace = await runtime.store.create_workspace(org_id="org_1")
    other_workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="List artifacts",
        workspace_id=workspace.id,
    )
    alpha = await runtime.store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="report",
        name="Alpha report",
    )
    beta = await runtime.store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="report",
        name="Beta report",
        retention=AgentArtifactRetentionPolicy(
            mode="expires_at",
            expires_at="2026-07-01T00:00:00Z",
        ),
    )
    gamma = await runtime.store.create_artifact(
        org_id="org_1",
        workspace_id=workspace.id,
        run_id=run.id,
        type="json",
        name="Gamma data",
        retention=AgentArtifactRetentionPolicy(mode="ephemeral"),
    )
    finalized_gamma = await runtime.store.finalize_artifact(gamma.id)
    other = await runtime.store.create_artifact(
        org_id="org_1",
        workspace_id=other_workspace.id,
        run_id=None,
        type="report",
        name="Other workspace report",
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        report_page = (
            await client.get(
                "/api/artifacts",
                params={
                    "workspace_id": workspace.id,
                    "type": "report",
                    "include_meta": True,
                    "order_by": "name",
                    "order_direction": "desc",
                    "limit": 1,
                    "offset": 0,
                },
            )
        ).json()
        expiring = (
            await client.get("/api/artifacts", params={"retention_mode": "expires_at"})
        ).json()
        retained = (
            await client.get(
                "/api/artifacts",
                params={"workspace_id": workspace.id, "retention_mode": "retained"},
            )
        ).json()
        finalized = (
            await client.get(
                "/api/artifacts",
                params={"workspace_id": workspace.id, "finalized": True},
            )
        ).json()
        missing_workspace = await client.get(
            "/api/artifacts",
            params={"workspace_id": "missing-workspace"},
        )

    assert [artifact["id"] for artifact in report_page["items"]] == [beta.id]
    assert report_page["total"] == 2
    assert report_page["count"] == 1
    assert report_page["limit"] == 1
    assert report_page["offset"] == 0
    assert report_page["order_by"] == "name"
    assert report_page["order_direction"] == "desc"
    assert report_page["filters"] == {
        "run_id": None,
        "workspace_id": workspace.id,
        "type": "report",
        "retention_mode": None,
        "finalized": None,
    }
    assert alpha.id not in [artifact["id"] for artifact in report_page["items"]]
    assert other.id not in [artifact["id"] for artifact in report_page["items"]]
    assert [artifact["id"] for artifact in expiring] == [beta.id]
    assert [artifact["id"] for artifact in retained] == [alpha.id]
    assert [artifact["id"] for artifact in finalized] == [finalized_gamma.id]
    assert missing_workspace.status_code == 404
    assert missing_workspace.json()["detail"] == "Workspace not found"


@pytest.mark.asyncio
async def test_agent_api_rejects_workspace_access_outside_trusted_identity() -> None:
    runtime = create_agent_runtime(
        agent_runtime=file_report_driver(),
        settings=AgentSettings(model="test", api_token="secret-token"),
    )
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_run = (
            await client.post("/api/runs", headers=user_a_headers, json={"task_msg": "User A"})
        ).json()
        user_b_run = (
            await client.post("/api/runs", headers=user_b_headers, json={"task_msg": "User B"})
        ).json()
        await runtime.worker.drain()
        visible_files = await client.get(
            f"/api/workspaces/{user_a_run['workspace_id']}/files",
            headers=user_a_headers,
        )
        hidden_files = await client.get(
            f"/api/workspaces/{user_b_run['workspace_id']}/files",
            headers=user_a_headers,
        )
        hidden_read = await client.get(
            f"/api/workspaces/{user_b_run['workspace_id']}/files/reports/report.md",
            headers=user_a_headers,
        )
        hidden_write = await client.put(
            f"/api/workspaces/{user_b_run['workspace_id']}/files/notes.md",
            headers=user_a_headers,
            json={"content": "nope", "media_type": "text/plain"},
        )
        hidden_patch = await client.post(
            f"/api/workspaces/{user_b_run['workspace_id']}/files/reports/report.md/patch",
            headers=user_a_headers,
            json={"edits": [{"old_text": "Report", "new_text": "Nope"}]},
        )
        hidden_upload = await client.post(
            f"/api/workspaces/{user_b_run['workspace_id']}/uploads",
            headers=user_a_headers,
            json={
                "path": "/uploads/hidden.txt",
                "content_base64": "bm9wZQ==",
                "media_type": "text/plain",
            },
        )
        hidden_convert = await client.post(
            f"/api/workspaces/{user_b_run['workspace_id']}/files/reports/report.md/convert",
            headers=user_a_headers,
        )
        hidden_delete = await client.delete(
            f"/api/workspaces/{user_b_run['workspace_id']}/files/reports/report.md",
            headers=user_a_headers,
        )

    assert visible_files.status_code == 200
    assert hidden_files.status_code == 404
    assert hidden_files.json()["detail"] == "Workspace not found"
    assert hidden_read.status_code == 404
    assert hidden_read.json()["detail"] == "Workspace not found"
    assert hidden_write.status_code == 404
    assert hidden_write.json()["detail"] == "Workspace not found"
    assert hidden_patch.status_code == 404
    assert hidden_patch.json()["detail"] == "Workspace not found"
    assert hidden_upload.status_code == 404
    assert hidden_upload.json()["detail"] == "Workspace not found"
    assert hidden_convert.status_code == 404
    assert hidden_convert.json()["detail"] == "Workspace not found"
    assert hidden_delete.status_code == 404
    assert hidden_delete.json()["detail"] == "Workspace not found"


@pytest.mark.asyncio
async def test_agent_api_patches_workspace_file_with_pydantic_contract() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        path="/reports/report.md",
        content="# Draft\nOld title\nNeeds work.\nOld title\n",
        media_type="text/markdown",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patched = await client.post(
            f"/api/workspaces/{workspace.id}/files/reports/report.md/patch",
            json={
                "edits": [
                    {
                        "old_text": "Old title",
                        "new_text": "Reviewed title",
                        "replace_all": True,
                        "expected_replacements": 2,
                    },
                    {
                        "old_text": "Needs work.",
                        "new_text": "Ready for review.",
                    },
                ],
            },
        )
        read_back = await client.get(f"/api/workspaces/{workspace.id}/files/reports/report.md")
        openapi = (await client.get("/openapi.json")).json()

    assert patched.status_code == 200
    result = patched.json()
    assert result["workspace_id"] == workspace.id
    assert result["path"] == "/reports/report.md"
    assert result["replacement_count"] == 3
    assert result["version_before"] == 1
    assert result["version_after"] == 2
    assert result["file_version_before"] == 1
    assert result["file_version_after"] == 2
    assert read_back.json()["content"] == "# Draft\nReviewed title\nReady for review.\nReviewed title\n"

    schemas = openapi["components"]["schemas"]
    assert "PatchWorkspaceFileRequest" in schemas
    assert "AgentWorkspaceTextPatchEdit" in schemas
    assert "AgentWorkspacePatchResult" in schemas
    path = openapi["paths"]["/api/workspaces/{workspace_id}/files/{path}/patch"]["post"]
    assert (
        path["requestBody"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/PatchWorkspaceFileRequest"}
    )
    assert (
        path["responses"]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentWorkspacePatchResult"}
    )


@pytest.mark.asyncio
async def test_agent_api_uploads_workspace_file_with_pydantic_contract() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        uploaded = await client.post(
            f"/api/workspaces/{workspace.id}/uploads",
            json={
                "path": "/uploads/source.txt",
                "content_base64": "SGVsbG8gdXBsb2FkCg==",
                "media_type": "text/plain",
            },
        )
        read_back = await client.get(f"/api/workspaces/{workspace.id}/files/uploads/source.txt")
        listed = await client.get(f"/api/workspaces/{workspace.id}/files")
        openapi = (await client.get("/openapi.json")).json()

    assert uploaded.status_code == 201
    result = uploaded.json()
    assert result["workspace_id"] == workspace.id
    assert result["path"] == "/uploads/source.txt"
    assert result["size"] == len(b"Hello upload\n")
    assert result["media_type"] == "text/plain"
    assert result["content_encoding"] == "base64"
    assert result["source"] == "api"
    assert result["overwritten"] is False
    assert result["conversion"] is None
    assert result["file"]["path"] == "/uploads/source.txt"
    assert result["file"]["size"] == len(b"Hello upload\n")
    assert read_back.json()["content"] == "Hello upload\n"
    assert [file["path"] for file in listed.json()] == ["/uploads/source.txt"]

    schemas = openapi["components"]["schemas"]
    assert "UploadWorkspaceFileRequest" in schemas
    assert "AgentWorkspaceUploadResult" in schemas
    assert "AgentWorkspaceConversionResult" in schemas
    assert "conversion" in schemas["AgentWorkspaceUploadResult"]["properties"]
    path = openapi["paths"]["/api/workspaces/{workspace_id}/uploads"]["post"]
    assert (
        path["requestBody"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/UploadWorkspaceFileRequest"}
    )
    assert (
        path["responses"]["201"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentWorkspaceUploadResult"}
    )
    convert_path = openapi["paths"]["/api/workspaces/{workspace_id}/files/{path}/convert"]["post"]
    assert (
        convert_path["responses"]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentWorkspaceConversionResult"}
    )


@pytest.mark.asyncio
async def test_agent_api_auto_converts_supported_upload_to_managed_markdown() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    docx = _docx_bytes("Uploaded report", "Revenue increased.")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        uploaded = await client.post(
            f"/api/workspaces/{workspace.id}/uploads",
            json={
                "path": "/uploads/report.docx",
                "content_base64": base64.b64encode(docx).decode("ascii"),
                "media_type": DOCX_MEDIA_TYPE,
            },
        )
        converted = await client.get(
            f"/api/workspaces/{workspace.id}/files/converted/uploads/report.docx.md"
        )
        listed = await client.get(f"/api/workspaces/{workspace.id}/files")

    original = await runtime.store.read_workspace_file(workspace.id, "/uploads/report.docx")
    assert uploaded.status_code == 201
    result = uploaded.json()
    conversion = result["conversion"]
    assert conversion["status"] == "converted"
    assert conversion["source_path"] == "/uploads/report.docx"
    assert conversion["output_path"] == "/converted/uploads/report.docx.md"
    assert conversion["output_media_type"] == "text/markdown"
    assert conversion["output_file"]["path"] == "/converted/uploads/report.docx.md"
    assert converted.status_code == 200
    assert "Uploaded report" in converted.json()["content"]
    assert "Revenue increased." in converted.json()["content"]
    assert original.content == docx
    assert original.media_type == DOCX_MEDIA_TYPE
    assert sorted(file["path"] for file in listed.json()) == [
        "/converted/uploads/report.docx.md",
        "/uploads/report.docx",
    ]


@pytest.mark.asyncio
async def test_agent_api_manually_converts_workspace_file_and_reports_controlled_statuses() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/simple.pdf",
        content=b"%PDF-1.4\nBT\n(Manual PDF) Tj\nET\n%%EOF",
        media_type="application/pdf",
    )
    await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/chart.png",
        content=b"image bytes",
        media_type="image/png",
    )
    await runtime.store.write_workspace_file(
        workspace_id=workspace.id,
        path="/uploads/broken.docx",
        content=b"not a zip file",
        media_type=DOCX_MEDIA_TYPE,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        converted = await client.post(
            f"/api/workspaces/{workspace.id}/files/uploads/simple.pdf/convert"
        )
        unsupported = await client.post(
            f"/api/workspaces/{workspace.id}/files/uploads/chart.png/convert"
        )
        failed = await client.post(
            f"/api/workspaces/{workspace.id}/files/uploads/broken.docx/convert"
        )
        missing = await client.post(
            f"/api/workspaces/{workspace.id}/files/uploads/missing.pdf/convert"
        )

    assert converted.status_code == 200
    assert converted.json()["status"] == "converted"
    assert converted.json()["output_path"] == "/converted/uploads/simple.pdf.md"
    assert unsupported.status_code == 200
    assert unsupported.json()["status"] == "unsupported"
    assert unsupported.json()["output_path"] is None
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["output_path"] is None
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Workspace file not found: /uploads/missing.pdf"


@pytest.mark.asyncio
async def test_agent_api_binds_memory_to_trusted_identity_headers() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test", api_token="secret-token"))
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_memory = (
            await client.post(
                "/api/memory",
                headers=user_a_headers,
                json={"scope": "user", "key": "preference.language", "value": "Chinese"},
            )
        ).json()
        await client.post(
            "/api/memory",
            headers=user_b_headers,
            json={"scope": "user", "key": "preference.language", "value": "English"},
        )
        conflicting_org = await client.post(
            "/api/memory",
            headers=user_a_headers,
            json={"org_id": "org_2", "scope": "user", "key": "bad", "value": "bad"},
        )
        conflicting_user_scope = await client.get(
            "/api/memory",
            headers=user_a_headers,
            params={"scope": "user", "scope_id": "user_b"},
        )
        user_a_entries = (
            await client.get(
                "/api/memory",
                headers=user_a_headers,
                params={"scope": "user"},
            )
        ).json()

    assert user_a_memory["org_id"] == "org_1"
    assert user_a_memory["scope_id"] == "user_a"
    assert conflicting_org.status_code == 403
    assert conflicting_org.json()["detail"] == "Request identity conflicts with authenticated context"
    assert conflicting_user_scope.status_code == 403
    assert conflicting_user_scope.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [entry["id"] for entry in user_a_entries] == [user_a_memory["id"]]


@pytest.mark.asyncio
async def test_agent_api_binds_subagent_specs_to_trusted_org_header() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test", api_token="secret-token"))
    app = create_app(runtime)
    org_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_a",
        "X-Aithru-User-Id": "user_a",
    }
    org_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_b",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        org_a_spec = (
            await client.post(
                "/api/subagents",
                headers=org_a_headers,
                json={"key": "researcher", "name": "Researcher", "instructions": "Research carefully."},
            )
        ).json()
        await client.post(
            "/api/subagents",
            headers=org_b_headers,
            json={"key": "writer", "name": "Writer", "instructions": "Write clearly."},
        )
        conflicting_create = await client.post(
            "/api/subagents",
            headers=org_a_headers,
            json={
                "org_id": "org_b",
                "key": "bad",
                "name": "Bad",
                "instructions": "Wrong org.",
            },
        )
        conflicting_list = await client.get(
            "/api/subagents",
            headers=org_a_headers,
            params={"org_id": "org_b"},
        )
        org_a_specs = (await client.get("/api/subagents", headers=org_a_headers)).json()
        hidden_spec = await client.get("/api/subagents/writer", headers=org_a_headers)
        visible_spec = await client.get("/api/subagents/researcher", headers=org_a_headers)

    assert org_a_spec["org_id"] == "org_a"
    assert conflicting_create.status_code == 403
    assert conflicting_create.json()["detail"] == "Request identity conflicts with authenticated context"
    assert conflicting_list.status_code == 403
    assert conflicting_list.json()["detail"] == "Request identity conflicts with authenticated context"
    assert [spec["key"] for spec in org_a_specs] == ["researcher"]
    assert hidden_spec.status_code == 404
    assert hidden_spec.json()["detail"] == "Subagent spec not found"
    assert visible_spec.status_code == 200
    assert visible_spec.json()["id"] == org_a_spec["id"]


@pytest.mark.asyncio
async def test_agent_api_returns_run_snapshot_for_inspection() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Write report", "scopes": ["*"]},
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/snapshot")

    snapshot = response.json()

    assert response.status_code == 200
    assert snapshot["run"]["id"] == run["id"]
    assert snapshot["run"]["status"] == "completed"
    assert [event["type"] for event in snapshot["events"]][-1] == "run.completed"
    assert {span["kind"] for span in snapshot["trace"]} >= {
        "run",
        "message",
        "model",
        "tool",
        "todo",
        "workspace",
        "artifact",
    }
    assert snapshot["todos"][0]["title"] == "Write report"
    assert snapshot["artifacts"][0]["type"] == "report"
    assert snapshot["workspace_files"][0]["path"] == "/reports/report.md"
    assert snapshot["research"]["status"] == "none"
    assert snapshot["research"]["degraded"] is False
    assert snapshot["approvals"] == []
    assert snapshot["subagents"] == []


@pytest.mark.asyncio
async def test_agent_api_snapshot_includes_sandbox_diagnostics_summary() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {
                        "code": (
                            "workspace_files = ["
                            "{"
                            "'path': '/reports/sandbox.md', "
                            "'content': '# Sandbox', "
                            "'media_type': 'text/markdown'"
                            "}"
                            "]\n"
                            "result = 'created'"
                        ),
                    },
                ),
                Step.finish(),
            ]
        )
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Create sandbox report",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/snapshot")

    snapshot = response.json()
    sandbox_summary = snapshot["summary"]["sandbox_runs"][0]

    assert response.status_code == 200
    assert snapshot["summary"]["sandbox_run_count"] == 1
    assert snapshot["summary"]["failed_sandbox_run_count"] == 0
    assert snapshot["summary"]["sandbox_workspace_file_count"] == 1
    assert snapshot["summary"]["sandbox_artifact_promotion_count"] == 0
    assert sandbox_summary["sandbox_run_id"] == "sandbox_toolcall_1"
    assert sandbox_summary["status"] == "completed"
    assert sandbox_summary["workspace_effects"]["paths"] == ["/reports/sandbox.md"]
    assert snapshot["workspace_files"][0]["path"] == "/reports/sandbox.md"


@pytest.mark.asyncio
async def test_agent_api_snapshot_includes_research_recovery_summary() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research recoverable web failures",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/snapshot")

    snapshot = response.json()
    research = snapshot["research"]

    assert response.status_code == 200
    assert snapshot["run"]["status"] == "completed"
    assert research["status"] == "insufficient_evidence"
    assert research["degraded"] is True
    assert research["failed_web_span_count"] == 1
    assert [(failure["tool_name"], failure["query"]) for failure in research["web_failures"]] == [
        ("web.search", "aithru snapshot web failure"),
    ]
    assert research["web_failures"][0]["limitation"]["code"] == "web_search_failed"
    assert [(todo["title"], todo["status"]) for todo in research["blocked_todos"]] == [
        ("Search sources", "blocked"),
    ]
    assert [(artifact["name"], artifact["report_status"]) for artifact in research["report_artifacts"]] == [
        ("Aithru Snapshot Recovery", "insufficient_evidence"),
    ]
    assert research["report_artifacts"][0]["source_count"] == 0
    assert research["report_artifacts"][0]["evidence_count"] == 0
    assert research["report_artifacts"][0]["limitation_count"] == 1
    assert {limitation["code"] for limitation in research["limitations"]} >= {
        "web_search_failed",
        "research_search_blocked",
    }


@pytest.mark.asyncio
async def test_agent_api_research_execution_snapshot_projects_run_progress() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Research"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research recoverable web failures",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/research/execution")
        thread_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{run['id']}/research/execution"
        )
        snapshot_response = await client.get(f"/api/runs/{run['id']}/snapshot")

    execution = response.json()

    assert response.status_code == 200
    assert thread_response.status_code == 200
    assert thread_response.json() == execution
    assert snapshot_response.json()["research_execution"] == execution
    assert execution["run_id"] == run["id"]
    assert execution["status"] == "degraded"
    assert execution["degraded"] is True
    assert execution["plan"]["query"] == "aithru snapshot web failure"
    assert [(step["title"], step["status"]) for step in execution["steps"]] == [
        ("Search sources", "blocked"),
        ("Fetch and review sources", "pending"),
        ("Synthesize findings", "done"),
        ("Create research report", "done"),
    ]
    assert execution["steps"][0]["attention"] is True
    assert execution["steps"][0]["web_failure_count"] == 1
    assert execution["steps"][3]["report_artifact_ids"]
    assert execution["progress"]["total_steps"] == 4
    assert execution["progress"]["pending_steps"] == 1
    assert execution["progress"]["done_steps"] == 2
    assert execution["progress"]["blocked_steps"] == 1
    assert execution["progress"]["web_failure_count"] == 1
    assert execution["progress"]["report_artifact_count"] == 1
    assert execution["summary"]["status"] == "insufficient_evidence"


@pytest.mark.asyncio
async def test_agent_api_research_evidence_ledger_projects_sources_and_evidence() -> None:
    runtime = create_agent_runtime(agent_runtime=evidence_research_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Evidence"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Create evidence ledger report",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/research/evidence")
        thread_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{run['id']}/research/evidence"
        )
        snapshot_response = await client.get(f"/api/runs/{run['id']}/snapshot")

    ledger = response.json()

    assert response.status_code == 200
    assert thread_response.status_code == 200
    assert thread_response.json() == ledger
    assert snapshot_response.json()["research_evidence"] == ledger
    assert ledger["run_id"] == run["id"]
    assert ledger["status"] == "complete"
    assert ledger["degraded"] is False
    assert ledger["title"] == "Aithru Evidence Ledger"
    assert ledger["query"] == "aithru evidence ledger"
    assert ledger["summary"] == "Collected evidence for the ledger API."
    assert ledger["counts"] == {
        "source_input_count": 1,
        "duplicate_source_count": 0,
        "source_count": 1,
        "evidence_count": 1,
        "limitation_count": 0,
        "section_count": 0,
        "missing_section_count": 0,
        "weak_section_count": 0,
        "report_artifact_count": 1,
    }
    assert ledger["quality_summary"] == {"high": 1, "medium": 0, "low": 0}
    assert ledger["sources"] == [
        {
            "title": "Aithru Agent",
            "url": "https://example.com/aithru",
            "snippet": "Aithru Agent supports evidence-backed work.",
            "content": "Fetched content for the evidence ledger API.",
            "source": "example-search",
            "published_at": "2026-06-19",
            "section_id": None,
        }
    ]
    assert ledger["evidence"][0]["citation_number"] == 1
    assert ledger["evidence"][0]["quality"]["label"] == "high"
    assert ledger["evidence"][0]["excerpt"] == "Fetched content for the evidence ledger API."
    assert ledger["limitations"] == []
    assert ledger["report_artifacts"][0]["report_status"] == "complete"


@pytest.mark.asyncio
async def test_agent_api_research_review_snapshot_grades_report_quality() -> None:
    passing_runtime = create_agent_runtime(agent_runtime=evidence_research_driver())
    passing_app = create_app(passing_runtime)

    async with AsyncClient(transport=ASGITransport(app=passing_app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Evidence"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Review evidence ledger quality",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await passing_runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/research/review")
        thread_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{run['id']}/research/review"
        )
        snapshot_response = await client.get(f"/api/runs/{run['id']}/snapshot")

    review = response.json()

    assert response.status_code == 200
    assert thread_response.status_code == 200
    assert thread_response.json() == review
    assert snapshot_response.json()["research_review"] == review
    assert review["run_id"] == run["id"]
    assert review["status"] == "pass"
    assert review["score"] == 100
    assert review["ready_for_answer"] is True
    assert review["report_status"] == "complete"
    assert review["counts"]["source_count"] == 1
    assert review["counts"]["evidence_count"] == 1
    assert review["counts"]["high_quality_source_count"] == 1
    assert review["counts"]["finding_count"] == 0
    assert review["findings"] == []

    failing_runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    failing_app = create_app(failing_runtime)

    async with AsyncClient(transport=ASGITransport(app=failing_app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Recovery"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Review insufficient evidence report",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await failing_runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/research/review")

    failing_review = response.json()

    assert response.status_code == 200
    assert failing_review["run_id"] == run["id"]
    assert failing_review["status"] == "fail"
    assert failing_review["score"] == 0
    assert failing_review["ready_for_answer"] is False
    assert failing_review["report_status"] == "insufficient_evidence"
    assert failing_review["counts"]["evidence_count"] == 0
    assert failing_review["counts"]["blocked_step_count"] == 1
    assert failing_review["counts"]["web_failure_count"] == 1
    assert [finding["code"] for finding in failing_review["findings"]] == [
        "insufficient_evidence_report",
        "missing_evidence",
        "blocked_research_steps",
        "web_failures",
        "research_limitations",
    ]


@pytest.mark.asyncio
async def test_agent_api_research_continuation_snapshot_suggests_next_actions() -> None:
    passing_runtime = create_agent_runtime(agent_runtime=evidence_research_driver())
    passing_app = create_app(passing_runtime)

    async with AsyncClient(transport=ASGITransport(app=passing_app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Evidence"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Plan continuation action set",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await passing_runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/research/continuation")
        thread_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{run['id']}/research/continuation"
        )
        snapshot_response = await client.get(f"/api/runs/{run['id']}/snapshot")

    continuation = response.json()

    assert response.status_code == 200
    assert thread_response.status_code == 200
    assert thread_response.json() == continuation
    assert snapshot_response.json()["research_continuation"] == continuation
    assert continuation["run_id"] == run["id"]
    assert continuation["status"] == "ready"
    assert continuation["ready_for_answer"] is True
    assert continuation["review_status"] == "pass"
    assert continuation["report_status"] == "complete"
    assert continuation["query"] == "aithru evidence ledger"
    assert continuation["counts"] == {
        "action_count": 0,
        "high_priority_action_count": 0,
        "suggested_tool_count": 0,
        "target_section_count": 0,
    }
    assert continuation["actions"] == []

    failing_runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    failing_app = create_app(failing_runtime)

    async with AsyncClient(transport=ASGITransport(app=failing_app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Recovery"},
            )
        ).json()
        run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Plan failed research continuation",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await failing_runtime.worker.drain()
        response = await client.get(f"/api/runs/{run['id']}/research/continuation")

    failing_continuation = response.json()

    assert response.status_code == 200
    assert failing_continuation["run_id"] == run["id"]
    assert failing_continuation["status"] == "needs_research"
    assert failing_continuation["ready_for_answer"] is False
    assert failing_continuation["review_status"] == "fail"
    assert failing_continuation["report_status"] == "insufficient_evidence"
    assert failing_continuation["query"] == "aithru snapshot web failure"
    assert failing_continuation["counts"] == {
        "action_count": 4,
        "high_priority_action_count": 2,
        "suggested_tool_count": 3,
        "target_section_count": 0,
    }
    assert [action["kind"] for action in failing_continuation["actions"]] == [
        "collect_more_sources",
        "retry_search",
        "address_limitations",
        "regenerate_report",
    ]
    assert failing_continuation["actions"][0]["suggested_tool_names"] == ["web.search", "web.fetch"]
    assert failing_continuation["actions"][1]["suggested_tool_names"] == ["web.search"]
    assert failing_continuation["actions"][3]["suggested_tool_names"] == ["research.create_report"]


@pytest.mark.asyncio
async def test_agent_api_creates_research_continuation_run_from_actions() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Continuation"},
            )
        ).json()
        source_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research recoverable web failures",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.post(
            f"/api/runs/{source_run['id']}/research/continue",
            json={
                "action_ids": ["retry_search", "regenerate_report"],
                "instructions": "Prefer two fresh independent sources before rewriting.",
            },
        )
        thread_response = await client.post(
            f"/api/threads/{thread['id']}/runs/{source_run['id']}/research/continue",
            json={"action_ids": ["retry_search"]},
        )
        unknown_action_response = await client.post(
            f"/api/runs/{source_run['id']}/research/continue",
            json={"action_ids": ["unknown_action"]},
        )
        source_lineage_response = await client.get(f"/api/runs/{source_run['id']}/research/lineage")
        child_lineage_response = await client.get(f"/api/runs/{response.json()['created_run']['id']}/research/lineage")
        thread_lineage_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{source_run['id']}/research/lineage"
        )
        source_snapshot_response = await client.get(f"/api/runs/{source_run['id']}/snapshot")

    result = response.json()
    created_run = result["created_run"]
    selected_actions = result["selected_actions"]
    created_events = await runtime.event_store.list_by_run(created_run["id"])
    source_events = await runtime.event_store.list_by_run(source_run["id"])
    queued = runtime.worker.queue.pop()
    source_lineage = source_lineage_response.json()
    child_lineage = child_lineage_response.json()

    assert response.status_code == 201
    assert result["source_run_id"] == source_run["id"]
    assert result["continuation_status"] == "needs_research"
    assert created_run["status"] == "queued"
    assert created_run["org_id"] == source_run["org_id"]
    assert created_run["actor_user_id"] == source_run["actor_user_id"]
    assert created_run["thread_id"] == source_run["thread_id"]
    assert created_run["workspace_id"] == source_run["workspace_id"]
    assert created_run["skill_id"] == "deep-research"
    assert created_run["scopes"] == ["*"]
    assert [action["action_id"] for action in selected_actions] == [
        "retry_search",
        "regenerate_report",
    ]
    assert "Continue research from source run" in created_run["harness_options"]["instructions"]
    assert source_run["id"] in created_run["harness_options"]["instructions"]
    assert "- retry_search [high] Retry controlled web search" in created_run["harness_options"]["instructions"]
    assert "- regenerate_report [medium] Regenerate the research report" in created_run["harness_options"]["instructions"]
    assert "Prefer two fresh independent sources before rewriting." in created_run["harness_options"]["instructions"]
    assert [event.type for event in created_events] == ["run.created"]
    assert created_events[0].payload["continuation"]["source_run_id"] == source_run["id"]
    assert created_events[0].payload["continuation"]["action_ids"] == [
        "retry_search",
        "regenerate_report",
    ]
    continuation_audit_events = [
        event for event in source_events if event.type == "research.continuation.created"
    ]
    assert len(continuation_audit_events) == 2
    assert continuation_audit_events[0].payload["child_run_id"] == created_run["id"]
    assert continuation_audit_events[0].payload["action_ids"] == [
        "retry_search",
        "regenerate_report",
    ]
    assert source_lineage_response.status_code == 200
    assert child_lineage_response.status_code == 200
    assert thread_lineage_response.status_code == 200
    assert thread_lineage_response.json() == source_lineage
    assert source_snapshot_response.json()["research_lineage"] == source_lineage
    assert source_lineage["run_id"] == source_run["id"]
    assert source_lineage["counts"] == {"source_count": 0, "child_count": 2}
    assert [child["child_run_id"] for child in source_lineage["children"]] == [
        created_run["id"],
        thread_response.json()["created_run"]["id"],
    ]
    assert source_lineage["children"][0]["child_run_status"] == "queued"
    assert source_lineage["children"][0]["action_ids"] == [
        "retry_search",
        "regenerate_report",
    ]
    assert child_lineage["run_id"] == created_run["id"]
    assert child_lineage["source"]["source_run_id"] == source_run["id"]
    assert child_lineage["source"]["child_run_id"] == created_run["id"]
    assert child_lineage["source"]["source_run_status"] == "completed"
    assert child_lineage["counts"] == {"source_count": 1, "child_count": 0}
    assert queued is not None
    assert queued.run_id == created_run["id"]
    assert thread_response.status_code == 201
    assert thread_response.json()["created_run"]["thread_id"] == thread["id"]
    assert unknown_action_response.status_code == 422

    ready_runtime = create_agent_runtime(agent_runtime=evidence_research_driver())
    ready_app = create_app(ready_runtime)

    async with AsyncClient(transport=ASGITransport(app=ready_app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Ready"},
            )
        ).json()
        ready_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research with enough evidence",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await ready_runtime.worker.drain()
        ready_response = await client.post(f"/api/runs/{ready_run['id']}/research/continue", json={})

    assert ready_response.status_code == 409


@pytest.mark.asyncio
async def test_agent_api_revalidates_model_profile_for_research_continuation_run() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/model-profiles",
            json={
                "org_id": "org_1",
                "key": "research",
                "name": "Research model",
                "provider": "test",
                "model": "test",
                "selection_policy": {"required_scopes": ["agent.model.research"]},
            },
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Continuation"},
            )
        ).json()
        source_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research recoverable web failures",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                    "harness_options": {"model_profile_key": "research"},
                },
            )
        ).json()
        await runtime.worker.drain()
        await client.post(
            "/api/model-profiles/research/disable",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        response = await client.post(
            f"/api/runs/{source_run['id']}/research/continue",
            json={"action_ids": ["retry_search"]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Model profile is disabled"


@pytest.mark.asyncio
async def test_agent_api_research_continuation_run_carries_target_sections() -> None:
    runtime = create_agent_runtime(agent_runtime=section_quality_research_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Section Quality"},
            )
        ).json()
        source_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research section quality gaps",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        continuation_response = await client.get(f"/api/runs/{source_run['id']}/research/continuation")
        response = await client.post(
            f"/api/runs/{source_run['id']}/research/continue",
            json={"action_ids": ["improve_source_quality"]},
        )

    continuation = continuation_response.json()
    result = response.json()
    created_run = result["created_run"]
    source_events = await runtime.event_store.list_by_run(source_run["id"])
    created_events = await runtime.event_store.list_by_run(created_run["id"])

    assert continuation_response.status_code == 200
    assert continuation["status"] == "needs_research"
    assert continuation["actions"][0]["action_id"] == "improve_source_quality"
    assert continuation["actions"][0]["target_section_ids"] == ["gaps"]
    assert response.status_code == 201
    assert result["target_section_ids"] == ["gaps"]
    assert result["selected_actions"][0]["target_section_ids"] == ["gaps"]
    assert created_run["harness_options"]["research_continuation"] == {
        "source_run_id": source_run["id"],
        "continuation_status": "needs_research",
        "query": "aithru section quality",
        "action_ids": ["improve_source_quality"],
        "target_section_ids": ["gaps"],
    }
    instructions = created_run["harness_options"]["instructions"]
    assert "- improve_source_quality [medium] Improve source quality" in instructions
    assert "sections: gaps" in instructions
    continuation_audit_events = [
        event for event in source_events if event.type == "research.continuation.created"
    ]
    assert continuation_audit_events[0].payload["target_section_ids"] == ["gaps"]
    assert created_events[0].payload["continuation"]["target_section_ids"] == ["gaps"]


@pytest.mark.asyncio
async def test_agent_api_run_detail_and_list_include_research_inspection_summary() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research recoverable web failures",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        detail = (await client.get(f"/api/runs/{run['id']}")).json()
        listed = (await client.get("/api/runs")).json()

    detail_summary = detail["summary"]
    list_summary = listed[0]["summary"]

    assert detail_summary["health"] == "degraded"
    assert detail_summary["needs_attention"] is True
    assert detail_summary["research_status"] == "insufficient_evidence"
    assert detail_summary["research_degraded"] is True
    assert detail_summary["blocked_todo_count"] == 1
    assert detail_summary["artifact_count"] == 1
    assert detail_summary["failed_trace_count"] >= 1
    assert detail_summary["last_event_type"] == "run.completed"
    assert list_summary == detail_summary


@pytest.mark.asyncio
async def test_agent_api_filters_runs_by_status_skill_and_inspection_summary() -> None:
    runtime = create_agent_runtime(
        agent_runtime=recoverable_web_failure_research_driver(),
        settings=AgentSettings(model="test", external_tools={"web_enabled": True}),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        degraded_run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research degraded run",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        await runtime.worker.drain()
        queued_run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Queued run",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()

        degraded = (
            await client.get(
                "/api/runs",
                params={
                    "status": "completed",
                    "skill_id": "deep-research",
                    "health": "degraded",
                    "needs_attention": True,
                },
            )
        ).json()
        queued = (await client.get("/api/runs", params={"status": "queued"})).json()
        healthy_completed = (await client.get("/api/runs", params={"health": "completed"})).json()

    assert [run["id"] for run in degraded] == [degraded_run["id"]]
    assert degraded[0]["summary"]["research_status"] == "insufficient_evidence"
    assert [run["id"] for run in queued] == [queued_run["id"]]
    assert healthy_completed == []


@pytest.mark.asyncio
async def test_agent_api_filters_runs_by_sandbox_summary() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {
                        "code": (
                            "workspace_files = ["
                            "{"
                            "'path': '/reports/sandbox.md', "
                            "'content': '# Sandbox', "
                            "'media_type': 'text/markdown'"
                            "}"
                            "]\n"
                            "result = 'created'"
                        ),
                    },
                ),
                Step.finish(),
            ]
        )
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sandbox_run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Create sandbox output file",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()

        workspace = await runtime.store.create_workspace(org_id="org_1")
        ordinary = await runtime.store.create_run(
            org_id="org_1",
            actor_user_id="user_1",
            source="api",
            task_msg="Ordinary completed run",
            workspace_id=workspace.id,
            scopes=["*"],
        )
        ordinary_running = await runtime.store.claim_run(ordinary.id)
        assert ordinary_running is not None
        ordinary_run = await runtime.store.update_run(
            ordinary_running.id,
            status=AgentRunStatus.COMPLETED,
        )
        failed = await runtime.store.create_run(
            org_id="org_1",
            actor_user_id="user_1",
            source="api",
            task_msg="Failed sandbox run",
            workspace_id=workspace.id,
            scopes=["*"],
        )
        failed_running = await runtime.store.claim_run(failed.id)
        assert failed_running is not None
        failed_run = await runtime.store.update_run(
            failed_running.id,
            status=AgentRunStatus.FAILED,
        )
        await AgentEventWriter(runtime.event_store).write(
            run_id=failed_run.id,
            thread_id=failed_run.thread_id,
            type="sandbox.failed",
            source={"kind": "sandbox", "id": "sandbox_toolcall_failed", "name": "python"},
            payload={
                "sandbox_run_id": "sandbox_toolcall_failed",
                "status": "failed",
                "error": {"code": "SandboxValidationError", "message": "imports are not allowed"},
                "diagnostics": {
                    "sandbox_run_id": "sandbox_toolcall_failed",
                    "status": "failed",
                    "language": "python",
                    "execution": {
                        "language": "python",
                        "timeout_ms": 1000,
                        "exit_code": 0,
                        "stdout_chars": 0,
                        "stderr_chars": 0,
                        "stdout_truncated": False,
                        "stderr_truncated": False,
                        "result_type": None,
                        "error_code": "SandboxValidationError",
                        "timed_out": False,
                    },
                    "workspace_effects": {
                        "declared_count": 0,
                        "persisted_count": 0,
                        "promoted_count": 0,
                        "paths": [],
                        "persistence_error": None,
                    },
                    "error_code": "SandboxValidationError",
                    "timed_out": False,
                },
            },
        )

        side_effect_runs = (
            await client.get("/api/runs", params={"sandbox_side_effects": True})
        ).json()
        no_side_effect_runs = (
            await client.get("/api/runs", params={"sandbox_side_effects": False})
        ).json()
        failed_sandbox_runs = (
            await client.get("/api/runs", params={"sandbox_failed": True})
        ).json()
        attention_runs = (
            await client.get("/api/runs", params={"needs_attention": True})
        ).json()
        no_attention_runs = (
            await client.get("/api/runs", params={"needs_attention": False})
        ).json()
        operator_action_queue = (
            await client.get(
                "/api/runs",
                params={
                    "needs_operator_action": True,
                    "include_meta": True,
                    "order_by": "sandbox_operator_action_count",
                    "order_direction": "desc",
                },
            )
        ).json()
        no_operator_action_runs = (
            await client.get("/api/runs", params={"needs_operator_action": False})
        ).json()
        retry_operator_runs = (
            await client.get(
                "/api/runs",
                params={"sandbox_operator_action_kind": "retry_sandbox_run"},
            )
        ).json()

    assert [run["id"] for run in side_effect_runs] == [sandbox_run["id"]]
    assert side_effect_runs[0]["summary"]["sandbox_workspace_file_count"] == 1
    assert side_effect_runs[0]["summary"]["sandbox_operator_action_count"] == 1
    assert [
        action["kind"]
        for action in side_effect_runs[0]["summary"]["sandbox_operator_actions"]
    ] == ["inspect_workspace_file"]
    assert "sandbox_workspace_side_effect" in side_effect_runs[0]["summary"]["attention_reasons"]
    assert sandbox_run["id"] not in [run["id"] for run in no_side_effect_runs]
    assert {ordinary_run.id, failed_run.id} <= {run["id"] for run in no_side_effect_runs}
    assert [run["id"] for run in failed_sandbox_runs] == [failed_run.id]
    assert failed_sandbox_runs[0]["summary"]["failed_sandbox_run_count"] == 1
    assert failed_sandbox_runs[0]["summary"]["sandbox_operator_action_count"] == 2
    assert [
        action["kind"]
        for action in failed_sandbox_runs[0]["summary"]["sandbox_operator_actions"]
    ] == ["inspect_sandbox_error", "retry_sandbox_run"]
    assert "sandbox_failed" in failed_sandbox_runs[0]["summary"]["attention_reasons"]
    assert sandbox_run["id"] in [run["id"] for run in attention_runs]
    assert failed_run.id in [run["id"] for run in attention_runs]
    assert ordinary_run.id in [run["id"] for run in no_attention_runs]
    assert sandbox_run["id"] not in [run["id"] for run in no_attention_runs]
    assert [run["id"] for run in operator_action_queue["items"]] == [
        failed_run.id,
        sandbox_run["id"],
    ]
    assert operator_action_queue["total"] == 2
    assert operator_action_queue["sandbox_operator_action_counts"] == {
        "inspect_sandbox_error": 1,
        "inspect_workspace_file": 1,
        "retry_sandbox_run": 1,
    }
    assert [run["id"] for run in no_operator_action_runs] == [ordinary_run.id]
    assert [run["id"] for run in retry_operator_runs] == [failed_run.id]


@pytest.mark.asyncio
async def test_agent_api_creates_operator_action_follow_up_run() -> None:
    runtime = create_agent_runtime(
        agent_runtime=StepAgentRuntime(
            [
                Step.tool(
                    "sandbox.run_python",
                    {
                        "code": (
                            "workspace_files = ["
                            "{"
                            "'path': '/reports/sandbox.md', "
                            "'content': '# Sandbox', "
                            "'media_type': 'text/markdown'"
                            "}"
                            "]\n"
                            "result = 'created'"
                        ),
                    },
                ),
                Step.finish(),
            ]
        )
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Operator"},
            )
        ).json()
        source_run = (
            await client.post(
                f"/api/threads/{thread['id']}/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Create sandbox output file",
                    "scopes": ["*"],
                    "retry_policy": {"max_attempts": 2, "initial_delay_seconds": 1},
                },
            )
        ).json()
        await runtime.worker.drain()

        response = await client.post(
            f"/api/runs/{source_run['id']}/operator-actions/follow-up",
            json={
                "action_kind": "inspect_workspace_file",
                "instructions": "Check whether the generated file should become the final report.",
                "scopes": ["workspace.read"],
            },
        )
        thread_response = await client.post(
            f"/api/threads/{thread['id']}/runs/{source_run['id']}/operator-actions/follow-up",
            json={"action_kind": "inspect_workspace_file"},
        )
        missing_action_response = await client.post(
            f"/api/runs/{source_run['id']}/operator-actions/follow-up",
            json={"action_kind": "retry_sandbox_run"},
        )
        source_lineage_response = await client.get(
            f"/api/runs/{source_run['id']}/operator-actions/lineage"
        )
        child_lineage_response = await client.get(
            f"/api/runs/{response.json()['created_run']['id']}/operator-actions/lineage"
        )
        thread_lineage_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{source_run['id']}/operator-actions/lineage"
        )
        source_snapshot_response = await client.get(f"/api/runs/{source_run['id']}/snapshot")

        workspace = await runtime.store.create_workspace(org_id="org_1")
        ordinary = await runtime.store.create_run(
            org_id="org_1",
            actor_user_id="user_1",
            source="api",
            task_msg="Ordinary completed run",
            workspace_id=workspace.id,
            scopes=["*"],
        )
        ordinary_running = await runtime.store.claim_run(ordinary.id)
        assert ordinary_running is not None
        ordinary_run = await runtime.store.update_run(
            ordinary_running.id,
            status=AgentRunStatus.COMPLETED,
        )
        no_actions_response = await client.post(
            f"/api/runs/{ordinary_run.id}/operator-actions/follow-up",
            json={"action_kind": "inspect_workspace_file"},
        )
        operator_follow_up_runs = (
            await client.get(
                "/api/runs",
                params={"operator_follow_up": True, "include_meta": True},
            )
        ).json()
        no_operator_follow_up_runs = (
            await client.get("/api/runs", params={"operator_follow_up": False})
        ).json()
        source_follow_up_runs = (
            await client.get(
                "/api/runs",
                params={"operator_follow_up_source_run_id": source_run["id"]},
            )
        ).json()
        thread_source_follow_up_runs = (
            await client.get(
                f"/api/threads/{thread['id']}/runs",
                params={
                    "operator_follow_up_source_run_id": source_run["id"],
                    "operator_follow_up_action_kind": "inspect_workspace_file",
                },
            )
        ).json()
        wrong_action_follow_up_runs = (
            await client.get(
                "/api/runs",
                params={
                    "operator_follow_up_source_run_id": source_run["id"],
                    "operator_follow_up_action_kind": "retry_sandbox_run",
                },
            )
        ).json()

    assert response.status_code == 201
    result = response.json()
    created_run = result["created_run"]
    selected_actions = result["selected_actions"]
    follow_up = result["operator_follow_up"]
    created_events = await runtime.event_store.list_by_run(created_run["id"])
    source_events = await runtime.event_store.list_by_run(source_run["id"])
    queued = runtime.worker.queue.pop()
    source_lineage = source_lineage_response.json()
    child_lineage = child_lineage_response.json()

    assert result["source_run_id"] == source_run["id"]
    assert created_run["status"] == "queued"
    assert created_run["org_id"] == source_run["org_id"]
    assert created_run["actor_user_id"] == source_run["actor_user_id"]
    assert created_run["thread_id"] == source_run["thread_id"]
    assert created_run["workspace_id"] == source_run["workspace_id"]
    assert created_run["skill_id"] == source_run["skill_id"]
    assert created_run["scopes"] == ["workspace.read"]
    assert created_run["retry_policy"] == source_run["retry_policy"]
    assert [action["kind"] for action in selected_actions] == ["inspect_workspace_file"]
    assert follow_up == created_run["harness_options"]["operator_follow_up"]
    assert follow_up["source_run_id"] == source_run["id"]
    assert follow_up["action_kind"] == "inspect_workspace_file"
    assert follow_up["action_label"] == "Inspect workspace file"
    assert follow_up["workspace_paths"] == ["/reports/sandbox.md"]
    assert follow_up["method"] == "GET"
    assert follow_up["path"] == (
        f"/api/workspaces/{source_run['workspace_id']}/files/reports/sandbox.md"
    )
    instructions = created_run["harness_options"]["instructions"]
    assert f"Follow up on operator action inspect_workspace_file from source run {source_run['id']}." in instructions
    assert "Review sandbox output file /reports/sandbox.md." in instructions
    assert "Check whether the generated file should become the final report." in instructions
    assert [event.type for event in created_events] == ["run.created"]
    assert created_events[0].payload["operator_follow_up"] == follow_up
    follow_up_events = [
        event for event in source_events if event.type == "operator_action.follow_up.created"
    ]
    assert len(follow_up_events) == 2
    assert follow_up_events[0].payload["child_run_id"] == created_run["id"]
    assert follow_up_events[0].payload["operator_follow_up"] == follow_up
    assert queued is not None
    assert queued.run_id == created_run["id"]
    assert thread_response.status_code == 201
    assert thread_response.json()["created_run"]["thread_id"] == thread["id"]
    assert thread_response.json()["created_run"]["scopes"] == ["*"]
    assert missing_action_response.status_code == 422
    assert no_actions_response.status_code == 409
    assert source_lineage_response.status_code == 200
    assert child_lineage_response.status_code == 200
    assert thread_lineage_response.status_code == 200
    assert thread_lineage_response.json() == source_lineage
    assert source_snapshot_response.json()["operator_follow_up_lineage"] == source_lineage
    assert source_lineage["run_id"] == source_run["id"]
    assert source_lineage["counts"] == {"source_count": 0, "child_count": 2}
    assert [child["child_run_id"] for child in source_lineage["children"]] == [
        created_run["id"],
        thread_response.json()["created_run"]["id"],
    ]
    assert source_lineage["children"][0]["child_run_status"] == "queued"
    assert source_lineage["children"][0]["operator_follow_up"]["action_kind"] == (
        "inspect_workspace_file"
    )
    assert child_lineage["run_id"] == created_run["id"]
    assert child_lineage["source"]["source_run_id"] == source_run["id"]
    assert child_lineage["source"]["child_run_id"] == created_run["id"]
    assert child_lineage["source"]["source_run_status"] == "completed"
    assert child_lineage["source"]["operator_follow_up"]["workspace_paths"] == [
        "/reports/sandbox.md"
    ]
    assert child_lineage["counts"] == {"source_count": 1, "child_count": 0}
    assert [run["id"] for run in operator_follow_up_runs["items"]] == [
        created_run["id"],
        thread_response.json()["created_run"]["id"],
    ]
    assert operator_follow_up_runs["total"] == 2
    assert operator_follow_up_runs["operator_follow_up_action_counts"] == {
        "inspect_workspace_file": 2,
    }
    assert operator_follow_up_runs["operator_follow_up_source_run_counts"] == {
        source_run["id"]: 2,
    }
    assert [run["id"] for run in no_operator_follow_up_runs] == [
        source_run["id"],
        ordinary_run.id,
    ]
    assert [run["id"] for run in source_follow_up_runs] == [
        created_run["id"],
        thread_response.json()["created_run"]["id"],
    ]
    assert [run["id"] for run in thread_source_follow_up_runs] == [
        created_run["id"],
        thread_response.json()["created_run"]["id"],
    ]
    assert wrong_action_follow_up_runs == []


@pytest.mark.asyncio
async def test_agent_api_filters_runs_by_external_run_stale_summary() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    stale_run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(stale_run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        started_at="2026-06-18T00:00:00Z",
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_stale",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )
    queued_run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Queued run",
        workspace_id=workspace.id,
        scopes=["*"],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stale = (await client.get("/api/runs", params={"external_run_stale": True})).json()
        not_stale = (await client.get("/api/runs", params={"external_run_stale": False})).json()

    assert [run["id"] for run in stale] == [stale_run.id]
    assert stale[0]["summary"]["external_run_stale"] is True
    assert stale[0]["summary"]["active_external_run"]["capability_run_id"] == "caprun_stale"
    actions = stale[0]["summary"]["active_external_run"]["operator_actions"]
    assert [action["kind"] for action in actions] == [
        "check_provider_status",
        "redeliver_completed_callback",
        "mark_failed",
        "mark_cancelled",
    ]
    assert actions[2]["status"] == "failed"
    assert actions[2]["path"] == f"/api/runs/{stale_run.id}/external-run/resolve"
    assert queued_run.id in [run["id"] for run in not_stale]


@pytest.mark.asyncio
async def test_agent_api_exposes_run_summary_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    stale_run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(stale_run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        started_at="2026-06-18T00:00:00Z",
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_contract",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        summary_response = await client.get(f"/api/runs/{stale_run.id}/summary")
        openapi_response = await client.get("/openapi.json")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["health"] == "waiting_external_run"
    assert summary["needs_attention"] is True
    assert summary["external_run_stale"] is True
    assert summary["active_external_run"]["capability_run_id"] == "caprun_contract"
    assert summary["active_external_run"]["operator_actions"][2]["kind"] == "mark_failed"
    assert "goal" not in summary

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "RunInspectionSummary" in schemas
    assert "RunActiveExternalRunDiagnostic" in schemas
    assert "RunActiveExternalRunOperatorAction" in schemas
    assert "RunSandboxOperatorAction" in schemas
    assert (
        openapi["paths"]["/api/runs/{run_id}/summary"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        == {"$ref": "#/components/schemas/RunInspectionSummary"}
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_run_list_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")
        page_response = await client.get("/api/runs", params={"include_meta": True})

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "RunListPage" in schemas
    assert "RunListItem" in schemas

    page_properties = set(schemas["RunListPage"]["properties"])
    assert {
        "items",
        "total",
        "count",
        "limit",
        "offset",
        "order_by",
        "order_direction",
        "sandbox_operator_action_counts",
        "operator_follow_up_action_counts",
        "operator_follow_up_source_run_counts",
    } <= page_properties
    assert schemas["RunListPage"]["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/RunListItem"
    }
    assert schemas["RunListItem"]["properties"]["summary"] == {
        "$ref": "#/components/schemas/RunInspectionSummary"
    }

    expected_query_names = {
        "status",
        "skill_id",
        "health",
        "needs_attention",
        "external_run_stale",
        "sandbox_failed",
        "sandbox_side_effects",
        "needs_operator_action",
        "sandbox_operator_action_kind",
        "operator_follow_up",
        "operator_follow_up_source_run_id",
        "operator_follow_up_action_kind",
        "include_meta",
        "order_by",
        "order_direction",
        "limit",
        "offset",
    }
    runs_operation = openapi["paths"]["/api/runs"]["get"]
    thread_runs_operation = openapi["paths"]["/api/threads/{thread_id}/runs"]["get"]
    assert expected_query_names <= {parameter["name"] for parameter in runs_operation["parameters"]}
    assert expected_query_names <= {
        parameter["name"] for parameter in thread_runs_operation["parameters"]
    }

    runs_response_schema = runs_operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert "RunListPage" in json.dumps(runs_response_schema)
    assert "RunListItem" in json.dumps(runs_response_schema)
    assert "array" in json.dumps(runs_response_schema)
    assert "sandbox_operator_action_count" in json.dumps(runs_operation["parameters"])
    assert "retry_sandbox_run" in json.dumps(runs_operation["parameters"])

    assert page_response.status_code == 200
    page = page_response.json()
    assert page["items"] == []
    assert page["sandbox_operator_action_counts"] == {}
    assert page["operator_follow_up_action_counts"] == {}
    assert page["operator_follow_up_source_run_counts"] == {}


@pytest.mark.asyncio
async def test_agent_api_exposes_operator_follow_up_lineage_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "OperatorFollowUpLineageSnapshot" in schemas
    assert "OperatorFollowUpChildLink" in schemas
    assert "OperatorFollowUpSourceLink" in schemas
    assert "OperatorFollowUpLineageCounts" in schemas

    expected_schema = {"$ref": "#/components/schemas/OperatorFollowUpLineageSnapshot"}
    assert (
        openapi["paths"]["/api/runs/{run_id}/operator-actions/lineage"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == expected_schema
    )
    assert (
        openapi["paths"][
            "/api/threads/{thread_id}/runs/{run_id}/operator-actions/lineage"
        ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        == expected_schema
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_run_export_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentRunExportBundle" in schemas
    assert "AgentRunExportSummary" in schemas
    assert "AgentRunExportArtifactResult" in schemas
    assert "CreateRunExportArtifactRequest" in schemas

    export_schema = {"$ref": "#/components/schemas/AgentRunExportBundle"}
    artifact_schema = {"$ref": "#/components/schemas/AgentRunExportArtifactResult"}
    assert (
        openapi["paths"]["/api/runs/{run_id}/export"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == export_schema
    )
    assert (
        openapi["paths"]["/api/threads/{thread_id}/runs/{run_id}/export"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == export_schema
    )
    assert (
        openapi["paths"]["/api/runs/{run_id}/export/artifact"]["post"]["responses"][
            "201"
        ]["content"]["application/json"]["schema"]
        == artifact_schema
    )
    assert (
        openapi["paths"][
            "/api/threads/{thread_id}/runs/{run_id}/export/artifact"
        ]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
        == artifact_schema
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_dashboard_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "RunTreeSnapshot" in schemas
    assert "RunTreeNode" in schemas
    assert "RunTreeSummary" in schemas
    assert "AgentCapabilityAuditLog" in schemas
    assert "AgentCapabilityAuditLogEntry" in schemas

    tree_schema = {"$ref": "#/components/schemas/RunTreeSnapshot"}
    audit_schema = {"$ref": "#/components/schemas/AgentCapabilityAuditLog"}
    assert (
        openapi["paths"]["/api/runs/{run_id}/tree"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == tree_schema
    )
    assert (
        openapi["paths"]["/api/threads/{thread_id}/runs/{run_id}/tree"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == tree_schema
    )
    assert (
        openapi["paths"]["/api/runs/{run_id}/capability-audit"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        == audit_schema
    )
    assert (
        openapi["paths"]["/api/threads/{thread_id}/runs/{run_id}/capability-audit"][
            "get"
        ]["responses"]["200"]["content"]["application/json"]["schema"]
        == audit_schema
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_run_snapshot_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "RunSnapshotResponse" in schemas

    assert (
        openapi["paths"]["/api/runs/{run_id}/snapshot"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/RunSnapshotResponse"}
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_event_trace_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentStreamEvent" in schemas
    assert "AgentTraceSpan" in schemas

    event_schema = {"$ref": "#/components/schemas/AgentStreamEvent"}
    trace_schema = {"$ref": "#/components/schemas/AgentTraceSpan"}
    for path in (
        "/api/runs/{run_id}/events",
        "/api/threads/{thread_id}/runs/{run_id}/events",
    ):
        schema = openapi["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert schema["type"] == "array"
        assert schema["items"] == event_schema

    trace = openapi["paths"]["/api/runs/{run_id}/trace"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert trace["type"] == "array"
    assert trace["items"] == trace_schema


@pytest.mark.asyncio
async def test_agent_api_exposes_workspace_inspection_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentWorkspaceSnapshot" in schemas
    assert "AgentWorkspaceDiff" in schemas
    assert "AgentWorkspaceRestoreResult" in schemas
    assert "AgentWorkspaceFile" in schemas
    assert "AgentWorkspaceFileVersion" in schemas

    assert (
        openapi["paths"]["/api/workspaces/{workspace_id}/snapshot"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentWorkspaceSnapshot"}
    )
    assert (
        openapi["paths"]["/api/workspaces/{workspace_id}/diff"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentWorkspaceDiff"}
    )
    assert (
        openapi["paths"]["/api/workspaces/{workspace_id}/restore"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentWorkspaceRestoreResult"}
    )

    files_schema = openapi["paths"]["/api/workspaces/{workspace_id}/files"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert files_schema["type"] == "array"
    assert files_schema["items"] == {"$ref": "#/components/schemas/AgentWorkspaceFile"}

    versions_schema = openapi["paths"][
        "/api/workspaces/{workspace_id}/files/{path}/versions"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert versions_schema["type"] == "array"
    assert versions_schema["items"] == {
        "$ref": "#/components/schemas/AgentWorkspaceFileVersion"
    }


@pytest.mark.asyncio
async def test_agent_api_exposes_workspace_file_operation_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentWorkspaceFileReadResult" in schemas
    assert "AgentWorkspaceFileDeleteResult" in schemas
    assert "AgentWorkspaceFile" in schemas
    assert "AgentArtifactPromotionResult" in schemas

    file_path = openapi["paths"]["/api/workspaces/{workspace_id}/files/{path}"]
    assert (
        file_path["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        == {"$ref": "#/components/schemas/AgentWorkspaceFileReadResult"}
    )
    assert (
        file_path["put"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        == {"$ref": "#/components/schemas/AgentWorkspaceFile"}
    )
    assert (
        file_path["delete"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        == {"$ref": "#/components/schemas/AgentWorkspaceFileDeleteResult"}
    )
    assert (
        openapi["paths"]["/api/workspaces/{workspace_id}/files/{path}/promote"][
            "post"
        ]["responses"]["201"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentArtifactPromotionResult"}
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_artifact_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentArtifact" in schemas
    assert "AgentArtifactListPage" in schemas
    assert "AgentArtifactDownloadInfo" in schemas

    list_schema = openapi["paths"]["/api/artifacts"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert "AgentArtifactListPage" in json.dumps(list_schema)
    assert "AgentArtifact" in json.dumps(list_schema)
    assert "array" in json.dumps(list_schema)

    assert (
        openapi["paths"]["/api/artifacts/{artifact_id}"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentArtifact"}
    )
    assert (
        openapi["paths"]["/api/artifacts/{artifact_id}/download-info"]["get"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentArtifactDownloadInfo"}
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_control_plane_resource_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentApproval" in schemas
    assert "AgentMemoryEntry" in schemas
    assert "AgentMemoryForgetResult" in schemas
    assert "AgentMessage" in schemas
    assert "AgentSkill" in schemas
    assert "AgentSkillConfiguration" in schemas
    assert "AgentSkillEnablementResult" in schemas
    assert "AgentSkillMarketplaceMetadata" in schemas
    assert "AgentSkillRegistryEntry" in schemas
    assert "RegisterSkillRegistryEntryRequest" in schemas
    assert "UpdateSkillRegistryEntryRequest" in schemas

    approval_schema = {"$ref": "#/components/schemas/AgentApproval"}
    run_schema = {"$ref": "#/components/schemas/AgentRun"}
    memory_schema = {"$ref": "#/components/schemas/AgentMemoryEntry"}
    forget_schema = {"$ref": "#/components/schemas/AgentMemoryForgetResult"}
    message_schema = {"$ref": "#/components/schemas/AgentMessage"}
    skill_schema = {"$ref": "#/components/schemas/AgentSkill"}
    registry_entry_schema = {"$ref": "#/components/schemas/AgentSkillRegistryEntry"}
    enablement_schema = {"$ref": "#/components/schemas/AgentSkillEnablementResult"}
    register_request_schema = {"$ref": "#/components/schemas/RegisterSkillRegistryEntryRequest"}
    update_request_schema = {"$ref": "#/components/schemas/UpdateSkillRegistryEntryRequest"}

    approvals_schema = openapi["paths"]["/api/approvals"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert approvals_schema["type"] == "array"
    assert approvals_schema["items"] == approval_schema
    assert (
        openapi["paths"]["/api/approvals/{approval_id}"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == approval_schema
    )
    assert (
        openapi["paths"]["/api/approvals/{approval_id}/resolve"]["post"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        == approval_schema
    )
    assert (
        openapi["paths"]["/api/runs/{run_id}/resume"]["post"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == run_schema
    )
    assert (
        openapi["paths"]["/api/runs/{run_id}/external-approval/resolve"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == run_schema
    )

    memory_list_schema = openapi["paths"]["/api/memory"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert (
        openapi["paths"]["/api/memory"]["post"]["responses"]["201"]["content"][
            "application/json"
        ]["schema"]
        == memory_schema
    )
    assert memory_list_schema["type"] == "array"
    assert memory_list_schema["items"] == memory_schema
    assert (
        openapi["paths"]["/api/memory/{memory_id}"]["delete"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == forget_schema
    )

    message_list_schema = openapi["paths"]["/api/threads/{thread_id}/messages"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert (
        openapi["paths"]["/api/threads/{thread_id}/messages"]["post"]["responses"][
            "201"
        ]["content"]["application/json"]["schema"]
        == message_schema
    )
    assert message_list_schema["type"] == "array"
    assert message_list_schema["items"] == message_schema

    skills_schema = openapi["paths"]["/api/skills"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert skills_schema["type"] == "array"
    assert skills_schema["items"] == skill_schema
    assert (
        openapi["paths"]["/api/skills/{skill_id_or_key}"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == skill_schema
    )

    registry_list_schema = openapi["paths"]["/api/skill-registry"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert registry_list_schema["type"] == "array"
    assert registry_list_schema["items"] == registry_entry_schema
    assert (
        openapi["paths"]["/api/skill-registry"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        == register_request_schema
    )
    assert (
        openapi["paths"]["/api/skill-registry"]["post"]["responses"]["201"]["content"][
            "application/json"
        ]["schema"]
        == registry_entry_schema
    )
    assert (
        openapi["paths"]["/api/skill-registry/{entry_id_or_key}"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        == registry_entry_schema
    )
    assert (
        openapi["paths"]["/api/skill-registry/{entry_id_or_key}"]["patch"]["requestBody"][
            "content"
        ]["application/json"]["schema"]
        == update_request_schema
    )
    assert (
        openapi["paths"]["/api/skill-registry/{entry_id_or_key}"]["patch"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        == registry_entry_schema
    )
    assert (
        openapi["paths"]["/api/skill-registry/{entry_id_or_key}/enable"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == enablement_schema
    )
    assert (
        openapi["paths"]["/api/skill-registry/{entry_id_or_key}/disable"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]
        == enablement_schema
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentThread" in schemas
    assert "AgentThreadStatus" in schemas
    assert "ThreadListPage" in schemas

    thread_schema = {"$ref": "#/components/schemas/AgentThread"}
    page_schema = {"$ref": "#/components/schemas/ThreadListPage"}

    assert (
        openapi["paths"]["/api/threads"]["post"]["responses"]["201"]["content"][
            "application/json"
        ]["schema"]
        == thread_schema
    )

    list_schema = openapi["paths"]["/api/threads"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    serialized_list_schema = json.dumps(list_schema)
    assert "array" in serialized_list_schema
    assert "ThreadListPage" in serialized_list_schema
    assert schemas["ThreadListPage"]["properties"]["items"]["items"] == thread_schema
    expected_query_names = {
        "status",
        "include_meta",
        "order_by",
        "order_direction",
        "limit",
        "offset",
    }
    assert expected_query_names <= {
        parameter["name"]
        for parameter in openapi["paths"]["/api/threads"]["get"]["parameters"]
    }

    assert (
        openapi["paths"]["/api/threads/{thread_id}"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        == thread_schema
    )


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_lifecycle_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "UpdateThreadRequest" in schemas
    assert "AgentThread" in schemas
    assert "AgentThreadStatus" in schemas

    operation = openapi["paths"]["/api/threads/{thread_id}"]["patch"]
    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/UpdateThreadRequest"}
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/AgentThread"}
    )
    properties = schemas["UpdateThreadRequest"]["properties"]
    assert properties["status"]["$ref"] == "#/components/schemas/AgentThreadStatus"


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_summary_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentThreadSummary" in schemas
    assert "AgentThreadSummaryMessage" in schemas
    assert "AgentThreadSummaryRun" in schemas

    summary_schema = {"$ref": "#/components/schemas/AgentThreadSummary"}
    assert (
        openapi["paths"]["/api/threads/{thread_id}/summary"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == summary_schema
    )
    summary_props = schemas["AgentThreadSummary"]["properties"]
    assert summary_props["latest_message"]["anyOf"][0] == {
        "$ref": "#/components/schemas/AgentThreadSummaryMessage"
    }
    assert summary_props["latest_run"]["anyOf"][0] == {
        "$ref": "#/components/schemas/AgentThreadSummaryRun"
    }


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_workbench_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentThreadWorkbench" in schemas
    assert "AgentThreadWorkbenchRun" in schemas
    assert "AgentThreadDashboardActionHint" in schemas
    assert "AgentThreadSummary" in schemas
    assert "RunSnapshotResponse" in schemas
    assert "RunInspectionSummary" in schemas

    workbench_schema = {"$ref": "#/components/schemas/AgentThreadWorkbench"}
    workbench_route = openapi["paths"]["/api/threads/{thread_id}/workbench"]["get"]
    assert (
        workbench_route["responses"]["200"]["content"]["application/json"]["schema"]
        == workbench_schema
    )
    assert {
        parameter["name"]
        for parameter in workbench_route["parameters"]
    } >= {"thread_id", "selected_run_id", "run_limit"}
    workbench_props = schemas["AgentThreadWorkbench"]["properties"]
    assert workbench_props["summary"] == {"$ref": "#/components/schemas/AgentThreadSummary"}
    assert workbench_props["selected_run"]["anyOf"][0] == {
        "$ref": "#/components/schemas/RunSnapshotResponse"
    }
    run_card_props = schemas["AgentThreadWorkbenchRun"]["properties"]
    assert run_card_props["summary"] == {"$ref": "#/components/schemas/RunInspectionSummary"}
    assert run_card_props["action_hints"]["items"] == {
        "$ref": "#/components/schemas/AgentThreadDashboardActionHint"
    }
    assert "action_count" in run_card_props
    assert "high_priority_action_count" in run_card_props


@pytest.mark.asyncio
async def test_agent_api_exposes_thread_dashboard_contract_schema() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentThreadDashboardPage" in schemas
    assert "AgentThreadDashboardItem" in schemas
    assert "AgentThreadDashboardActionHint" in schemas
    assert "AgentThreadSummary" in schemas
    assert "AgentThreadWorkbenchRun" in schemas
    assert "RunInspectionSummary" in schemas

    dashboard_schema = {"$ref": "#/components/schemas/AgentThreadDashboardPage"}
    dashboard_route = openapi["paths"]["/api/threads/dashboard"]["get"]
    assert (
        dashboard_route["responses"]["200"]["content"]["application/json"]["schema"]
        == dashboard_schema
    )
    assert {
        parameter["name"]
        for parameter in dashboard_route["parameters"]
    } >= {
        "status",
        "needs_attention",
        "research_degraded",
        "limit",
        "offset",
        "order_by",
        "order_direction",
    }
    page_props = schemas["AgentThreadDashboardPage"]["properties"]
    assert page_props["items"]["items"] == {
        "$ref": "#/components/schemas/AgentThreadDashboardItem"
    }
    assert "action_hint_count" in page_props
    assert "high_priority_action_hint_count" in page_props
    item_props = schemas["AgentThreadDashboardItem"]["properties"]
    assert item_props["summary"] == {"$ref": "#/components/schemas/AgentThreadSummary"}
    assert item_props["latest_run"]["anyOf"][0] == {
        "$ref": "#/components/schemas/AgentThreadWorkbenchRun"
    }
    assert item_props["action_hints"]["items"] == {
        "$ref": "#/components/schemas/AgentThreadDashboardActionHint"
    }
    assert "action_count" in item_props
    assert "high_priority_action_count" in item_props
    action_hint_props = schemas["AgentThreadDashboardActionHint"]["properties"]
    assert "thread_path" in action_hint_props


@pytest.mark.asyncio
async def test_agent_api_exposes_tool_subagent_and_health_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentHealthResponse" in schemas
    assert "AgentSubagentSpec" in schemas
    assert "AgentToolDescriptor" in schemas
    assert "AgentSubagentRun" in schemas

    assert (
        openapi["paths"]["/api/health"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        == {"$ref": "#/components/schemas/AgentHealthResponse"}
    )

    subagent_spec_schema = {"$ref": "#/components/schemas/AgentSubagentSpec"}
    assert (
        openapi["paths"]["/api/subagents"]["post"]["responses"]["201"]["content"][
            "application/json"
        ]["schema"]
        == subagent_spec_schema
    )
    subagent_list_schema = openapi["paths"]["/api/subagents"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert subagent_list_schema["type"] == "array"
    assert subagent_list_schema["items"] == subagent_spec_schema
    assert (
        openapi["paths"]["/api/subagents/{key}"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == subagent_spec_schema
    )

    run_tools_schema = openapi["paths"]["/api/runs/{run_id}/tools"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert run_tools_schema["type"] == "array"
    assert run_tools_schema["items"] == {"$ref": "#/components/schemas/AgentToolDescriptor"}

    run_subagents_schema = openapi["paths"]["/api/runs/{run_id}/subagents"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert run_subagents_schema["type"] == "array"
    assert run_subagents_schema["items"] == {"$ref": "#/components/schemas/AgentSubagentRun"}


@pytest.mark.asyncio
async def test_agent_api_exposes_run_lifecycle_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentRun" in schemas
    assert "AgentMessage" in schemas
    assert "RunDetailResponse" in schemas
    assert "RunInspectionSummary" in schemas

    run_schema = {"$ref": "#/components/schemas/AgentRun"}
    detail_schema = {"$ref": "#/components/schemas/RunDetailResponse"}
    message_schema = {"$ref": "#/components/schemas/AgentMessage"}

    for path in ("/api/runs", "/api/threads/{thread_id}/runs"):
        assert (
            openapi["paths"][path]["post"]["responses"]["201"]["content"][
                "application/json"
            ]["schema"]
            == run_schema
        )

    assert (
        openapi["paths"]["/api/runs/wait"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        == run_schema
    )

    for path in (
        "/api/runs/{run_id}",
        "/api/threads/{thread_id}/runs/{run_id}",
    ):
        assert (
            openapi["paths"][path]["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            == detail_schema
        )

    for path in (
        "/api/runs/{run_id}/join",
        "/api/threads/{thread_id}/runs/{run_id}/join",
    ):
        assert (
            openapi["paths"][path]["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            == run_schema
        )

    for path in (
        "/api/runs/{run_id}/cancel",
        "/api/threads/{thread_id}/runs/{run_id}/cancel",
    ):
        assert (
            openapi["paths"][path]["post"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            == run_schema
        )

    for path in (
        "/api/runs/{run_id}/input",
        "/api/threads/{thread_id}/runs/{run_id}/input",
    ):
        assert (
            openapi["paths"][path]["post"]["responses"]["201"]["content"][
                "application/json"
            ]["schema"]
            == message_schema
        )

    detail_properties = schemas["RunDetailResponse"]["properties"]
    assert detail_properties["summary"] == {
        "$ref": "#/components/schemas/RunInspectionSummary"
    }


@pytest.mark.asyncio
async def test_agent_api_exposes_continuation_and_recall_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "AgentMemoryRecall" in schemas
    assert "ResearchContinuationRunResult" in schemas
    assert "OperatorFollowUpRunResult" in schemas
    assert "ResearchContinuationAction" in schemas
    assert "RunSandboxOperatorAction" in schemas
    assert "AgentRun" in schemas

    recall_schema = {"$ref": "#/components/schemas/AgentMemoryRecall"}
    continuation_schema = {"$ref": "#/components/schemas/ResearchContinuationRunResult"}
    follow_up_schema = {"$ref": "#/components/schemas/OperatorFollowUpRunResult"}

    for path in (
        "/api/runs/{run_id}/memory-recall",
        "/api/threads/{thread_id}/runs/{run_id}/memory-recall",
    ):
        assert (
            openapi["paths"][path]["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            == recall_schema
        )

    for path in (
        "/api/runs/{run_id}/research/continue",
        "/api/threads/{thread_id}/runs/{run_id}/research/continue",
    ):
        assert (
            openapi["paths"][path]["post"]["responses"]["201"]["content"][
                "application/json"
            ]["schema"]
            == continuation_schema
        )

    for path in (
        "/api/runs/{run_id}/operator-actions/follow-up",
        "/api/threads/{thread_id}/runs/{run_id}/operator-actions/follow-up",
    ):
        assert (
            openapi["paths"][path]["post"]["responses"]["201"]["content"][
                "application/json"
            ]["schema"]
            == follow_up_schema
        )

    continuation_props = schemas["ResearchContinuationRunResult"]["properties"]
    assert continuation_props["created_run"] == {"$ref": "#/components/schemas/AgentRun"}
    assert continuation_props["selected_actions"]["items"] == {
        "$ref": "#/components/schemas/ResearchContinuationAction"
    }

    follow_up_props = schemas["OperatorFollowUpRunResult"]["properties"]
    assert follow_up_props["created_run"] == {"$ref": "#/components/schemas/AgentRun"}
    assert follow_up_props["selected_actions"]["items"] == {
        "$ref": "#/components/schemas/RunSandboxOperatorAction"
    }


@pytest.mark.asyncio
async def test_agent_api_exposes_research_dashboard_contract_schemas() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi_response = await client.get("/openapi.json")

    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    schemas = openapi["components"]["schemas"]
    assert "ResearchExecutionSnapshot" in schemas
    assert "ResearchEvidenceLedger" in schemas
    assert "ResearchReviewSnapshot" in schemas
    assert "ResearchContinuationSnapshot" in schemas
    assert "ResearchContinuationLineageSnapshot" in schemas

    expected_by_suffix = {
        "execution": {"$ref": "#/components/schemas/ResearchExecutionSnapshot"},
        "evidence": {"$ref": "#/components/schemas/ResearchEvidenceLedger"},
        "review": {"$ref": "#/components/schemas/ResearchReviewSnapshot"},
        "continuation": {"$ref": "#/components/schemas/ResearchContinuationSnapshot"},
        "lineage": {"$ref": "#/components/schemas/ResearchContinuationLineageSnapshot"},
    }
    for suffix, expected_schema in expected_by_suffix.items():
        assert (
            openapi["paths"][f"/api/runs/{{run_id}}/research/{suffix}"]["get"][
                "responses"
            ]["200"]["content"]["application/json"]["schema"]
            == expected_schema
        )
        assert (
            openapi["paths"][f"/api/threads/{{thread_id}}/runs/{{run_id}}/research/{suffix}"][
                "get"
            ]["responses"]["200"]["content"]["application/json"]["schema"]
            == expected_schema
        )


@pytest.mark.asyncio
async def test_agent_api_paginates_and_orders_run_list() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.post("/api/runs", json={"task_msg": "First"})).json()
        second = (await client.post("/api/runs", json={"task_msg": "Second"})).json()
        third = (await client.post("/api/runs", json={"task_msg": "Third"})).json()

        page = (
            await client.get(
                "/api/runs",
                params={
                    "order_by": "started_at",
                    "order_direction": "desc",
                    "offset": 1,
                    "limit": 2,
                },
            )
        ).json()

    assert [run["id"] for run in page] == [second["id"], first["id"]]
    assert third["id"] not in [run["id"] for run in page]


@pytest.mark.asyncio
async def test_agent_api_run_list_can_include_pagination_metadata() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.post("/api/runs", json={"task_msg": "First"})).json()
        second = (await client.post("/api/runs", json={"task_msg": "Second"})).json()
        third = (await client.post("/api/runs", json={"task_msg": "Third"})).json()

        page = (
            await client.get(
                "/api/runs",
                params={
                    "include_meta": True,
                    "order_by": "started_at",
                    "order_direction": "desc",
                    "offset": 1,
                    "limit": 2,
                },
            )
        ).json()

    assert [run["id"] for run in page["items"]] == [second["id"], first["id"]]
    assert third["id"] not in [run["id"] for run in page["items"]]
    assert page["total"] == 3
    assert page["count"] == 2
    assert page["limit"] == 2
    assert page["offset"] == 1
    assert page["order_by"] == "started_at"
    assert page["order_direction"] == "desc"


@pytest.mark.asyncio
async def test_agent_api_persists_completed_assistant_message_to_thread() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Report"},
            )
        ).json()
        user_message = (
            await client.post(
                f"/api/threads/{thread['id']}/messages",
                json={"role": "user", "content": "Please write a report"},
            )
        ).json()
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "task_msg": "Write the report draft",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        messages = (await client.get(f"/api/threads/{thread['id']}/messages")).json()

    assert messages[0] == user_message
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "I will write the report.\n"
    assert messages[1]["run_id"] == run["id"]


@pytest.mark.asyncio
async def test_agent_api_resolves_approval_and_resumes_run() -> None:
    runtime = create_agent_runtime(
        agent_runtime=approval_report_runtime(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run_response = await client.post(
            "/api/runs",
            json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Write report", "scopes": ["*"]},
        )
        run = run_response.json()
        await runtime.worker.drain()
        approvals = (await client.get("/api/approvals")).json()
        resolved = await client.post(
            f"/api/approvals/{approvals[0]['id']}/resolve",
            json={"decision": "approved", "comment": "ok"},
        )
        run_detail = (await client.get(f"/api/runs/{run['id']}")).json()

    assert run["status"] == "queued"
    assert approvals[0]["status"] == "pending"
    assert resolved.status_code == 200
    assert run_detail["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_api_run_resume_uses_current_approval() -> None:
    runtime = create_agent_runtime(
        agent_runtime=approval_report_runtime(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Write report", "scopes": ["*"]},
            )
        ).json()
        await runtime.worker.drain()
        paused = (await client.get(f"/api/runs/{run['id']}")).json()
        resumed = await client.post(
            f"/api/runs/{run['id']}/resume",
            json={"decision": "approved", "comment": "ok"},
        )
        run_detail = (await client.get(f"/api/runs/{run['id']}")).json()

    assert paused["status"] == "waiting_approval"
    assert paused["current_approval_id"] is not None
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert run_detail["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_api_run_resume_rejects_run_without_current_approval() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Write report", "scopes": ["*"]},
            )
        ).json()
        response = await client.post(
            f"/api/runs/{run['id']}/resume",
            json={"decision": "approved"},
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_agent_api_resolves_workflow_owned_external_approval_without_agent_approval() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for workflow approval",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_APPROVAL,
        current_external_approval=AgentExternalApprovalRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            approval_id="capapproval_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="pending",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resolved = await client.post(
            f"/api/runs/{run.id}/external-approval/resolve",
            json={
                "decision": "approved",
                "approval_id": "capapproval_1",
                "capability_run_id": "caprun_1",
                "comment": "approved in Workbench",
            },
        )
        run_detail = (await client.get(f"/api/runs/{run.id}")).json()
        approvals = (await client.get("/api/approvals")).json()

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "queued"
    assert resolved.json()["current_external_approval"] is None
    assert run_detail["current_external_approval"] is None
    assert approvals == []


@pytest.mark.asyncio
async def test_resolve_external_run_requeues_waiting_run() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resolved = await client.post(
            f"/api/runs/{run.id}/external-run/resolve",
            json={
                "capability_run_id": "caprun_1",
                "status": "completed",
                "output": {"review_status": "accepted"},
                "comment": "completed in Workbench",
            },
        )
        run_detail = (await client.get(f"/api/runs/{run.id}")).json()
        approvals = (await client.get("/api/approvals")).json()
        events = (await client.get(f"/api/runs/{run.id}/events")).json()

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "queued"
    assert resolved.json()["current_external_run"] is None
    assert run_detail["current_external_run"] is None
    assert approvals == []
    assert [event["type"] for event in events] == ["external_run.completed", "run.resumed"]


@pytest.mark.asyncio
async def test_resolve_external_run_accepts_duplicate_completed_callback() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )
    payload = {
        "capability_run_id": "caprun_1",
        "status": "completed",
        "output": {"review_status": "accepted"},
        "comment": "completed in Workbench",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(f"/api/runs/{run.id}/external-run/resolve", json=payload)
        second = await client.post(f"/api/runs/{run.id}/external-run/resolve", json=payload)
        events = (await client.get(f"/api/runs/{run.id}/events")).json()

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "queued"
    assert [event["type"] for event in events].count("external_run.completed") == 1
    assert [event["type"] for event in events].count("run.resumed") == 1


@pytest.mark.asyncio
async def test_external_run_resolve_response_exposes_contract_metadata() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_contract",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )
    payload = {
        "capability_run_id": "caprun_contract",
        "status": "completed",
        "output": {"review_status": "accepted"},
        "comment": "completed in Workbench",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(f"/api/runs/{run.id}/external-run/resolve", json=payload)
        second = await client.post(f"/api/runs/{run.id}/external-run/resolve", json=payload)
        openapi = (await client.get("/openapi.json")).json()

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["id"] == run.id
    assert first_payload["status"] == "queued"
    assert first_payload["external_run_resolved"] is True
    assert first_payload["external_run_idempotent"] is False
    assert first_payload["external_run_requeued"] is True
    assert first_payload["external_run_status"] == "completed"
    assert first_payload["external_run_capability_run_id"] == "caprun_contract"

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == run.id
    assert second_payload["status"] == "queued"
    assert second_payload["external_run_resolved"] is True
    assert second_payload["external_run_idempotent"] is True
    assert second_payload["external_run_requeued"] is False
    assert second_payload["external_run_status"] == "completed"
    assert second_payload["external_run_capability_run_id"] == "caprun_contract"

    schemas = openapi["components"]["schemas"]
    assert "ResolveExternalRunRequest" in schemas
    assert "ResolveExternalRunResponse" in schemas
    path = openapi["paths"]["/api/runs/{run_id}/external-run/resolve"]["post"]
    assert (
        path["requestBody"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/ResolveExternalRunRequest"}
    )
    assert (
        path["responses"]["200"]["content"]["application/json"]["schema"]
        == {"$ref": "#/components/schemas/ResolveExternalRunResponse"}
    )


@pytest.mark.asyncio
async def test_resolve_external_run_rejects_conflicting_terminal_callback() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            f"/api/runs/{run.id}/external-run/resolve",
            json={
                "capability_run_id": "caprun_1",
                "status": "completed",
                "output": {"review_status": "accepted"},
            },
        )
        second = await client.post(
            f"/api/runs/{run.id}/external-run/resolve",
            json={
                "capability_run_id": "caprun_1",
                "status": "failed",
                "error": {"message": "late provider failure"},
            },
        )
        events = (await client.get(f"/api/runs/{run.id}/events")).json()

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already resolved as completed" in second.json()["detail"]
    assert [event["type"] for event in events].count("external_run.completed") == 1
    assert "external_run.failed" not in [event["type"] for event in events]


@pytest.mark.asyncio
async def test_agent_api_run_summary_exposes_external_run_failure_diagnostic() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Wait for asynchronous workflow capability",
        workspace_id=workspace.id,
        scopes=["workflow.capability.report_review.invoke"],
    )
    running = await runtime.store.claim_run(run.id)
    assert running is not None
    await runtime.store.update_run(
        running.id,
        status=AgentRunStatus.WAITING_EXTERNAL_RUN,
        current_external_run=AgentExternalRunWaitRef(
            kind="workflow_capability",
            capability_key="report_review",
            capability_run_id="caprun_1",
            tool_call_id="tc_workflow",
            tool_name="workflow.report_review",
            correlation_id="run_1:tc_workflow",
            status="running",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resolved = await client.post(
            f"/api/runs/{run.id}/external-run/resolve",
            json={
                "capability_run_id": "caprun_1",
                "status": "failed",
                "error": {"message": "Workflow capability failed"},
                "comment": "failed in Workbench",
            },
        )
        run_detail = (await client.get(f"/api/runs/{run.id}")).json()

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "failed"
    summary = run_detail["summary"]
    assert summary["external_run_count"] == 1
    assert summary["failed_external_run_count"] == 1
    assert summary["cancelled_external_run_count"] == 0
    assert summary["external_runs"] == [
        {
            "kind": "workflow_capability",
            "capability_key": "report_review",
            "capability_run_id": "caprun_1",
            "tool_call_id": "tc_workflow",
            "tool_name": "workflow.report_review",
            "status": "failed",
            "source_event_sequence": 1,
            "correlation_id": "run_1:tc_workflow",
            "error": {"message": "Workflow capability failed"},
            "comment": "failed in Workbench",
        }
    ]


@pytest.mark.asyncio
async def test_agent_api_async_external_run_completes_after_worker_continuation() -> None:
    agent_runtime = AsyncExternalRunRuntime()
    runtime = create_agent_runtime(
        agent_runtime=agent_runtime,
        workflow_capability_providers=[RunningWorkflowCapabilityProvider()],
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Review the report asynchronously",
                    "scopes": ["workflow.capability.report_review.invoke"],
                },
            )
        ).json()
        await runtime.worker.drain(limit=1)

        paused = (await client.get(f"/api/runs/{run['id']}")).json()
        assert paused["status"] == "waiting_external_run"
        assert paused["current_external_run"]["capability_run_id"] == "caprun_async_1"

        resolved = await client.post(
            f"/api/runs/{run['id']}/external-run/resolve",
            json={
                "capability_run_id": "caprun_async_1",
                "status": "completed",
                "output": {"review_status": "accepted"},
                "comment": "completed in Workbench",
            },
        )
        queued = runtime.run_queue.pop()
        assert queued is not None
        assert queued.run_id == run["id"]
        runtime.run_queue.enqueue(queued.run_id)

        processed = await runtime.worker.drain(limit=1)
        run_detail = (await client.get(f"/api/runs/{run['id']}")).json()
        events = (await client.get(f"/api/runs/{run['id']}/events")).json()

    context_events = [event for event in events if event["type"] == "context.packet.built"]

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "queued"
    assert [run.status for run in processed] == [AgentRunStatus.COMPLETED]
    assert run_detail["status"] == "completed"
    assert run_detail["result"]["content"] == "External review result: review_status=accepted"
    assert run_detail["summary"]["external_run_count"] == 1
    assert run_detail["summary"]["external_runs"][0]["status"] == "completed"
    assert agent_runtime.calls == 2
    assert agent_runtime.external_result_summaries == ["review_status=accepted"]
    assert context_events[-1]["payload"]["tool_results"] >= 1
    assert [event["type"] for event in events][-3:] == [
        "model.completed",
        "message.completed",
        "run.completed",
    ]


@pytest.mark.asyncio
async def test_agent_api_accepts_user_input_for_paused_thread_run() -> None:
    runtime = create_agent_runtime(
        agent_runtime=approval_report_runtime(),
        policy=ToolPolicy(require_approval_for_risk=["write"]),
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Report"},
            )
        ).json()
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "task_msg": "Write the report draft",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        response = await client.post(
            f"/api/runs/{run['id']}/input",
            json={"content": "Please keep it brief."},
        )
        messages = (await client.get(f"/api/threads/{thread['id']}/messages")).json()
        events = (await client.get(f"/api/runs/{run['id']}/events")).json()

    created_message = response.json()

    assert response.status_code == 201
    assert created_message["role"] == "user"
    assert created_message["content"] == "Please keep it brief."
    assert created_message["run_id"] == run["id"]
    assert messages == [created_message]
    assert [event["type"] for event in events][-2:] == ["message.created", "message.completed"]
    assert events[-2]["payload"] == {"message_id": created_message["id"], "role": "user"}
    assert events[-1]["payload"] == {
        "message_id": created_message["id"],
        "content": "Please keep it brief.",
    }


@pytest.mark.asyncio
async def test_agent_api_waiting_input_run_resumes_after_user_input() -> None:
    input_runtime = InputRequestRuntime()
    runtime = create_agent_runtime(agent_runtime=input_runtime)
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Input"},
            )
        ).json()
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "task_msg": "Ask for missing input",
                    "scopes": ["*"],
                },
            )
        ).json()
        await runtime.worker.drain()
        paused = (await client.get(f"/api/runs/{run['id']}")).json()
        paused_events = (await client.get(f"/api/runs/{run['id']}/events")).json()
        paused_snapshot = (await client.get(f"/api/runs/{run['id']}/snapshot")).json()

        input_response = await client.post(
            f"/api/runs/{run['id']}/input",
            json={"content": "Use APAC."},
        )
        queued = (await client.get(f"/api/runs/{run['id']}")).json()
        await runtime.worker.drain()
        completed = (await client.get(f"/api/runs/{run['id']}")).json()
        events = (await client.get(f"/api/runs/{run['id']}/events")).json()
        completed_snapshot = (await client.get(f"/api/runs/{run['id']}/snapshot")).json()
        messages = (await client.get(f"/api/threads/{thread['id']}/messages")).json()

    assert paused["status"] == "waiting_input"
    assert paused["summary"]["health"] == "waiting_input"
    assert paused["summary"]["needs_attention"] is True
    assert "input.requested" in [event["type"] for event in paused_events]
    assert next(event for event in paused_events if event["type"] == "input.requested")["payload"] == {
        "input_request_id": "toolcall_input",
        "tool_call_id": "toolcall_input",
        "prompt": "Which region should I use?",
        "reason": "The report needs a geographic scope.",
    }
    assert paused_events[-1]["type"] == "run.paused"
    assert paused_events[-1]["payload"]["status"] == "waiting_input"
    assert paused_snapshot["resume"]["kind"] == "input"
    assert paused_snapshot["resume"]["resumable"] is True
    assert paused_snapshot["resume"]["input_request_id"] == "toolcall_input"
    assert paused_snapshot["resume"]["input_prompt"] == "Which region should I use?"
    assert paused_snapshot["resume"]["input_received"] is False

    assert input_response.status_code == 201
    assert input_response.json()["content"] == "Use APAC."
    assert queued["status"] == "queued"
    assert completed["status"] == "completed"
    assert completed["result"]["content"] == "Thanks, I can continue now."
    assert input_runtime.calls == 2
    assert [message["content"] for message in messages] == ["Use APAC.", "Thanks, I can continue now."]
    assert "input.received" in [event["type"] for event in events]
    assert next(event for event in events if event["type"] == "input.received")["payload"]["content"] == "Use APAC."
    assert next(event for event in events if event["type"] == "run.resumed")["payload"]["status"] == "queued"
    assert completed_snapshot["resume"]["kind"] == "input"
    assert completed_snapshot["resume"]["resumable"] is False
    assert completed_snapshot["resume"]["input_received"] is True
    assert completed_snapshot["resume"]["input_message_id"] == input_response.json()["id"]
    assert completed_snapshot["resume"]["resumed_event_sequence"] is not None


@pytest.mark.asyncio
async def test_agent_api_rejects_cancelling_completed_run() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Write report", "scopes": ["*"]},
            )
        ).json()
        await runtime.worker.drain()
        response = await client.post(f"/api/runs/{run['id']}/cancel")
        events = (await client.get(f"/api/runs/{run['id']}/events")).json()

    assert response.status_code == 409
    assert response.json()["detail"] == "Run is already terminal: completed"
    assert events[-1]["type"] == "run.completed"


@pytest.mark.asyncio
async def test_agent_api_validates_create_run_body() -> None:
    app = create_app(create_agent_runtime(agent_runtime=file_report_driver()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_api_lists_and_gets_published_skills() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Read files and write a report.",
        allowed_tools=["workspace.read_file"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        skills = (await client.get("/api/skills")).json()
        by_key = (await client.get("/api/skills/file-report")).json()
        by_id = (await client.get("/api/skills/skill_1")).json()
        missing = await client.get("/api/skills/missing")

    assert skills == [skill.model_dump(mode="json")]
    assert by_key["id"] == "skill_1"
    assert by_id["key"] == "file-report"
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_agent_api_exposes_default_deep_research_skill_and_filtered_tools() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        skills = (await client.get("/api/skills")).json()
        by_key = (await client.get("/api/skills/deep-research")).json()
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Research Aithru parity",
                    "scopes": ["*"],
                    "skill_id": "deep-research",
                },
            )
        ).json()
        tools = (await client.get(f"/api/runs/{run['id']}/tools")).json()

    assert set(skill["key"] for skill in skills) == {
        "deep-research",
        "surprise-me",
        "bootstrap",
        "find-skills",
        "skill-creator",
        "frontend-design",
        "chart-visualization",
        "web-design-guidelines",
        "ppt-generation",
        "data-analysis",
    }
    assert by_key["id"] == "skill_deep_research"
    assert [tool["name"] for tool in tools] == [
        "artifact.create",
        "artifact.finalize",
        "presentation.present",
        "research.create_plan",
        "research.create_report",
    ]


@pytest.mark.asyncio
async def test_agent_api_exposes_builtin_deep_research_as_read_only_registry_entry() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        registry_entries = (await client.get("/api/skill-registry")).json()
        detail = (await client.get("/api/skill-registry/deep-research")).json()
        disable_response = await client.post("/api/skill-registry/deep-research/disable")

    assert set(entry["key"] for entry in registry_entries) == {
        "bootstrap",
        "chart-visualization",
        "data-analysis",
        "deep-research",
        "find-skills",
        "frontend-design",
        "ppt-generation",
        "skill-creator",
        "surprise-me",
        "web-design-guidelines",
    }
    assert detail["source"] == "builtin"
    assert detail["read_only"] is True
    assert "research.create_plan" in detail["configuration"]["allowed_tools"]
    assert disable_response.status_code == 409
    assert "read-only" in disable_response.json()["detail"]


@pytest.mark.asyncio
async def test_agent_api_registers_disabled_skill_as_manageable_but_not_runtime_visible() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    skill_payload = {
        "id": "skill_file_report",
        "org_id": "org_1",
        "key": "file-report",
        "name": "File Report",
        "instructions": "Read files and write a report.",
        "allowed_tools": ["workspace.read_file"],
        "allowed_subagents": [],
        "workspace_policy": {"read": True, "write": False, "allowed_paths": ["/workspace"]},
        "version": "0.1.0",
        "status": "published",
        "enabled": False,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/skill-registry",
            json={"skill": skill_payload, "source": "managed"},
        )
        registry_response = await client.get("/api/skill-registry")
        runtime_response = await client.get("/api/skills")
        runtime_detail = await client.get("/api/skills/file-report")

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["id"] == "skill_file_report"
    assert created["key"] == "file-report"
    assert created["configuration"]["allowed_tools"] == ["workspace.read_file"]
    assert created["configuration"]["workspace_policy"]["allowed_paths"] == ["/workspace"]
    assert created["enabled"] is False
    assert [entry["key"] for entry in registry_response.json()] == ["file-report"]
    assert runtime_response.json() == []
    assert runtime_detail.status_code == 404


@pytest.mark.asyncio
async def test_agent_api_registers_marketplace_skill_with_typed_config_and_org_filtering() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    org_skill = {
        "id": "skill_research_brief",
        "org_id": "org_1",
        "key": "research-brief",
        "name": "Research Brief",
        "description": "Summarize collected evidence.",
        "instructions": "Read workspace sources and produce a concise brief.",
        "allowed_tools": ["workspace.read_file", "artifact.create"],
        "denied_tools": ["web.fetch"],
        "allowed_subagents": ["citation-checker"],
        "memory_policy": {"read": True, "write": False, "scopes": ["organization"]},
        "sandbox_policy": {"enabled": False, "network": "none"},
        "approval_policy": {
            "default_decision": "require_approval",
            "require_approval_for_risk": ["dangerous"],
        },
        "version": "1.2.3",
        "status": "draft",
    }
    external_skill = {
        **org_skill,
        "id": "skill_external_brief",
        "org_id": "org_2",
        "key": "external-brief",
        "name": "External Brief",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/skill-registry",
            json={
                "skill": org_skill,
                "source": "marketplace",
                "marketplace": {
                    "listing_id": "listing_research_brief",
                    "publisher": "Aithru Labs",
                    "homepage_url": "https://example.com/skills/research-brief",
                    "categories": ["research"],
                    "tags": ["brief", "evidence"],
                },
            },
        )
        await client.post("/api/skill-registry", json={"skill": external_skill, "source": "managed"})
        listed = await client.get("/api/skill-registry", headers={"X-Aithru-Org-Id": "org_1"})
        own_detail = await client.get(
            "/api/skill-registry/research-brief",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        external_detail = await client.get(
            "/api/skill-registry/external-brief",
            headers={"X-Aithru-Org-Id": "org_1"},
        )

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["source"] == "marketplace"
    assert created["marketplace"]["listing_id"] == "listing_research_brief"
    assert created["configuration"]["denied_tools"] == ["web.fetch"]
    assert created["configuration"]["allowed_subagents"] == ["citation-checker"]
    assert created["configuration"]["memory_policy"]["scopes"] == ["organization"]
    assert created["configuration"]["approval_policy"]["require_approval_for_risk"] == ["dangerous"]
    assert [entry["key"] for entry in listed.json()] == ["research-brief"]
    assert own_detail.status_code == 200
    assert external_detail.status_code == 404


@pytest.mark.parametrize(
    "policy_fragment",
    [
        {"memory_policy": {"read": True, "scopes": ["org"]}},
        {"approval_policy": {"default_decision": "auto_approve"}},
        {"approval_policy": {"require_approval_for_risk": ["high"]}},
        {"approval_policy": {"require_approval_for_risk": ["write", " "]}},
        {"sandbox_policy": {"enabled": True, "network": "allowlist"}},
        {"sandbox_policy": {"enabled": True, "allowed_commands": ["python"]}},
        {"sandbox_policy": {"enabled": True, "allowed_packages": ["pandas"]}},
        {
            "sandbox_policy": {
                "enabled": True,
                "allowed_mounts": [
                    {"source": "/workspace", "target": "/sandbox/workspace", "mode": "read"}
                ],
            }
        },
    ],
)
@pytest.mark.asyncio
async def test_agent_api_rejects_unsupported_skill_registry_policy_values(
    policy_fragment: dict[str, object],
) -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    skill_payload = {
        "id": "skill_policy_validation",
        "org_id": "org_1",
        "key": "policy-validation",
        "name": "Policy Validation",
        "instructions": "Validate managed policy.",
        "allowed_tools": [],
        "allowed_subagents": [],
        "version": "0.1.0",
        "status": "published",
        **policy_fragment,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/skill-registry",
            json={"skill": skill_payload, "source": "managed"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_api_enable_disable_controls_runtime_skill_visibility_and_runs() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    skill_payload = {
        "id": "skill_file_report",
        "org_id": "org_1",
        "key": "file-report",
        "name": "File Report",
        "instructions": "Read files and write a report.",
        "allowed_tools": ["workspace.read_file"],
        "allowed_subagents": [],
        "version": "0.1.0",
        "status": "published",
        "enabled": False,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/skill-registry", json={"skill": skill_payload, "source": "managed"})
        disabled_run = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Use disabled skill",
                "skill_id": "file-report",
                "scopes": ["*"],
            },
        )
        enabled_response = await client.post("/api/skill-registry/file-report/enable")
        runtime_skills_after_enable = (await client.get("/api/skills")).json()
        enabled_run = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Use enabled skill",
                "skill_id": "file-report",
                "scopes": ["*"],
            },
        )
        disabled_response = await client.post("/api/skill-registry/file-report/disable")
        runtime_skills_after_disable = (await client.get("/api/skills")).json()

    assert disabled_run.status_code == 404
    assert disabled_run.json()["detail"] == "Skill not found: file-report"
    assert enabled_response.status_code == 200
    enabled = enabled_response.json()
    assert enabled["enabled"] is True
    assert enabled["runtime_visible"] is True
    assert [skill["key"] for skill in runtime_skills_after_enable] == ["file-report"]
    assert enabled_run.status_code == 201
    assert enabled_run.json()["skill_id"] == "file-report"
    assert disabled_response.status_code == 200
    disabled = disabled_response.json()
    assert disabled["enabled"] is False
    assert disabled["runtime_visible"] is False
    assert runtime_skills_after_disable == []


@pytest.mark.asyncio
async def test_agent_api_updates_skill_registry_version_and_runtime_policy_config() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    skill_payload = {
        "id": "skill_file_report",
        "org_id": "org_1",
        "key": "file-report",
        "name": "File Report",
        "instructions": "List workspace files.",
        "allowed_tools": ["workspace.list_files"],
        "allowed_subagents": [],
        "workspace_policy": {"read": True, "write": False},
        "version": "0.1.0",
        "status": "published",
        "enabled": True,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/skill-registry", json={"skill": skill_payload, "source": "managed"})
        updated_response = await client.patch(
            "/api/skill-registry/file-report",
            json={
                "name": "Artifact Report",
                "description": "Create an artifact-only report.",
                "version": "0.2.0",
                "configuration": {
                    "instructions": "Create an artifact report.",
                    "allowed_tools": ["artifact.create"],
                    "denied_tools": ["workspace.write_file"],
                    "allowed_subagents": [],
                    "workspace_policy": {"read": False, "write": False},
                },
            },
        )
        runtime_detail = (await client.get("/api/skills/file-report")).json()
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Create artifact",
                    "skill_id": "file-report",
                    "scopes": ["*"],
                },
            )
        ).json()
        tools = (await client.get(f"/api/runs/{run['id']}/tools")).json()

    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["name"] == "Artifact Report"
    assert updated["description"] == "Create an artifact-only report."
    assert updated["version"] == "0.2.0"
    assert updated["configuration"]["allowed_tools"] == ["artifact.create"]
    assert updated["configuration"]["denied_tools"] == ["workspace.write_file"]
    assert updated["configuration"]["workspace_policy"]["read"] is False
    assert runtime_detail["version"] == "0.2.0"
    assert runtime_detail["allowed_tools"] == ["artifact.create"]
    assert [tool["name"] for tool in tools] == ["artifact.create"]


@pytest.mark.parametrize(
    "patch_payload",
    [
        {"name": None},
        {"version": None},
        {"status": None},
        {"configuration": None},
    ],
)
@pytest.mark.asyncio
async def test_agent_api_rejects_null_skill_registry_patch_values(
    patch_payload: dict[str, object],
) -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    skill_payload = {
        "id": "skill_file_report",
        "org_id": "org_1",
        "key": "file-report",
        "name": "File Report",
        "instructions": "List workspace files.",
        "allowed_tools": ["workspace.list_files"],
        "allowed_subagents": [],
        "version": "0.1.0",
        "status": "published",
        "enabled": True,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        await client.post("/api/skill-registry", json={"skill": skill_payload, "source": "managed"})
        response = await client.patch("/api/skill-registry/file-report", json=patch_payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_api_filters_skills_by_authenticated_org() -> None:
    org_skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Read files and write a report.",
        allowed_tools=["workspace.read_file"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    external_skill = AgentSkill(
        id="skill_2",
        org_id="org_2",
        key="external-report",
        name="External Report",
        instructions="Belongs to another organization.",
        allowed_tools=["workspace.read_file"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([org_skill, external_skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-Aithru-Org-Id": "org_1"}
        skills = (await client.get("/api/skills", headers=headers)).json()
        own_by_key = await client.get("/api/skills/file-report", headers=headers)
        external_by_key = await client.get("/api/skills/external-report", headers=headers)
        external_by_id = await client.get("/api/skills/skill_2", headers=headers)

    assert skills == [org_skill.model_dump(mode="json")]
    assert own_by_key.status_code == 200
    assert own_by_key.json()["id"] == "skill_1"
    assert external_by_key.status_code == 404
    assert external_by_id.status_code == 404


@pytest.mark.asyncio
async def test_agent_api_resolves_duplicate_skill_keys_with_authenticated_org() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([]))
    app = create_app(runtime)
    org_1_skill = {
        "id": "skill_org_1_shared_report",
        "org_id": "org_1",
        "key": "shared-report",
        "name": "Org 1 Shared Report",
        "instructions": "List workspace files for org 1.",
        "allowed_tools": ["workspace.list_files"],
        "allowed_subagents": [],
        "version": "0.1.0",
        "status": "published",
        "enabled": True,
    }
    org_2_skill = {
        **org_1_skill,
        "id": "skill_org_2_shared_report",
        "org_id": "org_2",
        "name": "Org 2 Shared Report",
        "instructions": "Create artifacts for org 2.",
        "allowed_tools": ["artifact.create"],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/skill-registry", json={"skill": org_1_skill, "source": "managed"})
        await client.post("/api/skill-registry", json={"skill": org_2_skill, "source": "managed"})
        org_2_detail = await client.get(
            "/api/skills/shared-report",
            headers={"X-Aithru-Org-Id": "org_2"},
        )
        org_1_detail = await client.get(
            "/api/skills/shared-report",
            headers={"X-Aithru-Org-Id": "org_1"},
        )
        org_2_run = await client.post(
            "/api/runs",
            headers={"X-Aithru-Org-Id": "org_2", "X-Aithru-User-Id": "user_2"},
            json={
                "org_id": "org_2",
                "actor_user_id": "user_2",
                "task_msg": "Use org 2 shared report",
                "skill_id": "shared-report",
                "scopes": ["*"],
            },
        )
        org_2_tools = await client.get(
            f"/api/runs/{org_2_run.json().get('id', 'missing')}/tools",
            headers={"X-Aithru-Org-Id": "org_2", "X-Aithru-User-Id": "user_2"},
        )

    assert org_2_detail.status_code == 200
    assert org_2_detail.json()["id"] == "skill_org_2_shared_report"
    assert org_1_detail.status_code == 200
    assert org_1_detail.json()["id"] == "skill_org_1_shared_report"
    assert org_2_run.status_code == 201
    assert org_2_run.json()["org_id"] == "org_2"
    assert org_2_run.json()["skill_id"] == "shared-report"
    assert org_2_tools.status_code == 200
    assert [tool["name"] for tool in org_2_tools.json()] == ["artifact.create"]


@pytest.mark.asyncio
async def test_agent_api_rejects_run_with_unknown_skill() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Use missing skill",
                "skill_id": "missing-skill",
                "scopes": ["*"],
            },
        )
        runs = (await client.get("/api/runs")).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found: missing-skill"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_rejects_run_with_skill_from_another_org() -> None:
    skill = AgentSkill(
        id="skill_external",
        org_id="org_2",
        key="external-skill",
        name="External Skill",
        instructions="Belongs to another organization.",
        allowed_tools=[],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "task_msg": "Use external skill",
                "skill_id": "external-skill",
                "scopes": ["*"],
            },
        )
        runs = (await client.get("/api/runs")).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Skill not found: external-skill"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_rejects_run_with_unknown_thread() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            json={
                "org_id": "org_1",
                "actor_user_id": "user_1",
                "thread_id": "missing-thread",
                "task_msg": "Use missing thread",
                "scopes": ["*"],
            },
        )
        runs = (await client.get("/api/runs")).json()

    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found: missing-thread"
    assert runs == []


@pytest.mark.asyncio
async def test_agent_api_rejects_messages_for_unknown_thread() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/threads/missing-thread/messages",
            json={"role": "user", "content": "hello"},
        )
        listed = await client.get("/api/threads/missing-thread/messages")

    assert created.status_code == 404
    assert created.json()["detail"] == "Thread not found"
    assert listed.status_code == 404
    assert listed.json()["detail"] == "Thread not found"


@pytest.mark.asyncio
async def test_agent_api_rejects_file_operations_for_unknown_workspace() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/workspaces/missing-workspace/files")
        read = await client.get("/api/workspaces/missing-workspace/files/notes.md")
        written = await client.put(
            "/api/workspaces/missing-workspace/files/notes.md",
            json={"content": "hello", "media_type": "text/plain"},
        )
        deleted = await client.delete("/api/workspaces/missing-workspace/files/notes.md")

    assert listed.status_code == 404
    assert read.status_code == 404
    assert written.status_code == 404
    assert deleted.status_code == 404
    assert listed.json()["detail"] == "Workspace not found"
    assert read.json()["detail"] == "Workspace not found"
    assert written.json()["detail"] == "Workspace not found"
    assert deleted.json()["detail"] == "Workspace not found"


@pytest.mark.asyncio
async def test_agent_api_rejects_run_event_reads_for_unknown_run() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        events = await client.get("/api/runs/missing-run/events")
        stream = await client.get("/api/runs/missing-run/stream")

    assert events.status_code == 404
    assert stream.status_code == 404
    assert events.json()["detail"] == "Run not found"
    assert stream.json()["detail"] == "Run not found"


@pytest.mark.asyncio
async def test_agent_api_validates_workspace_file_content_as_text() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={"org_id": "org_1", "actor_user_id": "user_1", "task_msg": "Prepare workspace"},
            )
        ).json()
        response = await client.put(
            f"/api/workspaces/{run['workspace_id']}/files/data.json",
            json={"content": {"nested": True}, "media_type": "application/json"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_api_lists_run_tools_filtered_by_skill_policy() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="file-report",
        name="File Report",
        instructions="Only list files.",
        allowed_tools=["workspace.list_files"],
        allowed_subagents=[],
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "List files",
                    "scopes": ["*"],
                    "skill_id": "file-report",
                },
            )
        ).json()
        tools_response = await client.get(f"/api/runs/{run['id']}/tools")
        tools = tools_response.json()

    assert tools_response.status_code == 200
    assert [tool["name"] for tool in tools] == ["workspace.list_files"]
    assert tools[0]["kind"] == "local_tool"


@pytest.mark.asyncio
async def test_agent_api_rejects_run_tools_for_unresolvable_run_skill() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Inspect tools with missing skill",
        workspace_id=workspace.id,
        scopes=["*"],
        skill_id="missing-skill",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/runs/{run.id}/tools")

    assert response.status_code == 409
    assert response.json()["detail"] == "Skill not found: missing-skill"


@pytest.mark.asyncio
async def test_agent_api_hides_sandbox_tools_when_skill_disables_sandbox() -> None:
    skill = AgentSkill(
        id="skill_1",
        org_id="org_1",
        key="no-sandbox",
        name="No Sandbox",
        instructions="Do not execute code.",
        allowed_tools=["sandbox.run_python"],
        allowed_subagents=[],
        sandbox_policy=AgentSandboxPolicy(enabled=False),
        version="0.1.0",
        status="published",
    )
    runtime = create_agent_runtime(settings=AgentSettings(model="test"), skill_resolver=InMemorySkillResolver([skill]))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "task_msg": "Try code.",
                    "scopes": ["*"],
                    "skill_id": "no-sandbox",
                },
            )
        ).json()
        tools_response = await client.get(f"/api/runs/{run['id']}/tools")

    assert tools_response.status_code == 200
    assert [tool["name"] for tool in tools_response.json()] == []


@pytest.mark.asyncio
async def test_agent_api_creates_and_lists_memory_entries() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/memory",
            json={
                "org_id": "org_1",
                "scope": "user",
                "scope_id": "user_1",
                "key": "preference.language",
                "value": "Prefers Chinese summaries.",
            },
        )
        listed = (
            await client.get(
                "/api/memory",
                params={"org_id": "org_1", "scope": "user", "query": "Chinese"},
            )
        ).json()

    created = created_response.json()

    assert created_response.status_code == 201
    assert created["key"] == "preference.language"
    assert [entry["id"] for entry in listed] == [created["id"]]


@pytest.mark.asyncio
async def test_agent_api_disables_local_memory_routes_in_mem0_mode() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            long_term_memory=AgentLongTermMemorySettings(
                provider="mem0",
                mem0_api_key="mem0-key",
            ),
        ),
        long_term_memory_provider=ApiMem0Provider(),
    )
    entry = await runtime.store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="legacy.preference",
        value="Legacy local memory should be unreachable.",
        owner="user_1",
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/memory",
            json={
                "org_id": "org_1",
                "scope": "user",
                "scope_id": "user_1",
                "key": "preference.language",
                "value": "Prefers Chinese summaries.",
            },
        )
        listed_response = await client.get("/api/memory", params={"org_id": "org_1"})
        deleted_response = await client.delete(f"/api/memory/{entry.id}")

    assert created_response.status_code == 410
    assert listed_response.status_code == 410
    assert deleted_response.status_code == 410
    assert created_response.json()["detail"] == (
        "Local memory is disabled when long-term memory provider is mem0"
    )


@pytest.mark.asyncio
async def test_agent_api_returns_run_memory_recall_projection() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        thread = (
            await client.post(
                "/api/threads",
                json={"org_id": "org_1", "owner_user_id": "user_1", "title": "Memory"},
            )
        ).json()
        run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "task_msg": "Inspect memory",
                    "scopes": ["agent.memory.read"],
                },
            )
        ).json()
        no_memory_run = (
            await client.post(
                "/api/runs",
                json={
                    "org_id": "org_1",
                    "actor_user_id": "user_1",
                    "thread_id": thread["id"],
                    "task_msg": "No memory",
                    "scopes": ["agent.workspace.read"],
                },
            )
        ).json()
        await client.post(
            "/api/memory",
            json={
                "org_id": "org_1",
                "scope": "user",
                "scope_id": "user_1",
                "key": "preference.language",
                "value": "Prefers Chinese summaries.",
            },
        )
        await client.post(
            "/api/memory",
            json={
                "org_id": "org_1",
                "scope": "thread",
                "scope_id": thread["id"],
                "key": "thread.region",
                "value": "Use APAC.",
            },
        )
        await client.post(
            "/api/memory",
            json={
                "org_id": "org_1",
                "scope": "user",
                "scope_id": "user_2",
                "key": "preference.language",
                "value": "Prefers English summaries.",
            },
        )

        recall_response = await client.get(f"/api/runs/{run['id']}/memory-recall")
        thread_recall_response = await client.get(
            f"/api/threads/{thread['id']}/runs/{run['id']}/memory-recall"
        )
        no_memory_response = await client.get(f"/api/runs/{no_memory_run['id']}/memory-recall")

    recall = recall_response.json()

    assert recall_response.status_code == 200
    assert thread_recall_response.json() == recall
    assert recall["run_id"] == run["id"]
    assert recall["count"] == 2
    assert recall["dropped"] == 0
    assert [item["key"] for item in recall["items"]] == ["preference.language", "thread.region"]
    assert recall["items"][0]["reason"] == "Current user memory is readable by this run."
    assert no_memory_response.json() == {
        "run_id": no_memory_run["id"],
        "items": [],
        "count": 0,
        "dropped": 0,
    }


@pytest.mark.asyncio
async def test_agent_api_memory_recall_uses_only_mem0_in_mem0_mode() -> None:
    runtime = create_agent_runtime(
        settings=AgentSettings(
            model="test",
            long_term_memory=AgentLongTermMemorySettings(
                provider="mem0",
                mem0_api_key="mem0-key",
            ),
        ),
        long_term_memory_provider=ApiMem0Provider(),
    )
    workspace = await runtime.store.create_workspace(org_id="org_1")
    run = await runtime.store.create_run(
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        task_msg="Inspect memory",
        workspace_id=workspace.id,
        scopes=["agent.memory.read"],
    )
    await runtime.store.create_memory_entry(
        org_id="org_1",
        scope="user",
        scope_id="user_1",
        key="legacy.preference",
        value="Legacy local memory should not be recalled.",
        owner="user_1",
    )
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        recall_response = await client.get(f"/api/runs/{run.id}/memory-recall")

    recall = recall_response.json()

    assert recall_response.status_code == 200
    assert recall["count"] == 1
    assert recall["items"][0]["source"] == "mem0"
    assert recall["items"][0]["key"] == "mem0:mem0_api_1"


@pytest.mark.asyncio
async def test_agent_api_memory_lifecycle_retention_and_forget() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test"))
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        active = (
            await client.post(
                "/api/memory",
                json={
                    "org_id": "org_1",
                    "scope": "user",
                    "scope_id": "user_1",
                    "key": "preference.language",
                    "value": "Chinese",
                    "retention": {"mode": "retained"},
                },
            )
        ).json()
        expired = (
            await client.post(
                "/api/memory",
                json={
                    "org_id": "org_1",
                    "scope": "user",
                    "scope_id": "user_1",
                    "key": "preference.region",
                    "value": "APAC",
                    "retention": {
                        "mode": "expires_at",
                        "expires_at": "2000-01-01T00:00:00Z",
                    },
                },
            )
        ).json()
        visible = (
            await client.get(
                "/api/memory",
                params={"org_id": "org_1", "scope": "user", "scope_id": "user_1"},
            )
        ).json()
        all_entries = (
            await client.get(
                "/api/memory",
                params={
                    "org_id": "org_1",
                    "scope": "user",
                    "scope_id": "user_1",
                    "include_expired": "true",
                },
            )
        ).json()
        forget_response = await client.delete(f"/api/memory/{active['id']}")
        after_forget = (
            await client.get(
                "/api/memory",
                params={
                    "org_id": "org_1",
                    "scope": "user",
                    "scope_id": "user_1",
                    "include_expired": "true",
                },
            )
        ).json()

    forget = forget_response.json()

    assert active["retention"] == {"mode": "retained", "expires_at": None}
    assert expired["retention"]["mode"] == "expires_at"
    assert [entry["id"] for entry in visible] == [active["id"]]
    assert [entry["id"] for entry in all_entries] == [active["id"], expired["id"]]
    assert forget_response.status_code == 200
    assert forget == {
        "memory_id": active["id"],
        "org_id": "org_1",
        "forgotten": True,
        "deleted_count": 1,
    }
    assert [entry["id"] for entry in after_forget] == [expired["id"]]


@pytest.mark.asyncio
async def test_agent_api_filters_private_memory_by_owner() -> None:
    runtime = create_agent_runtime(settings=AgentSettings(model="test", api_token="secret-token"))
    app = create_app(runtime)
    user_a_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_a",
    }
    user_b_headers = {
        "Authorization": "Bearer secret-token",
        "X-Aithru-Org-Id": "org_1",
        "X-Aithru-User-Id": "user_b",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user_a_private = (
            await client.post(
                "/api/memory",
                headers=user_a_headers,
                json={
                    "scope": "organization",
                    "scope_id": "org_1",
                    "key": "private.a",
                    "value": "Only user A.",
                    "visibility": "private",
                    "owner": "user_a",
                },
            )
        ).json()
        user_b_private = (
            await client.post(
                "/api/memory",
                headers=user_b_headers,
                json={
                    "scope": "organization",
                    "scope_id": "org_1",
                    "key": "private.b",
                    "value": "Only user B.",
                    "visibility": "private",
                    "owner": "user_b",
                },
            )
        ).json()
        shared = (
            await client.post(
                "/api/memory",
                headers=user_a_headers,
                json={
                    "scope": "organization",
                    "scope_id": "org_1",
                    "key": "shared.policy",
                    "value": "Visible to org readers.",
                    "visibility": "shared",
                    "owner": "user_a",
                },
            )
        ).json()
        user_a_entries = (
            await client.get(
                "/api/memory",
                headers=user_a_headers,
                params={"scope": "organization", "scope_id": "org_1"},
            )
        ).json()
        user_b_entries = (
            await client.get(
                "/api/memory",
                headers=user_b_headers,
                params={"scope": "organization", "scope_id": "org_1"},
            )
        ).json()
        forbidden_forget = await client.delete(
            f"/api/memory/{user_a_private['id']}",
            headers=user_b_headers,
        )
        allowed_forget = await client.delete(
            f"/api/memory/{user_a_private['id']}",
            headers=user_a_headers,
        )

    assert [entry["id"] for entry in user_a_entries] == [user_a_private["id"], shared["id"]]
    assert [entry["id"] for entry in user_b_entries] == [user_b_private["id"], shared["id"]]
    assert forbidden_forget.status_code == 404
    assert allowed_forget.status_code == 200
    assert allowed_forget.json()["forgotten"] is True


@pytest.mark.asyncio
async def test_run_snapshot_exposes_presentations_only() -> None:
    runtime = create_agent_runtime(agent_runtime=file_report_driver())
    app = create_app(runtime)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (
            await client.post(
                "/api/runs",
                json={
                    "task_msg": "Write file",
                    "scopes": ["agent.workspace.write", "agent.workspace.read"],
                },
            )
        ).json()
        run_id = created["id"]
        await runtime.worker.drain()

        snapshot = (await client.get(f"/api/runs/{run_id}/snapshot")).json()

    assert "display" + "_cards" not in snapshot
    assert snapshot["presentations"]
    assert snapshot["presentations"][0]["resource"]["kind"] in {"workspace_file", "artifact"}
    assert snapshot["presentations"][0]["sequence"] is not None
