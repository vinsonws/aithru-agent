import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from aithru_agent.capabilities.workflow import (
    WorkflowCapabilityInvocation,
    WorkflowCapabilitySpec,
)
from aithru_agent.capabilities.workflow_http import (
    ControlledHTTPWorkflowCapabilityProvider,
    ControlledHTTPWorkflowCapabilityProviderConfig,
)
from aithru_agent.domain import AgentExternalRunRef


class WorkflowCapabilityHandler(BaseHTTPRequestHandler):
    payloads: list[dict] = []

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        self.payloads.append(payload)
        body = json.dumps(
            {
                "status": "completed",
                "output": {
                    "accepted": True,
                    "capability_key": payload["capability_key"],
                    "artifact_id": payload["input"]["artifact_id"],
                },
                "redaction": "partial",
                "external_run": {
                    "kind": "workflow_capability",
                    "capability_key": payload["capability_key"],
                    "capability_run_id": "caprun_http_1",
                    "status": "completed",
                    "correlation_id": payload["correlation_id"],
                    "approval_id": None,
                },
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def capability_endpoint() -> str:
    WorkflowCapabilityHandler.payloads = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), WorkflowCapabilityHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/capability-runs"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def workflow_capability_spec() -> WorkflowCapabilitySpec:
    return WorkflowCapabilitySpec(
        key="report_review",
        tool_name="workflow.report_review",
        description="Run report review in Workbench.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level="write",
        required_scopes=["workflow.capability.report_review.invoke"],
        approval_policy="never",
    )


def test_controlled_http_workflow_capability_config_requires_allowlisted_endpoint(
    capability_endpoint: str,
) -> None:
    with pytest.raises(ValueError, match="endpoint host"):
        ControlledHTTPWorkflowCapabilityProviderConfig(
            capabilities=[workflow_capability_spec()],
            endpoint_url=capability_endpoint,
            allowed_hosts=["allowed.example"],
        )


@pytest.mark.asyncio
async def test_controlled_http_workflow_capability_provider_posts_invocation_to_endpoint(
    capability_endpoint: str,
) -> None:
    provider = ControlledHTTPWorkflowCapabilityProvider(
        capabilities=[workflow_capability_spec()],
        endpoint_url=capability_endpoint,
        allowed_hosts=["127.0.0.1"],
        timeout_ms=1_000,
        max_response_bytes=64_000,
    )
    invocation = WorkflowCapabilityInvocation(
        tool_call_id="toolcall_1",
        tool_name="workflow.report_review",
        capability_key="report_review",
        input={"artifact_id": "artifact_1"},
        run_id="run_1",
        org_id="org_1",
        actor_user_id="user_1",
        workspace_id="workspace_1",
        thread_id="thread_1",
        skill_id="skill_1",
        correlation_id="run_1:toolcall_1",
    )

    result = await provider.invoke(invocation)

    assert provider.list_capabilities() == [workflow_capability_spec()]
    assert WorkflowCapabilityHandler.payloads == [invocation.model_dump(mode="json")]
    assert result.status == "completed"
    assert result.output == {
        "accepted": True,
        "capability_key": "report_review",
        "artifact_id": "artifact_1",
    }
    assert result.redaction == "partial"
    assert result.external_run == AgentExternalRunRef(
        kind="workflow_capability",
        capability_key="report_review",
        capability_run_id="caprun_http_1",
        status="completed",
        correlation_id="run_1:toolcall_1",
    )
