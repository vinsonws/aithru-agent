# Agent Skill Specification

Status: target skill spec

This document defines the structure, requirements, and rules for Agent Skills in Aithru Agent.

## Definition

```txt
Agent Skill = structured, reusable capability package with instructions, allowed tools, subagents, workspace/memory/sandbox/approval policies, and output expectations.
```

Skills are first-class product objects, not engine configurations or workflow nodes.

## Skill Package Layout

```txt
skills/
  builtin/                    read-only system packages
    skill_key/
      SKILL.md                frontmatter plus instructions
      references/             optional supplementary resources
      scripts/                optional support scripts
      examples/               optional input/output examples
  user/                       current-user private packages (database)
    skill_key/
      SKILL.md
      references/
      scripts/
      examples/
```

Two MVP sources:

- `builtin`: code-shipped, read-only, system provided.
- `user`: current user's private packages, stored in the database, editable.

Both sources expose the same `SkillPackage` contract. The registry is an index
over packages. The package body (`SKILL.md`) is the source of instructions.

The stage-1 backend still supports legacy `skill.json` manifests while new
packages converge on `SKILL.md`.

## Skill Metadata

- `key`: unique identifier
- `name`: display name (discovery only)
- `description`: brief description (discovery only)
- `version`: semantic version
- `status`: draft | published | deprecated
- `enabled`: true | false
- `owner`: org/user
- `permissions`: org/app scoped grants

## Policies

- WorkspacePolicy: read/write, sandbox mount, retention, quota
- MemoryPolicy: scope, visibility, retention, authz
- SandboxPolicy: allowed commands, resources, timeouts, network policy
- ApprovalPolicy: never | on_risk | always
- ToolPolicy: allowed tools, denied tools, risk levels, required scopes

## Input/Output Schema

- Optional JSON schema or custom validator
- Defines expected structure of input arguments and output artifacts

## Versioning and Publication

- Skills can be versioned independently
- Only published skills can be invoked in AgentRun
- Disabled skills are not resolved for execution even when published
- Draft skills can be used for testing but not Workbench nodes

## Skill Activation

- Skills are Pydantic AI deferred capabilities.
- `name` and `description` are discovery metadata only.
- The `SKILL.md` body is loaded only after the skill is selected or triggered by the runtime.
- User-selected skills (via `skill_id`) are active from run start.
- Unselected visible skills are deferred; the model may load them via Pydantic AI's `load_capability`.
- Aithru does not add a custom `skill.activate` business tool.
- The allowed tools list is an upper bound; workspace, memory, sandbox,
  approval, and subagent policy can further narrow the tools exposed to a run.
- Denied tools are removed from the run catalog even when they appear in the
  allowed list.
- Sandbox tools require an explicit enabled sandbox policy.
- Workspace `allowedPaths` is enforced by workspace tools at execution time.
- Approval policy contributes required risk approvals to the capability router.
- Active skill instructions are injected through a Pydantic AI capability
  runtime path; Pydantic AI and harness types are not part of the skill contract.

## Multi-Skill Policy Composition

When multiple skills are loaded in the same run, policies combine conservatively:

- `denied_tools` always removes tools.
- `allowed_tools` combines by intersection across loaded skills that define an
  allowlist.
- workspace, memory, sandbox, approval, and subagent policies use the strictest
  effective setting.

## Observability

- All skill execution events must emit `AgentStreamEvent` for run streaming
- Include skill start, step events, tool proposals, subagent spawn, completion
- Emit `skill.activated` events with trigger type (`explicit` or `pydantic_load_capability`)

## Guidelines

- Skills must not execute platform capabilities directly.
- All tool invocations go through the Capability Router:
  `Pydantic AI -> AithruToolset -> PydanticAIToolBridge -> Aithru Capability Router -> policy/scope/approval boundary -> concrete tool -> event/trace/artifact/redaction`
- Workspace writes and artifact creation go through the Workspace Provider
- Sandbox execution only via SandboxProvider interface
- Subagents are spawned via SubagentRunner interface

## Minimal implementation

- `SkillPackage` contract with `SKILL.md` parsing
- Registry entries are indexes over packages
- `builtin` and `user` as the only supported MVP sources
- Pydantic AI deferred capabilities for unselected skills
- Explicit `skill_id` for user-selected skills
- Tool policy enforced in both `AithruToolset.get_tools()` and `PydanticAIToolBridge.call_tool()`

## Acceptance criteria

- Skill is a reusable, self-contained capability
- Skill does not expose workflow DAG semantics
- Skill integrates with harness kernel through standard API
- Skill produces events for stream and artifacts
- Skill respects all policy and capability router boundaries
- Registry entries are indexes over packages, not the source of instructions
- Skills never execute tools directly
