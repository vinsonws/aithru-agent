from aithru_agent.domain import (
    AgentRun,
    AgentSubagentResultSummary,
    AgentWorkspaceFile,
)


SUBAGENT_RESULT_CONTENT_MAX_CHARS = 4_000

def build_subagent_result_summary(
    child: AgentRun,
    child_workspace_files: list[AgentWorkspaceFile],
) -> AgentSubagentResultSummary:
    content, content_truncated = _bounded_content(
        child.result.content if child.result and child.result.content else None
    )
    return AgentSubagentResultSummary(
        content=content,
        content_truncated=content_truncated,
        workspace_paths=list(child.result.workspace_paths) if child.result else [],
        workspace_files=child_workspace_files,
        message_id=child.result.message_id if child.result else None,
        thread_message_id=child.result.thread_message_id if child.result else None,
    )


def _bounded_content(value: str | None) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if len(value) <= SUBAGENT_RESULT_CONTENT_MAX_CHARS:
        return value, False
    return value[:SUBAGENT_RESULT_CONTENT_MAX_CHARS], True

