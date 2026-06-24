from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

from aithru_agent.domain import AgentMessage, AgentRun, AgentRunStatus

from .base import (
    AgentRuntimeProcessor,
    AgentRuntimeProcessorContext,
    AgentRuntimeProcessorDecision,
)

TITLE_STRIP_CHARS = " \t\r\n\"'`.,:;!?()[]{}，。！？；：（）【】《》"
DEFAULT_THREAD_TITLE = "New Agent Thread"
TITLE_PROMPT_MAX_CHARS = 500
TITLE_FALLBACK_MAX_CHARS = 60


class TitleProvider(Protocol):
    async def generate_title(
        self,
        *,
        run: AgentRun,
        user_message: str,
        assistant_message: str,
        max_words: int,
    ) -> str:
        ...


class PydanticAITitleProvider:
    def __init__(self, *, model_resolver: Callable[[AgentRun], str | object | None]) -> None:
        self._model_resolver = model_resolver

    async def generate_title(
        self,
        *,
        run: AgentRun,
        user_message: str,
        assistant_message: str,
        max_words: int,
    ) -> str:
        from pydantic_ai import Agent

        model = self._model_resolver(run)
        if model is None:
            return ""
        agent = Agent(
            model,
            instructions=(
                "Generate a concise conversation title. Return only the title, "
                "with no quotes and no explanation."
            ),
            output_type=str,
        )
        prompt = (
            f"Generate a concise title (max {max_words} words) for this conversation.\n"
            f"User: {_trim_for_prompt(user_message)}\n"
            f"Assistant: {_trim_for_prompt(_strip_thinking(assistant_message))}\n\n"
            "Return ONLY the title, no quotes, no explanation."
        )
        result = await agent.run(
            prompt,
            model_settings={
                "temperature": 0,
                "max_tokens": 64,
            },
        )
        output = getattr(result, "output", None)
        if output is None:
            output = getattr(result, "data", "")
        return str(output)


class ThreadTitleProcessor(AgentRuntimeProcessor):
    name: str = "thread_title"

    def __init__(
        self,
        *,
        max_words: int = 6,
        provider: TitleProvider | None = None,
    ) -> None:
        self.max_words = max_words
        self._provider = provider

    async def after_terminal(
        self,
        context: AgentRuntimeProcessorContext,
    ) -> AgentRuntimeProcessorDecision:
        if context.terminal_status != AgentRunStatus.COMPLETED:
            return AgentRuntimeProcessorDecision()
        if context.run.thread_id is None:
            return AgentRuntimeProcessorDecision()

        thread = await context.store.get_thread(context.run.thread_id)
        if thread is None:
            return AgentRuntimeProcessorDecision()
        if thread.title is not None and thread.title.strip():
            return AgentRuntimeProcessorDecision()

        exchange = await _first_complete_exchange(context, thread_id=thread.id)
        if exchange is None:
            return AgentRuntimeProcessorDecision()

        user_message, assistant_message = exchange
        title = await self._title_from_exchange(
            run=context.run,
            user_message=user_message,
            assistant_message=assistant_message,
        )
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

    async def _title_from_exchange(
        self,
        *,
        run: AgentRun,
        user_message: str,
        assistant_message: str,
    ) -> str:
        if self._provider is not None:
            try:
                generated = await self._provider.generate_title(
                    run=run,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    max_words=self.max_words,
                )
            except Exception:
                generated = ""
            title = _clean_generated_title(generated, max_words=self.max_words)
            if title is not None:
                return title
        return _fallback_title(user_message, max_words=self.max_words) or DEFAULT_THREAD_TITLE


async def _first_complete_exchange(
    context: AgentRuntimeProcessorContext,
    *,
    thread_id: str,
) -> tuple[str, str] | None:
    messages = await context.store.list_messages(thread_id)
    user_message: AgentMessage | None = None
    for message in messages:
        if message.role == "user" and message.content.strip():
            user_message = message
            continue
        if (
            message.role == "assistant"
            and message.content.strip()
        ):
            user_content = (
                user_message.content
                if user_message is not None
                else context.run.task_msg
            )
            if user_content.strip():
                return user_content, message.content
    return None


def _clean_generated_title(value: str, *, max_words: int) -> str | None:
    stripped = _strip_thinking(value)
    first_line = next((line.strip() for line in stripped.splitlines() if line.strip()), "")
    normalized = _collapse_spaces(first_line).strip(TITLE_STRIP_CHARS)
    if not normalized:
        return None
    return _limit_words(normalized, max_words=max_words)


def _fallback_title(value: str, *, max_words: int) -> str | None:
    normalized = _collapse_spaces(value).strip(TITLE_STRIP_CHARS)
    if not normalized:
        return None
    limited = _limit_words(normalized, max_words=max_words)
    if len(limited) <= TITLE_FALLBACK_MAX_CHARS:
        return limited
    return limited[:TITLE_FALLBACK_MAX_CHARS].rstrip(TITLE_STRIP_CHARS) or None


def _limit_words(value: str, *, max_words: int) -> str:
    words = value.split()
    if len(words) <= max_words:
        return value
    return " ".join(words[:max_words]).strip(TITLE_STRIP_CHARS)


def _trim_for_prompt(value: str) -> str:
    normalized = _collapse_spaces(value)
    if len(normalized) <= TITLE_PROMPT_MAX_CHARS:
        return normalized
    return normalized[:TITLE_PROMPT_MAX_CHARS].rstrip() + "..."


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strip_thinking(value: str) -> str:
    without_xml = re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL | re.IGNORECASE)
    without_fenced = re.sub(
        r"```(?:thinking|reasoning)\b.*?```",
        "",
        without_xml,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return without_fenced.strip()
