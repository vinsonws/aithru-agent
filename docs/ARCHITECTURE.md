# Aithru Agent Architecture

## Responsibility

```txt
Workflow product = deterministic workflow and capability execution plane
Agent product    = AI harness and intelligent orchestration plane
```

Agent is not a workflow runtime and does not own `WorkflowSpec`.

## Agent Owns

- Agent threads, messages, skills, runs, todos, workspace, artifacts, and
  Agent-owned approvals.
- Agent stream events and Agent trace projections.
- Agent-owned local tools.
- Workflow capability client integration.

## Agent Does Not Own

- Core node execution.
- Core tool execution.
- Workbench workflow scheduling.
- Raw workflow node catalog access.
- Workflow-owned `CapabilityRun` or approval records.

## Tool Boundary

Agent production tools have two kinds:

```txt
local_tool
workflow_capability
```

External deterministic actions go through the Workflow product:

```txt
Agent Harness
  -> WorkflowCapabilityAdapter
  -> Workflow CapabilityRun API
  -> Workflow/Core executor
```
