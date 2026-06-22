"""FastAPI app factory for the Aithru Agent backend."""

from secrets import compare_digest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aithru_agent.api.dependencies import ApiDependencies
from aithru_agent.api.routes import include_agent_routes
from aithru_agent.application import AgentRuntime, create_agent_runtime


def create_app(runtime: AgentRuntime | None = None) -> FastAPI:
    rt = runtime or create_agent_runtime()
    app = FastAPI(title="Aithru Agent Backend")
    app.state.aithru_api = ApiDependencies(rt)

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        token = rt.settings.api_token
        if token and request.url.path != "/api/health":
            expected = f"Bearer {token}"
            actual = request.headers.get("authorization", "")
            if not compare_digest(actual, expected):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    include_agent_routes(app)
    return app


app = create_app()
