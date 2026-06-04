# @aithru/agent-runtime

Agent execution runtime for Aithru Agent.

This package runs bounded intelligent tasks. It is not a workflow runtime and does not own WorkflowSpec.

## Initial engines

- `ClassifyEngine`
- `PlanRunReviewEngine`

## Boundary

Tool calls must go through `AgentHost.callTool`.

Workflow execution belongs to `aithru-core`.
