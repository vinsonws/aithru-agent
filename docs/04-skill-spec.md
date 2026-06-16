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
  skill_key/
    skill.yaml        # metadata, version, owner, description
    instructions.md   # instructions and guidance
    when-to-use.md    # guidance for invocation
    examples/         # optional input/output examples
    templates/        # optional prompt templates or file templates
    rubrics/          # optional scoring/evaluation guidelines
    resources/        # optional supplementary resources
```

## Skill Metadata

- `key`: unique identifier
- `name`: display name
- `description`: brief description
- `version`: semantic version
- `status`: draft | published | deprecated
- `owner`: org/user
- `permissions`: org/app scoped grants

## Policies

- WorkspacePolicy: read/write, sandbox mount, retention, quota
- MemoryPolicy: scope, visibility, retention, authz
- SandboxPolicy: allowed commands, resources, timeouts, network policy
- ApprovalPolicy: never | on_risk | always
- ToolPolicy: allowed tools, risk levels, required scopes

## Input/Output Schema

- Optional JSON schema or custom validator
- Defines expected structure of input arguments and output artifacts

## Versioning and Publication

- Skills can be versioned independently
- Only published skills can be invoked in AgentRun
- Draft skills can be used for testing but not Workbench nodes

## Skill Activation

- Skills may be loaded on-demand by the Harness Kernel
- Context loading should be progressive to avoid context window bloat
- Activation may trigger middleware hooks (workspace, memory, event logging)
- The allowed tools list is an upper bound; workspace, memory, sandbox,
  approval, and subagent policy can further narrow the tools exposed to a run
- Sandbox tools require an explicit enabled sandbox policy
- Workspace `allowedPaths` is enforced by workspace tools at execution time
- Approval policy contributes required risk approvals to the capability router

## Observability

- All skill execution events must emit `AgentStreamEvent` for run streaming
- Include skill start, step events, tool proposals, subagent spawn, completion

## Guidelines

- Skills must not execute platform capabilities directly
- All tool invocations go through the Capability Router
- Workspace writes and artifact creation go through the Workspace Provider
- Sandbox execution only via SandboxProvider interface
- Subagents are spawned via SubagentRunner interface

## Minimal implementation

- YAML or JSON manifest
- Instructions and optional examples
- Allowed tools list
- Version and status
- Basic policy fields (workspace, memory, sandbox, approval)
- Hook for skill activation middleware

## Acceptance criteria

- Skill is a reusable, self-contained capability
- Skill does not expose workflow DAG semantics
- Skill integrates with harness kernel through standard API
- Skill produces events for stream and artifacts
- Skill respects all policy and capability router boundaries
