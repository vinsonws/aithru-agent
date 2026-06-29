import json

from .events import AgentStreamEvent


def format_sse_event(event: AgentStreamEvent) -> str:
    data = event.model_dump(mode="json")
    return f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def format_sse_comment(comment: str) -> str:
    safe_comment = comment.replace("\r", " ").replace("\n", " ")
    return f": {safe_comment}\n\n"
