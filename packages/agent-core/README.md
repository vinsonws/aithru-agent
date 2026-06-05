# @aithru/agent-core

Core contracts for Aithru Agent.

This package defines Agent types and interfaces only. It does not call models, execute tools, schedule workflows, or depend on provider SDKs.

## Owns

- AgentTask
- AgentPlan
- AgentRun
- AgentEvent
- AgentTraceEvent
- AgentHost
- AgentEngine
- AgentModelAdapter
- AgentArtifact

## Does not own

- WorkflowSpec
- workflow graph scheduling
- concrete tools
- model provider SDKs
- UI
- server workers
