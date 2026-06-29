import pytest

from aithru_agent.domain import (
    AgentPresentation,
    AgentPresentationAction,
    AgentPresentationEffect,
    AgentPresentationResource,
    AgentPresentationSource,
)


def test_artifact_presentation_requires_id_and_allows_html_preview() -> None:
    presentation = AgentPresentation(
        id="presentation_1",
        org_id="org_1",
        thread_id="thread_1",
        run_id="run_1",
        status="ready",
        priority="normal",
        title="index.html",
        reason="Show the generated webpage as an interactive preview.",
        resource=AgentPresentationResource(kind="artifact", id="artifact_1"),
        surfaces=["conversation", "side_panel"],
        preferred_view="html_preview",
        available_views=["html_preview", "source_text", "download"],
        effects=[
            AgentPresentationEffect(kind="open_panel", panel="preview", mode="soft")
        ],
        actions=[
            AgentPresentationAction(kind="open_view", label="Preview", view="html_preview"),
            AgentPresentationAction(kind="open_view", label="Source", view="source_text"),
            AgentPresentationAction(kind="download", label="Download"),
        ],
        source=AgentPresentationSource(
            created_by="harness",
            tool_call_id="tool_1",
            tool_name="artifact.create",
        ),
    )

    assert presentation.resource.id == "artifact_1"
    assert presentation.preferred_view == "html_preview"
    assert presentation.available_views == ["html_preview", "source_text", "download"]
    assert presentation.effects[0].panel == "preview"


def test_resource_validation_rejects_missing_required_references() -> None:
    with pytest.raises(ValueError, match="artifact presentation resources require id"):
        AgentPresentationResource(kind="artifact")

    with pytest.raises(ValueError, match="workspace file presentation resources require path"):
        AgentPresentationResource(kind="workspace_file")

    with pytest.raises(ValueError, match="external url presentation resources require url"):
        AgentPresentationResource(kind="external_url")


def test_preferred_view_must_be_available() -> None:
    with pytest.raises(ValueError, match="preferred view must be in available views"):
        AgentPresentation(
            id="presentation_2",
            org_id="org_1",
            thread_id="thread_1",
            run_id="run_1",
            title="index.html",
            resource=AgentPresentationResource(kind="artifact", id="artifact_1"),
            surfaces=["conversation"],
            preferred_view="html_preview",
            available_views=["source_text", "download"],
            source=AgentPresentationSource(created_by="model_request"),
        )


def test_effects_do_not_accept_freeform_ui_schema() -> None:
    with pytest.raises(ValueError):
        AgentPresentationEffect(
            kind="open_panel",
            panel="preview",
            mode="soft",
            component="DangerousComponent",
        )
