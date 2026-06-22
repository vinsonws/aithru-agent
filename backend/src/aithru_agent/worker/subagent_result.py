import json

from aithru_agent.domain import (
    AgentArtifact,
    AgentArtifactSummary,
    AgentRun,
    AgentSubagentResultSummary,
)


SUBAGENT_RESULT_CONTENT_MAX_CHARS = 4_000
ARTIFACT_SUMMARY_MAX_CHARS = 1_000


def build_subagent_result_summary(
    child: AgentRun,
    child_artifacts: list[AgentArtifact],
) -> AgentSubagentResultSummary:
    content, content_truncated = _bounded_content(
        child.result.content if child.result and child.result.content else None
    )
    return AgentSubagentResultSummary(
        content=content,
        content_truncated=content_truncated,
        artifact_ids=list(child.result.artifact_ids) if child.result else [],
        artifacts=child_artifact_summaries(child, child_artifacts),
        message_id=child.result.message_id if child.result else None,
        thread_message_id=child.result.thread_message_id if child.result else None,
    )


def child_artifact_summaries(
    child: AgentRun,
    child_artifacts: list[AgentArtifact],
) -> list[AgentArtifactSummary]:
    artifact_ids = set(child.result.artifact_ids) if child.result else set()
    matched = [
        artifact
        for artifact in child_artifacts
        if artifact.run_id == child.id and (not artifact_ids or artifact.id in artifact_ids)
    ]
    return [_artifact_summary(artifact) for artifact in matched]


def _bounded_content(value: str | None) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if len(value) <= SUBAGENT_RESULT_CONTENT_MAX_CHARS:
        return value, False
    return value[:SUBAGENT_RESULT_CONTENT_MAX_CHARS], True


def _artifact_summary(artifact: AgentArtifact) -> AgentArtifactSummary:
    value = _artifact_summary_value(artifact)
    truncated = False
    if value is not None and len(value) > ARTIFACT_SUMMARY_MAX_CHARS:
        value = value[:ARTIFACT_SUMMARY_MAX_CHARS]
        truncated = True
    return AgentArtifactSummary(
        id=artifact.id,
        type=artifact.type,
        name=artifact.name,
        uri=artifact.uri,
        media_type=artifact.media_type,
        summary=value,
        truncated=truncated,
    )


def _artifact_summary_value(artifact: AgentArtifact) -> str | None:
    if isinstance(artifact.content, str):
        return artifact.content
    if isinstance(artifact.content, bytes):
        return artifact.content.decode("utf-8", errors="replace")
    if isinstance(artifact.content, dict):
        for key in ("summary", "title", "path"):
            value = artifact.content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(artifact.content, sort_keys=True)
    if artifact.metadata:
        for key in ("summary", "report_status", "quality_label"):
            value = artifact.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
