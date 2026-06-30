# Skill Package Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement package-backed Agent Skills with two MVP sources: read-only built-in skills and editable current-user private skills. Runtime skill discovery and loading must use Pydantic AI deferred capability semantics, while all real actions remain enforced by the Aithru Capability Router.

**Architecture:** Add a package layer under `aithru_agent.skills` that parses `SKILL.md`, stores built-in and user-private packages, exposes registry entries as indexes over packages, maps visible packages to Pydantic AI capabilities, and computes effective tool policy from explicit and loaded skills at both tool discovery and execution time.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Pydantic AI 1.107.0 capability APIs, pytest, React 19, TypeScript, TanStack Query.

## Global Constraints

- Preserve the repository boundary: skills are Agent Harness capabilities, not workflow definitions, graphs, schedulers, or persisted plans.
- Keep Pydantic AI types inside `backend/src/aithru_agent/agent` and `backend/src/aithru_agent/harness`; do not expose them as public Aithru API contracts.
- Use `SKILL.md` as the source of package instructions. Registry entries are indexes and management state.
- Expose only `builtin` and `user` as the supported MVP sources in new APIs and UI. Accept legacy registry rows without making them first-class runtime concepts.
- Do not give skills direct execution rights. Scripts, files, browser actions, network calls, workflow capabilities, and workspace writes must still pass through the Aithru Capability Router and its policies.
- Recompute policy in both `AithruToolset.get_tools(ctx)` and `PydanticAIToolBridge.call_tool(ctx, tool_name, tool_input)`; prompt-only policy is not sufficient.
- Combine multiple active skill policies conservatively: denied tools win, allowlists intersect, and workspace/memory/sandbox/approval/subagent restrictions never widen access.
- Preserve existing explicit `selected_skill_keys` behavior: if the user selects a skill for a run, that skill is active from the first model request.
- For unselected visible skills, let the model decide through Pydantic AI `load_capability`; do not add a custom `skill.activate` business tool.
- Keep user-private skills scoped to `org_id` plus `actor_user_id`.
- Do not log secrets, credentials, or full sensitive skill resources in stream events.

---

## Task 1: Add Package Domain And Parser

- [ ] Write tests for the package contract before implementation.

Files:

- `backend/tests/skills/test_skill_packages.py`
- `backend/src/aithru_agent/skills/packages.py`
- `backend/src/aithru_agent/skills/loader.py`
- `backend/src/aithru_agent/skills/__init__.py`

Test cases to add:

```python
def test_parse_skill_package_uses_frontmatter_for_discovery_and_body_for_instructions() -> None:
    package = parse_skill_package(
        key="file-report",
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md="""---
name: File Report
description: Use for concise reports from workspace files.
---

# File Report

Read the relevant files, then write a short report.
""",
        policy=AgentSkillConfiguration(
            instructions="",
            allowed_tools=["workspace.read_file", "artifact.create"],
            denied_tools=[],
            allowed_subagents=[],
        ),
    )

    assert package.key == "file-report"
    assert package.metadata.name == "File Report"
    assert package.metadata.description == "Use for concise reports from workspace files."
    assert "Read the relevant files" in package.instructions
    assert package.discovery_description == "File Report: Use for concise reports from workspace files."
```

```python
def test_render_user_skill_md_round_trips_metadata_and_body() -> None:
    skill_md = render_skill_md(
        name="File Report",
        description="Use for concise reports from workspace files.",
        body="# File Report\n\nWrite from evidence.",
    )

    package = parse_skill_package(
        key="file-report",
        org_id="org_1",
        owner_user_id="user_1",
        source=AgentSkillRegistrySource.USER,
        skill_md=skill_md,
        policy=AgentSkillConfiguration(instructions="", allowed_tools=[], allowed_subagents=[]),
    )

    assert package.metadata.name == "File Report"
    assert package.instructions == "# File Report\n\nWrite from evidence."
```

Implementation shape:

```python
class SkillPackageMetadata(AithruBaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class SkillPackage(AithruBaseModel):
    id: str
    org_id: str
    key: str
    source: AgentSkillRegistrySource
    owner_user_id: str | None = None
    skill_md: str
    metadata: SkillPackageMetadata
    instructions: str
    policy: AgentSkillConfiguration
    version: str = "0.1.0"
    status: AgentSkillStatus = AgentSkillStatus.PUBLISHED
    enabled: bool = True
    read_only: bool = False
    created_at: str
    updated_at: str

    @property
    def discovery_description(self) -> str:
        return f"{self.metadata.name}: {self.metadata.description}"
```

```python
def parse_skill_package(
    *,
    key: str,
    org_id: str,
    owner_user_id: str | None,
    source: AgentSkillRegistrySource,
    skill_md: str,
    policy: AgentSkillConfiguration,
    id: str | None = None,
    version: str = "0.1.0",
    status: AgentSkillStatus = AgentSkillStatus.PUBLISHED,
    enabled: bool = True,
    read_only: bool = False,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> SkillPackage:
    parsed = parse_skill_md(skill_md)
    metadata = SkillPackageMetadata(
        name=parsed.name,
        description=parsed.description,
    )
    now = created_at or utc_now()
    return SkillPackage(
        id=id or f"skill_{key.replace('-', '_')}",
        org_id=org_id,
        key=key,
        source=source,
        owner_user_id=owner_user_id,
        skill_md=skill_md,
        metadata=metadata,
        instructions=parsed.instructions,
        policy=policy.model_copy(update={"instructions": parsed.instructions}),
        version=version,
        status=status,
        enabled=enabled,
        read_only=read_only,
        created_at=now,
        updated_at=updated_at or now,
    )
```

Notes:

- Reuse `parse_skill_md` initially so existing policy section support is not lost.
- `FileSkillLoader` should delegate `SKILL.md` parsing to `parse_skill_package(key=skill_file.parent.name, skill_md=content, policy=policy).to_skill()` rather than duplicating parser logic.
- Add `AgentSkillRegistrySource.USER = "user"` in `backend/src/aithru_agent/domain/skill.py`. Keep existing legacy enum values readable for old tests and rows, but new writes should use `USER`.

---

## Task 2: Add Built-In And User Package Stores

- [ ] Write store tests for built-in read-only packages, user-private packages, and key collisions.

Files:

- `backend/src/aithru_agent/skills/package_store.py`
- `backend/src/aithru_agent/skills/registry.py`
- `backend/src/aithru_agent/domain/skill.py`
- `backend/tests/skills/test_skill_package_store.py`
- `backend/tests/skills/test_skill_registry.py`

Test cases to add:

```python
def test_user_package_keys_cannot_collide_with_builtin_keys() -> None:
    builtin = BuiltinSkillPackageStore([_package(key="deep-research", source="builtin")])
    users = InMemoryUserSkillPackageStore()
    store = CompositeSkillPackageStore(builtin=builtin, users=users)

    with pytest.raises(SkillRegistryConflictError, match="deep-research"):
        store.save_user_package(
            actor=_actor("org_1", "user_1"),
            package=_package(key="deep-research", source="user", owner_user_id="user_1"),
        )
```

```python
def test_user_packages_are_visible_only_to_the_owner() -> None:
    users = InMemoryUserSkillPackageStore()
    users.save_user_package(
        actor=_actor("org_1", "user_1"),
        package=_package(key="file-report", source="user", owner_user_id="user_1"),
    )

    assert [pkg.key for pkg in users.list_visible_packages(_actor("org_1", "user_1"))] == [
        "file-report"
    ]
    assert users.list_visible_packages(_actor("org_1", "user_2")) == []
```

Implementation shape:

```python
class SkillPackageStore(Protocol):
    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        raise NotImplementedError

    def get_visible_package(self, actor: SkillActor, key: str) -> SkillPackage | None:
        raise NotImplementedError

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        raise NotImplementedError

    def update_user_package(
        self,
        actor: SkillActor,
        key: str,
        patch: SkillPackagePatch,
    ) -> SkillPackage:
        raise NotImplementedError

    def set_user_enabled(self, actor: SkillActor, key: str, enabled: bool) -> SkillPackage:
        raise NotImplementedError
```

```python
class SkillActor(AithruBaseModel):
    org_id: str
    actor_user_id: str
```

```python
class CompositeSkillPackageStore:
    def list_visible_packages(self, actor: SkillActor) -> list[SkillPackage]:
        packages = [
            *self._builtin.list_visible_packages(actor),
            *self._users.list_visible_packages(actor),
        ]
        return sorted(packages, key=lambda package: (package.source, package.key))

    def save_user_package(self, actor: SkillActor, package: SkillPackage) -> SkillPackage:
        if self._builtin.get_visible_package(actor, package.key) is not None:
            raise SkillRegistryConflictError(f"Skill package already exists: {package.key}")
        return self._users.save_user_package(actor, package)
```

Persistence:

- `InMemoryUserSkillPackageStore` stores packages by `(org_id, owner_user_id, key)`.
- `SQLiteUserSkillPackageStore` stores package JSON in `agent_documents` with kind `skill_package_user` and id `"{org_id}:{owner_user_id}:{key}"`.
- Built-in packages are always `read_only=True`, `owner_user_id=None`, `source=builtin`.

Registry compatibility:

- `AgentSkillRegistryEntry` should add `owner_user_id: str | None = None`.
- `AgentSkillRegistryEntry.from_package(package)` should produce the management index.
- `AgentSkillRegistryEntry.to_skill()` remains supported for worker and API compatibility.
- Existing `register_skill(skill, source=AgentSkillRegistrySource.USER)` can keep accepting legacy payloads, but should persist them as `source=user` packages when called by the current MVP API path.

---

## Task 3: Move Deep Research Into A Built-In Package

- [ ] Replace the Python-only built-in skill with a built-in package folder.

Files:

- `backend/src/aithru_agent/skills/builtin_packages/deep-research/SKILL.md`
- `backend/src/aithru_agent/skills/builtin.py`
- `backend/tests/skills/test_builtin_skill_packages.py`
- `backend/tests/integration/test_api.py`

Package file content:

```md
---
name: Deep Research
description: Plan research, use controlled web tools, and produce cited report artifacts.
---

# Deep Research

Use this skill for evidence-backed research tasks.

Start with `research.create_plan` to create runtime todos and typed research sections.
Use `web.search` only when it is available in the current tool catalog.
Use `web.fetch` only for allowed sources that need more evidence.
Finish with `research.create_report` using structured sources and citations.
Do not create or persist workflow definitions.
```

Policy in code:

```python
DEEP_RESEARCH_POLICY = AgentSkillConfiguration(
    instructions="",
    when_to_use="research, deep research, evidence-backed report, cited web investigation",
    allowed_tools=[
        "research.create_plan",
        "web.search",
        "web.fetch",
        "research.create_report",
        "artifact.create",
        "artifact.finalize",
    ],
    denied_tools=[],
    allowed_subagents=[],
    workspace_policy=AgentWorkspacePolicy(
        read=True,
        write=True,
        allowed_paths=["/reports", "/workspace", "/artifacts"],
    ),
)
```

Acceptance checks:

- `BuiltInResearchSkillResolver().list_skills()` still returns one published `deep-research` skill.
- `/api/skills` still includes `deep-research`.
- `/api/skill-registry/deep-research` reports `source == "builtin"` and `read_only is True`.
- Disabling a built-in skill still returns `409`.

---

## Task 4: Add User Package API Routes

- [ ] Add package-aware create and update endpoints for current-user private skills.

Files:

- `backend/src/aithru_agent/api/routes/skills.py`
- `backend/src/aithru_agent/application/runtime.py`
- `backend/src/aithru_agent/skills/package_store.py`
- `backend/tests/integration/test_api.py`
- `frontend/src/lib/api/schema.d.ts` after OpenAPI regeneration
- `frontend/src/lib/api/types.ts` if new named schemas are exported
- `frontend/src/lib/api/resources.ts`

Request models:

```python
class CreateUserSkillPackageRequest(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    body: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_subagents: list[str] = Field(default_factory=list)
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    approval_policy: AgentApprovalPolicy | None = None
    input_schema: dict[str, object] | None = None
    output_schema: dict[str, object] | None = None
    enabled: bool = True
```

```python
class UpdateUserSkillPackageRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    body: str | None = Field(default=None, min_length=1)
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    allowed_subagents: list[str] | None = None
    workspace_policy: AgentWorkspacePolicy | None = None
    memory_policy: AgentMemoryPolicy | None = None
    sandbox_policy: AgentSandboxPolicy | None = None
    approval_policy: AgentApprovalPolicy | None = None
    input_schema: dict[str, object] | None = None
    output_schema: dict[str, object] | None = None
    enabled: bool | None = None
```

Route behavior:

```python
@router.post("/api/skill-registry/user", status_code=201, response_model=AgentSkillRegistryEntry)
async def create_user_skill_package(
    request: Request,
    body: CreateUserSkillPackageRequest,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    actor = _skill_actor_from_request(request, body_org_id=None)
    package = build_user_skill_package(actor, body)
    saved = deps.runtime.skill_package_store.save_user_package(actor, package)
    return AgentSkillRegistryEntry.from_package(saved)
```

```python
@router.patch("/api/skill-registry/user/{skill_key}", response_model=AgentSkillRegistryEntry)
async def update_user_skill_package(
    request: Request,
    skill_key: str,
    body: UpdateUserSkillPackageRequest,
    org_id: str | None = None,
    deps: ApiDependencies = Depends(api_deps),
) -> AgentSkillRegistryEntry:
    actor = _skill_actor_from_request(request, org_id)
    saved = deps.runtime.skill_package_store.update_user_package(actor, skill_key, patch)
    return AgentSkillRegistryEntry.from_package(saved)
```

Tests:

- Creating a user skill returns `source == "user"` and `owner_user_id == actor_user_id`.
- The same user can resolve the created skill through `/api/skills/{key}`.
- A different user in the same org cannot resolve the private skill.
- Attempting to create a user skill with a built-in key returns `409`.
- Attempting to patch a built-in skill through `/api/skill-registry/user/{key}` returns `404`.
- Existing enable/disable routes work for user skills and still reject built-ins.

---

## Task 5: Map Skill Packages To Pydantic AI Capabilities

- [ ] Replace heuristic progressive activation with Pydantic AI deferred capabilities.

Files:

- `backend/src/aithru_agent/agent/capabilities/skill_package.py`
- `backend/src/aithru_agent/agent/capabilities/__init__.py`
- `backend/src/aithru_agent/agent/deps.py`
- `backend/src/aithru_agent/agent/runtime.py`
- `backend/src/aithru_agent/worker/runner.py`
- `backend/tests/agent/test_skill_package_capability.py`
- `backend/tests/unit/agent/test_progressive_skills.py`

Capability implementation:

```python
def skill_capability_id(key: str) -> str:
    return f"skill:{key}"
```

```python
@dataclass
class AithruSkillCapability(AbstractCapability[PydanticAgentDeps]):
    package: SkillPackage
    explicit: bool = False

    def __post_init__(self) -> None:
        self.id = skill_capability_id(self.package.key)
        self.description = self.package.discovery_description
        self.defer_loading = not self.explicit

    def get_instructions(self) -> str:
        return "\n\n".join(
            [
                f"## Aithru Skill: {self.package.metadata.name}",
                self.package.instructions,
            ]
        )
```

Dependency additions:

```python
@dataclass(frozen=True)
class PydanticAgentDeps:
    run: AgentRun
    run_context: AgentRunContext
    event_writer: AgentEventWriter
    capability_router: AithruCapabilityRouter
    store: AgentStore
    skill: AgentSkill | None = None
    visible_skill_packages: dict[str, SkillPackage] = field(default_factory=dict)
    explicit_skill_key: str | None = None
```

Runtime assembly:

```python
def _skill_capabilities_for_run(deps: PydanticAgentDeps) -> list[AithruSkillCapability]:
    capabilities = []
    for package in deps.visible_skill_packages.values():
        capabilities.append(
            AithruSkillCapability(
                package=package,
                explicit=package.key == deps.explicit_skill_key,
            )
        )
    return capabilities
```

`AgentRuntime.build_agent()` should:

- Stop calling `_activate_progressive_skills(deps)`.
- Stop injecting `SkillInstructionCapability`.
- Add `AithruSkillCapability` instances to the `capabilities` list.
- Pass `AithruToolset(tool_specs=None, tool_callback=bridge.call_tool)` so tools are computed per Pydantic AI run context.
- Keep `SubagentTaskCapability` if the current effective toolset exposes `task`.

Worker behavior:

- Resolve explicit `run.selected_skill_keys` as today; unresolved explicit skills still fail before tools execute.
- Populate `visible_skill_packages` from the package store for the current actor.
- Set `explicit_skill_key` when `run.selected_skill_keys` is supplied.
- Convert the explicit package to `AgentSkill` for existing `deps.skill` compatibility until all older drivers are migrated.

Tests:

```python
def test_skill_package_capability_is_deferred_unless_explicit() -> None:
    package = _package(key="file-report")
    deferred = AithruSkillCapability(package=package)
    explicit = AithruSkillCapability(package=package, explicit=True)

    assert deferred.id == "skill:file-report"
    assert deferred.defer_loading is True
    assert deferred.description == "File Report: Use for reports."
    assert explicit.defer_loading is False
```

```python
@pytest.mark.asyncio
async def test_runtime_adds_visible_skills_as_pydantic_capabilities() -> None:
    agent = await runtime.build_agent(_deps_with_visible_packages(["file-report"]))
    root_capabilities = getattr(getattr(agent, "_root_capability"), "capabilities")

    assert any(
        getattr(capability, "id", None) == "skill:file-report"
        and getattr(capability, "defer_loading", None) is True
        for capability in root_capabilities
    )
```

---

## Task 6: Enforce Effective Skill Policy In Tool Discovery And Execution

- [ ] Add a single policy composition helper and use it in both tool listing and tool execution.

Files:

- `backend/src/aithru_agent/agent/skill_policy.py`
- `backend/src/aithru_agent/agent/capabilities/toolset.py`
- `backend/src/aithru_agent/agent/tools/bridge.py`
- `backend/src/aithru_agent/harness/context_builder.py`
- `backend/tests/agent/test_skill_policy_context.py`
- `backend/tests/agent/test_aithru_toolset.py`
- `backend/tests/integration/test_pydantic_tool_bridge.py`
- `backend/tests/integration/test_skill_policy.py`

Implementation shape:

```python
def active_skill_keys(ctx: RunContext[PydanticAgentDeps]) -> list[str]:
    keys: list[str] = []
    explicit = ctx.deps.explicit_skill_key
    if explicit:
        keys.append(explicit)
    for capability_id in sorted(ctx.loaded_capability_ids):
        if capability_id.startswith("skill:"):
            keys.append(capability_id.removeprefix("skill:"))
    return list(dict.fromkeys(keys))
```

```python
def effective_run_context(ctx: RunContext[PydanticAgentDeps]) -> AgentRunContext:
    packages = [
        ctx.deps.visible_skill_packages[key]
        for key in active_skill_keys(ctx)
        if key in ctx.deps.visible_skill_packages
    ]
    return compose_skill_run_context(ctx.deps.run_context, packages)
```

```python
def compose_skill_run_context(
    base: AgentRunContext,
    packages: Sequence[SkillPackage],
) -> AgentRunContext:
    if not packages:
        return base
    allowed_tools = _compose_allowed_tools(base.allowed_tools, [pkg.policy for pkg in packages])
    denied_tools = {tool for pkg in packages for tool in pkg.policy.denied_tools}
    if allowed_tools is not None:
        allowed_tools = [tool for tool in allowed_tools if tool not in denied_tools]
    return base.model_copy(
        update={
            "allowed_tools": allowed_tools,
            "allowed_subagents": _compose_allowed_subagents(base.allowed_subagents, packages),
            "workspace_allowed_paths": _compose_workspace_paths(base.workspace_allowed_paths, packages),
            "sandbox_policy": _compose_sandbox_policy(base.sandbox_policy, packages),
            "require_approval_for_risk": _compose_approval_risks(base.require_approval_for_risk, packages),
        }
    )
```

`AithruToolset._tool_specs(ctx)`:

```python
run_context = effective_run_context(ctx)
descriptors = await ctx.deps.capability_router.list_tools(run_context)
return [
    (
        descriptor,
        await ctx.deps.capability_router.requires_approval_for_tool(descriptor.name, run_context),
    )
    for descriptor in descriptors
]
```

`PydanticAIToolBridge.call_tool(ctx, tool_name, tool_input)`:

```python
run_context = effective_run_context(ctx)
prepared = await self._capability_router.prepare_tool_call(request, run_context)
descriptor = await self._capability_router.get_tool_descriptor(tool_name, run_context)
result = await self._capability_router.execute_tool_call(request, run_context)
```

Tests:

- With no explicit or loaded skill, the base run context exposes base tools.
- With explicit `file-report`, the first model request exposes only that skill's allowed tools.
- With `ctx.loaded_capability_ids == {"skill:file-report"}`, `AithruToolset.get_tools(ctx)` exposes only that skill's allowed tools.
- If a tool is denied by the loaded skill, `PydanticAIToolBridge.call_tool(ctx, tool_name, tool_input)` emits `tool.denied` and returns the denial payload.
- If two loaded skills have allowlists, only the intersection is visible.
- If a loaded skill denies a tool that another loaded skill allows, the tool is not visible.

---

## Task 7: Emit Skill Lifecycle Events

- [ ] Emit auditable events for explicit and Pydantic-loaded skills.

Files:

- `backend/src/aithru_agent/agent/capabilities/skill_package.py`
- `backend/src/aithru_agent/agent/runtime.py`
- `backend/src/aithru_agent/stream` only if event helper types need updates
- `backend/tests/agent/test_skill_package_capability.py`
- `backend/tests/integration/test_skill_policy.py`

Implementation shape:

```python
@dataclass
class AithruSkillActivationObserver(AbstractCapability[PydanticAgentDeps]):
    def __post_init__(self) -> None:
        self.id = "aithru-skill-activation-observer"
        self.defer_loading = False

    async def before_model_request(
        self,
        ctx: RunContext[PydanticAgentDeps],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        active = active_skill_keys(ctx)
        already_emitted = ctx.deps.emitted_skill_activation_keys
        for key in active:
            if key in already_emitted:
                continue
            package = ctx.deps.visible_skill_packages.get(key)
            if package is None:
                continue
            await ctx.deps.event_writer.write(
                run_id=ctx.deps.run.id,
                thread_id=ctx.deps.run.thread_id,
                type="skill.activated",
                source={"kind": "harness"},
                visibility="debug",
                payload={
                    "skill_key": key,
                    "source": package.source,
                    "owner_user_id": package.owner_user_id,
                    "trigger": "explicit" if key == ctx.deps.explicit_skill_key else "pydantic_load_capability",
                    "policy": {
                        "allowed_tools": package.policy.allowed_tools,
                        "denied_tools": package.policy.denied_tools,
                    },
                },
            )
            already_emitted.add(key)
        return request_context
```

Dependency addition:

```python
emitted_skill_activation_keys: set[str] = field(default_factory=set)
```

Tests:

- Explicit `selected_skill_keys` emits one `skill.activated` event with `trigger == "explicit"`.
- Deferred loaded skill emits one `skill.activated` event with `trigger == "pydantic_load_capability"`.
- Repeated model requests do not duplicate the event for the same skill.
- Event payload does not include the full `SKILL.md` body.

---

## Task 8: Update Runtime Tests From Heuristic Triggering To Deferred Capability Loading

- [ ] Replace old progressive heuristic expectations with Pydantic capability expectations.

Files:

- `backend/tests/unit/agent/test_progressive_skills.py`
- `backend/tests/agent/test_skill_capability.py`
- `backend/tests/integration/test_skill_policy.py`
- `backend/tests/integration/test_pydantic_driver.py`

Changes:

- Keep parser coverage for policy sections if `parse_skill_md` remains as the package parser foundation.
- Replace `test_agent_runtime_activates_progressive_skill_and_filters_tools` with a test that constructs a `RunContext` containing `loaded_capability_ids={"skill:report-helper"}` and asserts the toolset filters tools.
- Add an integration test for explicit skill activation through `selected_skill_keys`.
- Add an integration test for Pydantic-loaded skill behavior. If `TestModel` cannot reliably exercise framework-managed `load_capability`, test the Aithru boundary directly by creating a `RunContext` with `loaded_capability_ids` and asserting the same visible tools and bridge denial behavior. Keep one smoke test around Pydantic capability construction.

Example replacement test:

```python
@pytest.mark.asyncio
async def test_loaded_skill_policy_filters_aithru_toolset() -> None:
    deps = await _deps_with_visible_packages(
        [_package(key="report-helper", allowed_tools=["workspace.list_files"])]
    )
    ctx = RunContext(
        deps=deps,
        model=TestModel(),
        usage=RunUsage(),
        loaded_capability_ids={"skill:report-helper"},
    )

    tools = await AithruToolset().get_tools(ctx)

    assert list(tools) == ["workspace.list_files"]
```

---

## Task 9: Update Frontend Skills Manager

- [ ] Present skills as built-in and user-private packages.

Files:

- `frontend/src/features/admin/SkillsPage.tsx`
- `frontend/src/lib/api/resources.ts`
- `frontend/src/lib/api/schema.d.ts`
- `frontend/src/lib/api/types.ts`
- `frontend/src/i18n/resources/en/skills.json`
- `frontend/src/i18n/resources/zh/skills.json`
- `frontend/tests/settings-tabs.test.mjs`
- `frontend/tests/skills-page.test.mjs`

UI behavior:

- Show source as `Built-in` or `My skill`.
- Show `read_only` and disable content-edit actions for built-ins.
- Add a create form for user skills with fields: key, name, description, body, allowed tools, denied tools, enabled.
- Keep enable/disable controls for both sources, but built-in attempts must show the API error when the backend rejects read-only changes.
- Do not present skills as workflow nodes, graph branches, schedules, or execution plans.

API client additions:

```ts
export const skillsApi = {
  createUser: (body: CreateUserSkillPackageRequest) =>
    apiRequest<AgentSkillRegistryEntry>("/api/skill-registry/user", {
      method: "POST",
      body,
    }),
  updateUser: (key: string, body: UpdateUserSkillPackageRequest) =>
    apiRequest<AgentSkillRegistryEntry>(`/api/skill-registry/user/${key}`, {
      method: "PATCH",
      body,
    }),
};
```

i18n keys:

```json
{
  "builtin": "Built-in",
  "user": "My skill",
  "createUserSkill": "Create skill",
  "editUserSkill": "Edit skill",
  "readOnly": "Read-only",
  "description": "Description",
  "body": "Instructions"
}
```

Frontend tests:

- Skills page renders source labels for `builtin` and `user`.
- Create form calls `/api/skill-registry/user`.
- Built-in rows do not show edit actions.
- User rows show edit actions.

---

## Task 10: Update Documentation And Verification

- [ ] Update docs to match the implemented package-backed runtime.

Files:

- `docs/04-skill-spec.md`
- `docs/00-agent-harness-design.md`
- `README.md` only if repository positioning text changes
- `backend/README.md` only if backend ownership/API descriptions change

Documentation updates:

- Replace `public/custom` language with `builtin/user`.
- State that `name` and `description` are discovery metadata and the body is progressively loaded.
- Document explicit `selected_skill_keys` as active from run start.
- Document unselected skills as Pydantic AI deferred capabilities.
- State that skills never execute tools directly and all real actions pass through the Aithru Capability Router.
- Document conservative multi-skill policy composition.

Verification commands:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

```bash
cd frontend
npm test
npm run typecheck
```

Additional focused commands during development:

```bash
cd backend
uv run pytest tests/skills/test_skill_packages.py tests/skills/test_skill_package_store.py
uv run pytest tests/agent/test_skill_package_capability.py tests/agent/test_skill_policy_context.py
uv run pytest tests/integration/test_skill_policy.py
```

```bash
cd frontend
npm test -- tests/skills-page.test.mjs
```

Final acceptance:

- Built-in and user-private skills share one package contract.
- User-private skills are editable and scoped to the current user.
- Registry entries are indexes over packages, not the source of instructions.
- Pydantic AI deferred capabilities are the model-decided skill loading path.
- Explicit `selected_skill_keys` remains supported and active from the first request.
- Tool exposure and tool execution both use the same effective skill policy.
- All real tool actions still pass through the Aithru Capability Router.
- Backend verification commands pass, or any failures are documented with the failing test names and error causes.
- Frontend tests and typecheck pass if frontend code is changed.
