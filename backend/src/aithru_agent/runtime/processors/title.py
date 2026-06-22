from __future__ import annotations

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)

TITLE_STRIP_CHARS = ".,:;!?()[]{}"
DEFAULT_THREAD_TITLE = "New Agent Thread"
TRAILING_TITLE_CONNECTORS = {
    "A",
    "An",
    "And",
    "As",
    "At",
    "By",
    "For",
    "From",
    "In",
    "Of",
    "On",
    "Or",
    "The",
    "To",
}


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

        title = _title_from_goal(context.run.goal, max_words=self.max_words)
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


def _title_from_goal(goal: str, *, max_words: int) -> str:
    words = [
        stripped.capitalize()
        for word in goal.split()
        if (stripped := word.strip(TITLE_STRIP_CHARS))
    ]
    if not words:
        return DEFAULT_THREAD_TITLE
    title_words = words[:max_words]
    while title_words and title_words[-1] in TRAILING_TITLE_CONNECTORS:
        title_words = title_words[:-1]
    return " ".join(title_words) or DEFAULT_THREAD_TITLE
