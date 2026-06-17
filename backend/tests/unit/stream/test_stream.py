import json

import pytest

from aithru_agent.stream import (
    AgentEventWriter,
    AgentStreamEvent,
    InMemoryAgentEventStore,
    format_sse_event,
)


@pytest.mark.asyncio
async def test_writer_assigns_sequences_and_store_replays_by_run() -> None:
    store = InMemoryAgentEventStore()
    writer = AgentEventWriter(store)

    first = await writer.write(
        run_id="run_1",
        thread_id="thread_1",
        type="run.created",
        source={"kind": "harness"},
        payload={"status": "queued"},
    )
    second = await writer.write(
        run_id="run_1",
        thread_id="thread_1",
        type="run.started",
        source={"kind": "harness"},
        payload={"status": "running"},
    )
    other = await writer.write(
        run_id="run_2",
        type="run.created",
        source={"kind": "harness"},
        payload={"status": "queued"},
    )

    assert first.id == "run_1:1"
    assert first.sequence == 1
    assert second.id == "run_1:2"
    assert second.sequence == 2
    assert other.id == "run_2:1"
    assert other.sequence == 1

    assert [event.type for event in await store.list_by_run("run_1")] == [
        "run.created",
        "run.started",
    ]
    assert [event.type for event in await store.list_after_sequence("run_1", 1)] == [
        "run.started",
    ]


def test_sse_format_uses_event_id_type_and_json_payload() -> None:
    event = AgentStreamEvent(
        id="run_1:1",
        run_id="run_1",
        thread_id="thread_1",
        sequence=1,
        timestamp="2026-06-16T00:00:00Z",
        type="message.delta",
        source={"kind": "model"},
        visibility="user",
        redaction="none",
        summary=None,
        payload={"message_id": "msg_1", "delta": "hello"},
    )

    encoded = format_sse_event(event)

    assert encoded.startswith("id: run_1:1\nevent: message.delta\ndata: ")
    assert encoded.endswith("\n\n")
    data_line = encoded.split("\n")[2]
    data = json.loads(data_line.removeprefix("data: "))
    assert data["payload"] == {"message_id": "msg_1", "delta": "hello"}
    assert data["source"] == {"kind": "model", "id": None, "name": None}
