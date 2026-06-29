"""System prompt assembly for the native Pydantic AI agent."""

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.domain import (
    AgentMemoryEntry,
    AgentMemoryRecallItem,
    AgentMessage,
    AgentRunHarnessOptions,
    AgentRunContextBudgetUsage,
    AgentRunContextPacket,
    AgentRunContextToolResult,
    AgentWorkspaceFile,
)


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

        # Add clarification guidance
        sections.append(_CLARIFICATION_GUIDANCE)

        sections.append(_WORKSPACE_FILE_PRESENTATION_GUIDANCE)

        if deps.run.harness_options and deps.run.harness_options.instructions:
            sections.append(f"Run instructions:\n{deps.run.harness_options.instructions}")

        if deps.skill:
            sections.append(f"Skill instructions:\n{deps.skill.instructions}")

        if deps.context_packet and deps.context_packet.has_context:
            sections.append(_render_context_packet(deps.context_packet))

        thread_messages = await self._thread_messages_for_run(deps)
        if thread_messages:
            lines = [
                f"- {message.role}: {_truncate_message(message.content)}"
                for message in thread_messages
            ]
            sections.append("Thread messages:\n" + "\n".join(lines))
            image_lines = _image_attachment_lines(
                thread_messages,
                vision_enabled=_vision_enabled(deps.run.harness_options),
            )
            if image_lines:
                sections.append("Attached images:\n" + "\n".join(image_lines))

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


def _image_attachment_lines(
    messages: list[AgentMessage],
    *,
    vision_enabled: bool,
) -> list[str]:
    lines: list[str] = []
    for message in messages:
        for attachment in message.attachments:
            hash_suffix = f" content_hash={attachment.content_hash}" if attachment.content_hash else ""
            lines.append(
                f"- {message.role}: {attachment.path} "
                f"({attachment.workspace_id}, {attachment.media_type}, {attachment.size} bytes)"
                f"{hash_suffix}"
            )
    if not lines:
        return []
    if vision_enabled:
        lines.append("Model vision is enabled for this run; attached workspace images are directly viewable.")
    else:
        lines.append("Model vision is not enabled for this run; use workspace.view_image when available.")
    return lines


def _vision_enabled(options: AgentRunHarnessOptions | None) -> bool:
    return bool(options and options.model_capabilities and options.model_capabilities.vision)


def _render_context_packet(packet: AgentRunContextPacket) -> str:
    lines = [
        "Run context packet:",
        f"Status: {packet.status.value}",
    ]
    if packet.resume:
        lines.append(f"Resume: {packet.resume.reason} - {packet.resume.detail}")
    if packet.budget:
        lines.append(_budget_line(packet.budget))
    if packet.compressed_context:
        lines.append("Compressed context:")
        lines.append(
            f"- {_display_truncated(packet.compressed_context.summary, packet.compressed_context.truncated)}"
        )
    if packet.thread_messages:
        lines.append("Recent thread messages:")
        lines.extend(
            f"- {message.role}: {_display_truncated(message.content, message.truncated)}"
            for message in packet.thread_messages
        )
    if packet.todos:
        lines.append("Run todos:")
        lines.extend(
            f"- [{todo.status.value}] {todo.title}{_description_suffix(todo.description)}"
            for todo in packet.todos
        )
    if packet.research:
        lines.append("Research continuation:")
        lines.extend(_research_lines(packet.research))
    if packet.workspace_files:
        lines.append("Workspace files:")
        lines.extend(
            _workspace_file_line(file)
            for file in packet.workspace_files
        )
    if packet.tool_results:
        lines.append("Recent tool results:")
        lines.extend(
            _tool_result_line(result)
            for result in packet.tool_results
        )
    if packet.memory and packet.memory.items:
        lines.append("Relevant memory:")
        lines.extend(_memory_line(item) for item in packet.memory.items)
    if packet.presentations:
        lines.append("Presented to user:")
        lines.extend(
            f"- {presentation.id}: {presentation.title} "
            f"(status={presentation.status}, "
            f"resource={presentation.resource_kind}"
            f"{_resource_reference_suffix(presentation.resource_id, presentation.resource_path)}, "
            f"surfaces={','.join(presentation.surfaces)}, "
            f"preferred_view={presentation.preferred_view}, "
            f"available_views={','.join(presentation.available_views)})"
            for presentation in packet.presentations
        )
    return "\n".join(lines)


def _tool_result_line(result: AgentRunContextToolResult) -> str:
    label = result.status
    if result.source_type == "external_run":
        external_label = "external"
        if result.capability_run_id:
            external_label = f"{external_label} {result.capability_run_id}"
        label = f"{label} {external_label}"
    return f"- {result.tool_name} [{label}]: {_display_truncated(result.summary, result.truncated)}"


def _budget_line(budget: AgentRunContextBudgetUsage) -> str:
    return (
        f"Context budget: {budget.used_chars}/{budget.max_chars} chars used, "
        f"{budget.remaining_chars} remaining; dropped details: "
        f"{_count_label(budget.dropped_thread_messages, 'message', 'messages')}, "
        f"{_count_label(budget.dropped_todos, 'todo', 'todos')}, "
        f"{_count_label(budget.dropped_workspace_files, 'workspace file', 'workspace files')}, "
        f"{_count_label(budget.dropped_tool_results, 'tool result', 'tool results')}, "
        f"{_count_label(budget.dropped_memory, 'memory entry', 'memory entries')}; "
        f"truncated items: {budget.truncated_items}"
    )


def _display_truncated(value: str, truncated: bool) -> str:
    return value + ("..." if truncated else "")


def _description_suffix(description: str | None) -> str:
    if not description:
        return ""
    return f" - {description}"


def _workspace_file_line(file: object) -> str:
    details = []
    media_type = getattr(file, "media_type", None)
    size = getattr(file, "size", None)
    if media_type:
        details.append(str(media_type))
    if isinstance(size, int):
        details.append(f"{size} bytes")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"- {getattr(file, 'path', 'workspace file')}{suffix}"


def _memory_line(item: AgentMemoryRecallItem) -> str:
    scope = f"{item.scope}:{item.key}"
    reason = f" ({item.reason})" if item.reason else ""
    return f"- {scope} = {_display_truncated(item.value, item.truncated)}{reason}"


def _research_lines(research: object) -> list[str]:
    query = getattr(research, "query", None) or "unknown"
    report_status = getattr(research, "report_status", None) or "none"
    lines = [
        f"- Status: {getattr(research, 'status', 'none')}; report status: {report_status}; query: {query}"
    ]
    source_run_id = getattr(research, "source_run_id", None)
    if source_run_id:
        lines.append(f"- Source run: {source_run_id}")
    target_section_ids = getattr(research, "target_section_ids", [])
    if target_section_ids:
        lines.append("- Target sections: " + ", ".join(str(section_id) for section_id in target_section_ids))
    completed_steps = getattr(research, "completed_steps", [])
    pending_steps = getattr(research, "pending_steps", [])
    blocked_steps = getattr(research, "blocked_steps", [])
    if completed_steps:
        lines.append("- Completed steps: " + ", ".join(completed_steps))
    if pending_steps:
        lines.append("- Pending steps: " + ", ".join(pending_steps))
    if blocked_steps:
        lines.append("- Blocked steps: " + ", ".join(blocked_steps))
    report_file_line = _research_report_file_line(
        getattr(research, "report_workspace_paths", []),
    )
    if report_file_line:
        lines.append(report_file_line)
    sections = getattr(research, "sections", [])
    if sections:
        lines.append("Research sections:")
        lines.extend(_research_section_line(section) for section in sections)
    for item in getattr(research, "evidence", []):
        lines.append(_research_evidence_line(item))
    for limitation in getattr(research, "limitations", []):
        lines.append(_research_limitation_line(limitation))
    for action in getattr(research, "next_actions", []):
        lines.append(f"- Next action: {action}")
    for action_hint in getattr(research, "action_hints", []):
        lines.append(_research_action_hint_line(action_hint))
    dropped = getattr(research, "dropped_evidence", 0)
    if dropped:
        lines.append(f"- Dropped evidence rows: {dropped}")
    return lines


def _research_report_file_line(paths: list[str]) -> str | None:
    if not paths:
        return None
    return "- Report files: " + ", ".join(paths)


def _research_section_line(section: object) -> str:
    section_id = getattr(section, "section_id", "section")
    status = "covered" if getattr(section, "covered", False) else "missing"
    priority = getattr(section, "priority", "medium")
    title = getattr(section, "title", section_id)
    question = getattr(section, "question", None)
    question_suffix = f" - {_display_truncated(question, bool(getattr(section, 'truncated', False)))}" if question else ""
    source_count = getattr(section, "source_count", 0)
    evidence_count = getattr(section, "evidence_count", 0)
    return (
        f"- Section {section_id} [{status}, {priority}]: {title}{question_suffix} "
        f"sources={source_count}; evidence={evidence_count}"
    )


def _research_evidence_line(item: object) -> str:
    citation_number = getattr(item, "citation_number", "?")
    title = getattr(item, "title", "source")
    url = getattr(item, "url", "")
    quality = getattr(item, "quality_label", None) or "unknown"
    evidence_text = _research_evidence_text(item)
    location = f", {url}" if url else ""
    section = getattr(item, "section_id", None)
    section_prefix = f" section={section};" if section else ""
    return (
        f"- Evidence [{citation_number}]{section_prefix} {title} ({quality}{location}): "
        f"{_display_truncated(evidence_text, bool(getattr(item, 'truncated', False)))}"
    )


def _research_evidence_text(item: object) -> str:
    parts = [
        value
        for value in [getattr(item, "snippet", None), getattr(item, "excerpt", None)]
        if isinstance(value, str) and value
    ]
    return " ".join(dict.fromkeys(parts)) or "No evidence text provided."


def _research_limitation_line(limitation: object) -> str:
    severity = getattr(limitation, "severity", "warning")
    code = getattr(limitation, "code", "research_limitation")
    message = getattr(limitation, "message", "Research limitation.")
    source_url = getattr(limitation, "source_url", None)
    suffix = f" ({source_url})" if source_url else ""
    return f"- Limitation {severity} {code}: {message}{suffix}"


def _research_action_hint_line(action_hint: object) -> str:
    priority = getattr(action_hint, "priority", "medium")
    kind = getattr(action_hint, "kind", "action")
    title = getattr(action_hint, "title", "Continue research")
    reason = getattr(action_hint, "reason", "Continue from current research context.")
    suffixes = []
    target_section_ids = getattr(action_hint, "target_section_ids", [])
    if target_section_ids:
        suffixes.append("sections: " + ", ".join(str(section_id) for section_id in target_section_ids))
    suggested_tools = getattr(action_hint, "suggested_tool_names", [])
    if suggested_tools:
        suffixes.append("Tools: " + ", ".join(suggested_tools))
    suggested_phases = getattr(action_hint, "suggested_research_phases", [])
    if suggested_phases:
        suffixes.append("phases: " + ", ".join(str(phase) for phase in suggested_phases))
    suffix = "; ".join(suffixes)
    if suffix:
        suffix = " " + suffix
    punctuation = "" if str(reason).endswith((".", "!", "?")) else "."
    return f"- Action hint [{priority}] {kind}: {title} - {reason}{punctuation}{suffix}"


def _resource_reference_suffix(resource_id: str | None, resource_path: str | None) -> str:
    if resource_id:
        return f" {resource_id}"
    if resource_path:
        return f" {resource_path}"
    return ""


def _count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


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


_WORKSPACE_FILE_PRESENTATION_GUIDANCE = """## Workspace File Presentation Guidance

Workspace files are platform resources rendered by Aithru as presentation entries or in the Files panel.
Do not invent legacy resource URLs.
When a workspace file is created, refer to it by path and let Aithru Presentation handle preview and download actions.
Use `presentation.present` when you need to request a specific safe view such as html_preview, source_text, markdown, image, pdf, or download.
If you need to mention where the user can open a file, say it is available in the presentation entries or the Files panel."""


_CLARIFICATION_GUIDANCE = """## When to Ask for Clarification

You have access to the `ask_clarification` tool. Use it before taking tool actions when:
- The user's task is too vague to proceed safely
- You need to choose between different approaches — provide `options` (2-5 choices)
- A requested action has important implications that need user confirmation

When providing options, keep them concise. When there are no clear discrete options, ask a focused open-ended question without providing options.

Do NOT use `ask_clarification` for:
- Simple informational questions you can answer directly
- Tasks where the task is clear enough to start working
- Situations where you already have enough context from the workspace or memory"""
