# DeerFlow 2.0 Benchmark for Aithru Agent

Status: target capability benchmark

This document uses DeerFlow 2.0 as a benchmark for the target shape of Aithru Agent.

It does not mean Aithru Agent should copy DeerFlow code or depend on DeerFlow directly. The goal is to define the minimum product and architecture maturity that Aithru Agent should eventually reach as an AI harness.

## Benchmark statement

```txt
Aithru Agent should reach at least DeerFlow 2.0-level harness capability,
while replacing DeerFlow's local-trusted execution assumptions with Aithru Platform,
Aithru Core, and Aithru Workbench permission and capability boundaries.
```

Aithru Agent should be:

```txt
DeerFlow-like harness shape
+ Aithru Platform identity/authz/audit
+ Aithru Core capability contracts
+ Aithru Workbench workflow integration
+ Aithru-specific redaction, approval, and delegation boundaries
```

## Why DeerFlow matters

DeerFlow 2.0 is useful as a reference because it is not just a deep research demo. It represents a broader SuperAgent / AI harness shape:

- lead agent;
- skills;
- tools;
- subagents;
- sandboxed workspace;
- file operations;
- memory;
- context engineering;
- streaming gateway;
- full-stack UI;
- long-running task orientation.

This maps closely to the Aithru Agent target direction.

The key lesson is:

```txt
Agent is not an engine.
Agent is an execution environment for intelligent work.
```

## Non-goal: copying DeerFlow directly

Aithru Agent must not simply copy DeerFlow's runtime assumptions.

Aithru Agent is a Platform subsystem. It must preserve:

- organization context;
- user/service/delegated actor identity;
- app manifest permissions;
- platform grants;
- service clients and token exchange;
- connection policies;
- Aithru Core tool policy;
- Workbench workflow boundaries;
- audit events;
- redaction;
- approval gates;
- deployable server boundaries.

DeerFlow is a benchmark for harness completeness. Aithru defines the enterprise and platform control plane.

## Capability matrix

| Capability | DeerFlow-like expectation | Aithru Agent target |
| --- | --- | --- |
| Lead agent | One main agent coordinates the task. | `AgentHarness` owns run loop, context, todos, tools, subagents, approvals, artifacts, and streaming. |
| Chat thread | User interacts with an agent over time. | `AgentThread` + `AgentMessage` are first-class product objects under `orgId` and `actorUserId`. |
| Skills | Structured reusable agent capabilities. | `AgentSkill` is a real package/manifest concept with instructions, when-to-use, allowed tools, subagents, policies, examples, and output expectations. |
| Skill activation | Load relevant skill context only when useful. | `SkillResolver` and `SkillActivationMiddleware` choose explicit/user-selected or inferred skills without bloating context. |
| Todos / planning | Agent tracks multi-step progress. | `AgentTodo` is runtime state used for UI, trace, and recovery. It is not a Workbench node or `WorkflowSpec`. |
| Workspace filesystem | Agent reads/writes task files. | `AgentWorkspace` provides scoped virtual files, snapshots, diffs, artifacts, upload handling, and retention policy. |
| Outputs / artifacts | Agent produces durable outputs. | `AgentArtifact` supports reports, markdown, JSON, patches, files, decisions, charts, and `workflow_draft` artifacts. |
| Tools | Agent can call search/fetch/file/code/custom tools. | All tools are `AgentToolDescriptor` entries routed through `AithruCapabilityRouter`. |
| Sandbox | Code/file execution happens in an isolated environment. | `AgentSandboxProvider` is an explicit adapter. File writes, process execution, package install, and network access are policy-gated. |
| Subagents | Lead agent can spawn focused workers. | `SubagentSpec` and `SubagentRun` support scoped context, scoped tools, async execution, cancellation, and result merging. |
| Memory | Agent can use long-term state. | `AgentMemoryProvider` supports scoped memory with source, owner, confidence, visibility, retention, and authz policy. |
| Context engineering | Keep context useful and bounded. | `ContextBuilder` manages thread summary, skill context, workspace references, artifact summaries, tool result compression, and subagent isolation. |
| Streaming | UI sees live progress. | `AgentStreamEvent` is an append-only event stream covering message deltas, todos, tools, sandbox, workspace, artifacts, approvals, subagents, and run lifecycle. |
| Human approval | Risky actions can pause. | `ApprovalGateway` handles tool/workspace/sandbox/workbench/delegated actions, with platform audit and resume semantics. |
| UI | Full-stack app for chat, files, runs, outputs. | `agent-web` should be a Platform hosted app with Chat, Skills, Workspace, Runs, Artifacts, Approvals, Tools, Memory, Settings. |
| Deployment posture | Local trusted harness by default. | Aithru Agent must be server-deployable under Platform identity, grants, audit, and connection policies. |

## Target capabilities by area

### 1. Skills

Aithru Agent skills should be closer to a skill package than a simple engine config.

Target shape:

```txt
skills/
  pr-reviewer/
    skill.yaml
    instructions.md
    when-to-use.md
    examples/
    templates/
    rubrics/
    resources/
```

A skill should define:

- key, name, description, version, owner;
- instructions;
- when-to-use guidance;
- examples;
- allowed tools;
- allowed subagents;
- workspace rules;
- sandbox rules;
- memory rules;
- approval rules;
- output expectations;
- optional templates and resources.

Aithru-specific additions:

- org scope;
- app permission requirements;
- resource grants;
- publication status;
- skill versioning;
- audit metadata;
- Workbench node compatibility metadata.

### 2. Tools and capability routing

DeerFlow-like tools must map to Aithru-controlled capability routing.

```txt
model proposes tool call
  -> harness normalizes call
  -> skill policy check
  -> platform scope/authz check
  -> approval gateway if required
  -> AithruCapabilityRouter
  -> concrete adapter
  -> result normalization
  -> event stream + audit + redaction
```

Target adapters:

- `core-tool-adapter`;
- `core-node-adapter`;
- `workbench-workflow-adapter`;
- `subsystem-api-adapter`;
- `workspace-adapter`;
- `memory-adapter`;
- `sandbox-adapter`;
- future `mcp-adapter`.

Rules:

- Model adapters never execute tools.
- Tools declare risk level and required scopes.
- Dangerous tools require approval or explicit policy.
- Tool results are structured and redacted before long-term trace storage.
- Workbench workflows are invoked only through Workbench APIs/tools.

### 3. Subagents

Subagents should be first-class harness runtime objects.

A subagent should have:

- key and display name;
- instructions;
- allowed tools;
- workspace scope;
- memory scope;
- context budget;
- termination conditions;
- output contract;
- event stream projection;
- parent run link.

Subagent runs should be observable in the parent run timeline, but they are not Workbench nodes.

### 4. Workspace and files

Aithru Agent should have a DeerFlow-like workspace abstraction, but with Aithru policy controls.

Recommended virtual layout:

```txt
/input
/uploads
/workspace
/scratch
/reports
/patches
/artifacts
/workflow-drafts
/sandbox
```

Workspace operations:

- list;
- read;
- write;
- delete;
- diff;
- patch;
- snapshot;
- restore;
- promote to artifact;
- attach to thread;
- open workflow draft in Workbench.

Rules:

- Workspace writes are evented.
- File operations are scoped to workspace policy.
- Sandbox mounts are explicit.
- Retention is policy-controlled.
- Sensitive file contents are not leaked into debug UI by default.

### 5. Sandbox and controlled execution

Aithru Agent should eventually support code/script execution, but only through a provider boundary.

Target provider interface examples:

```txt
sandbox.runPython
sandbox.runNode
sandbox.executeCommand
sandbox.installPackage
sandbox.readFile
sandbox.writeFile
sandbox.diff
sandbox.patch
```

Rules:

- No direct model shell access.
- Network policy is explicit.
- File mount policy is explicit.
- Resource limits are explicit.
- Timeout is mandatory.
- Risky operations require approval.
- stdout/stderr are stream events.
- Generated files are workspace events.

### 6. Context engineering

Aithru Agent needs a real context system, not just recent message slicing.

Target components:

- `ContextBuilder`;
- `ContextBudget`;
- thread summarization;
- tool result compression;
- workspace file references;
- artifact summaries;
- skill context loading;
- memory snippets;
- subagent context isolation;
- final answer context assembly.

Rules:

- Subagents should not automatically see the full parent context.
- Large tool outputs should be written to workspace and summarized.
- Completed subtasks should be summarized and link to artifacts/files.
- Skill context should load progressively when relevant.

### 7. Memory

Memory should be scoped and explainable.

Memory scopes:

- thread;
- workspace;
- project;
- user;
- organization;
- skill.

Memory metadata:

- owner;
- source;
- confidence;
- visibility;
- retention;
- createdBy;
- createdAt;
- updatedAt;
- permission requirements.

Rules:

- No unbounded global black-box memory.
- Sensitive memory requires explicit permission and retention policy.
- Memory reads/writes are evented and auditable at the appropriate visibility.

### 8. Middleware-driven harness

Aithru Agent should avoid becoming one large while-loop.

Recommended middleware areas:

- actor context;
- thread loading;
- workspace mounting;
- upload handling;
- skill activation;
- context building;
- todo management;
- tool policy;
- approval;
- sandbox;
- tool recovery;
- memory;
- summarization;
- subagent limit;
- loop detection;
- artifact creation;
- audit;
- error normalization.

The harness kernel should be composable and testable.

### 9. Streaming gateway

Aithru Agent stream should be a structured run event stream, not only token deltas.

Required event groups:

- run lifecycle;
- message deltas;
- todo updates;
- model calls;
- tool calls;
- approval requests/resolutions;
- workspace file changes;
- artifact events;
- subagent events;
- sandbox stdout/stderr/file changes;
- memory events;
- audit/debug events.

Rules:

- Events are append-only.
- Run sequence is strictly increasing.
- Persist before publish.
- Support SSE replay with `afterSequence` or `Last-Event-ID`.
- Terminal event closes the stream.

## Aithru-specific extensions beyond DeerFlow

Aithru Agent should eventually exceed DeerFlow in platform governance.

| Area | Aithru extension |
| --- | --- |
| Identity | Platform actor context: user, service, delegated, org. |
| Authorization | Platform grants, scopes, resource authz, connection policy. |
| Audit | Every sensitive action emits platform/audit-compatible events. |
| Workbench | Agent can be called from formal workflows and can call formal workflows as tools. |
| Core | Capability routing reuses Core contracts, nodes, tools, trace, redaction, approval. |
| Subsystems | Agent can call other Aithru apps through token exchange/delegation. |
| Enterprise deployment | Server-side trusted host with fail-closed authz and no browser-held service credentials. |
| Redaction | Sensitive model/tool/workspace/sandbox values are redacted by policy. |

## Target architecture comparison

```txt
DeerFlow 2.0
  lead agent
  skills
  tools
  subagents
  filesystem/sandbox
  memory
  streaming UI

Aithru Agent
  AgentHarness
  AgentSkill packages
  AithruCapabilityRouter
  SubagentRunner
  AgentWorkspace
  AgentSandboxProvider
  AgentMemoryProvider
  AgentStreamEvent gateway
  Platform authz/audit
  Core/Workbench capability adapters
```

## Implementation principles

1. Design for complete harness first; cut MVP from the full model later.
2. Keep Aithru product contracts independent from external harness libraries.
3. Treat DeerFlow as a benchmark, not a dependency.
4. Keep all real actions behind Aithru capability routing.
5. Do not expose Agent runtime plans as workflow graphs.
6. Keep Workbench integration explicit and narrow.
7. Make streaming, workspace, artifacts, approvals, and trace first-class from the beginning.
8. Use middleware-style runtime composition instead of a single monolithic loop.

## Phased target

### Phase 1: Harness skeleton

- Thread/message model;
- Skill package spec;
- Run/event model;
- Workspace abstraction;
- Todo runtime state;
- structured stream protocol;
- fake model/tool adapters;
- capability router interface.

### Phase 2: Work-capable harness

- real model adapter;
- workspace file tools;
- artifact pipeline;
- approval gateway;
- sandbox provider interface;
- subagent interface;
- memory provider interface;
- context builder and summarizer.

### Phase 3: Aithru integration

- Platform hosted token verification;
- app manifest and permissions;
- platform authz/audit integration;
- Core tool adapter;
- Core node adapter;
- Workbench workflow adapter;
- Platform subsystem API adapter.

### Phase 4: DeerFlow-level product maturity

- subagent orchestration;
- async subagents;
- sandbox-backed coding/data tasks;
- skill marketplace/library;
- context compression;
- durable run resume;
- workspace snapshots/diffs;
- advanced UI for chat/workspace/runs/artifacts/approvals.

## Acceptance benchmark

Aithru Agent reaches the DeerFlow-level target when it can:

- run a long multi-step task from chat;
- load a skill package relevant to the task;
- maintain a workspace with uploaded and generated files;
- create/update todos and stream progress;
- call policy-gated tools;
- spawn at least one scoped subagent;
- execute code or data processing through a controlled sandbox provider;
- create artifacts from outputs;
- request and resume from approval;
- summarize or compress context;
- expose a replayable structured event stream;
- call a Workbench workflow as a tool;
- produce a Workbench workflow draft artifact;
- preserve Platform org/user/authz/audit/redaction boundaries.
