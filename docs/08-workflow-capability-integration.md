# Workflow Capability and Agent Integration

Status: target architecture / design decision

This document defines how Aithru Agent should consume deterministic
capabilities exposed by the Workflow product, and how the Workflow product
should invoke Agent runs.

The key decision is that Aithru has two product execution planes:

```txt
Workflow product = deterministic workflow and capability execution plane
Agent product    = AI harness and intelligent orchestration plane
```

They should call each other through HTTP APIs and replayable event streams.
They must not import each other's internals.

## Why this exists

Agent needs tools such as `http_download`, `fetch_json`, `send_email`, or
`run_workflow`. Some of these capabilities already exist as workflow nodes or
runtime tools. Agent should not reimplement them, and it should not need to
wrap every deterministic action in a full `WorkflowSpec`.

The Workflow product should therefore expose curated standalone capabilities
that Agent can call. Those calls must still pass through the same production
boundaries as workflow execution: authorization, policy, approval, audit,
secret handling, redaction, artifacts, cancellation, events, and trace.

## Product Boundaries

### Workflow Product

The Workflow product owns deterministic execution:

- Workbench workflow UI;
- `WorkflowSpec` authoring, validation, versioning, and running;
- `WorkflowRun` APIs, workers, events, and approvals;
- curated `CapabilityCatalog`;
- standalone `CapabilityRun` APIs, workers, events, and approvals;
- deterministic node/capability executors;
- capability worker and execution policy.

The Workflow product is the deterministic capability provider for MVP.

### Agent Product

The Agent product owns intelligent harness behavior:

- Agent threads, messages, skills, and runs;
- model loop and tool proposal handling;
- runtime todos and plans;
- workspace, artifacts, memory, sandbox, and subagents;
- Agent stream and trace;
- Agent approval presentation for Agent-owned actions;
- Workflow capability client adapter.

Agent consumes Workflow capabilities through the Workflow product API. It does
not import Workbench internals, schedule workflow graphs, or execute workflow
nodes directly.

### Platform

Platform owns cross-cutting control-plane concerns:

- identity and organization context;
- hosted access and delegated tokens;
- scope and resource authorization;
- grants and connection policy;
- audit;
- service identity and token exchange.

Cross-product calls should default to delegated user identity. Service identity
is reserved for explicit background/system tasks and must include audit metadata
that identifies the originating actor, source run, and purpose.

## Core Concepts

### Capability Catalog

The Workflow product exposes a curated capability catalog. Agent consumes this
catalog and maps capabilities to Agent tool descriptors.

The catalog is not the raw workflow node catalog.

Raw nodes are designed for workflow graph authoring and may include trigger,
branching, manual approval, mapping, and UI semantics. Agent needs stable,
action-oriented tool descriptors with natural-language usage, schemas, risk,
scopes, approval policy, and output expectations.

Example:

```json
{
  "key": "http_download",
  "version": "0.1.0",
  "displayName": "Download URL",
  "description": "Fetch content from an HTTP or HTTPS URL.",
  "agentToolName": "workflow.http_download",
  "inputSchema": {
    "type": "object",
    "required": ["url"],
    "properties": {
      "url": { "type": "string" },
      "responseType": { "type": "string", "enum": ["text", "json"] }
    }
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "status": { "type": "number" },
      "headers": { "type": "object" },
      "body": {}
    }
  },
  "riskLevel": "read",
  "requiredScopes": ["workflow.capability.invoke.http_download"],
  "approvalPolicy": "on_risk",
  "executionRecordPolicy": "capability_run",
  "backing": {
    "kind": "core_node",
    "nodeType": "core.httpRequest"
  }
}
```

The same underlying executor may back multiple capabilities. For example,
`core.httpRequest` may back `http_download`, `fetch_json`, and `call_webhook`
with different schemas, risk levels, and approval policies.

### CapabilityRun

A `CapabilityRun` is a first-class deterministic execution record for a single
capability invocation outside a full workflow graph.

It is not a hidden `WorkflowRun`, and it is not merely an Agent trace event.

```txt
WorkflowRun   = execution of a saved or inline WorkflowSpec
CapabilityRun = execution of one curated deterministic capability
AgentRun      = execution of an AI harness task
```

Capability runs support:

- status;
- input and output;
- event history and stream;
- approvals;
- cancellation;
- retry policy where applicable;
- artifacts;
- audit correlation;
- source and parent run references.

Recommended statuses:

```txt
queued
running
waiting_approval
completed
failed
cancelled
```

### AgentRun

When Agent calls a Workflow capability, the Agent run records an external run
reference rather than duplicating the capability execution state.

Agent events should include the external capability run id and correlation
metadata. The Workflow product remains the source of truth for the capability
run and its approval record.

## APIs

The Workflow product should expose capability APIs alongside workflow APIs:

```txt
GET  /api/capabilities
GET  /api/capabilities/:key

POST /api/capabilities/:key/runs
GET  /api/capability-runs/:runId
GET  /api/capability-runs/:runId/events?afterSequence=123
GET  /api/capability-runs/:runId/stream?afterSequence=123

POST /api/capability-runs/:runId/cancel
POST /api/capability-runs/:runId/approvals/:approvalId/resolve
```

Agent product APIs remain Agent-owned:

```txt
POST /api/runs
GET  /api/runs/:runId
GET  /api/runs/:runId/summary
GET  /api/runs/:runId/events?afterSequence=123
GET  /api/runs/:runId/stream?afterSequence=123
POST /api/runs/:runId/cancel
POST /api/runs/:runId/external-approval/resolve
POST /api/runs/:runId/external-run/resolve
```

The MVP transport is HTTP plus SSE. Reverse operations such as approval,
cancel, and resume use HTTP. WebSocket may be added later for collaborative or
interactive sessions, but the first contract should be HTTP/SSE.

## Agent Calls Workflow Capability

Agent should call capabilities through a Workflow capability adapter:

```txt
model proposes tool call
  -> Agent Harness normalizes tool call
  -> Agent skill allowed-tool policy
  -> Agent WorkflowCapabilityAdapter
  -> Workflow product CapabilityRun API
  -> Workflow product policy/authz/approval/executor
  -> CapabilityRun events
  -> Agent observes result and continues
```

MVP behavior:

- short capability calls default to synchronous wait;
- long capability calls may return a `capabilityRunId` and continue
  asynchronously;
- the protocol supports both modes;
- approval is owned by the Workflow product;
- asynchronous CapabilityRun status is owned by the Workflow product;
- Agent UI may present and resolve Workflow-owned approvals through Workflow
  APIs.

Agent should not create a second approval record for a Workflow capability
approval. It should store and stream a reference to the Workflow-owned approval.
The Agent run may enter `waiting_approval` with `current_external_approval`
pointing at the Workflow-owned approval. Resolving that reference through the
run-scoped Agent API records `external_approval.resolved` and either requeues
the Agent run or fails it if the Workflow approval was rejected; the underlying
approval record remains owned by Workflow.

Agent should also not duplicate asynchronous CapabilityRun state into an
Agent-owned scheduler. If a provider returns `status="running"` with an external
run reference, the Agent run may enter `waiting_external_run` with
`current_external_run` pointing at the provider-owned CapabilityRun. Resolving
that reference through the run-scoped Agent API records terminal
`external_run.*` events and requeues, fails, or cancels the Agent run around the
provider-owned result. Completed external results are placed back on the Agent
worker queue, and the next harness continuation receives the external output
through bounded typed tool-result context that includes the external
capability run id.
Provider retries that repeat the same terminal status for the same CapabilityRun
are idempotent. A late callback with a different terminal status is rejected so
Agent does not overwrite the already recorded provider-owned outcome. The
run-scoped resolve response should expose typed metadata for the external
CapabilityRun id, terminal status, idempotency, and fresh requeue decision while
preserving the Agent Run fields expected by control-plane clients.
While waiting, Agent may expose an `active_external_run` diagnostic with wait
age and stale status, and run lists may filter stale waits for operator
attention. This diagnostic must not become polling, cancellation, retry, or
Workflow scheduling behavior. Stale diagnostics may include operator action
hints for checking provider status or resolving the external run through the
existing Agent control-plane endpoint; the hints are metadata, not execution.

Current Agent backend support covers the provider-side adapter contract:
injected `WorkflowCapabilityProvider` instances publish typed
`WorkflowCapabilitySpec` descriptors, execute through the Aithru capability
router, and return `AgentExternalRunRef` values that stream as `external_run.*`
events. `completed`, `failed`, and `cancelled` results are terminal; `running`
results pause Agent as `waiting_external_run` until the provider calls the
run-scoped resolve API. Completed external run results requeue the Agent Run and
are collected into subsequent context packets from `external_run.completed`
events. Failed or cancelled external runs are exposed in Agent run summaries as
derived diagnostics over `external_run.*` events, so UI surfaces can distinguish
provider failures from Agent harness failures. Duplicate terminal callbacks with
the same status return the current Agent Run without writing duplicate events;
conflicting terminal callbacks return an error. Resolve responses include
typed idempotency and requeue metadata so clients can distinguish a fresh
completed callback from a duplicate provider retry. Active waiting external runs
can be flagged as stale in summaries and run-list filters, and stale summaries
can include inert operator action hints. The backend also includes a controlled
HTTP JSON provider for a settings-configured CapabilityRun endpoint.
It posts typed `WorkflowCapabilityInvocation` payloads, validates bounded
`WorkflowCapabilityResult` responses, requires explicit allowed hosts, and still
must not import Workbench internals or execute `WorkflowSpec` graphs directly.

Recommended Agent event shape:

```json
{
  "type": "external_run.created",
  "payload": {
    "kind": "capability",
    "capabilityKey": "http_download",
    "capabilityRunId": "caprun_123",
    "toolCallId": "toolcall_456"
  }
}
```

If the capability waits for approval:

```json
{
  "type": "external_approval.requested",
  "payload": {
    "kind": "capability",
    "capabilityRunId": "caprun_123",
    "approvalId": "capapproval_456"
  }
}
```

## Workflow Calls Agent

The Workflow product calls Agent through explicit workflow nodes such as:

```txt
agent.skill
agent.task
```

The outer graph remains a formal `WorkflowSpec`. Agent owns only the intelligent
harness behavior inside that node.

Recommended node behavior:

```txt
WorkflowRun reaches agent.skill node
  -> Workflow product creates AgentRun through Agent API
  -> node waits for AgentRun completion or pause/failure
  -> WorkflowRun records AgentRun reference in node events
  -> node output is mapped from AgentRun result/artifacts
```

Workflow node events should include an external run reference:

```json
{
  "type": "node.externalRun.started",
  "nodeId": "review",
  "externalRun": {
    "kind": "agent",
    "id": "arun_123"
  }
}
```

## Workflow Nodes Calling Capabilities

Not every workflow node should create a standalone `CapabilityRun`.

Pure graph/control/transform nodes should execute inline within the
`WorkflowRun`. Risky, external, long-running, auditable, or independently
cancellable capabilities should create a `CapabilityRun`.

The capability descriptor should declare:

```txt
executionRecordPolicy = inline | capability_run | auto
```

Examples:

```txt
json.pick       -> inline
text.template   -> inline
http_download   -> capability_run or auto
send_email      -> capability_run
agent.skill     -> external AgentRun
```

When a workflow node creates a `CapabilityRun`, both sides should store source
references:

```json
{
  "source": {
    "kind": "workflow_node",
    "workflowRunId": "wrun_123",
    "nodeId": "download"
  }
}
```

## Identity and Authorization

Cross-product calls default to delegated user identity:

```txt
AgentRun actor = user_123
CapabilityRun actor = delegated:user_123
```

This prevents Agent from using service identity to bypass user grants.

Service identity is allowed only for explicit background/system tasks. Such
calls must include source, purpose, originating actor when available, and audit
metadata.

Every cross-product call should include:

```json
{
  "source": {
    "kind": "agent_tool_call",
    "agentRunId": "arun_123",
    "toolCallId": "toolcall_456"
  },
  "actor": {
    "mode": "delegated_user",
    "userId": "user_123",
    "orgId": "org_abc"
  },
  "purpose": "Agent tool call from skill research.download"
}
```

The Workflow product checks capability scopes, resource authorization,
connection policy, and approval policy. Platform audit records the actor,
source, target capability, target resources, and outcome.

## Approval Ownership

Capability approval records are owned by the Workflow product.

Both Workflow UI and Agent UI may provide approval entry points:

- Workflow UI shows the global capability approval queue.
- Agent UI shows approvals triggered by the current Agent run and may call the
  Workflow product resolve API.

The approval record must be single-source-of-truth in the Workflow product.
Resolve APIs must be idempotent to avoid double approval from multiple UIs.

## Trace and Correlation

Workflow, Capability, and Agent runs keep independent event streams:

```txt
WorkflowRun events
CapabilityRun events
AgentRun events
```

Each stream is replayable using its own run id and sequence.

Cross-product calls carry shared correlation metadata:

```json
{
  "correlationId": "corr_abc",
  "traceId": "trace_xyz",
  "parent": {
    "kind": "agent_run",
    "runId": "arun_123",
    "spanId": "toolcall_456"
  },
  "source": {
    "kind": "agent_tool_call",
    "agentRunId": "arun_123",
    "toolCallId": "toolcall_456"
  }
}
```

This allows:

- independent replay;
- jumping from Agent trace to CapabilityRun trace;
- jumping from WorkflowRun node trace to AgentRun or CapabilityRun;
- future unified trace views without merging event models.

## Deployment Model

Workflow and Agent should remain separate products and separate API/runtime
boundaries.

MVP deployment can be one host and one release bundle:

```txt
workflow-api
workflow-worker
agent-api
agent-worker
postgres
```

The products may be released together initially, but they should remain
separate processes communicating over localhost HTTP/SSE. Future deployments may
scale them independently.

## Shared Protocols, Not Shared Internals

The products should share protocol contracts, generated clients, or small SDK
packages, but they should not import each other's app internals.

Acceptable shared artifacts:

- capability catalog schema;
- capability run API client;
- event envelope types;
- source/correlation metadata types;
- delegated identity helper types;
- test fixtures for cross-product contract tests.

Forbidden coupling:

- Agent importing Workbench stores or runtime host internals;
- Workflow importing Agent harness internals;
- Agent executing Workflow nodes directly;
- Workflow treating Agent todos or plans as workflow nodes;
- either product bypassing Platform authorization or audit.

## Non-Goals

This design does not require:

- merging Workflow and Agent into one product;
- wrapping every capability call in a hidden `WorkflowSpec`;
- exposing the raw node catalog to Agent;
- adding WebSocket in MVP;
- making Platform the MVP capability catalog owner;
- duplicating approvals between Agent and Workflow;
- using service identity for normal user-triggered Agent tool calls.

## Implementation Phases

### Phase 1: Workflow Capability Catalog

- Add curated capability descriptors in the Workflow product.
- Expose `GET /api/capabilities`.
- Map existing node/tool implementations to capability descriptors.
- Start with `http_download` or `fetch_json` backed by `core.httpRequest`.

### Phase 2: CapabilityRun

- Add `CapabilityRun` storage, events, status, and SSE stream.
- Add run creation, get, events, stream, cancel, and approval resolve APIs.
- Add source/correlation metadata.
- Add platform scope/audit coverage.

### Phase 3: Agent Workflow Capability Adapter

- Add Agent adapter that reads the Workflow capability catalog.
- Convert capability descriptors to Agent tool descriptors.
- Invoke capability runs using delegated user identity.
- Support synchronous wait and asynchronous run references.
- Display Workflow-owned approval references in Agent stream/UI.
- Display and resolve asynchronous CapabilityRun references in Agent stream/UI.

### Phase 4: Workflow Agent Node

- Add `agent.skill` or `agent.task` workflow node.
- Node creates AgentRun through Agent API.
- Node records external AgentRun references in WorkflowRun events.
- Node maps Agent output/artifacts into workflow node output.

### Phase 5: Cross-Product Trace and Contract Tests

- Add shared correlation metadata helpers.
- Add contract tests for Agent -> CapabilityRun.
- Add contract tests for WorkflowRun -> AgentRun.
- Add replay tests for linked event streams.

## Acceptance Criteria

The design is acceptable when:

- Agent can call `http_download` without reimplementing HTTP execution.
- `http_download` can run outside any `WorkflowSpec`.
- the call creates a first-class `CapabilityRun`;
- the CapabilityRun owns its approval record;
- Agent can present and resolve the Workflow-owned approval;
- Agent can pause on and resolve an asynchronous provider-owned CapabilityRun;
- the call uses delegated user identity by default;
- Workflow and Agent traces remain independent but linked;
- no product imports the other's internals;
- Workflow remains deterministic execution plane;
- Agent remains AI harness execution plane.
