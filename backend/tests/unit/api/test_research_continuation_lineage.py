from aithru_agent.api.snapshots import build_research_continuation_lineage_snapshot
from aithru_agent.domain import AgentRun, AgentRunStatus
from aithru_agent.stream.events import AgentStreamEvent


def run(run_id: str, *, task_msg: str = "Research.") -> AgentRun:
    return AgentRun(
        id=run_id,
        org_id="org_1",
        actor_user_id="user_1",
        source="api",
        skill_id="deep-research",
        thread_id="thread_1",
        task_msg=task_msg,
        workspace_id="workspace_1",
        status=AgentRunStatus.QUEUED,
        started_at="2026-06-19T00:00:00Z",
    )


def event(run_id: str, sequence: int, event_type: str, payload: dict) -> AgentStreamEvent:
    return AgentStreamEvent(
        id=f"event_{run_id}_{sequence}",
        run_id=run_id,
        sequence=sequence,
        timestamp="2026-06-19T00:00:00Z",
        type=event_type,
        source={"kind": "test"},
        payload=payload,
    )


def test_research_continuation_lineage_projects_source_and_child_links() -> None:
    source = run("run_source", task_msg="Original research.")
    child = run("run_child", task_msg="Continue research.")
    continuation = {
        "source_run_id": source.id,
        "child_run_id": child.id,
        "action_ids": ["retry_search", "regenerate_report"],
        "continuation_status": "needs_research",
        "query": "aithru continuation",
    }
    source_snapshot = build_research_continuation_lineage_snapshot(
        run=source,
        events=[
            event(
                source.id,
                4,
                "research.continuation.created",
                continuation,
            )
        ],
        runs_by_id={source.id: source, child.id: child},
    ).model_dump(mode="json")
    child_snapshot = build_research_continuation_lineage_snapshot(
        run=child,
        events=[
            event(
                child.id,
                1,
                "run.created",
                {
                    "status": "queued",
                    "workspace_id": child.workspace_id,
                    "continuation": continuation,
                },
            )
        ],
        runs_by_id={source.id: source, child.id: child},
    ).model_dump(mode="json")

    assert source_snapshot == {
        "run_id": source.id,
        "source": None,
        "children": [
            {
                "source_run_id": source.id,
                "child_run_id": child.id,
                "action_ids": ["retry_search", "regenerate_report"],
                "continuation_status": "needs_research",
                "query": "aithru continuation",
                "source_event_sequence": 4,
                "child_run_status": "queued",
                "child_run_task_msg": "Continue research.",
            }
        ],
        "counts": {
            "source_count": 0,
            "child_count": 1,
        },
    }
    assert child_snapshot == {
        "run_id": child.id,
        "source": {
            "source_run_id": source.id,
            "child_run_id": child.id,
            "action_ids": ["retry_search", "regenerate_report"],
            "continuation_status": "needs_research",
            "query": "aithru continuation",
            "source_event_sequence": 1,
            "source_run_status": "queued",
            "source_run_task_msg": "Original research.",
        },
        "children": [],
        "counts": {
            "source_count": 1,
            "child_count": 0,
        },
    }
