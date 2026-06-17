"""System prompt assembly for the native Pydantic AI agent."""

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import AgentMemoryEntry, AgentMessage, AgentWorkspaceFile


MAX_WORKSPACE_FILES_IN_PROMPT = 50
MAX_THREAD_MESSAGES_IN_PROMPT = 20
MAX_THREAD_MESSAGE_CHARS = 1_000


class InstructionBuilder:
    """Build system instructions from run config, skill policy, and store context."""

    def __init__(self, base_instructions: str) -> None:
        self._base = base_instructions

    async def build(self, deps: PydanticAgentDeps) -> str:
        """Build a full system prompt from store-backed run context."""
        sections = [self._base]

        if deps.run.harness_options and deps.run.harness_options.instructions:
            sections.append(f"Run instructions:\n{deps.run.harness_options.instructions}")

        if deps.skill:
            sections.append(f"Skill instructions:\n{deps.skill.instructions}")

        thread_messages = await self._thread_messages_for_run(deps)
        if thread_messages:
            lines = [
                f"- {message.role}: {_truncate_message(message.content)}"
                for message in thread_messages
            ]
            sections.append("Thread messages:\n" + "\n".join(lines))

        workspace_files = await self._workspace_files_for_run(deps)
        if workspace_files:
            lines = [
                f"- {file.path} ({file.media_type or 'unknown'}, {file.size} bytes)"
                for file in workspace_files
            ]
            sections.append("Workspace files:\n" + "\n".join(lines))

        memory_entries = await self._memory_entries_for_run(deps)
        if memory_entries:
            lines = [
                f"- {entry.scope}:{entry.key} = {entry.value}"
                for entry in memory_entries
            ]
            sections.append("Memory:\n" + "\n".join(lines))

        return "\n\n".join(sections)

    async def _thread_messages_for_run(self, deps: PydanticAgentDeps) -> list[AgentMessage]:
        if not deps.run.thread_id:
            return []
        messages = await deps.store.list_messages(deps.run.thread_id)
        return messages[-MAX_THREAD_MESSAGES_IN_PROMPT:]

    async def _workspace_files_for_run(self, deps: PydanticAgentDeps) -> list[AgentWorkspaceFile]:
        skill = deps.skill
        if skill and skill.workspace_policy and not skill.workspace_policy.read:
            return []
        files = await deps.store.list_workspace_files(deps.run.workspace_id)
        if skill and skill.workspace_policy and skill.workspace_policy.allowed_paths:
            files = [
                file
                for file in files
                if _workspace_path_allowed(file.path, skill.workspace_policy.allowed_paths)
            ]
        return files[:MAX_WORKSPACE_FILES_IN_PROMPT]

    async def _memory_entries_for_run(self, deps: PydanticAgentDeps) -> list[AgentMemoryEntry]:
        skill = deps.skill
        if not skill or not skill.memory_policy or not skill.memory_policy.read:
            return []
        entries: list[AgentMemoryEntry] = []
        seen: set[str] = set()
        for scope in skill.memory_policy.scopes or ["user", "thread", "workspace", "organization", "skill"]:
            scope_id = _memory_scope_id(scope, deps)
            scoped_entries = await deps.store.list_memory_entries(
                org_id=deps.run.org_id,
                scope=scope,
                scope_id=scope_id,
            )
            for entry in scoped_entries:
                if entry.id in seen:
                    continue
                seen.add(entry.id)
                entries.append(entry)
        return entries


def _workspace_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    return any(path == allowed or path.startswith(allowed.rstrip("/") + "/") for allowed in allowed_paths)


def _truncate_message(content: str) -> str:
    if len(content) <= MAX_THREAD_MESSAGE_CHARS:
        return content
    return content[:MAX_THREAD_MESSAGE_CHARS] + "..."


def _memory_scope_id(scope: str, deps: PydanticAgentDeps) -> str | None:
    match scope:
        case "thread":
            return deps.run.thread_id or deps.run.id
        case "workspace":
            return deps.run.workspace_id
        case "user":
            return deps.run.actor_user_id
        case "organization":
            return deps.run.org_id
        case "skill":
            return deps.run.skill_id
        case _:
            return None
