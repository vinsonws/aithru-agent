# Skill Package Registry Design

Date: 2026-06-25
Status: superseded implementation details, product intent retained for native TypeScript backend

This document preserves the package-first skill decision. Implementation work
must follow the native TypeScript backend under `backend-ts/` and the current
skill spec in `docs/04-skill-spec.md`.

## Problem

Aithru Agent needs skills to be reusable product capabilities rather than
workflow graphs, direct local execution privileges, or provider-framework
objects.

The target model remains:

```txt
Agent Skill = package with SKILL.md metadata, delayed instructions, optional
resources, and Aithru policy.
```

## Decision

Use a package-first Skill model with two MVP sources:

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

## Native TS Runtime Integration

The native backend owns progressive disclosure:

```txt
model adapter
  -> native model turn loop
  -> skill registry / active skill context
  -> capability router
  -> policy / scope / approval boundary
  -> concrete tool
```

Rules:

- `SKILL.md` is the canonical instruction body.
- `name` and `description` are discovery metadata.
- `allowed_tools` is an upper bound, not a grant of privilege.
- Actor scopes, run policy, approval policy, and capability router checks still
  apply.
- Skill scripts and resources never execute directly; they are accessed only
  through Aithru tools.
- Skill activation emits `skill.activated` events.

## Non-Goals

- Do not add organization-shared skills, marketplace skills, public publishing,
  or team libraries in this MVP.
- Do not add an Agent workflow graph editor, Agent-owned `WorkflowSpec`
  semantics, persisted plans-as-workflows, branch graphs, or schedulers.
- Do not expose unrestricted local files, scripts, browser automation, platform
  credentials, service tokens, or external network calls to model code through
  skills.
- Do not make model-provider or framework types part of the public Aithru skill
  API.

## Acceptance

- Built-in and user skills use the same package contract.
- The registry indexes packages; it does not replace package contents.
- Skill policy constrains model-visible tools before a run and again at
  execution time.
- Skills remain Aithru harness capabilities, not workflow definitions.
