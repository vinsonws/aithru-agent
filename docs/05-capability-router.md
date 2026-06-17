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
    | "local_tool"
    | "workflow_capability";
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

### local-tool adapter

Agent-owned harness tools such as workspace operations and artifact creation.

#### workspace-adapter

Provides tools:

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

### workflow-capability-adapter

Allows Agent to call curated standalone Workflow product capabilities as tools.

Example tool:

```txt
workflow.http_download
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

Workflow capabilities may be backed by Core nodes, but the backing details
belong to the Workflow product. Agent consumes the curated capability API and
stores linked external run references.

Sandbox, memory, or MCP adapters must enter Agent through either Agent-owned
local harness interfaces or Workflow product capabilities. They are not
top-level `AgentToolKind` values in the simplified Agent contract.

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

- built-in workspace tools (local_tool);
- skill-provided tools;
- Workflow capability catalog;
- Workbench workflows exposed as workflow capabilities;
- sandbox, memory, MCP providers through local or capability interfaces.

`listTools(context)` should return only tools available under current actor/org/skill/runtime context.

## Workbench workflows as tools

A saved Workbench workflow can be exposed as a workflow capability:

```ts
type WorkbenchWorkflowToolDescriptor = AgentToolDescriptor & {
  kind: "workflow_capability";
  metadata: {
    capabilityKey: string;
    capabilityVersion?: string;
    workflowId: string;
    version?: string;
    inputSchema?: unknown;
    externalApprovalOwner: "workflow";
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

Core nodes are not Agent tool kinds. Workflow capabilities may be backed by
Core nodes, but the backing details belong to the Workflow product. Agent
consumes the curated capability catalog and stores linked external run
references.

Agent must not execute raw Core nodes directly. Deterministic actions must be
exposed through the Workflow product capability catalog and invoked through
`CapabilityRun` APIs.

## Minimal implementation requirements

First implementation should include:

- `AithruCapabilityRouter` interface;
- `AgentToolAdapter` interface;
- static tool descriptor registry;
- workspace adapter with list/read/write (as `local_tool`);
- artifact creation hook;
- `WorkflowCapabilityAdapter` with `WorkflowCapabilityClient` interface;
- policy checks for allowed tool names and risk level;
- stream events for proposed/started/completed/failed/denied;
- external run and approval reference events.

Future phases add:

- Platform authz integration;
- approval gateway;
- sandbox, memory, and MCP adapters through local or capability interfaces;
- additional Workflow product capability adapters.

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
