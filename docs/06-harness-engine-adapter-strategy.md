# Native Harness Core Strategy

Status: current decision

This document defines how Aithru Agent uses external libraries after the native
TypeScript backend replacement.

## Decision

Aithru Agent owns its core harness. The backend must not replace the previous
Python implementation with another agent framework.

Disallowed as core owners:

- model-loop frameworks;
- graph/runtime agent frameworks;
- framework-owned workflow systems;
- framework-owned memory/workspace/tool execution;
- framework-native stream protocols exposed to the UI.

Allowed:

- model provider SDKs behind Aithru model adapters;
- schema, HTTP, SQLite, testing, and utility libraries;
- optional exporters that receive already-redacted Aithru trace data;
- future sidecar services only when called through explicit capability APIs.

## One-line Strategy

```txt
Aithru owns the harness core. External libraries are replaceable implementation
details behind Aithru contracts.
```

## Non-negotiable Aithru-owned Layers

### 1. Product Contracts

Aithru owns:

```txt
AgentThread
AgentMessage
AgentSkill
AgentRun
AgentTodo
AgentWorkspace
AgentArtifact
AgentToolDescriptor
AgentApproval
AgentMemoryEntry
AgentStreamEvent
AgentTraceSpan
```

Provider-specific objects must be normalized before crossing into product or
API contracts.

### 2. Native Model Turn Loop

The TypeScript backend owns the loop that:

- builds model context;
- streams text and usage events;
- normalizes tool calls;
- returns tool results to the next turn;
- enforces turn limits;
- pauses for approval or external runs;
- completes, fails, cancels, and recovers runs.

Model SDKs return normalized `AgentModelEvent` values. They do not execute
tools and do not own run state.

### 3. Stream Protocol

Aithru owns `AgentStreamEvent`.

```txt
provider event/token/tool update
  -> model adapter
  -> native model turn loop
  -> AgentStreamEvent
  -> EventStore
  -> SSE/API/UI
```

The UI must not depend on provider-native stream shapes.

### 4. Capability Router

All real actions must go through `AithruCapabilityRouter`.

```txt
model tool proposal
  -> native turn loop
  -> skill policy
  -> platform/core/workbench authorization
  -> approval gateway
  -> capability router
  -> concrete adapter
```

No model adapter may directly execute filesystem, shell, browser, network,
Workbench, Core, Platform, memory, or sandbox operations.

### 5. Trace and Observability

Aithru owns the trace plane:

```txt
AgentStreamEvent append-only log
  -> AgentTraceSpan projection
  -> Aithru Trace UI
  -> optional exporters
```

OpenTelemetry, Langfuse, Phoenix, or similar systems may be exporters only.

### 6. Workbench/Core Integration

Workbench owns formal `WorkflowSpec` product behavior. Core owns deterministic
workflow/tool contracts.

Agent may:

- be invoked by Workbench through explicit `agent.*` nodes;
- invoke Workbench workflows through explicit tools;
- use selected Core-backed capabilities through Workflow capability adapters.

Agent must not define Aithru formal workflow semantics.

## Engine Interface

The backend exposes one Aithru-owned execution interface:

```ts
export interface HarnessCore {
  execute(run: AgentRun, options?: unknown): Promise<AgentRun>;
}
```

Current implementations:

- `ScriptedHarnessCore`: deterministic execution for examples and tests.
- `ModelTurnLoop`: native model-driven loop using normalized model events.

Future implementations must satisfy the same ownership rules and cannot expose
framework-native semantics as product API.

## Model Adapter Interface

Model providers are wrapped by an Aithru adapter:

```ts
export interface AgentModelAdapter {
  createTurn(input: AgentModelTurnInput): AsyncIterable<AgentModelEvent>;
}
```

Allowed event kinds are Aithru-owned:

```txt
text_delta
reasoning_delta
tool_call
usage
failed
```

This keeps provider SDKs replaceable.

## Disallowed Core Dependencies

The backend must not add a dependency whose purpose is to own:

- agent planning semantics;
- tool execution;
- runtime graph scheduling;
- workflow graphs;
- durable agent state;
- framework-native memory/workspace;
- approval pause/resume;
- canonical stream or trace format.

If such a dependency is proposed, it must be redesigned as either a provider SDK
behind a narrow adapter or a separate external capability called through the
capability router.

## Validation Criteria

Any future adapter or library use is acceptable only if:

- `AgentStreamEvent` remains canonical;
- `AithruCapabilityRouter` remains the only execution boundary;
- tool calls can be audited, redacted, approved, denied, and replayed;
- model provider objects never become public API contracts;
- Workbench/Core ownership boundaries stay intact;
- the backend can run without any Python backend process;
- the backend can run without a third-party agent framework.

## Implementation Plan

1. Keep `backend/packages/contracts/src` as the public contract layer.
2. Keep `backend/packages/harness/src` as the native harness core.
3. Keep `backend/packages/model/src` limited to provider adapters and normalized
   model events.
4. Keep `backend/packages/capabilities/src` as the only path to real actions.
5. Add tests for any future adapter proving that direct execution is impossible.

## Final Rule

```txt
Aithru may use libraries. Aithru must not outsource the meaning, permission,
trace, stream, state, or capability boundary of an agent.
```
