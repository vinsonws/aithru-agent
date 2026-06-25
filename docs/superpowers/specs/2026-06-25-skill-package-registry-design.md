# Skill Package Registry Design

**Date**: 2026-06-25
**Status**: draft

## Problem

The current backend has useful Skill foundations, but the concepts are split:

- `backend/src/aithru_agent/skills` models product-level skills, registry
  entries, API listing, enablement, and file package loading.
- `backend/src/aithru_agent/agent/skills` models a separate progressive skill
  parser and heuristic activator.
- The built-in `deep-research` skill is still constructed as Python data rather
  than loaded from the same package shape as future user skills.
- The frontend Skills page can list and enable registry entries, but it does
  not yet present skills as standard skill packages.

The target is a smaller, standard model:

```txt
Agent Skill = package with SKILL.md metadata, delayed instructions, optional
resources, and Aithru policy.
```

Skills should be first-class Aithru harness capabilities, not workflow graphs,
not direct local execution privileges, and not Pydantic AI public API
contracts.

## Decision

Use a package-first Skill model with exactly two MVP sources:

```txt
builtin = system-provided, code-shipped, read-only packages
user    = current user's private packages, stored in the database, editable
```

Both sources expose the same package contract:

```txt
skill-key/
  SKILL.md                 required
  references/              optional, loaded on demand
  scripts/                 optional, executed only through Aithru tools
  assets/                  optional, used as controlled resources
  agents/openai.yaml       optional UI metadata
```

The registry is an index and management surface. The package is the source of
skill instructions and resources.

## Non-Goals

- Do not add organization-shared skills, marketplace skills, public publishing,
  or team libraries in this MVP.
- Do not add an Agent workflow graph editor, Agent-owned WorkflowSpec
  semantics, persisted plans-as-workflows, branch graphs, or schedulers.
- Do not expose unrestricted local files, scripts, browser automation,
  platform credentials, service tokens, or external network calls to model
  code through skills.
- Do not make Pydantic AI types part of the public Aithru skill API.
- Do not treat `allowed_tools` as a grant of privilege. It is an upper bound
  applied after actor scopes, run policy, approvals, and capability router
  checks.

## Package Contract

`SKILL.md` follows the standard skill shape:

```md
---
name: File Report
description: Use for concise reports from workspace files and evidence.
---

# File Report

Read the relevant files first. Then write a concise report...
```

Only the frontmatter metadata is used for discovery:

- `name`
- `description`

The markdown body is loaded only after the skill is selected or triggered by
the runtime. Additional Aithru policy can be stored beside the package or in
the registry index, but it must not replace the package body as the skill
source.

For MVP user-created skills, the database can store:

```txt
skill_key
owner_user_id
skill_md
resources_json
policy_json
enabled
created_at
updated_at
```

This is still a database-backed package, not a flat `instructions` row.

## Registry Index

The registry presents package metadata and management state:

```txt
id
key
source: builtin | user
owner_user_id: null for builtin, current user id for user skill
enabled
read_only
created_at
updated_at
metadata:
  name
  description
  optional UI metadata
policy:
  allowed_tools
  denied_tools
  allowed_subagents
  workspace_policy
  memory_policy
  sandbox_policy
  approval_policy
  input_schema
  output_schema
```

For MVP, visible skill keys must be unique for a user. A user-private skill
cannot reuse a built-in key. That keeps Pydantic AI capability ids stable and
unambiguous.

## Storage

Add a package store abstraction:

```txt
SkillPackageStore
  list_visible_packages(actor)
  get_visible_package(actor, key)
  save_user_package(actor, package)
  update_user_package(actor, key, patch)
  set_user_enabled(actor, key, enabled)
```

Implementations:

- `BuiltinSkillPackageStore`: reads code-shipped package folders and marks
  them read-only.
- `DatabaseUserSkillPackageStore`: persists current-user private packages.
- `CompositeSkillPackageStore`: merges built-in and user-private packages for
  the current actor.

The existing registry can wrap this store and continue to provide management
APIs, but new code should avoid treating registry entries as the skill body.

## API Surface

Keep existing list/detail routes where possible and add package-aware user
management routes:

```txt
GET  /api/skills
GET  /api/skills/{skill_key}
GET  /api/skill-registry
GET  /api/skill-registry/{skill_key}
POST /api/skill-registry/user
PATCH /api/skill-registry/user/{skill_key}
POST /api/skill-registry/{skill_key}/enable
POST /api/skill-registry/{skill_key}/disable
```

`POST /api/skill-registry/user` accepts form-level fields for MVP:

```txt
key
name
description
body
allowed_tools
denied_tools
policy fields
```

The backend renders those fields into a valid `SKILL.md` package and validates
the package before saving it. Later import/export can accept zip or folder
uploads without changing the runtime model.

## Pydantic AI Runtime Integration

Pydantic AI already has the correct progressive disclosure model:
on-demand capabilities. A capability with `defer_loading=True` appears to the
model only as a stable `id` and `description`. When the model decides it needs
the capability, Pydantic AI's framework-managed `load_capability` tool loads
the full instructions and records the loaded capability id in message history.

Therefore, every visible Aithru Skill Package maps to an Aithru-owned
Pydantic AI capability for the run:

```txt
AithruSkillCapability(
  id = "skill:{key}",
  description = "{name}: {description}",
  instructions = SKILL.md body,
  defer_loading = true unless explicitly selected
)
```

User-selected skills are not guessed. If `skill_id` is supplied on the run,
the selected skill is included as a non-deferred `AithruSkillCapability` for
that run. Its instructions and policy are active from the first model request.

Unselected visible skills are deferred. The model sees the catalog and chooses
whether to load one with `load_capability`. Aithru does not add a custom
`skill.activate` business tool.

## Runtime Policy

Pydantic AI controls when the model loads the skill body. Aithru controls what
real actions are allowed.

The runtime must derive an effective `AgentRunContext` from:

- actor and run scopes;
- static run policy;
- explicitly selected skill, if any;
- Pydantic AI `ctx.loaded_capability_ids`;
- policy from the corresponding Aithru skill packages.

That effective context must be used in both places:

1. `AithruToolset.get_tools(ctx)` when building model-visible tool definitions.
2. `PydanticAIToolBridge.call_tool(ctx, ...)` before prepare/execute through
   the capability router.

This prevents a prompt-only policy gap. Even if a model calls a tool by name,
the capability router sees the same effective skill policy and can deny the
call.

When multiple deferred skills are loaded in the same run, policies combine
conservatively:

- `denied_tools` always removes tools.
- `allowed_tools` combines by intersection across loaded skills that define an
  allowlist.
- workspace, memory, sandbox, approval, and subagent policies use the strictest
  effective setting.

The model should be instructed to load at most one primary skill unless the user
asks for a combined task. The enforcement rule remains conservative so loading
multiple skills cannot widen tool access.

## Tool Exposure

Skills do not execute tools directly.

All real actions continue through:

```txt
model / Pydantic AI
  -> AithruToolset
  -> PydanticAIToolBridge
  -> Aithru Capability Router
  -> policy / scope / approval boundary
  -> concrete local/external/workflow tool
  -> event / trace / artifact / redaction
```

Skill package resources are also controlled:

- `references/` can be exposed through read-only skill resource APIs or tools.
- `scripts/` can only run through sandbox/interpreter tools when the loaded
  skill and run policy allow it.
- `assets/` can be copied or referenced only through workspace/artifact tools.

The model never receives unrestricted filesystem paths or process execution
rights because a skill contains a script.

## Events And Trace

Emit auditable events for skill lifecycle:

```txt
skill.catalog.presented
skill.loaded
skill.activated
skill.resource.read
skill.resource.denied
skill.policy.applied
skill.policy.denied
```

For Pydantic AI deferred loading, an Aithru skill activation observer compares
new `ctx.loaded_capability_ids` against skill package ids during model request
hooks or event stream processing. It emits `skill.activated` once per run and
skill.

Event payloads should include:

```txt
skill_key
source
owner_user_id for user skills
trigger: explicit | pydantic_load_capability
policy summary
```

Do not log raw secrets, credentials, or full sensitive package resources.

## Frontend

The Skills manager shows packages, not workflow nodes.

MVP layout:

```txt
Filters
  Built-in
  My skills

List
  name
  description
  source
  enabled
  read_only
  allowed tools count
  updated_at

Detail
  SKILL.md metadata
  instructions preview
  references/scripts/assets summary
  allowed and denied tools
  workspace/memory/sandbox/approval policy
  runtime visibility
```

Actions:

- Built-in skill: view, enable, disable. Content is read-only.
- User skill: create, edit, enable, disable. Delete is out of scope for MVP;
  disable is the safe removal path.

The UI must not present skills as workflow graphs or editable execution DAGs.

## Migration

1. Move built-in `deep-research` to a built-in skill package folder.
2. Load built-in packages through `BuiltinSkillPackageStore`.
3. Convert `AgentSkill` registry entries into package index entries.
4. Replace the heuristic `SkillActivator` path with Pydantic AI deferred
   capabilities.
5. Keep legacy `skill.json` loading only as a compatibility import path that
   produces a package-shaped record.
6. Keep current run creation behavior for explicit `skill_id`, but implement it
   through package-backed skill loading.

## Testing

- Unit: parse `SKILL.md` frontmatter and body into package metadata and
  instructions.
- Unit: user skill keys cannot collide with built-in keys for the same user.
- Unit: built-in packages are read-only.
- Unit: user-private packages are visible only to their owner.
- Unit: Pydantic deferred skill capability has stable id, description, and
  `defer_loading=True`.
- Unit: explicit `skill_id` is active on the first model request.
- Unit: loaded skill policy filters `AithruToolset.get_tools`.
- Unit: loaded skill policy is enforced again in `PydanticAIToolBridge`.
- Integration: model can load a deferred user skill via Pydantic AI
  `load_capability` and receives the skill body.
- Integration: loaded skill emits `skill.activated`.
- Integration: a denied tool from a loaded skill is not exposed and is denied
  if called anyway.
- Integration: resume/approval paths preserve any needed Pydantic message
  history for already-loaded deferred capabilities within the run.

## Acceptance Criteria

- Built-in and user-private skills share one package contract.
- Registry entries are indexes over packages, not the source of instructions.
- Skill discovery uses `name` and `description` only.
- Skill body is loaded progressively through Pydantic AI on-demand capability
  semantics.
- User-selected skills are active from run start.
- Models never execute real actions directly through skills.
- Tool calls remain capability-router controlled, policy-aware, traceable, and
  redacted.
- Skills remain reusable agent capabilities, not workflow definitions.

## References

- Pydantic AI capabilities:
  <https://pydantic.dev/docs/ai/core-concepts/capabilities/>
- Pydantic AI tool search:
  <https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/#tool-search>
- Pydantic AI on-demand capabilities article:
  <https://pydantic.dev/articles/pydantic-ai-capabilities>
