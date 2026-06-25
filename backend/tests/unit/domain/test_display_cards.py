import pytest

from aithru_agent.domain import (
    AgentDisplayCard,
    AgentDisplayCardAction,
    AgentDisplayCardResource,
    AgentDisplayCardSource,
)


def test_workspace_file_card_requires_path_and_forbids_extra_ui_schema() -> None:
    card = AgentDisplayCard(
        id="card_1",
        thread_id="thread_1",
        run_id="run_1",
        surface="conversation",
        type="file",
        status="ready",
        title="a.txt",
        resource=AgentDisplayCardResource(kind="workspace_file", path="/a.txt"),
        actions=[AgentDisplayCardAction(kind="preview", label="Preview")],
        source=AgentDisplayCardSource(
            created_by="harness",
            tool_call_id="tool_1",
            tool_name="workspace.write_file",
        ),
    )

    assert card.resource.path == "/a.txt"
    assert card.type == "file"

    with pytest.raises(ValueError):
        AgentDisplayCardResource(kind="workspace_file")

    with pytest.raises(ValueError):
        AgentDisplayCard(
            id="card_2",
            thread_id="thread_1",
            run_id="run_1",
            surface="conversation",
            type="file",
            status="ready",
            title="a.txt",
            resource=AgentDisplayCardResource(kind="workspace_file", path="/a.txt"),
            source=AgentDisplayCardSource(created_by="model_request"),
            component="DangerousComponent",
        )


def test_artifact_card_requires_id() -> None:
    with pytest.raises(ValueError):
        AgentDisplayCardResource(kind="artifact")

    resource = AgentDisplayCardResource(kind="artifact", id="artifact_1")
    assert resource.id == "artifact_1"
