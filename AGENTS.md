# AGENTS.md

This file gives coding agents working in `vinsonws/aithru-agent` the repository rules.

Read this before changing code or docs.

## Repository direction

`aithru-agent` is being redesigned as an Aithru-native AI harness.

Target direction:

```txt
Aithru Agent = platform-hosted AI harness for skills, tools, workspace files, subagents, controlled execution, approvals, artifacts, memory, and traceable intelligent work.
```

The existing engine-based packages remain useful primitives, but they are not the final product architecture.

Primary design doc:

```txt
docs/00-agent-harness-design.md
```

## Hard boundaries

Aithru has one formal workflow system:

```txt
WorkflowSpec in Aithru Core, surfaced by Aithru Workbench.
```

Agent runtime todos, plans, subagents, workspace operations, and tool-call sequences are harness state, not workflow definitions.

Do not add:

- an Agent workflow graph editor;
- Agent-owned WorkflowSpec semantics;
- Agent-owned graph branch semantics;
- Agent-owned workflow scheduler behavior;
- persisted AgentPlan-as-workflow definitions;
- drag-and-drop node/edge editing for Agent plans.

## Capability boundary

Models may propose tool calls. They must not execute real actions directly.

All real actions must pass through an Aithru capability boundary:

```txt
model proposal
  -> Agent Harness
  -> skill/tool policy
  -> Aithru Capability Router or AgentHost
  -> platform/core/workbench permission and approval boundary
  -> concrete executor
  -> trace/artifact/redaction
```

Do not expose unrestricted local system access, browser automation, external network calls, database access, Workbench internals, platform credentials, or service tokens to model code.

## Dependency direction

Keep dependency direction clear:

```txt
Agent may depend on Core public contracts.
Core must not depend on Agent packages.
Workbench may call Agent through explicit node/API boundaries.
Agent may call Workbench through explicit API/tool boundaries.
```

## Package ownership

Current packages:

```txt
packages/
  agent-core/             shared harness contracts and types
  agent-stream/           AgentStreamEvent protocol and in-memory implementations
  agent-skills/           Skill manifest parsing, validation, and conversion
  agent-workspace/        AgentWorkspaceProvider interface and InMemoryWorkspaceProvider
  agent-tools/            AithruCapabilityRouter, StaticCapabilityRouter, tool adapters
  agent-harness/          NativeHarnessEngine, ScriptedModelPort, AgentModelPort
```

Package meanings:

- `agent-core`: Pure TypeScript contract types. No runtime dependencies. No Node-only APIs.
- `agent-stream`: Event protocol envelope, InMemoryEventStore, EventBus, EventWriter, SSE format helper.
- `agent-skills`: Skill manifest definitions, parsing, validation, and AgentSkill conversion.
- `agent-workspace`: Workspace provider abstractions. InMemoryWorkspaceProvider for test/dev.
- `agent-tools`: Capability Router interface and implementation. Tool adapters for workspace, search, etc.
- `agent-harness`: Harness engine with NativeHarnessEngine. ScriptedModelPort for testing without real LLM.

Future target packages may include:

```txt
agent-subagents
agent-sandbox
agent-memory
node-agent
```

Do not create these packages casually. If adding them, update docs and README first.

## Naming rules

Prefer these product names:

- Agent Harness
- Agent Thread
- Agent Skill
- Agent Run
- Agent Todo
- Agent Workspace
- Agent Tool
- Subagent
- Sandbox / Interpreter
- Memory
- Artifact
- Approval

Avoid these labels unless referring to a real Aithru Core `WorkflowSpec`:

- Agent workflow
- Agent workflow graph
- Agent graph editor
- sub-workflow
- save AgentPlan as workflow

If a feature becomes a reusable, user-editable, versioned graph, it belongs in Workbench/Core, not Agent.

## Tool and controlled execution rules

Tool calls must be policy-aware and traceable.

When adding tool-related code:

- define risk level;
- define required scopes;
- validate allowed tools from skill/run policy;
- route through `AgentHost.callTool` or the future capability router;
- preserve event order;
- produce inspectable trace events;
- redact sensitive inputs and outputs where needed;
- require approval for risky operations;
- avoid logging tokens, secrets, credentials, or raw sensitive payloads.

Controlled code or data processing environments must be explicit:

- keep implementation optional and behind an interface;
- treat file writes, external network access, process execution, and package installation as risky operations;
- make approval and audit requirements visible in contracts and tests.

## Workbench integration rules

Workbench may call Agent as a formal workflow node.

Recommended future direction:

```txt
agent.skill
agent.task
```

The Workbench graph remains the formal workflow. Agent owns only the intelligent harness behavior inside the node.

Agent may call Workbench workflows as tools:

```txt
workbench.runWorkflow
```

Agent must not import Workbench internals, schedule workflow graphs, or redefine workflow run persistence.

Agent may generate `WorkflowSpec` draft artifacts, but Workbench must validate, save, version, and run them.

## Frontend rules

Agent frontend should be a Platform hosted app, not a standalone global shell.

It should focus on:

```txt
Chat
Skills
Workspace
Runs
Artifacts
Approvals
Tools
Memory
Settings
```

It must not become a workflow graph editor.

If building UI:

- use the Aithru frontend constraints from `aithru-docs`;
- preserve Platform hosted app boundaries;
- do not duplicate platform org/user/app switcher chrome;
- show mock vs real execution clearly;
- show permission, approval, and recovery states explicitly;
- never persist secrets in browser storage.

## Documentation rules

When changing design or boundaries:

1. Update `docs/00-agent-harness-design.md`.
2. Update `README.md` if repository positioning changes.
3. Update package READMEs if package-level ownership changes.
4. Update examples only after the design is clear.
5. Avoid code changes that imply a new architecture without docs.

## Verification commands

Run these before finishing meaningful code changes:

```bash
pnpm typecheck
pnpm build
pnpm test
```

When changing examples or runtime behavior, also run the harness example:

```bash
pnpm example:harness-basic
```

## Pre-merge checklist

- [ ] The change reinforces Agent as an AI harness, not a workflow editor.
- [ ] Skills remain reusable agent capabilities, not DAGs.
- [ ] Todos/runtime plans remain runtime state, not workflow definitions.
- [ ] Models do not execute tools directly.
- [ ] Real tools and controlled execution are capability-boundary controlled.
- [ ] Workbench integration uses explicit node/API/tool boundaries.
- [ ] Core does not depend on Agent.
- [ ] Sensitive values are not logged or persisted insecurely.
- [ ] Typecheck/build/tests pass or failures are documented honestly.
