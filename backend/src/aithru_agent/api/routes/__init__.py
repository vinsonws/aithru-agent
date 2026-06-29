"""FastAPI route groups for the Aithru Agent API."""

from fastapi import FastAPI

from aithru_agent.api.routes import (
    approvals,
    events,
    external_tools,
    health,
    long_term_memory,
    memory,
    memory_candidates,
    messages,
    model_profiles,
    runs,
    skills,
    subagents,
    threads,
    workspaces,
)


def include_agent_routes(app: FastAPI) -> None:
    """Register Aithru Agent route groups."""
    for router in [
        health.router,
        threads.router,
        messages.router,
        runs.router,
        events.router,
        external_tools.router,
        model_profiles.router,
        approvals.router,
        workspaces.router,
        skills.router,
        subagents.router,
        long_term_memory.router,
        memory.router,
        memory_candidates.router,
    ]:
        app.include_router(router)


__all__ = ["include_agent_routes"]
