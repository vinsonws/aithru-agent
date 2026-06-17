# Aithru Agent Architecture

## Responsibility

```txt
Workflow product = deterministic workflow and capability execution plane
Agent product    = AI harness and intelligent orchestration plane
```

Agent is not a workflow runtime and does not own `WorkflowSpec`.

## Current Backend

The active implementation is the Python backend under `backend/`.

```txt
FastAPI API
  -> Agent application runtime
  -> Agent worker
  -> scripted or Pydantic AI harness driver
  -> Aithru capability router
  -> workspace / todo / artifact local tools
  -> AgentStreamEvent store
  -> trace projection
```

## Agent Owns

- Agent threads, messages, runs, todos, workspaces, artifacts, and Agent-owned
  approvals.
- Agent stream events and Agent trace projection.
- Agent-owned local tools.
- Pydantic AI driver integration through an adapter boundary.
- Future Workflow Capability client integration.

## Agent Does Not Own

- Core node execution.
- Core tool execution.
- Workbench workflow scheduling.
- Raw workflow node catalog access.
- Workflow-owned `CapabilityRun` or approval records.
- Pydantic AI public product semantics.

## Tool Boundary

Agent production tools have two kinds:

```txt
local_tool
workflow_capability
```

Stage 1 implements local tools in Python. External deterministic actions will
later go through the Workflow product:

```txt
Agent Harness
  -> Workflow Capability Adapter
  -> Workflow CapabilityRun API
  -> Workflow/Core executor
```

## Event And Trace Boundary

`AgentStreamEvent` is the source of truth.

Pydantic AI events are internal driver signals. The backend maps them into
Aithru events and projects trace spans from the Aithru event log.
