import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator

from .base import AithruBaseModel


MAX_RESEARCH_SOURCES = 20
MAX_RESEARCH_PLAN_STEPS = 12
MAX_RESEARCH_PLAN_SECTIONS = 8

ResearchPlanPhase = Literal["search", "fetch", "synthesize", "report", "custom"]
ResearchPlanSectionPriority = Literal["high", "medium", "low"]
ResearchTodoProgressToolName = Literal["web.search", "web.fetch", "research.create_report"]
ResearchTodoProgressOutcome = Literal["completed", "failed"]
ResearchTodoProgressStatus = Literal["done", "blocked"]
ResearchToolFailureToolName = Literal["web.search", "web.fetch"]
ResearchSourceQualityLabel = Literal["high", "medium", "low"]
ResearchLimitationSeverity = Literal["info", "warning", "error"]
ResearchReportStatus = Literal["complete", "partial", "insufficient_evidence"]


class ResearchPlanSection(AithruBaseModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    priority: ResearchPlanSectionPriority = "medium"

    @field_validator("section_id")
    @classmethod
    def _section_id_must_be_stable_slug(cls, value: str) -> str:
        section_id = value.strip()
        if not section_id:
            raise ValueError("research plan section id cannot be blank")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", section_id):
            raise ValueError("research plan section id must be a stable lowercase slug")
        return section_id

    @field_validator("title", "question")
    @classmethod
    def _section_required_strings_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("research plan section strings cannot be blank")
        return stripped


class ResearchPlanStep(AithruBaseModel):
    phase: ResearchPlanPhase
    title: str = Field(min_length=1)
    description: str | None = None

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("research plan step title cannot be blank")
        return title

    @field_validator("description")
    @classmethod
    def _description_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ResearchPlanRequest(AithruBaseModel):
    query: str = Field(min_length=1)
    objective: str | None = None
    sections: list[ResearchPlanSection] | None = Field(default=None, max_length=MAX_RESEARCH_PLAN_SECTIONS)
    steps: list[ResearchPlanStep] | None = Field(default=None, max_length=MAX_RESEARCH_PLAN_STEPS)

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("research plan query cannot be blank")
        return query

    @field_validator("objective")
    @classmethod
    def _objective_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("research plan objective cannot be blank")
        return stripped

    @model_validator(mode="after")
    def _collections_must_not_be_empty(self) -> "ResearchPlanRequest":
        if self.sections is not None and not self.sections:
            raise ValueError("research plan sections cannot be empty")
        if self.steps is not None and not self.steps:
            raise ValueError("research plan steps cannot be empty")
        return self


class ResearchPlan(AithruBaseModel):
    query: str
    objective: str | None = None
    sections: list[ResearchPlanSection]
    steps: list[ResearchPlanStep]


class ResearchTodoProgress(AithruBaseModel):
    tool_name: ResearchTodoProgressToolName
    todo_title: str = Field(min_length=1)
    status: ResearchTodoProgressStatus = "done"

    @field_validator("todo_title")
    @classmethod
    def _todo_title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("research todo progress title cannot be blank")
        return title


class ResearchSource(AithruBaseModel):
    title: str = Field(min_length=1)
    url: str
    snippet: str | None = None
    content: str | None = None
    source: str | None = None
    published_at: str | None = None
    section_id: str | None = None

    @field_validator("title")
    @classmethod
    def _title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("research source title cannot be blank")
        return title

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, value: str) -> str:
        url = value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("research source url must use http or https")
        return url

    @field_validator("snippet", "content", "source", "published_at")
    @classmethod
    def _optional_string_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("section_id")
    @classmethod
    def _section_id_must_be_stable_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        section_id = value.strip()
        if not section_id:
            return None
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", section_id):
            raise ValueError("research source section id must be a stable lowercase slug")
        return section_id


class ResearchLimitation(AithruBaseModel):
    code: str = Field(min_length=1)
    severity: ResearchLimitationSeverity
    message: str = Field(min_length=1)
    source_url: str | None = None

    @field_validator("code", "message")
    @classmethod
    def _limitation_required_string_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("research limitation strings cannot be blank")
        return stripped

    @field_validator("source_url")
    @classmethod
    def _limitation_source_url_must_be_http(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = value.strip()
        if not url:
            return None
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("research limitation source url must use http or https")
        return url


class ResearchToolFailure(AithruBaseModel):
    tool_name: ResearchToolFailureToolName
    query: str | None = None
    url: str | None = None
    error_message: str = "Tool failed"

    @field_validator("query", "url")
    @classmethod
    def _failure_optional_strings_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("url")
    @classmethod
    def _failure_url_keeps_only_http(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value if value.startswith("http://") or value.startswith("https://") else None

    @field_validator("error_message")
    @classmethod
    def _failure_message_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        return stripped or "Tool failed"


class ResearchRecoverableToolFailure(AithruBaseModel):
    status: Literal["failed"] = "failed"
    recoverable: Literal[True] = True
    tool_name: ResearchToolFailureToolName
    query: str | None = None
    url: str | None = None
    error: dict
    limitation: ResearchLimitation


class ResearchReportRequest(AithruBaseModel):
    title: str = Field(min_length=1)
    query: str = Field(min_length=1)
    summary: str | None = None
    sections: list[ResearchPlanSection] = Field(default_factory=list, max_length=MAX_RESEARCH_PLAN_SECTIONS)
    sources: list[ResearchSource] = Field(default_factory=list, max_length=MAX_RESEARCH_SOURCES)
    limitations: list[ResearchLimitation] = Field(default_factory=list)

    @field_validator("title", "query")
    @classmethod
    def _required_string_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("research report strings cannot be blank")
        return stripped

    @field_validator("summary")
    @classmethod
    def _summary_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _must_have_sources_or_limitations(self) -> "ResearchReportRequest":
        if not self.sources and not self.limitations:
            raise ValueError("research report requires sources or limitations")
        return self


class ResearchSourceQuality(AithruBaseModel):
    label: ResearchSourceQualityLabel
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class ResearchQualitySummary(AithruBaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class ResearchEvidenceSectionSummary(AithruBaseModel):
    section_id: str
    source_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class ResearchEvidence(AithruBaseModel):
    citation_number: int = Field(ge=1)
    title: str = Field(min_length=1)
    url: str
    snippet: str | None = None
    excerpt: str | None = None
    source: str | None = None
    published_at: str | None = None
    section_id: str | None = None
    quality: ResearchSourceQuality

    @field_validator("title")
    @classmethod
    def _evidence_title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("research evidence title cannot be blank")
        return title

    @field_validator("url")
    @classmethod
    def _evidence_url_must_be_http(cls, value: str) -> str:
        url = value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("research evidence url must use http or https")
        return url

    @field_validator("snippet", "excerpt", "source", "published_at")
    @classmethod
    def _optional_evidence_string_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("section_id")
    @classmethod
    def _section_id_must_be_stable_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        section_id = value.strip()
        if not section_id:
            return None
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", section_id):
            raise ValueError("research evidence section id must be a stable lowercase slug")
        return section_id


class ResearchReport(AithruBaseModel):
    title: str
    query: str
    status: ResearchReportStatus
    summary: str
    source_input_count: int
    duplicate_source_count: int
    quality_summary: ResearchQualitySummary
    sections: list[ResearchPlanSection] = Field(default_factory=list)
    section_summary: list[ResearchEvidenceSectionSummary] = Field(default_factory=list)
    limitations: list[ResearchLimitation]
    findings: list[str]
    evidence: list[ResearchEvidence]
    sources: list[ResearchSource]
    markdown: str


def build_research_report(request: ResearchReportRequest) -> ResearchReport:
    sources = _prepare_sources(request.sources)
    findings = [_finding_for_source(source) for source in sources]
    evidence = [
        _evidence_for_source(index, source)
        for index, source in enumerate(sources, start=1)
    ]
    summary = request.summary or _default_summary(request, source_count=len(sources))
    report = ResearchReport(
        title=request.title,
        query=request.query,
        status=_report_status(sources, request.limitations),
        summary=summary,
        source_input_count=len(request.sources),
        duplicate_source_count=len(request.sources) - len(sources),
        quality_summary=_quality_summary(evidence),
        sections=request.sections,
        section_summary=_section_summary(evidence),
        limitations=request.limitations,
        findings=findings,
        evidence=evidence,
        sources=sources,
        markdown="",
    )
    return report.model_copy(update={"markdown": _render_markdown(report)})


def build_research_plan(request: ResearchPlanRequest) -> ResearchPlan:
    return ResearchPlan(
        query=request.query,
        objective=request.objective,
        sections=request.sections or _default_research_plan_sections(request.query),
        steps=request.steps or _default_research_plan_steps(request.query),
    )


def research_todo_progress_for_tool(
    tool_name: str,
    *,
    outcome: ResearchTodoProgressOutcome = "completed",
) -> list[ResearchTodoProgress]:
    return [
        progress.model_copy()
        for progress in _RESEARCH_TODO_PROGRESS_BY_TOOL.get((tool_name, outcome), ())
    ]


def research_limitation_for_tool_failure(failure: ResearchToolFailure) -> ResearchLimitation:
    if failure.tool_name == "web.search":
        query = f" for `{failure.query}`" if failure.query else ""
        return ResearchLimitation(
            code="web_search_failed",
            severity="warning",
            message=f"Controlled web search failed{query}: {failure.error_message}.",
        )
    return ResearchLimitation(
        code="web_fetch_failed",
        severity="warning",
        message=f"Controlled web fetch failed: {failure.error_message}.",
        source_url=failure.url,
    )


def research_limitation_for_blocked_todo_title(title: str) -> ResearchLimitation | None:
    limitation = _RESEARCH_LIMITATION_BY_BLOCKED_TODO_TITLE.get(title)
    return limitation.model_copy() if limitation is not None else None


def research_report_uri(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return f"/reports/{slug or 'research-report'}.md"


def _default_research_plan_steps(query: str) -> list[ResearchPlanStep]:
    return [
        ResearchPlanStep(
            phase="search",
            title="Search sources",
            description=f"Find relevant sources for `{query}`.",
        ),
        ResearchPlanStep(
            phase="fetch",
            title="Fetch and review sources",
            description="Fetch the strongest sources and extract usable evidence.",
        ),
        ResearchPlanStep(
            phase="synthesize",
            title="Synthesize findings",
            description="Compare evidence, note gaps, and prepare cited findings.",
        ),
        ResearchPlanStep(
            phase="report",
            title="Create research report",
            description="Create the final markdown research report workspace file.",
        ),
    ]


def _default_research_plan_sections(query: str) -> list[ResearchPlanSection]:
    return [
        ResearchPlanSection(
            section_id="background",
            title="Background and context",
            question=f"What background and current context matter for `{query}`?",
            priority="medium",
        ),
        ResearchPlanSection(
            section_id="evidence",
            title="Direct evidence",
            question=f"What evidence directly answers `{query}`?",
            priority="high",
        ),
        ResearchPlanSection(
            section_id="gaps",
            title="Gaps and limitations",
            question=f"What gaps, risks, or limitations remain for `{query}`?",
            priority="medium",
        ),
    ]


_RESEARCH_TODO_PROGRESS_BY_TOOL: dict[
    tuple[str, ResearchTodoProgressOutcome],
    tuple[ResearchTodoProgress, ...],
] = {
    ("web.search", "completed"): (
        ResearchTodoProgress(
            tool_name="web.search",
            todo_title="Search sources",
        ),
    ),
    ("web.search", "failed"): (
        ResearchTodoProgress(
            tool_name="web.search",
            todo_title="Search sources",
            status="blocked",
        ),
    ),
    ("web.fetch", "completed"): (
        ResearchTodoProgress(
            tool_name="web.fetch",
            todo_title="Fetch and review sources",
        ),
    ),
    ("web.fetch", "failed"): (
        ResearchTodoProgress(
            tool_name="web.fetch",
            todo_title="Fetch and review sources",
            status="blocked",
        ),
    ),
    ("research.create_report", "completed"): (
        ResearchTodoProgress(
            tool_name="research.create_report",
            todo_title="Synthesize findings",
        ),
        ResearchTodoProgress(
            tool_name="research.create_report",
            todo_title="Create research report",
        ),
    ),
}


_RESEARCH_LIMITATION_BY_BLOCKED_TODO_TITLE: dict[str, ResearchLimitation] = {
    "Search sources": ResearchLimitation(
        code="research_search_blocked",
        severity="warning",
        message="Research source search was blocked before report creation.",
    ),
    "Fetch and review sources": ResearchLimitation(
        code="research_fetch_blocked",
        severity="warning",
        message="Research source fetching was blocked before report creation.",
    ),
}


def _default_summary(request: ResearchReportRequest, *, source_count: int) -> str:
    if source_count == 0:
        return f"No usable sources were collected for `{request.query}`."
    source_label = "source" if source_count == 1 else "sources"
    return f"Collected {source_count} {source_label} for `{request.query}`."


def _report_status(
    sources: list[ResearchSource],
    limitations: list[ResearchLimitation],
) -> ResearchReportStatus:
    if not sources:
        return "insufficient_evidence"
    if limitations:
        return "partial"
    return "complete"


def _finding_for_source(source: ResearchSource) -> str:
    content_excerpt = _excerpt(source.content)
    evidence_parts = [
        part
        for part in [source.snippet, content_excerpt]
        if part is not None
    ]
    evidence = " ".join(dict.fromkeys(evidence_parts)) or "No summary provided."
    return f"{source.title}: {evidence}"


def _evidence_for_source(index: int, source: ResearchSource) -> ResearchEvidence:
    return ResearchEvidence(
        citation_number=index,
        title=source.title,
        url=source.url,
        snippet=source.snippet,
        excerpt=_excerpt(source.content),
        source=source.source,
        published_at=source.published_at,
        section_id=source.section_id,
        quality=_quality_for_source(source),
    )


def _prepare_sources(sources: list[ResearchSource]) -> list[ResearchSource]:
    by_url: dict[str, ResearchSource] = {}
    for source in sources:
        key = _source_url_key(source.url)
        existing = by_url.get(key)
        by_url[key] = source if existing is None else _merge_sources(existing, source)
    return sorted(
        by_url.values(),
        key=lambda source: (
            -_quality_for_source(source).score,
            source.title.casefold(),
            source.url,
        ),
    )


def _merge_sources(existing: ResearchSource, incoming: ResearchSource) -> ResearchSource:
    return existing.model_copy(
        update={
            "snippet": _merge_text(existing.snippet, incoming.snippet, separator=" "),
            "content": _merge_text(existing.content, incoming.content, separator="\n\n"),
            "source": existing.source or incoming.source,
            "published_at": existing.published_at or incoming.published_at,
            "section_id": existing.section_id or incoming.section_id,
        }
    )


def _merge_text(left: str | None, right: str | None, *, separator: str) -> str | None:
    if left is None:
        return right
    if right is None or right == left:
        return left
    return f"{left}{separator}{right}"


def _source_url_key(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.query,
            "",
        )
    )


def _quality_for_source(source: ResearchSource) -> ResearchSourceQuality:
    score = 40
    reasons = ["valid_http_source"]
    if source.snippet:
        score += 20
        reasons.append("has_search_snippet")
    if source.content:
        score += 30
        reasons.append("has_fetched_content")
    if source.source:
        score += 5
        reasons.append("has_provider")
    if source.published_at:
        score += 5
        reasons.append("has_published_date")
    return ResearchSourceQuality(
        label=_quality_label(score),
        score=score,
        reasons=reasons,
    )


def _quality_label(score: int) -> ResearchSourceQualityLabel:
    if score >= 85:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _quality_summary(evidence: list[ResearchEvidence]) -> ResearchQualitySummary:
    counts = {"high": 0, "medium": 0, "low": 0}
    for row in evidence:
        counts[row.quality.label] += 1
    return ResearchQualitySummary(**counts)


def _section_summary(evidence: list[ResearchEvidence]) -> list[ResearchEvidenceSectionSummary]:
    source_urls_by_section: dict[str, set[str]] = {}
    evidence_count_by_section: dict[str, int] = {}
    for row in evidence:
        if row.section_id is None:
            continue
        source_urls_by_section.setdefault(row.section_id, set()).add(row.url)
        evidence_count_by_section[row.section_id] = evidence_count_by_section.get(row.section_id, 0) + 1
    return [
        ResearchEvidenceSectionSummary(
            section_id=section_id,
            source_count=len(source_urls),
            evidence_count=evidence_count_by_section[section_id],
        )
        for section_id, source_urls in source_urls_by_section.items()
    ]


def _excerpt(value: str | None, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}..."


def _render_markdown(report: ResearchReport) -> str:
    lines = [
        f"# {report.title}",
        "",
        f"Query: `{report.query}`",
        "",
        "## Summary",
        "",
        report.summary,
        "",
        "## Findings",
        "",
    ]
    lines.extend(
        f"- {finding} [{index}]"
        for index, finding in enumerate(report.findings, start=1)
    )
    if report.section_summary:
        lines.extend(["", "## Evidence by Section", ""])
        lines.extend(_section_summary_line(summary) for summary in report.section_summary)
    lines.extend(["", "## Evidence", ""])
    include_section = any(evidence.section_id for evidence in report.evidence)
    if include_section:
        lines.extend(
            [
                "| # | Section | Source | Quality | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
    else:
        lines.extend(
            [
                "| # | Source | Quality | Evidence |",
                "| --- | --- | --- | --- |",
            ]
        )
    lines.extend(
        _evidence_line(evidence, include_section=include_section)
        for evidence in report.evidence
    )
    if report.limitations:
        lines.extend(["", "## Limitations", ""])
        lines.extend(_limitation_line(limitation) for limitation in report.limitations)
    lines.extend(["", "## Sources", ""])
    if report.sources:
        lines.extend(
            _source_line(index, source)
            for index, source in enumerate(report.sources, start=1)
        )
    else:
        lines.append("No usable sources were collected.")
    return "\n".join(lines).rstrip() + "\n"


def _section_summary_line(summary: ResearchEvidenceSectionSummary) -> str:
    source_label = "source" if summary.source_count == 1 else "sources"
    evidence_label = "evidence row" if summary.evidence_count == 1 else "evidence rows"
    return (
        f"- `{summary.section_id}`: "
        f"{summary.source_count} {source_label}, {summary.evidence_count} {evidence_label}"
    )


def _evidence_line(evidence: ResearchEvidence, *, include_section: bool) -> str:
    evidence_text = " ".join(
        dict.fromkeys(
            part
            for part in [evidence.snippet, evidence.excerpt]
            if part is not None
        )
    ) or "No evidence text provided."
    cells = [
        f"| {evidence.citation_number} | "
    ]
    if include_section:
        section = f"`{evidence.section_id}`" if evidence.section_id else "-"
        cells.append(f"{section} | ")
    cells.extend(
        [
            f"[{_markdown_cell(evidence.title)}]({evidence.url}) | ",
            f"{evidence.quality.label} | ",
            f"{_markdown_cell(evidence_text)} |",
        ]
    )
    return "".join(cells)


def _source_line(index: int, source: ResearchSource) -> str:
    details = [
        value
        for value in [source.source, source.published_at]
        if value
    ]
    suffix = f" — {', '.join(details)}" if details else ""
    return f"{index}. [{source.title}]({source.url}){suffix}"


def _limitation_line(limitation: ResearchLimitation) -> str:
    source = f", {limitation.source_url}" if limitation.source_url else ""
    return f"- {limitation.severity}: {limitation.message} (`{limitation.code}`{source})"


def _markdown_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")
