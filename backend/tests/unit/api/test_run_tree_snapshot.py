from aithru_agent.api.snapshots import build_run_tree_snapshot
from aithru_agent.domain import (
    AgentArtifact,
    AgentArtifactSummary,
    AgentRun,
    AgentRunResult,
    AgentRunSource,
    AgentRunStatus,
    AgentSubagentResultSummary,
    AgentSubagentRun,
    AgentSubagentRunStatus,
)
from aithru_agent.stream.events import AgentStreamEvent, AgentStreamSource


def run(
    run_id: str,
    status: AgentRunStatus,
    *,
    source: AgentRunSource = AgentRunSource.API,
    result: AgentRunResult | None = None,
) -> AgentRun:
    return AgentRun(
        id=run_id,
        org_id="org_1",
        actor_user_id="user_1",
        source=source,
        goal=f"Goal for {run_id}",
        workspace_id="workspace_1",
        status=status,
        result=result,
        started_at="2026-06-18T00:00:00Z",
    )


def subagent(
    subagent_id: str,
    parent_run_id: str,
    child_run_id: str,
    status: AgentSubagentRunStatus,
    result_summary: AgentSubagentResultSummary | None = None,
) -> AgentSubagentRun:
    return AgentSubagentRun(
        id=subagent_id,
        org_id="org_1",
        parent_run_id=parent_run_id,
        child_run_id=child_run_id,
        name=f"Subagent {subagent_id}",
        task=f"Task {subagent_id}",
        spec_key="researcher",
        status=status,
        result_summary=result_summary,
        created_at="2026-06-18T00:00:00Z",
    )


def artifact(
    artifact_id: str,
    run_id: str,
    *,
    metadata: dict | None = None,
) -> AgentArtifact:
    return AgentArtifact(
        id=artifact_id,
        org_id="org_1",
        workspace_id="workspace_1",
        run_id=run_id,
        type="report",
        name=f"Artifact {artifact_id}",
        uri=f"/reports/{artifact_id}.md",
        metadata=metadata,
        created_at="2026-06-18T00:00:00Z",
    )


def event(
    event_id: str,
    run_id: str,
    event_type: str,
    payload: dict | None = None,
) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=event_id,
        run_id=run_id,
        sequence=1,
        timestamp="2026-06-18T00:00:00Z",
        type=event_type,
        source=AgentStreamSource(kind="test"),
        payload=payload or {},
    )


def sandbox_diagnostics(
    sandbox_run_id: str,
    status: str,
    *,
    persisted_count: int = 0,
    promoted_count: int = 0,
    persistence_error: dict | None = None,
) -> dict:
    return {
        "sandbox_run_id": sandbox_run_id,
        "status": status,
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
            "error_code": None,
            "timed_out": False,
        },
        "workspace_effects": {
            "declared_count": persisted_count + promoted_count,
            "persisted_count": persisted_count,
            "promoted_count": promoted_count,
            "paths": ["/reports/sandbox.md"] if persisted_count else [],
            "persistence_error": persistence_error,
        },
        "error_code": None,
        "timed_out": False,
    }


def test_run_tree_snapshot_projects_descendant_runs_and_delegations() -> None:
    root = run("run_root", AgentRunStatus.WAITING_SUBAGENT)
    child = run(
        "run_child",
        AgentRunStatus.COMPLETED,
        source=AgentRunSource.DELEGATED_TASK,
        result=AgentRunResult(content="Child done.", artifact_ids=["artifact_child"]),
    )
    grandchild = run(
        "run_grandchild",
        AgentRunStatus.FAILED,
        source=AgentRunSource.DELEGATED_TASK,
    )
    unrelated = run("run_other", AgentRunStatus.COMPLETED)

    snapshot = build_run_tree_snapshot(
        root_run=root,
        runs=[root, child, grandchild, unrelated],
        subagents=[
            subagent("subagent_1", "run_root", "run_child", AgentSubagentRunStatus.COMPLETED),
            subagent("subagent_2", "run_child", "run_grandchild", AgentSubagentRunStatus.FAILED),
        ],
        artifacts=[
            artifact("artifact_root", "run_root"),
            artifact("artifact_child", "run_child"),
            artifact("artifact_other", "run_other"),
        ],
    )

    payload = snapshot.model_dump(mode="json")

    assert payload["root_run_id"] == "run_root"
    assert [node["run_id"] for node in payload["nodes"]] == [
        "run_root",
        "run_child",
        "run_grandchild",
    ]
    assert [node["depth"] for node in payload["nodes"]] == [0, 1, 2]
    assert payload["nodes"][1]["parent_run_id"] == "run_root"
    assert payload["nodes"][1]["subagent_run_id"] == "subagent_1"
    assert payload["nodes"][1]["artifact_count"] == 1
    assert payload["nodes"][1]["result_artifact_ids"] == ["artifact_child"]
    assert payload["nodes"][2]["needs_attention"] is True
    assert [delegation["subagent_run_id"] for delegation in payload["delegations"]] == [
        "subagent_1",
        "subagent_2",
    ]
    assert payload["summary"] == {
        "root_run_id": "run_root",
        "total_runs": 3,
        "total_delegations": 2,
        "max_depth": 2,
        "active_runs": 1,
        "waiting_runs": 1,
        "failed_runs": 1,
        "completed_runs": 1,
        "artifact_count": 2,
        "attention_runs": 3,
        "degraded_runs": 0,
        "sandbox_attention_runs": 0,
        "sandbox_run_count": 0,
        "failed_sandbox_run_count": 0,
        "sandbox_workspace_file_count": 0,
        "sandbox_artifact_promotion_count": 0,
        "sandbox_persistence_error_count": 0,
        "sandbox_operator_action_count": 0,
        "root_needs_attention": True,
    }


def test_run_tree_snapshot_exposes_subagent_result_summary_on_delegations() -> None:
    root = run("run_root", AgentRunStatus.COMPLETED)
    child = run(
        "run_child",
        AgentRunStatus.COMPLETED,
        source=AgentRunSource.DELEGATED_TASK,
        result=AgentRunResult(content="Child done.", artifact_ids=["artifact_child"]),
    )
    summary = AgentSubagentResultSummary(
        content="Child done.",
        artifacts=[
            AgentArtifactSummary(
                id="artifact_child",
                type="report",
                name="Child Report",
                uri="/reports/child.md",
                summary="# Child Report",
            )
        ],
    )

    snapshot = build_run_tree_snapshot(
        root_run=root,
        runs=[root, child],
        subagents=[
            subagent(
                "subagent_1",
                "run_root",
                "run_child",
                AgentSubagentRunStatus.COMPLETED,
                result_summary=summary,
            ),
        ],
        artifacts=[artifact("artifact_child", "run_child")],
    )

    delegation = snapshot.model_dump(mode="json")["delegations"][0]

    assert delegation["result_summary"]["content"] == "Child done."
    assert delegation["result_summary"]["artifact_ids"] == ["artifact_child"]
    assert delegation["result_summary"]["artifact_count"] == 1


def test_run_tree_snapshot_rolls_descendant_attention_to_ancestors() -> None:
    root = run("run_root", AgentRunStatus.WAITING_SUBAGENT)
    child = run(
        "run_child",
        AgentRunStatus.WAITING_INPUT,
        source=AgentRunSource.DELEGATED_TASK,
    )
    grandchild = run(
        "run_grandchild",
        AgentRunStatus.FAILED,
        source=AgentRunSource.DELEGATED_TASK,
    )

    snapshot = build_run_tree_snapshot(
        root_run=root,
        runs=[root, child, grandchild],
        subagents=[
            subagent("subagent_1", "run_root", "run_child", AgentSubagentRunStatus.RUNNING),
            subagent("subagent_2", "run_child", "run_grandchild", AgentSubagentRunStatus.FAILED),
        ],
        artifacts=[],
    )

    nodes_by_id = {
        node["run_id"]: node
        for node in snapshot.model_dump(mode="json")["nodes"]
    }

    assert nodes_by_id["run_root"]["needs_attention"] is True
    assert nodes_by_id["run_root"]["attention_reasons"] == [
        "descendant_failed",
        "descendant_waiting_input",
    ]
    assert nodes_by_id["run_root"]["descendant_attention_count"] == 2
    assert nodes_by_id["run_root"]["descendant_failed_count"] == 1
    assert nodes_by_id["run_root"]["descendant_waiting_count"] == 1
    assert nodes_by_id["run_root"]["descendant_degraded_count"] == 0

    assert nodes_by_id["run_child"]["needs_attention"] is True
    assert nodes_by_id["run_child"]["attention_reasons"] == [
        "self_waiting_input",
        "descendant_failed",
    ]
    assert nodes_by_id["run_child"]["descendant_attention_count"] == 1
    assert nodes_by_id["run_grandchild"]["attention_reasons"] == ["self_failed"]

    summary = snapshot.model_dump(mode="json")["summary"]
    assert summary["attention_runs"] == 3
    assert summary["degraded_runs"] == 0
    assert summary["root_needs_attention"] is True


def test_run_tree_snapshot_marks_research_degraded_runs_for_attention() -> None:
    root = run("run_root", AgentRunStatus.WAITING_SUBAGENT)
    child = run(
        "run_child",
        AgentRunStatus.COMPLETED,
        source=AgentRunSource.DELEGATED_TASK,
    )

    snapshot = build_run_tree_snapshot(
        root_run=root,
        runs=[root, child],
        subagents=[
            subagent("subagent_1", "run_root", "run_child", AgentSubagentRunStatus.COMPLETED),
        ],
        artifacts=[
            artifact(
                "artifact_child",
                "run_child",
                metadata={
                    "generated_by": "research.create_report",
                    "report_status": "partial",
                    "source_count": 1,
                    "evidence_count": 1,
                    "limitation_count": 1,
                },
            )
        ],
        events_by_run={
            "run_child": [
                event(
                    "event_1",
                    "run_child",
                    "web.fetch.failed",
                    {
                        "tool_call_id": "tool_1",
                        "url": "https://example.test",
                        "error": {"type": "timeout"},
                    },
                )
            ]
        },
    )

    nodes_by_id = {
        node["run_id"]: node
        for node in snapshot.model_dump(mode="json")["nodes"]
    }

    assert nodes_by_id["run_child"]["research_status"] == "partial"
    assert nodes_by_id["run_child"]["research_degraded"] is True
    assert nodes_by_id["run_child"]["attention_reasons"] == ["self_degraded"]
    assert nodes_by_id["run_root"]["attention_reasons"] == ["descendant_degraded"]
    assert nodes_by_id["run_root"]["descendant_degraded_count"] == 1

    summary = snapshot.model_dump(mode="json")["summary"]
    assert summary["attention_runs"] == 2
    assert summary["degraded_runs"] == 1
    assert summary["root_needs_attention"] is True


def test_run_tree_snapshot_rolls_sandbox_attention_to_ancestors() -> None:
    root = run("run_root", AgentRunStatus.WAITING_SUBAGENT)
    child = run(
        "run_child",
        AgentRunStatus.COMPLETED,
        source=AgentRunSource.DELEGATED_TASK,
    )

    snapshot = build_run_tree_snapshot(
        root_run=root,
        runs=[root, child],
        subagents=[
            subagent("subagent_1", "run_root", "run_child", AgentSubagentRunStatus.COMPLETED),
        ],
        artifacts=[],
        events_by_run={
            "run_child": [
                event(
                    "event_sandbox_completed",
                    "run_child",
                    "sandbox.completed",
                    {
                        "sandbox_run_id": "sandbox_1",
                        "status": "completed",
                        "diagnostics": sandbox_diagnostics(
                            "sandbox_1",
                            "completed",
                            persisted_count=1,
                            promoted_count=1,
                        ),
                    },
                ),
                event(
                    "event_sandbox_failed",
                    "run_child",
                    "sandbox.failed",
                    {
                        "sandbox_run_id": "sandbox_2",
                        "status": "failed",
                        "error": {"message": "Path is outside allowed workspace paths"},
                        "diagnostics": sandbox_diagnostics(
                            "sandbox_2",
                            "failed",
                            persistence_error={
                                "message": "Path is outside allowed workspace paths"
                            },
                        ),
                    },
                ),
            ]
        },
    )

    payload = snapshot.model_dump(mode="json")
    nodes_by_id = {node["run_id"]: node for node in payload["nodes"]}

    assert nodes_by_id["run_child"]["sandbox_run_count"] == 2
    assert nodes_by_id["run_child"]["failed_sandbox_run_count"] == 1
    assert nodes_by_id["run_child"]["sandbox_workspace_file_count"] == 1
    assert nodes_by_id["run_child"]["sandbox_artifact_promotion_count"] == 1
    assert nodes_by_id["run_child"]["sandbox_persistence_error_count"] == 1
    assert nodes_by_id["run_child"]["sandbox_operator_action_count"] == 5
    assert nodes_by_id["run_child"]["attention_reasons"] == [
        "self_sandbox_failed",
        "self_sandbox_workspace_side_effect",
        "self_sandbox_artifact_promotion",
        "self_sandbox_persistence_error",
    ]

    assert nodes_by_id["run_root"]["attention_reasons"] == [
        "descendant_sandbox_failed",
        "descendant_sandbox_workspace_side_effect",
        "descendant_sandbox_artifact_promotion",
        "descendant_sandbox_persistence_error",
    ]
    assert nodes_by_id["run_root"]["descendant_failed_sandbox_run_count"] == 1
    assert nodes_by_id["run_root"]["descendant_sandbox_workspace_file_count"] == 1
    assert nodes_by_id["run_root"]["descendant_sandbox_artifact_promotion_count"] == 1
    assert nodes_by_id["run_root"]["descendant_sandbox_persistence_error_count"] == 1
    assert nodes_by_id["run_root"]["descendant_sandbox_operator_action_count"] == 5

    summary = payload["summary"]
    assert summary["attention_runs"] == 2
    assert summary["sandbox_attention_runs"] == 1
    assert summary["sandbox_run_count"] == 2
    assert summary["failed_sandbox_run_count"] == 1
    assert summary["sandbox_workspace_file_count"] == 1
    assert summary["sandbox_artifact_promotion_count"] == 1
    assert summary["sandbox_persistence_error_count"] == 1
    assert summary["sandbox_operator_action_count"] == 5
