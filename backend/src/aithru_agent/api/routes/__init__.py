"""FastAPI route groups for the Aithru Agent API."""

from fastapi import FastAPI

from aithru_agent.api.routes import (
    approvals,
    artifacts,
    events,
    external_tools,
    health,
    memory,
    memory_candidates,
    messages,
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
        approvals.router,
        workspaces.router,
        artifacts.router,
        skills.router,
        subagents.router,
        memory.router,
        memory_candidates.router,
    ]:
        app.include_router(router)


__all__ = ["include_agent_routes"]
