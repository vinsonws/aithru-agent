from collections.abc import Callable
from dataclasses import dataclass

from pydantic_ai.models.test import TestModel

from aithru_agent.agent import AgentRuntime as NativeAgentRuntime
from aithru_agent.capabilities import (
    AithruCapabilityRouter,
    ControlledHTTPMCPToolExecutor,
    ControlledHTTPWorkflowCapabilityProvider,
    ExternalToolAdapter,
    ExternalToolProvider,
    MCPToolExecutor,
    MCPToolInvocation,
    MCPToolProvider,
    MCPToolResult,
    ToolPolicy,
    WebToolInvocation,
    WebToolExecutor,
    WebToolProvider,
    WebToolResult,
    WorkflowCapabilityAdapter,
    WorkflowCapabilityResult,
    WorkflowCapabilityProvider,
    WorkflowCapabilitySpec,
)
from aithru_agent.capabilities.local_tools import (
    ArtifactLocalTool,
    ClarificationLocalTool,
    InputLocalTool,
    MemoryLocalTool,
    ResearchLocalTool,
    SandboxLocalTool,
    SubagentLocalTool,
    TodoLocalTool,
    WorkbenchLocalTool,
    WorkspaceLocalTool,
)
from aithru_agent.capabilities.web_http import ControlledHTTPWebExecutor
from aithru_agent.external_tools import (
    AgentExternalToolConfigRegistry,
    InMemoryExternalToolConfigRegistry,
    SQLiteExternalToolConfigRegistry,
)
from aithru_agent.model_profiles import (
    AgentModelProfileRegistry,
    InMemoryModelProfileRegistry,
    SQLiteModelProfileRegistry,
)
from aithru_agent.model_profiles.factory import create_model_from_profile
from aithru_agent.domain import AgentModelProfileEntry, AgentRun
from aithru_agent.memory import LongTermMemoryProvider, create_long_term_memory_provider
from aithru_agent.persistence.memory import InMemoryAgentStore
from aithru_agent.persistence.protocols import AgentEventStore, AgentStore
from aithru_agent.persistence.sqlite import SQLiteAgentEventStore, SQLiteAgentStore
from aithru_agent.runtime.processors import AgentRuntimeProcessorRunner
from aithru_agent.runtime.processors.clarification import ClarificationPreflightProcessor
from aithru_agent.runtime.processors.memory_extraction import MemoryExtractionProcessor
from aithru_agent.runtime.processors.summarization import ContextSummarizationProcessor
from aithru_agent.runtime.processors.title import (
    PydanticAITitleProvider,
    ThreadTitleProcessor,
    TitleProvider,
)
from aithru_agent.sandbox import LocalPythonSandboxProvider
from aithru_agent.secrets import AgentSecretStore, InMemorySecretStore, SQLiteSecretStore
from aithru_agent.settings import AgentSettings
from aithru_agent.skills import (
    AgentSkillRegistry,
    AgentSkillResolver,
    BuiltInResearchSkillResolver,
    InMemorySkillRegistry,
    SQLiteSkillRegistry,
)
from aithru_agent.stream import AgentEventWriter, InMemoryAgentEventStore
from aithru_agent.worker import AgentWorkerRunner, AgentWorkerService, InProcessRunQueue


@dataclass
class AgentApplication:
    settings: AgentSettings
    store: AgentStore
    event_store: AgentEventStore
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    runner: AgentWorkerRunner
    run_queue: InProcessRunQueue
    worker: AgentWorkerService
    skill_resolver: AgentSkillResolver
    skill_registry: AgentSkillRegistry
    external_tool_config_registry: AgentExternalToolConfigRegistry
    model_profile_registry: AgentModelProfileRegistry
    secret_store: AgentSecretStore
    agent_runtime: NativeAgentRuntime
    processor_runner: AgentRuntimeProcessorRunner
    long_term_memory_provider: LongTermMemoryProvider


AgentRuntime = AgentApplication


def create_agent_application(
    *,
    store: AgentStore | None = None,
    event_store: AgentEventStore | None = None,
    agent_runtime: NativeAgentRuntime | None = None,
    policy: ToolPolicy | None = None,
    settings: AgentSettings | None = None,
    skill_resolver: AgentSkillResolver | None = None,
    skill_registry: AgentSkillRegistry | None = None,
    external_tool_providers: list[ExternalToolProvider] | None = None,
    workflow_capability_providers: list[WorkflowCapabilityProvider] | None = None,
    long_term_memory_provider: LongTermMemoryProvider | None = None,
) -> AgentApplication:
    resolved_settings = settings or AgentSettings.from_env()
    resolved_store = store or _create_store(resolved_settings)
    resolved_event_store = event_store or _create_event_store(resolved_settings)
    event_writer = AgentEventWriter(resolved_event_store)
    seed_skill_resolver = skill_resolver or BuiltInResearchSkillResolver()
    resolved_skill_registry = skill_registry or _create_skill_registry(
        resolved_settings,
        seed_skill_resolver,
    )
    external_tool_config_registry = _create_external_tool_config_registry(resolved_settings)
    model_profile_registry = _create_model_profile_registry(resolved_settings)
    secret_store = _create_secret_store(resolved_settings)
    resolved_skill_resolver = resolved_skill_registry
    subagent_tool = SubagentLocalTool(resolved_store, event_writer, resolved_skill_resolver)
    tool_adapters = [
        WorkspaceLocalTool(resolved_store),
        TodoLocalTool(resolved_store),
        ArtifactLocalTool(resolved_store),
        ClarificationLocalTool(),
        InputLocalTool(),
        MemoryLocalTool(resolved_store),
        ResearchLocalTool(resolved_store),
        WorkbenchLocalTool(resolved_store),
        subagent_tool,
        SandboxLocalTool(event_writer, store=resolved_store, provider=LocalPythonSandboxProvider()),
    ]
    configured_external_tool_providers = _create_external_tool_providers(resolved_settings)
    tool_adapters.extend(
        ExternalToolAdapter(provider)
        for provider in [
            *configured_external_tool_providers,
            *(external_tool_providers or []),
        ]
    )
    configured_workflow_capability_providers = _create_workflow_capability_providers(
        resolved_settings
    )
    tool_adapters.extend(
        WorkflowCapabilityAdapter(provider)
        for provider in [
            *configured_workflow_capability_providers,
            *(workflow_capability_providers or []),
        ]
    )
    capability_router = AithruCapabilityRouter(
        adapters=tool_adapters,
        policy=policy or ToolPolicy(require_approval_for_risk=[]),
    )
    resolved_agent_runtime = agent_runtime or _create_native_agent_runtime(
        resolved_settings,
        model_profile_registry=model_profile_registry,
        secret_store=secret_store,
    )
    resolved_long_term_memory_provider = (
        long_term_memory_provider
        or create_long_term_memory_provider(resolved_settings)
    )
    processor_runner = _create_processor_runner(
        resolved_settings,
        model_profile_registry=model_profile_registry,
        secret_store=secret_store,
    )
    runner = AgentWorkerRunner(
        store=resolved_store,
        event_writer=event_writer,
        capability_router=capability_router,
        event_store=resolved_event_store,
        agent_runtime=resolved_agent_runtime,
        skill_resolver=resolved_skill_resolver,
        processor_runner=processor_runner,
        long_term_memory_provider=resolved_long_term_memory_provider,
    )
    subagent_tool.set_task_runner(runner.execute_child_run_for_task)
    run_queue = InProcessRunQueue()
    worker = AgentWorkerService(runner=runner, queue=run_queue)
    return AgentApplication(
        settings=resolved_settings,
        store=resolved_store,
        event_store=resolved_event_store,
        event_writer=event_writer,
        capability_router=capability_router,
        runner=runner,
        run_queue=run_queue,
        worker=worker,
        skill_resolver=resolved_skill_resolver,
        skill_registry=resolved_skill_registry,
        external_tool_config_registry=external_tool_config_registry,
        model_profile_registry=model_profile_registry,
        secret_store=secret_store,
        agent_runtime=resolved_agent_runtime,
        processor_runner=processor_runner,
        long_term_memory_provider=resolved_long_term_memory_provider,
    )


create_agent_runtime = create_agent_application


def _create_native_agent_runtime(
    settings: AgentSettings,
    *,
    model_profile_registry: AgentModelProfileRegistry,
    secret_store: AgentSecretStore,
) -> NativeAgentRuntime:
    if settings.model == "test":
        model: object | str = TestModel(
            call_tools=[],
            custom_output_text=settings.test_model_output,
        )
    elif settings.model:
        model = settings.model
    else:
        raise ValueError(
            "AITHRU_AGENT_MODEL is required for the Pydantic AI runtime. "
            "Use AITHRU_AGENT_MODEL=test only for tests or local deterministic development."
        )

    return NativeAgentRuntime(
        model=model,
        model_factory=lambda model_name: (
            TestModel(call_tools=[], custom_output_text=settings.test_model_output)
            if model_name == "test"
            else model_name
        ),
        model_profile_resolver=model_profile_registry.get_profile,
        profile_model_factory=lambda profile: create_model_from_profile(
            profile,
            secret_store=secret_store,
            test_model_output=settings.test_model_output,
        ),
        instructions=settings.instructions,
    )


def _create_processor_runner(
    settings: AgentSettings,
    *,
    model_profile_registry: AgentModelProfileRegistry | None = None,
    secret_store: AgentSecretStore | None = None,
) -> AgentRuntimeProcessorRunner:
    processors = []
    if settings.processors.clarification_enabled:
        processors.append(ClarificationPreflightProcessor())
    if settings.processors.title_generation_enabled:
        processors.append(
            ThreadTitleProcessor(
                max_words=settings.processors.title_max_words,
                provider=_create_title_provider(
                    settings,
                    model_profile_registry=model_profile_registry,
                    secret_store=secret_store,
                ),
            )
        )
    if settings.processors.summarization_enabled:
        processors.append(
            ContextSummarizationProcessor(
                min_message_count=settings.processors.summarization_min_message_count,
            )
        )
    if settings.processors.memory_extraction_enabled:
        processors.append(MemoryExtractionProcessor())
    return AgentRuntimeProcessorRunner(processors=processors)


def _create_title_provider(
    settings: AgentSettings,
    *,
    model_profile_registry: AgentModelProfileRegistry | None = None,
    secret_store: AgentSecretStore | None = None,
) -> TitleProvider | None:
    if settings.model is None and model_profile_registry is None:
        return None
    return PydanticAITitleProvider(
        model_resolver=lambda run: _resolve_title_model_for_run(
            run,
            settings=settings,
            model_profile_resolver=(
                model_profile_registry.get_profile
                if model_profile_registry is not None
                else None
            ),
            profile_model_factory=(
                lambda profile: create_model_from_profile(
                    profile,
                    secret_store=secret_store or InMemorySecretStore(),
                    test_model_output=settings.test_model_output,
                )
            ),
        )
    )


def _resolve_title_model_for_run(
    run: AgentRun,
    *,
    settings: AgentSettings,
    model_profile_resolver: (
        Callable[[str, str], AgentModelProfileEntry | None] | None
    ) = None,
    profile_model_factory: Callable[[AgentModelProfileEntry], str | object] | None = None,
) -> str | object | None:
    if run.harness_options and run.harness_options.model:
        if (
            run.harness_options.model_profile_key
            and model_profile_resolver is not None
            and profile_model_factory is not None
        ):
            profile = model_profile_resolver(
                run.org_id,
                run.harness_options.model_profile_key,
            )
            if profile is not None:
                return profile_model_factory(profile)
        if run.harness_options.model == "test":
            return _test_model_for_settings(settings)
        return run.harness_options.model
    return _create_processor_model(settings)


def _create_processor_model(settings: AgentSettings) -> str | object | None:
    if settings.model == "test":
        return _test_model_for_settings(settings)
    if settings.model:
        return settings.model
    return None


def _test_model_for_settings(settings: AgentSettings) -> TestModel:
    return TestModel(
        call_tools=[],
        custom_output_text=settings.test_model_output,
    )


def _create_skill_registry(
    settings: AgentSettings,
    seed_skill_resolver: AgentSkillResolver,
) -> AgentSkillRegistry:
    seed_skills = seed_skill_resolver.list_skills()
    if settings.persistence_backend == "sqlite":
        return SQLiteSkillRegistry(settings.sqlite_path, seed_skills=seed_skills)
    return InMemorySkillRegistry(seed_skills=seed_skills)


def _create_external_tool_config_registry(
    settings: AgentSettings,
) -> AgentExternalToolConfigRegistry:
    if settings.persistence_backend == "sqlite":
        return SQLiteExternalToolConfigRegistry(settings.sqlite_path)
    return InMemoryExternalToolConfigRegistry()


def _create_model_profile_registry(settings: AgentSettings) -> AgentModelProfileRegistry:
    if settings.persistence_backend == "sqlite":
        return SQLiteModelProfileRegistry(settings.sqlite_path)
    return InMemoryModelProfileRegistry()


def _create_secret_store(settings: AgentSettings) -> AgentSecretStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteSecretStore(settings.sqlite_path)
    return InMemorySecretStore()


def _create_external_tool_providers(settings: AgentSettings) -> list[ExternalToolProvider]:
    providers: list[ExternalToolProvider] = []
    if settings.external_tools.web_enabled:
        providers.append(WebToolProvider(executor=_create_web_tool_executor(settings)))
    if settings.external_tools.mcp_servers:
        providers.append(
            MCPToolProvider(
                servers=settings.external_tools.mcp_servers,
                executor=_create_mcp_tool_executor(settings),
            )
        )
    return providers


def _create_web_tool_executor(settings: AgentSettings) -> WebToolExecutor:
    if settings.external_tools.web_executor == "http":
        return ControlledHTTPWebExecutor(
            allowed_hosts=settings.external_tools.web_allowed_hosts,
            timeout_ms=settings.external_tools.web_timeout_ms,
            max_fetch_bytes=settings.external_tools.web_max_fetch_bytes,
            fetch_enabled=settings.external_tools.web_executor == "http",
            search_endpoint_url=(
                settings.external_tools.web_search_endpoint_url
                if settings.external_tools.web_search_executor == "http_json"
                else None
            ),
        )
    if settings.external_tools.web_search_executor == "http_json":
        return ControlledHTTPWebExecutor(
            allowed_hosts=settings.external_tools.web_allowed_hosts,
            timeout_ms=settings.external_tools.web_timeout_ms,
            max_fetch_bytes=settings.external_tools.web_max_fetch_bytes,
            fetch_enabled=False,
            search_endpoint_url=settings.external_tools.web_search_endpoint_url,
        )
    return _UnavailableWebToolExecutor()


def _create_mcp_tool_executor(settings: AgentSettings) -> MCPToolExecutor:
    if settings.external_tools.mcp_executor == "http_json":
        return ControlledHTTPMCPToolExecutor(
            allowed_hosts=settings.external_tools.mcp_allowed_hosts,
            server_endpoints=_mcp_server_endpoints(settings),
            timeout_ms=settings.external_tools.mcp_timeout_ms,
            max_response_bytes=settings.external_tools.mcp_max_response_bytes,
        )
    return _UnavailableMCPToolExecutor()


def _mcp_server_endpoints(settings: AgentSettings) -> dict[str, str]:
    endpoints: dict[str, str] = {}
    for server in settings.external_tools.mcp_servers:
        if not server.enabled:
            continue
        metadata = server.metadata or {}
        endpoint_url = metadata.get("endpoint_url")
        if isinstance(endpoint_url, str) and endpoint_url.strip():
            endpoints[server.key] = endpoint_url.strip()
    return endpoints


def _create_workflow_capability_providers(
    settings: AgentSettings,
) -> list[WorkflowCapabilityProvider]:
    capabilities = settings.workflow_capabilities.capabilities
    if not capabilities:
        return []
    if settings.workflow_capabilities.executor == "http_json":
        if settings.workflow_capabilities.endpoint_url is None:
            return [_UnavailableWorkflowCapabilityProvider(capabilities)]
        return [
            ControlledHTTPWorkflowCapabilityProvider(
                capabilities=capabilities,
                endpoint_url=settings.workflow_capabilities.endpoint_url,
                allowed_hosts=settings.workflow_capabilities.allowed_hosts,
                timeout_ms=settings.workflow_capabilities.timeout_ms,
                max_response_bytes=settings.workflow_capabilities.max_response_bytes,
            )
        ]
    return [_UnavailableWorkflowCapabilityProvider(capabilities)]


def _create_store(settings: AgentSettings) -> AgentStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentStore(settings.sqlite_path)
    return InMemoryAgentStore()


def _create_event_store(settings: AgentSettings) -> AgentEventStore:
    if settings.persistence_backend == "sqlite":
        return SQLiteAgentEventStore(settings.sqlite_path)
    return InMemoryAgentEventStore()


class _UnavailableWebToolExecutor:
    async def execute(self, invocation: WebToolInvocation) -> WebToolResult:
        return WebToolResult(
            status="failed",
            error={"message": "Web tool executor is not configured"},
            redaction="none",
        )


class _UnavailableMCPToolExecutor:
    async def execute(self, invocation: MCPToolInvocation) -> MCPToolResult:
        return MCPToolResult(
            status="failed",
            error={"message": "MCP-like tool executor is not configured"},
            redaction="none",
        )


class _UnavailableWorkflowCapabilityProvider:
    def __init__(self, capabilities: list[WorkflowCapabilitySpec]) -> None:
        self._capabilities = capabilities

    def list_capabilities(self) -> list[WorkflowCapabilitySpec]:
        return self._capabilities

    async def invoke(self, invocation: object) -> WorkflowCapabilityResult:
        return WorkflowCapabilityResult(
            status="failed",
            error={"message": "Workflow capability executor is not configured"},
            redaction="none",
        )
