"""FastAPI route groups for the Aithru Agent API."""

from fastapi import FastAPI

from aithru_agent.api.routes import (
    approvals,
    artifacts,
    events,
    health,
    memory,
    messages,
    runs,
    skills,
    subagents,
    threads,
    workspaces,
)


def include_agent_routes(app: FastAPI) -> None:
    """Register new route groups and legacy compatibility aliases."""
    for router in [
        health.router,
        threads.router,
        messages.router,
        runs.router,
        events.router,
        approvals.router,
        workspaces.router,
        artifacts.router,
        skills.router,
        subagents.router,
        memory.router,
    ]:
        app.include_router(router)


__all__ = ["include_agent_routes"]

