from typing import Literal, Protocol

from pydantic import Field, ValidationError, field_validator

from aithru_agent.domain.base import AithruBaseModel

from .external import ExternalToolInvocation, ExternalToolResult, ExternalToolSpec


MAX_WEB_SEARCH_RESULTS = 50
MAX_WEB_FETCH_BYTES = 1_000_000


class WebSearchRequest(AithruBaseModel):
    query: str = Field(min_length=1)
    max_results: int = Field(default=5, ge=1, le=MAX_WEB_SEARCH_RESULTS)
    recency_days: int | None = Field(default=None, ge=1)

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query cannot be blank")
        return query


class WebSearchItem(AithruBaseModel):
    title: str = Field(min_length=1)
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title cannot be blank")
        return title

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, value: str) -> str:
        return _http_url(value)


class WebSearchResult(AithruBaseModel):
    query: str = Field(min_length=1)
    results: list[WebSearchItem]


class WebFetchRequest(AithruBaseModel):
    url: str
    max_bytes: int = Field(default=100_000, ge=1, le=MAX_WEB_FETCH_BYTES)
    extract_text: bool = True

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, value: str) -> str:
        return _http_url(value)


class WebFetchResult(AithruBaseModel):
    url: str
    status_code: int = Field(ge=100, le=599)
    media_type: str | None = None
    content: str
    truncated: bool = False

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, value: str) -> str:
        return _http_url(value)


class WebToolInvocation(AithruBaseModel):
    tool_call_id: str
    external_tool_name: str
    action: Literal["search", "fetch"]
    input: object
    run_id: str
    org_id: str
    actor_user_id: str
    workspace_id: str
    thread_id: str | None = None
    skill_id: str | None = None


class WebToolResult(AithruBaseModel):
    status: Literal["completed", "failed", "denied"]
    output: object | None = None
    error: dict | None = None
    redaction: Literal["none", "partial", "full"] = "none"


class WebToolExecutor(Protocol):
    async def execute(self, invocation: WebToolInvocation) -> WebToolResult:
        ...


class WebToolProvider:
    def __init__(self, *, executor: WebToolExecutor) -> None:
        self._executor = executor

    def list_tools(self) -> list[ExternalToolSpec]:
        return [
            ExternalToolSpec(
                name="web.search",
                description="Search the web through a controlled web provider.",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_WEB_SEARCH_RESULTS},
                        "recency_days": {"type": "integer", "minimum": 1},
                    },
                },
                output_schema={"type": "object"},
                risk_level="read",
                required_scopes=["agent.external.web.search"],
                approval_policy="on_risk",
                failure_policy="return_recoverable",
                provider="web",
                metadata={"action": "search"},
            ),
            ExternalToolSpec(
                name="web.fetch",
                description="Fetch a URL through a controlled web provider.",
                input_schema={
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "url": {"type": "string"},
                        "max_bytes": {"type": "integer", "minimum": 1, "maximum": MAX_WEB_FETCH_BYTES},
                        "extract_text": {"type": "boolean"},
                    },
                },
                output_schema={"type": "object"},
                risk_level="read",
                required_scopes=["agent.external.web.fetch"],
                approval_policy="on_risk",
                failure_policy="return_recoverable",
                provider="web",
                metadata={"action": "fetch"},
            ),
        ]

    async def execute(self, invocation: ExternalToolInvocation) -> ExternalToolResult:
        if invocation.tool_name == "web.search":
            validation_error = _validate_search_input(invocation.input)
            action: Literal["search", "fetch"] = "search"
        elif invocation.tool_name == "web.fetch":
            validation_error = _validate_fetch_input(invocation.input)
            action = "fetch"
        else:
            return ExternalToolResult(
                status="denied",
                error={"message": f"Unknown web tool: {invocation.tool_name}"},
                redaction="none",
            )
        if validation_error is not None:
            return ExternalToolResult(
                status="denied",
                error={"message": validation_error},
                redaction="none",
            )
        result = await self._executor.execute(
            WebToolInvocation(
                tool_call_id=invocation.tool_call_id,
                external_tool_name=invocation.tool_name,
                action=action,
                input=invocation.input,
                run_id=invocation.run_id,
                org_id=invocation.org_id,
                actor_user_id=invocation.actor_user_id,
                workspace_id=invocation.workspace_id,
                thread_id=invocation.thread_id,
                skill_id=invocation.skill_id,
            )
        )
        return ExternalToolResult(
            status=result.status,
            output=result.output,
            error=result.error,
            redaction=result.redaction,
        )

    def external_invocation(
        self,
        *,
        tool_call_id: str,
        external_tool_name: str,
        input: object,
        run_id: str,
        org_id: str,
        actor_user_id: str,
        workspace_id: str,
        thread_id: str | None = None,
        skill_id: str | None = None,
    ) -> ExternalToolInvocation:
        return ExternalToolInvocation(
            tool_call_id=tool_call_id,
            tool_name=external_tool_name,
            input=input,
            run_id=run_id,
            org_id=org_id,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            skill_id=skill_id,
        )


def _validate_search_input(value: object) -> str | None:
    try:
        WebSearchRequest.model_validate(value)
    except ValidationError as exc:
        return f"Invalid web tool input: {exc}"
    return None


def _validate_fetch_input(value: object) -> str | None:
    try:
        WebFetchRequest.model_validate(value)
    except ValidationError as exc:
        return f"Invalid web tool input: {exc}"
    return None


def _http_url(value: str) -> str:
    url = value.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url must use http or https")
    return url
