# Aithru Agent Harness Design

Status: design reset / target architecture

This document resets the product and architecture direction of `aithru-agent`.

The previous implementation centered on `AgentTask`, `AgentPlan`, `AgentRuntime`, `ClassifyEngine`, `PlanRunReviewEngine`, and `DeepResearchEngine`. Those primitives remain useful, but they are not the final product center.

The new direction is:

```txt
Aithru Agent = Aithru-native DeepAgents-like AI harness
```

Aithru Agent should feel closer to Codex, Claude Code, ChatGPT Agent, or DeepAgents than to a workflow graph editor.

## One-line definition

```txt
Aithru Agent is a platform-hosted AI harness for skill-driven, tool-using, workspace-aware, permission-aware intelligent work.
```

## Core idea

Aithru Agent should provide:

- chat threads;
- real skills;
- long-running agent runs;
- runtime todos / plans;
- workspace files;
- artifacts;
- tool calls;
- subagents;
- sandboxed execution;
- memory;
- human approvals;
- review/evaluation;
- event streaming and traces.

The actual execution capability must depend on Aithru-controlled capability boundaries:

- Agent-owned local tools (workspace operations, artifact creation);
- Workflow product capabilities consumed through `CapabilityRun` APIs.
- Sandbox, memory, or MCP behavior through Agent-owned harness interfaces or
  additional Workflow product capabilities.

Workflow capabilities may be backed by Core nodes, but the backing details
belong to the Workflow product. Agent consumes the curated capability API and
stores linked external run references.

The model may propose actions, but it must never execute real actions directly.

## Non-goal: not a second workflow system

Aithru Agent can have workflow-like runtime state:

```txt
user goal
  -> skill selection
  -> todo / runtime plan
  -> tool call
  -> subagent task
  -> sandbox execution
  -> artifact
  -> review
  -> approval
```

That does not make it a Workbench workflow.

Formal workflows remain:

```txt
WorkflowSpec
  -> nodes
  -> edges
  -> validation
  -> branch semantics
  -> scheduler/runtime
  -> workflow run
```

Owned by Aithru Core and surfaced through Aithru Workbench.

Agent todos, plans, subagents, and workspace operations are runtime harness state. They must not become a draggable graph editor or a persisted workflow definition.

## Mental model

Use this analogy:

```txt
LangGraph / low-level runtime  -> DeepAgents / high-level agent harness
Aithru Core + Workbench         -> Aithru Agent / high-level AI harness
```

This is only an analogy. Aithru Core is a deterministic workflow kernel and Workbench is a workflow product surface. Aithru Agent should borrow the high-level harness shape from DeepAgents, while preserving Aithru permission, trace, redaction, approval, platform identity, and workflow boundaries.

## Target product surfaces

Aithru Agent is expected to be a Platform-hosted subsystem.

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

### Chat

Chat is the primary entry point.

A chat thread can:

- run a skill;
- create an agent run;
- produce artifacts;
- request approval;
- call a Workbench workflow as a tool;
- create a `WorkflowSpec` draft artifact that opens in Workbench.

### Skills

Skills are real reusable agent capabilities.

A skill contains:

- instructions;
- when-to-use description;
- allowed tools;
- allowed subagents;
- model/profile preferences;
- workspace policy;
- memory policy;
- sandbox policy;
- approval policy;
- input/output expectations;
- artifact expectations.

A skill is not a workflow graph. It may be invoked from Chat, API, delegated work, or a Workbench `agent.*` node.

`allowedTools` is an upper bound. Workspace, memory, sandbox, approval, and
subagent policies can further remove tools from a run's available catalog.
Sandbox tools are unavailable unless the skill explicitly enables sandbox use.

### Workspace

Workspace is the harness file/context surface.

It may contain:

- user-provided files;
- generated files;
- intermediate analysis files;
- patches;
- reports;
- JSON outputs;
- execution logs;
- workflow draft artifacts.

Workspace operations must be policy-gated and traceable.

### Runs

Runs represent intelligent execution, not formal workflow execution.

A run should show:

- selected skill;
- runtime todos;
- subagent tasks;
- tool calls;
- sandbox executions;
- workspace file changes;
- artifacts;
- approvals;
- trace events;
- errors and recovery paths.

### Artifacts

Artifacts are outputs of intelligent work:

- markdown;
- reports;
- JSON;
- decisions;
- patches;
- files;
- workflow drafts;
- charts or structured analysis outputs.

### Approvals

Approvals guard risky agent actions:

- write operations;
- external calls;
- code/sandbox execution;
- sensitive data access;
- Workbench workflow execution;
- exports;
- delegated/background actions.

Agent approvals are distinct from Workbench human-approval workflow pauses, but both must remain auditable.

### Tools

Tools are capability descriptors the harness can request.

Tools may be backed by:

- Core tool executors;
- Core node adapters;
- Workbench workflows;
- Platform subsystem APIs;
- sandbox executors;
- workspace/memory providers;
- optional MCP adapters.

Tools must expose risk, scopes, input schema, output schema, and approval requirements.

## Target concepts

### AgentThread

```ts
type AgentThread = {
  id: string;
  orgId: string;
  ownerUserId: string;
  title: string;
  status: "active" | "archived";
  defaultSkillId?: string;
  workspaceId: string;
  createdAt: string;
  updatedAt: string;
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
  allowedSubagents?: string[];
  memoryPolicy?: AgentMemoryPolicy;
  workspacePolicy?: AgentWorkspacePolicy;
  sandboxPolicy?: AgentSandboxPolicy;
  approvalPolicy?: AgentApprovalPolicy;
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
  threadId?: string;
  skillId?: string;
  orgId: string;
  actorUserId: string;
  source: "chat" | "skill" | "api" | "workbench_node" | "delegated_task";
  goal: string;
  harnessOptions?: {
    model?: string;
    instructions?: string;
  };
  status:
    | "queued"
    | "running"
    | "waiting_approval"
    | "completed"
    | "failed"
    | "cancelled";
  workspaceId: string;
  result?: {
    content?: string;
    artifactIds: string[];
    messageId?: string;
    threadMessageId?: string;
  };
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

Todos are runtime state. They are not Workbench nodes.

### AgentWorkspace

```ts
type AgentWorkspace = {
  id: string;
  orgId: string;
  threadId?: string;
  runId?: string;
  storageBackend: "memory" | "local" | "server" | "sandbox";
  retentionPolicyId?: string;
};
```

### AgentToolDescriptor

```ts
type AgentToolDescriptor = {
  name: string;
  description: string;
  kind:
    | "local_tool"
    | "workflow_capability";
  inputSchema?: unknown;
  outputSchema?: unknown;
  requiredScopes: string[];
  riskLevel: "safe" | "read" | "write" | "dangerous";
  approvalPolicy?: "never" | "on_risk" | "always";
};
```

### AgentSubagentSpec

```ts
type AgentSubagentSpec = {
  key: string;
  name: string;
  instructions: string;
  allowedTools: string[];
  workspacePolicy?: AgentWorkspacePolicy;
  memoryPolicy?: AgentMemoryPolicy;
};
```

Subagents are harness-level specialized workers. They are not Workbench nodes.

## Aithru Capability Router

The harness should call all real actions through a capability router.

```ts
interface AithruCapabilityRouter {
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;

  callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}
```

Backend adapters:

- `local_tool` adapters for Agent-owned tools (workspace, todo, artifact,
  memory, subagent delegation, restricted sandbox execution);
- `workflow_capability` adapters that consume Workflow product capability APIs.

Workflow capabilities may be backed by Core nodes, but the backing details
belong to the Workflow product. Additional sandbox, memory, or MCP behavior must
enter Agent through either Agent-owned local harness interfaces or Workflow
product capabilities - they are not top-level `AgentToolKind` values.

## Tool call pipeline

```txt
model proposes action
  -> harness parses and normalizes tool call
  -> skill policy check
  -> platform scope/authz check
  -> capability router
  -> approval gate if required
  -> concrete executor
  -> result normalization
  -> event stream
  -> trace redaction
  -> artifact/workspace update
```

Rules:

- Model adapters do not execute tools.
- Skills do not bypass allowed tool policy.
- Sandbox execution is always explicit and policy-gated.
- Workspace file writes are traceable.
- Workbench workflows are invoked through Workbench APIs, not imported internals.
- Core nodes exposed as tools must be explicitly allowlisted.
- Sensitive data must be redacted before long-term trace storage or user display.

## Workbench integration

### Workbench calls Agent

Workbench can call Agent through formal workflow nodes.

Future node shape:

```txt
agent.skill
agent.task
```

Recommended node config:

```ts
type AgentSkillNodeConfig = {
  skillId: string;
  inputMapping?: Record<string, string>;
  outputMapping?: Record<string, string>;
  workspaceMode?: "ephemeral" | "workflow_run";
  approvalMode?: "inherit_workflow" | "agent_policy" | "both";
  toolPolicyOverride?: unknown;
};
```

Workbench owns the outer workflow. Agent owns the intelligent behavior inside the node.

### Agent calls Workflow product

Agent can call Workflow product capabilities and workflows as tools:

```txt
Agent Harness
  -> workflow.invokeCapability tool
  -> Workflow product creates a CapabilityRun
  -> Agent receives result/artifact/trace summary
```

```txt
Agent Harness
  -> workbench.runWorkflow tool
  -> Workbench runs WorkflowSpec
  -> Agent receives result/artifact/trace summary
```

Agent does not parse, schedule, or execute workflow graphs. Agent also does not
execute raw workflow nodes directly. Deterministic standalone actions should be
exposed by the Workflow product through curated capabilities and CapabilityRun
APIs.

See [Workflow Capability and Agent Integration](./08-workflow-capability-integration.md).

### Agent creates Workbench drafts

Agent can create a `WorkflowSpec` draft artifact.

UI actions:

```txt
Open in Workbench
Validate in Workbench
Download WorkflowSpec JSON
```

Only Workbench validates, saves, versions, and runs formal workflows.

## Backend direction

The active implementation direction is Python-first:

```txt
backend/
  api/              FastAPI control plane
  application/      runtime assembly and use-case services
  capabilities/     capability router, policy, local tools, future Workflow capabilities
  domain/           Agent product contracts
  harness/          scripted and Pydantic AI harness drivers
  persistence/      store interfaces and implementations
  stream/           AgentStreamEvent writer/store/SSE
  trace/            event-to-span projection
  worker/           Agent run execution, pause/resume, cancellation
```

Pydantic AI is the default harness driver. It powers model loop mechanics, tool
calling mechanics, streaming, and structured output, but it does not define
public Aithru product contracts. Pydantic AI tool calls must enter Aithru's
capability router through the Aithru tool bridge.

Current runtime subagent support is harness state: `subagent.delegate` creates a
controlled child `AgentRun` with `source = "delegated_task"`, links it to the
parent run through `AgentSubagentRun`, and projects `subagent.started`,
`subagent.completed`, and `subagent.failed` events into the parent stream and
trace. Delegation validates requested child skills through the skill resolver
and child run scopes must not exceed parent run scopes. This is not a
WorkflowSpec, graph branch, or Workbench node.

Current sandbox support is a restricted local `sandbox.run_python` tool. It
does not expose shell access, imports, file APIs, or network APIs to model code;
input enters through the tool payload, and stdout/stderr plus completion/failure
are emitted as `sandbox.*` events and trace spans. Production-grade isolation
can later replace the local provider behind the same capability boundary.

## Migration direction

1. Keep Agent as a Python backend with Aithru-owned contracts.
2. Use FastAPI for the control plane.
3. Use Pydantic AI as the default real harness driver.
4. Keep a scripted driver for deterministic tests.
5. Route every real action through the Aithru capability router.
6. Add Workflow Capability HTTP integration only through explicit tools.
7. Add Platform hosted UI only after the backend run/event/tool loop is stable.

## Verification checklist

- [ ] Is Aithru Agent clearly an AI harness, not a workflow editor?
- [ ] Are Skills reusable agent capabilities, not DAGs?
- [ ] Are todos/runtime plans observable state, not persisted workflow definitions?
- [ ] Do all real actions pass through the capability router?
- [ ] Are sandbox/code/file operations policy-gated and traceable?
- [ ] Does Workbench call Agent only through explicit `agent.*` node integration?
- [ ] Does Agent call Workbench only through Workbench APIs/tools?
- [ ] Do Platform org/user/scopes/authz/delegation/audit boundaries remain explicit?
- [ ] Do Core and Workbench avoid depending on Agent internals?
