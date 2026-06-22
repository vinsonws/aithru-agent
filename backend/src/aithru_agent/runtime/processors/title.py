from __future__ import annotations

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)

TITLE_STRIP_CHARS = ".,:;!?()[]{}"
DEFAULT_THREAD_TITLE = "New Agent Thread"


class ThreadTitleProcessor(AgentRuntimeProcessor):
    name: str = "thread_title"

    def __init__(self, *, max_words: int = 6) -> None:
        self.max_words = max_words

    async def before_model(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()

        thread = await context.store.get_thread(context.run.thread_id)
        if thread is None:
            return AgentRuntimeProcessorDecision()
        if thread.title is not None and thread.title.strip():
            return AgentRuntimeProcessorDecision()

        title = await _title_from_context(context, max_words=self.max_words)
        await context.store.update_thread(thread.id, title=title)
        await context.event_writer.write(
            run_id=context.run.id,
            thread_id=thread.id,
            type="thread.title.generated",
            source={"kind": "harness"},
            visibility="debug",
            payload={
                "thread_id": thread.id,
                "title": title,
            },
        )
        return AgentRuntimeProcessorDecision()


async def _title_from_context(
    context: AgentRuntimeProcessorContext,
    *,
    max_words: int,
) -> str:
    input_content = await _latest_input_content(context)
    if input_content is not None:
        input_title = _format_title(input_content, max_words=max_words)
        if input_title is not None:
            return input_title
    return _format_title(context.run.goal, max_words=max_words) or DEFAULT_THREAD_TITLE


async def _latest_input_content(context: AgentRuntimeProcessorContext) -> str | None:
    if context.event_store is None:
        return None
    events = await context.event_store.list_by_run(context.run.id)
    for event in reversed(events):
        if event.type != "input.received":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            continue
        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def _format_title(value: str, *, max_words: int) -> str | None:
    words = [
        stripped.capitalize()
        for word in value.split()
        if (stripped := word.strip(TITLE_STRIP_CHARS))
    ]
    if not words:
        return None
    return " ".join(words[:max_words]) or DEFAULT_THREAD_TITLE
