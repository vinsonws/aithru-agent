# Aithru Agent Architecture

## Responsibility

```txt
Formal Workflow
  -> aithru-core

Intelligent Execution
  -> aithru-agent
```

## Core Concepts

### AgentTask

Represents a bounded intelligent task.

### AgentPlan

Task-local execution plan.

Not a WorkflowSpec.

### AgentRun

Execution state of a task.

### AgentHost

Bridge between agent runtime and environment.

Responsible for:

- tool execution
- approval
- artifacts
- trace events

### AgentEngine

Execution strategy.

Examples:

- classify
- plan-run-review

## Package Layout

```txt
packages/
  agent-core/
    contracts
    types

  agent-runtime/
    engines
    runners

  agent-model-test/
    scripted adapters

  agent-model-openai-compatible/
    OpenAI-compatible HTTP adapter

  node-agent/
    agent.task
    agent.classify
```
