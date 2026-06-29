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
  -> Pydantic AI runtime emits a model tool call
  -> Aithru Tool Bridge normalizes request
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
    | "external_tool"
    | "workflow_capability";
  inputSchema?: unknown;
  outputSchema?: unknown;
  requiredScopes: string[];
  riskLevel: "safe" | "read" | "write" | "dangerous";
  approvalPolicy: "never" | "on_risk" | "always";
  failurePolicy: "fail_run" | "return_recoverable";
  display?: {
    name?: string;
    description?: string;
    icon?: string;
    category?: string;
  };
  metadata?: Record<string, unknown>;
};
```

`failurePolicy` controls harness behavior after a tool returns a failed result.
The default is `fail_run`, which preserves normal `TOOL_FAILED` behavior.
Selected controlled tools, such as web search/fetch, may use
`return_recoverable` so the model receives a structured failure payload and can
continue toward a degraded artifact while stream and audit events still record
the failed tool call. Detailed recoverability is carried by tool-result
recovery metadata rather than bridge tool-name special cases; see
`docs/superpowers/specs/2026-06-29-tool-result-recovery-loop-design.md`.

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
  recovery?: {
    recoverable: boolean;
    kind:
      | "invalid_input"
      | "not_found"
      | "transient"
      | "execution_failed"
      | "ambiguous_input"
      | "policy_denied"
      | "approval_required"
      | "fatal_system";
    action:
      | "return_to_model"
      | "retry_with_corrected_input"
      | "use_alternative_tool"
      | "ask_user"
      | "wait_or_degrade"
      | "require_approval"
      | "fail_run";
    message: string;
    modelGuidance?: string;
    suggestedInput?: unknown;
    allowedValues?: Record<string, unknown>;
    retryAfterMs?: number;
    attemptKey?: string;
    maxAttempts?: number;
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

### external-tool adapter

Allows Agent to expose hosted integrations, MCP-like servers, search, fetch, or
other provider-backed tools as `external_tool` descriptors.

Current provider contracts include:

```txt
mcp.<server>.<tool>
web.search
web.fetch
```

Rules:

- provider tools are optional runtime inputs, not ambient model access;
- settings can enable the built-in `web.search` / `web.fetch` catalog or
  Pydantic-validated MCP-like catalogs, but they are disabled by default;
- each provider maps its catalog into `ExternalToolSpec` descriptors;
- every tool keeps explicit risk, scope, approval, provider, and metadata;
- provider input/output contracts use Pydantic models at the boundary;
- adapters validate inputs before calling provider executors;
- actual web/network or MCP execution must be supplied by a controlled executor
  and still passes through scope, risk, approval, trace, and redaction policy;
- the built-in HTTP web executor supports `web.fetch`, and the built-in
  HTTP-JSON search executor supports `web.search` through a configured endpoint;
- Web executors require explicit allowed hosts and enforce timeout and byte
  limits;
- settings-installed provider catalogs use safe unavailable executors until a
  concrete provider integration is supplied.

Sandbox and memory adapters may enter Agent through Agent-owned local harness
interfaces. MCP-like, search, fetch, or hosted integration tools enter through
`external_tool` adapters. Workflow capabilities remain separate
`workflow_capability` adapters. All forms still pass through the same
scope/risk/approval/redaction checks.

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

Terminal tool events should include safe governance projections when available:
`authorization_decision` for actor/scope status and `audit` for the capability
prepare/execute outcome. The event payload must avoid sensitive field names such
as `authorization`; nested audit authorization is serialized as
`authorization_decision` so stream redaction does not remove the policy proof.
Recoverable failures should include policy-safe recovery metadata and a
`recovery_attempt` counter. When the bridge returns that failure to the model it
also emits `tool.recovery.offered`; when the retry budget is exhausted it emits
`tool.recovery.exhausted` before failing the run.

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

## Current backend alignment

The stage-1 backend uses Pydantic AI and `pydantic-ai-harness` only as internal
runtime/capability composition details. Public Aithru contracts remain
`AgentRun`, `AgentToolDescriptor`, `AgentRunContext`, `AgentStreamEvent`,
artifacts, approvals, workspaces, memory, and subagents.

Current execution path:

```txt
model / Pydantic AI
  -> AithruBoundaryCapability / AithruToolset
  -> PydanticAIToolBridge
  -> AithruCapabilityRouter
  -> local tool adapter or future Workflow Capability API
  -> AgentStreamEvent / trace / artifact / workspace state
```

`AithruBoundaryCapability` and `AithruToolset` may mark, filter, and prepare
Pydantic AI tool definitions. They do not execute concrete actions. Concrete
workspace, artifact, memory, sandbox, approval, and subagent operations remain
inside local Aithru adapters behind `AithruCapabilityRouter`.

Skill package policy is applied before tools are exposed: `allowed_tools` is an
upper bound, `denied_tools` removes tools explicitly, and workspace, memory,
sandbox, approval, and subagent policy can further narrow availability. Sandbox
execution is only available through the `sandbox.run_python` local tool and only
when the active skill/run context exposes that tool.

The model-facing `task(description, prompt, subagent_type)` tool is also a local
tool adapter behind the router. It creates Aithru child `AgentRun` state and
`AgentSubagentRun` links, then joins the child result through worker semantics;
it is not a workflow graph or `WorkflowSpec` branch.

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
- sandbox and memory providers through local interfaces;
- MCP-like, search, fetch, and hosted providers through external tool adapters.

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
