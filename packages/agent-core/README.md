# @aithru/agent-core

Agent-owned contract types for Aithru Agent.

This package defines the Agent product model: threads, messages, skills, runs,
todos, workspace references, artifacts, Agent-owned approvals, tool
descriptors, subagent references, memory references, and error types.

It does not define Aithru Core workflow execution. Agent production tools are
limited to:

- `local_tool`: Agent-owned harness tools such as workspace operations.
- `workflow_capability`: deterministic capabilities exposed by the Workflow
  product through `CapabilityCatalog` and `CapabilityRun` APIs.

Agent does not execute raw Core nodes, Core tools, Workbench workflow graphs, or
Workflow product internals directly.
