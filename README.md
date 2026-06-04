# Aithru Agent

Aithru Agent is the intelligent execution layer of the Aithru ecosystem.

## Position

```txt
aithru-core
  owns formal workflows

aithru-agent
  owns intelligent execution
```

Aithru Agent is not a workflow engine.

It provides:

- AgentTask
- AgentPlan
- AgentRun
- AgentHost
- AgentEngine
- Model Adapters
- Agent Runtime

## Initial Packages

```txt
packages/
  agent-core/
  agent-runtime/
  model-test/
  node-agent/
```

## V0 Goal

Build a minimal agent execution loop:

```txt
Task
  -> Plan
  -> Execute
  -> Tool Call
  -> Artifact
  -> Review
  -> Output
```
