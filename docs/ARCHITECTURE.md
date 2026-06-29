# Aithru Agent Architecture

Status: current architecture

## Responsibility

```txt
Workflow product = deterministic workflow and capability execution plane
Agent product    = AI harness and intelligent orchestration plane
```

Agent is not a workflow runtime and does not own `WorkflowSpec`.

## Current Backend

The active implementation is the native TypeScript backend under `backend-ts/`.
The previous Python backend package has been removed from tracked source.

```txt
Fastify API
  -> Agent application runtime
  -> Agent worker
  -> native TypeScript scripted core or model turn loop
  -> Aithru capability router
  -> local, external, or workflow capability adapters
  -> AgentStreamEvent store
  -> trace projection
```

The backend must not start, import, shell out to, or depend on a Python backend
process. Provider SDKs may be wrapped behind Aithru model adapters, but no
third-party agent framework owns Agent product semantics or tool execution.

## Agent Owns

- Agent threads, messages, runs, todos, workspaces, artifacts, and Agent-owned
  approvals.
- Agent stream events and Agent trace projection.
- Agent-owned local tools and policy-aware external/workflow tool adapters.
- The native model turn loop, retry/recovery rules, pause/resume behavior, and
  capability boundary.
- Future Workflow Capability client integration through explicit APIs.

## Agent Does Not Own

- Core node execution.
- Core tool execution.
- Workbench workflow scheduling.
- Raw workflow node catalog access.
- Workflow-owned `CapabilityRun` or approval records.
- Public semantics from any model SDK or agent framework.

## Tool Boundary

Agent production tools have three kinds:

```txt
local_tool
external_tool
workflow_capability
```

Every real action flows through the same boundary:

```txt
model adapter
  -> native model turn loop
  -> AithruCapabilityRouter
  -> policy / scope / approval / audit
  -> concrete adapter
  -> AgentStreamEvent / trace / artifact / workspace state
```

Model adapters propose tool calls. They never execute tools directly.

## Event And Trace Boundary

`AgentStreamEvent` is the source of truth.

Model-provider events are internal adapter signals. The backend maps them into
Aithru events and projects trace spans from the Aithru event log.
