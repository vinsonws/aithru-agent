# Agent Skill Progressive Disclosure Design

Date: 2026-06-30
Status: draft

## Problem

The native TypeScript backend currently treats a single selected skill key as the active
skill on `AgentRun`. That is too narrow for Aithru Agent's target model:

- a user may explicitly request more than one skill;
- the model should see available skills as lightweight discovery metadata;
- the model should be able to request skill loading during a run;
- loaded skills must affect instructions, tool visibility, and tool execution
  policy;
- all skill loading must stay inside the Aithru capability boundary.

## Decision

Remove the legacy run skill field outright. Do not preserve API, contract, persistence, or
frontend compatibility for it.

Replace it with run-local active skill state:

```txt
selected_skill_keys  = user/UI/slash-selected skills loaded at run start
visible_skill_catalog = metadata for skills visible to the actor
loaded_skill_keys    = skills whose full instructions are loaded for this run
```

`selected_skill_keys` and `loaded_skill_keys` are arrays. A run can have zero,
one, or many active skills.

## Non-Goals

- Do not add Agent-owned workflow graphs, WorkflowSpec semantics, graph branch
  semantics, or workflow scheduler behavior.
- Do not expose skill files, scripts, resources, local filesystem access, MCP,
  browser automation, or network access directly to model code.
- Do not build a separate LLM classifier to choose skills before the run.
- Do not use keyword heuristics as the primary activation model.
- Do not load every `SKILL.md` body into the first model request.

## Concepts

### Skill Catalog Entry

The model may see catalog entries before loading a skill:

```ts
type SkillCatalogEntry = {
  key: string;
  name: string;
  description: string | null;
  source: "builtin" | "user" | "registry";
  version: string;
};
```

Catalog entries do not include the `SKILL.md` body or resource contents.

### Loaded Skill

A loaded skill is a resolved skill package plus activation metadata:

```ts
type LoadedSkill = {
  key: string;
  trigger: "explicit" | "slash" | "model_load";
  loaded_at: string;
};
```

The event stream is the durable source of activation history. Snapshot builders
may project `loaded_skill_keys` from `skill.activated` events.

## Run Creation

`CreateRunRequest` accepts:

```ts
selected_skill_keys?: string[] | null;
```

Rules:

- unknown selected skills reject the request;
- disabled or unpublished skills reject the request;
- duplicate keys are removed while preserving order;
- selected skills are loaded before the first model turn;
- The legacy run skill field is removed from request and response schemas.

## Model Turn Flow

Each model turn receives:

1. normal run/thread context;
2. visible skill catalog metadata;
3. full instructions for currently loaded skills;
4. tools filtered by the effective policy of loaded skills.

The model can request another skill through a controlled harness action:

```txt
skill.load({ key: "deep-research" })
```

`skill.load` is not a direct local action. It routes through the Aithru
capability boundary:

```txt
model request
  -> native model turn loop
  -> skill load request
  -> skill resolver / visibility check
  -> policy check
  -> skill.activated event
  -> next model turn includes full skill instructions
```

## Context Packet

Replace:

```ts
active_skill_key: string | null
```

with:

```ts
active_skill_keys: string[]
visible_skill_count: number
```

The context packet stats never include full skill instructions.

## Policy Composition

Policy is computed from all loaded skills plus the base run policy.

Rules:

- `denied_tools` is the union across base policy and all loaded skills.
- If any loaded skill defines `allowed_tools`, tool visibility is restricted to
  the intersection of those allowlists and the base allowlist.
- A denied tool always wins over an allowed tool.
- Workspace, memory, sandbox, approval, and subagent policies use the strictest
  effective setting available.
- Tool listing and tool execution use the same effective policy helper.

Most general-purpose skills should not define `allowed_tools`; otherwise two
unrelated loaded skills can accidentally intersect to an empty toolset.

## Skill Resources

`SKILL.md` may reference `references/`, `scripts/`, `assets/`, and examples.
Those resources are progressively disclosed after the skill is loaded.

Rules:

- resource metadata can be listed in the catalog;
- resource contents are fetched through controlled Aithru tools;
- scripts never execute directly from the skill package;
- resource reads and executions emit traceable events.

## Events

Emit one `skill.activated` event per loaded skill key per run:

```json
{
  "type": "skill.activated",
  "payload": {
    "key": "deep-research",
    "trigger": "model_load",
    "source": "builtin",
    "version": "0.0.0",
    "policy": {
      "allowed_tools": [],
      "denied_tools": []
    }
  }
}
```

The payload must not include the full `SKILL.md` body or resource contents.

Rejected load attempts emit an audit/debug event with the key and reason, but
not private skill contents.

## API And Persistence Changes

Remove the legacy run skill field from:

- `AgentRun`;
- `CreateRunRequest`;
- SQLite `runs` table;
- in-memory store run shape;
- OpenAPI and generated frontend types;
- run list filters;
- frontend composer request bodies.

Add:

- `selected_skill_keys` to `CreateRunRequest`;
- projected `active_skill_keys` to run snapshot/read models;
- optional `skill_catalog` endpoint/read model for UI selection.

No compatibility shim is required. Old persisted rows with the legacy run skill field can fail
fast during migration or be dropped in local development stores.

## Frontend

The composer can support two paths:

- explicit selection: user picks zero or more skills;
- slash selection: `/skill-key task...` maps to `selected_skill_keys`.

The run inspector shows loaded skills from `skill.activated` events, not from a
single run field.

## Testing

Required coverage:

- creating a run with selected skills loads all selected skill instructions;
- unknown selected skills reject run creation;
- a model `skill.load` request loads a visible skill and emits
  `skill.activated`;
- repeated load of the same skill does not duplicate activation;
- multiple loaded skills compose tool policy conservatively;
- tool listing and tool execution use the same composed policy;
- context packet stats expose keys/counts but not skill bodies;
- The legacy run skill field is absent from contracts, persistence, API responses, and
  frontend request bodies.

## Migration Order

1. Add multi-skill types and policy composition helpers.
2. Remove the legacy run skill field from contracts and persistence.
3. Update run creation to accept `selected_skill_keys`.
4. Project active skills from `skill.activated` events.
5. Add controlled `skill.load`.
6. Update frontend composer and inspector.
7. Delete the temporary single-skill runtime-load code.
