# Complete Harness Architecture

Status: target architecture

This document defines the complete Aithru Agent Harness architecture. It should be read before implementation work begins.

Aithru Agent is not a collection of small engines. It is a platform-hosted AI harness for long-running, tool-using, workspace-aware, permission-aware intelligent work.

The architecture must support a complete harness first, then cut smaller implementation phases from that complete model.

## One-line definition

```txt
Aithru Agent Harness = Thread + Skill + Run + Todos + Workspace + Tools + Subagents + Sandbox + Memory + Artifacts + Approvals + Stream.
```

## Design principles

1. Complete harness first, MVP second.
2. Agent is not a formal workflow system.
3. Workbench owns `WorkflowSpec` and formal workflow execution.
4. Agent owns intelligent runtime behavior and harness state.
5. Core owns deterministic contracts, node/tool contracts, trace/redaction/pause primitives.
6. Platform owns identity, org context, grants, app shell, token exchange, connection policy, and audit.
7. Models may propose actions, but all real actions go through Aithru capability boundaries.
8. Every important operation emits structured events.
9. Workspace, stream, approvals, tools, and artifacts are first-class from the beginning.
10. External harness frameworks may be adapters, but Aithru product contracts remain Aithru-owned.

## Boundary model

```txt
Aithru Platform
  identity, org context, app shell, hosted app, grants, service clients,
  token exchange, delegated access, connection policy, audit

Aithru Workbench
  formal WorkflowSpec UI, workflow run APIs, workflow event storage,
  workflow approval endpoints, runtime composition with Aithru Core

Aithru Core
  WorkflowSpec, graph validation, deterministic workflow contracts,
  node SDK, runtime contracts, tool contracts, trace, redaction,
  pause/resume primitives, primitive nodes

Aithru Agent
  AI harness behavior: chat threads, skills, runs, todos, workspace,
  tools, subagents, sandbox, memory, artifacts, approvals, stream events
```

Agent runtime plans, todos, tool-call sequences, and subagent tasks are harness state. They are not `WorkflowSpec` and must not become an editable workflow graph.

## Complete capability map

| Area | Capability | First-class object |
| --- | --- | --- |
| Conversation | Multi-turn context and continuation | `AgentThread`, `AgentMessage` |
| Skills | Reusable capability packages | `AgentSkill`, `AgentSkillVersion` |
| Execution | One intelligent task execution | `AgentRun` |
| Planning | Runtime task breakdown | `AgentTodo` |
| Files | Virtual work directory | `AgentWorkspace`, `WorkspaceFile` |
| Output | Durable result | `AgentArtifact` |
| Tools | Model-requested capabilities | `AgentToolDescriptor`, `AgentToolCall` |
| Subagents | Scoped specialized workers | `SubagentSpec`, `SubagentRun` |
| Sandbox | Controlled code/data execution | `SandboxRun` |
| Memory | Scoped reusable context | `AgentMemoryEntry` |
| Approval | Human/policy decisions | `AgentApproval` |
| Streaming | Realtime/replayable execution events | `AgentStreamEvent` |

## Target package layout

```txt
packages/
  agent-core/            shared types and contracts
  agent-harness/         main harness kernel and runtime interfaces
  agent-stream/          event envelope, projections, SSE helpers
  agent-skills/          skill package loading, validation, composition
  agent-workspace/       workspace/files/snapshots/diffs/artifact promotion
  agent-tools/           capability router and tool adapter contracts
  agent-subagents/       subagent registry and runner contracts
  agent-sandbox/         sandbox provider interfaces and policy types
  agent-memory/          memory provider interfaces and policies
  agent-model-*/         model adapters
  node-agent/            Workbench/Core workflow node integration

apps/
  agent-server/          Platform subsystem backend host
  agent-web/             Platform hosted app frontend
```

## Target app layout

```txt
apps/agent-server/src/
  api/
    thread-routes.ts
    skill-routes.ts
    run-routes.ts
    workspace-routes.ts
    artifact-routes.ts
    approval-routes.ts
    tool-routes.ts

  platform/
    actor-context.ts
    token-verifier.ts
    authz-client.ts
    audit-client.ts
    delegation-client.ts
    hosted-app-context.ts

  harness/
    harness-kernel.ts
    model-loop.ts
    context-builder.ts
    todo-manager.ts
    event-bus.ts
    run-controller.ts
    resume-controller.ts
    cancellation.ts

  skills/
    skill-loader.ts
    skill-registry.ts
    skill-resolver.ts
    skill-validator.ts
    prompt-composer.ts

  workspace/
    workspace-service.ts
    filesystem-provider.ts
    snapshot-service.ts
    diff-service.ts
    artifact-service.ts

  tools/
    capability-router.ts
    core-tool-adapter.ts
    core-node-adapter.ts
    workbench-workflow-adapter.ts
    subsystem-api-adapter.ts
    workspace-tool-adapter.ts
    memory-tool-adapter.ts

  sandbox/
    sandbox-provider.ts
    sandbox-policy.ts
    sandbox-runner.ts

  subagents/
    subagent-registry.ts
    subagent-runner.ts
    async-subagent-manager.ts

  memory/
    memory-provider.ts
    memory-index.ts
    memory-policy.ts

  storage/
    agent-store.ts
    file-store.ts
    postgres-store.ts
```

## Core contracts

### AgentThread

```ts
type AgentThread = {
  id: string;
  orgId: string;
  ownerUserId: string;
  title: string;
  status: "active" | "archived";
  workspaceId: string;
  defaultSkillId?: string;
  createdAt: string;
  updatedAt: string;
};
```

### AgentMessage

```ts
type AgentMessage = {
  id: string;
  threadId: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  runId?: string;
  artifactIds?: string[];
  createdAt: string;
};
```

### AgentSkill

```ts
type AgentSkill = {
  id: string;
  orgId: string;
  key: string;
  name: string;
  description?: string;
  instructions: string;
  whenToUse?: string;
  allowedTools: string[];
  allowedSubagents: string[];
  workspacePolicy: AgentWorkspacePolicy;
  memoryPolicy: AgentMemoryPolicy;
  sandboxPolicy: AgentSandboxPolicy;
  approvalPolicy: AgentApprovalPolicy;
  inputSchema?: unknown;
  outputSchema?: unknown;
  version: string;
  status: "draft" | "published" | "deprecated";
};
```

### AgentRun

```ts
type AgentRun = {
  id: string;
  orgId: string;
  actorUserId: string;
  source: "chat" | "skill" | "api" | "workbench_node" | "delegated_task";
  threadId?: string;
  skillId?: string;
  workspaceId: string;
  goal: string;
  status:
    | "queued"
    | "running"
    | "waiting_approval"
    | "completed"
    | "failed"
    | "cancelled";
  startedAt: string;
  completedAt?: string;
};
```

### AgentTodo

```ts
type AgentTodo = {
  id: string;
  runId: string;
  title: string;
  description?: string;
  status: "pending" | "running" | "done" | "blocked" | "cancelled";
  createdBy: "agent" | "user" | "system";
  order: number;
};
```

Todos are runtime harness state. They are not Workbench nodes.

### AgentWorkspace

```ts
type AgentWorkspace = {
  id: string;
  orgId: string;
  threadId?: string;
  runId?: string;
  storageBackend: "memory" | "local" | "server" | "object_storage" | "sandbox";
  rootPath?: string;
  retentionPolicyId?: string;
  createdAt: string;
};
```

### AgentArtifact

```ts
type AgentArtifact = {
  id: string;
  orgId: string;
  workspaceId: string;
  runId?: string;
  type:
    | "text"
    | "markdown"
    | "json"
    | "decision"
    | "report"
    | "file"
    | "patch"
    | "workflow_draft";
  name: string;
  mediaType?: string;
  uri?: string;
  content?: unknown;
  metadata?: Record<string, unknown>;
  createdAt: string;
};
```

### AgentToolDescriptor

```ts
type AgentToolDescriptor = {
  name: string;
  description: string;
  kind:
    | "core_tool"
    | "core_node"
    | "workbench_workflow"
    | "subsystem_api"
    | "workspace"
    | "memory"
    | "sandbox"
    | "mcp";
  inputSchema?: unknown;
  outputSchema?: unknown;
  requiredScopes: string[];
  riskLevel: "safe" | "read" | "write" | "dangerous";
  approvalPolicy: "never" | "on_risk" | "always";
};
```

### SubagentSpec

```ts
type SubagentSpec = {
  key: string;
  name: string;
  instructions: string;
  allowedTools: string[];
  workspacePolicy?: AgentWorkspacePolicy;
  memoryPolicy?: AgentMemoryPolicy;
  contextBudget?: {
    maxInputTokens?: number;
    maxOutputTokens?: number;
  };
};
```

### AgentStreamEvent

`AgentStreamEvent` is defined in [Stream Protocol](./03-stream-protocol.md).

## Harness kernel

The harness kernel is the runtime coordinator.

```ts
interface AgentHarnessEngine {
  run(input: AgentHarnessRunInput): AsyncIterable<AgentStreamEvent>;
  resume(input: AgentHarnessResumeInput): AsyncIterable<AgentStreamEvent>;
  cancel(runId: string): Promise<void>;
}
```

The kernel coordinates:

- actor context;
- thread context;
- skill context;
- workspace context;
- memory context;
- todo state;
- tool catalog;
- capability router;
- model adapter;
- approval gateway;
- artifact writer;
- event stream.

## Full run lifecycle

```txt
1. Request enters through Platform hosted app or API.
2. Resolve ActorContext.
3. Create or load AgentThread.
4. Create user AgentMessage when applicable.
5. Resolve AgentSkill.
6. Create AgentRun.
7. Create or attach AgentWorkspace.
8. Load memory according to policy.
9. List tools allowed by skill and actor context.
10. Build model context.
11. Enter Harness Loop.

Harness Loop:
  a. Model produces message, todo update, tool call, subagent call, or final response.
  b. Append event.
  c. If todo update, persist todo projection.
  d. If tool call, run capability pipeline.
  e. If subagent call, start subagent run.
  f. If workspace write, persist workspace file and event.
  g. If artifact output, create artifact.
  h. If approval is required, pause run.
  i. If final response, complete assistant message and run.

12. Persist final state.
13. Emit terminal event.
```

## Capability pipeline

```txt
model proposes action
  -> harness parses and normalizes request
  -> skill policy check
  -> actor/platform authz check
  -> approval gateway if required
  -> AithruCapabilityRouter
  -> concrete adapter
  -> result normalization
  -> event stream
  -> trace redaction
  -> artifact/workspace update
```

The capability router is defined in [Capability Router](./05-capability-router.md).

## Storage model

The store should be interface-first.

```ts
interface AgentStore {
  threads: AgentThreadStore;
  messages: AgentMessageStore;
  skills: AgentSkillStore;
  runs: AgentRunStore;
  events: AgentEventStore;
  todos: AgentTodoStore;
  workspaces: AgentWorkspaceStore;
  workspaceFiles: AgentWorkspaceFileStore;
  artifacts: AgentArtifactStore;
  approvals: AgentApprovalStore;
  subagents: AgentSubagentStore;
  memory: AgentMemoryStore;
  sandboxRuns: AgentSandboxRunStore;
}
```

Target tables:

```txt
agent_threads
agent_messages
agent_skills
agent_skill_versions
agent_skill_files
agent_runs
agent_run_events
agent_todos
agent_workspaces
agent_workspace_files
agent_workspace_snapshots
agent_artifacts
agent_tool_catalog
agent_tool_policies
agent_tool_calls
agent_approvals
agent_subagent_specs
agent_subagent_runs
agent_memory_entries
agent_memory_links
agent_sandbox_runs
agent_sandbox_files
```

MVP may implement a subset, but the store boundaries should match the complete model.

## Middleware model

The harness should be middleware-driven, not one monolithic loop.

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
- subagent limits;
- loop detection;
- artifact creation;
- audit;
- error normalization.

Middleware should be composable and testable.

## Platform integration

Agent server is a Platform subsystem.

It should eventually use Platform SDK capabilities for:

- JWT verification;
- current actor extraction;
- org-scoped authorization;
- hosted app token handling;
- service token exchange;
- delegated token handling;
- resource registration;
- audit reporting.

Browser UI must not receive service client credentials or internal service tokens.

## Workbench integration

### Workbench calls Agent

Workbench uses explicit node/API boundaries, for example future:

```txt
agent.skill
agent.task
```

Workbench remains the formal workflow owner. Agent owns only harness behavior inside the node.

### Agent calls Workflow product

Agent calls Workflow product capabilities and workflows through tool adapters:

```txt
workflow.invokeCapability
```

```txt
workbench.runWorkflow
```

Agent must not import Workbench internals, schedule workflow graphs, or execute
raw workflow nodes directly. Standalone deterministic actions are exposed by the
Workflow product as curated capabilities and invoked through CapabilityRun APIs.

See [Workflow Capability and Agent Integration](./08-workflow-capability-integration.md).

### Agent creates workflow drafts

Agent may produce a `workflow_draft` artifact. Workbench must validate and save it.

## UI implication

Agent frontend should feel like a harness product, not a workflow editor.

Recommended product navigation:

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

The UI should show:

- chat;
- workspace files;
- todos;
- tool calls;
- subagents;
- sandbox output;
- artifacts;
- approvals;
- stream trace.

It must not show Agent runtime plans as draggable graphs.

## Implementation phases

### Phase 0: cleanup and contract reset

- Treat old engine packages as legacy reference.
- Preserve README/docs/AGENTS.md.
- Define target contracts in docs.
- Decide whether to delete or move old packages.

### Phase 1: protocol packages

- `agent-core` target contracts;
- `agent-stream` event model;
- `agent-skills` skill spec parser/validator;
- `agent-workspace` provider interface;
- `agent-tools` capability router interface.

### Phase 2: minimal harness loop

- `agent-harness` kernel;
- fake model adapter;
- fake capability router;
- todo updates;
- workspace write/read;
- artifact creation;
- stream events.

### Phase 3: server host

- `agent-server` API;
- in-memory/file store;
- thread/message/run API;
- SSE stream;
- approval API skeleton.

### Phase 4: Aithru integration

- Platform actor context;
- manifest/permissions;
- Core tool adapter;
- Core node adapter;
- Workbench workflow adapter.

### Phase 5: complete harness maturity

- sandbox provider;
- subagents;
- memory;
- context compression;
- durable resume;
- workspace snapshots/diffs;
- advanced UI.

## Architecture acceptance criteria

A design or implementation change is acceptable only if:

- Agent remains an AI harness, not a workflow editor.
- Skills remain agent capabilities, not DAG workflows.
- Todos/runtime plans remain runtime state.
- Workspace is first-class.
- Artifacts are first-class.
- Tool calls route through capability boundaries.
- Sandbox and external actions are policy-gated.
- Stream events are structured and replayable.
- Platform identity/authz/audit is preserved.
- Workbench integration is explicit and narrow.
- Core does not depend on Agent.
