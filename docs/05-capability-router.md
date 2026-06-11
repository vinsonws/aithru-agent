# Capability Router

Status: target architecture

This document defines the Aithru Agent Capability Router.

The Capability Router is the boundary between model-proposed actions and real execution. It is the main reason Aithru Agent can be a powerful AI harness without letting models directly access tools, files, workflow execution, credentials, network calls, or sandbox execution.

## One-line definition

```txt
Aithru Capability Router = policy-aware, approval-aware, traceable execution boundary for every real Agent action.
```

## Goals

The Capability Router must:

- expose tool descriptors to the harness;
- normalize model-proposed tool calls;
- enforce skill tool policy;
- enforce actor/platform authorization;
- request approval when needed;
- dispatch to concrete adapters;
- emit stream events;
- support redaction;
- support audit;
- prevent direct model access to execution capabilities;
- preserve Core/Workbench/Platform boundaries.

## Non-goals

The Capability Router must not:

- become a workflow runtime;
- own `WorkflowSpec` semantics;
- bypass Platform authz;
- bypass Aithru Core tool permission policy;
- expose service credentials to browser/model code;
- let model adapters execute tools directly;
- import Workbench internals directly;
- silently execute dangerous operations without policy and audit.

## High-level pipeline

```txt
model proposes tool call
  -> Harness normalizes request
  -> Skill policy check
  -> Actor/platform authz check
  -> Approval gateway if required
  -> Capability Router dispatch
  -> Concrete adapter executes
  -> Result normalization
  -> Stream event append
  -> Audit/redaction/artifact/workspace updates
```

## Primary interface

```ts
type AgentToolPrepareResult =
  | { status: "ready"; descriptor: AgentToolDescriptor; redaction: "none" | "partial" | "full" }
  | { status: "waiting_approval"; descriptor: AgentToolDescriptor; approvalId?: string; output?: unknown; redaction: "none" | "partial" | "full" }
  | { status: "denied"; error: { code: string; message: string; retryable?: boolean }; redaction: "none" | "partial" | "full" };

interface AithruCapabilityRouter {
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;

  /**
   * Two-phase prepare: check policy (scopes, approval). Never calls the adapter.
   * Returns "ready", "waiting_approval", or "denied".
   */
  prepareToolCall(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolPrepareResult>;

  /**
   * Two-phase execute: called only after prepare returned "ready" (or after
   * an approval was resolved). Calls the adapter.
   */
  executeToolCall(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;

  /**
   * Compatibility helper.
   * Must call prepareToolCall + executeToolCall.
   */
  callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}
```

### Two-phase protocol

```
prepareToolCall = policy/authz/approval preflight  (never executes the adapter)
executeToolCall = actual adapter execution          (only after prepare succeeds)
callTool        = compatibility wrapper             (prepare + execute in one call)
```

The harness must call `prepareToolCall` first to determine if the tool is allowed, needs approval, or is denied. After approval is resolved, the harness calls `executeToolCall` with `alreadyApproved: true` + `requestedBy: "harness"` to bypass the approval check and execute the adapter directly.

Approval bypass is only allowed when:
- `request.alreadyApproved === true` AND `request.requestedBy === "harness"`

Model-initiated calls with `alreadyApproved: true` still go through the approval gate. Only the harness can bypass after resolving a pending approval.

## AgentRunContext

```ts
type AgentRunContext = {
  runId: string;
  threadId?: string;
  skillId?: string;
  workspaceId: string;
  actor: {
    actorType: "user" | "service" | "delegated" | "system";
    userId?: string;
    serviceId?: string;
    orgId: string;
    scopes: string[];
    authzVersion?: number;
    delegation?: unknown;
  };
  requestId?: string;
  traceId?: string;
};
```

## Tool descriptor

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
  display?: {
    name?: string;
    description?: string;
    icon?: string;
    category?: string;
  };
  metadata?: Record<string, unknown>;
};
```

## Tool call request

```ts
type AgentToolCallRequest = {
  id: string;
  toolName: string;
  input: unknown;
  reason?: string;
  requestedBy: "model" | "harness" | "subagent" | "user" | "system";
  subagentRunId?: string;
  todoId?: string;
};
```

## Tool call result

```ts
type AgentToolCallResult = {
  id: string;
  toolName: string;
  status: "completed" | "failed" | "denied" | "waiting_approval";
  output?: unknown;
  artifactIds?: string[];
  workspaceChanges?: Array<{
    path: string;
    operation: "created" | "updated" | "deleted";
  }>;
  approvalId?: string;
  error?: {
    code: string;
    message: string;
    retryable?: boolean;
  };
  redaction: "none" | "partial" | "full";
};
```

## Adapter interface

```ts
interface AgentToolAdapter {
  kind: AgentToolDescriptor["kind"];
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;
  callTool(
    request: AgentToolCallRequest,
    descriptor: AgentToolDescriptor,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}
```

## Adapter types

### core-tool-adapter

Routes Agent tool calls to Aithru Core tool executor contracts.

Use for:

- deterministic tool execution;
- existing Core tool contracts;
- reusable action executors.

Rules:

- preserve Core `ToolPermissionPolicy` behavior;
- emit tool lifecycle events;
- preserve redaction expectations;
- do not expose raw secrets to Agent model context.

### core-node-adapter

Exposes selected Core nodes as Agent tools.

Use only for single-node capability cases.

Rules:

- node must be explicitly allowlisted;
- node must not require graph scheduling semantics;
- node execution must receive a controlled execution context;
- if node calls tools, those calls still route through Core tool policy;
- do not allow arbitrary node execution by type string.

### workflow-capability-adapter

Allows Agent to call curated standalone Workflow product capabilities as tools.

Example tool:

```txt
workflow.invokeCapability
```

Rules:

- Agent consumes the Workflow product capability catalog, not the raw node
  catalog;
- each invocation creates or observes a first-class `CapabilityRun`;
- capability approval records are owned by the Workflow product;
- Agent may present and resolve those approvals through Workflow APIs;
- adapter calls Workflow APIs through platform-approved delegated user identity
  by default;
- return normalized result, artifact references, trace references, and external
  run references to Agent.

### workbench-workflow-adapter

Allows Agent to call saved Workbench workflows as tools.

Example tool:

```txt
workbench.runWorkflow
```

Rules:

- Agent does not parse or schedule `WorkflowSpec`;
- Workbench owns validation, run storage, events, and workflow approvals;
- adapter calls Workbench API through platform-approved service/user/delegated token flow;
- return only result, artifact references, and trace summary to Agent.

### subsystem-api-adapter

Calls other Platform subsystems.

Rules:

- use platform token exchange, service token, or delegated token as appropriate;
- obey connection policy;
- obey app-level and resource-level authorization;
- fail closed when policy is missing;
- never expose service credentials to browser or model context.

### workspace-adapter

Provides tools such as:

```txt
workspace.listFiles
workspace.readFile
workspace.writeFile
workspace.deleteFile
workspace.diff
workspace.snapshot
workspace.promoteArtifact
```

Rules:

- enforce workspace policy;
- write workspace events;
- avoid leaking large/sensitive file contents into normal UI;
- support artifact promotion.

### memory-adapter

Provides tools such as:

```txt
memory.search
memory.read
memory.write
memory.delete
```

Rules:

- memory scope must be explicit;
- memory writes should be attributed to source and actor;
- sensitive memory requires policy and retention controls;
- memory events are normally debug/audit visibility.

### sandbox-adapter

Provides controlled execution tools such as:

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

- no direct shell access to model code;
- all execution is provider-mediated;
- timeout is mandatory;
- resource limits are mandatory;
- network policy is explicit;
- file mounts are explicit;
- stdout/stderr stream as sandbox events;
- dangerous operations require approval.

### mcp-adapter

Future optional adapter for MCP servers.

Rules:

- MCP servers must be registered and allowlisted;
- capability descriptors must be normalized into `AgentToolDescriptor`;
- tool calls still pass through skill policy, platform authz, approval, trace, and redaction;
- MCP transport lifecycle stays outside Core.

## Policy checks

Capability routing has layered checks.

### 1. Skill policy

Does the current skill allow this tool?

Inputs:

- skill allowed tools;
- skill risk policy;
- skill sandbox policy;
- skill memory/workspace policy;
- skill approval policy.

Fail result:

```txt
tool.denied: skill_policy_denied
```

### 2. Actor authorization

Does the actor have required platform scopes and resource permissions?

Inputs:

- `actor.orgId`;
- actor type;
- scopes;
- platform grants;
- delegation context;
- resource reference;
- requested action.

Fail result:

```txt
tool.denied: authz_denied
```

### 3. Connection policy

For cross-app calls, is source app allowed to call target app?

Fail result:

```txt
tool.denied: connection_policy_denied
```

### 4. Risk and approval

Does the request require approval?

If approval is needed:

```txt
approval.requested
run.paused
tool result = waiting_approval
```

After approval:

```txt
approval.resolved
run.resumed
tool.started
```

If rejected:

```txt
approval.resolved
tool.denied or run.failed
```

### 5. Adapter-level validation

The adapter validates input schema and adapter-specific constraints.

Fail result:

```txt
tool.failed: invalid_input | adapter_error | timeout | unavailable
```

## Event emission

Capability Router participates in stream events.

Recommended event order for successful tool call:

```txt
tool.proposed
tool.started
tool.completed
```

For denied tool:

```txt
tool.proposed
tool.denied
```

For approval:

```txt
tool.proposed
approval.requested
run.paused
approval.resolved
run.resumed
tool.started
tool.completed
```

For failure:

```txt
tool.proposed
tool.started
tool.failed
```

Workspace/artifact/sandbox events may be emitted between `tool.started` and `tool.completed`.

## Redaction

Tool inputs and outputs may contain sensitive values.

Every tool result must specify:

```txt
redaction = none | partial | full
```

Rules:

- secrets and tokens are never emitted to user/debug streams;
- raw tool input may be audit-only or redacted;
- file contents may be summarized instead of emitted;
- model context should receive only the safe result form;
- persisted trace should apply redaction policy before long-term storage.

## Tool catalog

Tool catalog can combine static and dynamic sources.

Sources:

- built-in workspace tools;
- skill-provided tools;
- platform app capabilities;
- Workbench workflows exposed as tools;
- Core tool adapters;
- sandbox provider capabilities;
- MCP server manifests;
- memory provider capabilities.

`listTools(context)` should return only tools available under current actor/org/skill/runtime context.

## Workbench workflows as tools

A saved Workbench workflow can be exposed as:

```ts
type WorkbenchWorkflowToolDescriptor = AgentToolDescriptor & {
  kind: "workbench_workflow";
  metadata: {
    workflowId: string;
    version?: string;
    inputSchema?: unknown;
  };
};
```

Rules:

- tool name should be stable, e.g. `workbench.workflow.salesReport.run`;
- workflow execution belongs to Workbench;
- Agent receives a normalized result;
- workflow trace may be linked, not copied in full by default.

See [Workflow Capability and Agent Integration](./08-workflow-capability-integration.md).

## Core nodes as tools

A Core node may be exposed as a tool only if it is safe to execute outside graph scheduling.

Examples may include deterministic transformations or simple utility nodes.

Rules:

- explicit allowlist only;
- no graph traversal;
- no hidden scheduling;
- no direct secret access;
- no bypassing Core tool policy.
- Agent-facing production capabilities should normally be exposed through the
  Workflow product capability catalog rather than by exposing raw nodes directly.

## Minimal implementation requirements

First implementation should include:

- `AithruCapabilityRouter` interface;
- `AgentToolAdapter` interface;
- static tool descriptor registry;
- workspace adapter with list/read/write;
- artifact creation hook;
- fake search/fetch tool for tests;
- policy checks for allowed tool names and risk level;
- stream events for proposed/started/completed/failed/denied.

Future phases add:

- Platform authz integration;
- approval gateway;
- sandbox adapter;
- Core tool adapter;
- Core node adapter;
- Workbench workflow adapter;
- subsystem API adapter;
- memory adapter;
- MCP adapter.

## Testing strategy

Tests should cover:

- unknown tool denied;
- tool not allowed by skill denied;
- high-risk tool requires approval;
- approved tool resumes correctly;
- adapter failure becomes `tool.failed`;
- redaction metadata is preserved;
- workspace file write emits workspace event;
- Workbench workflow adapter does not parse WorkflowSpec locally;
- model adapter cannot execute tools directly.

## Acceptance criteria

Capability Router design is acceptable when:

- every real action crosses one explicit boundary;
- model adapters remain execution-free;
- skills constrain available tools;
- platform/core/workbench permissions can be enforced;
- approval can pause and resume execution;
- events are emitted in predictable order;
- redaction is visible in tool results and stream events;
- Workbench and Core ownership boundaries are preserved.
