# DeerFlow Benchmark

Status: benchmark reference, rebaselined for native TypeScript backend

This document keeps the useful DeerFlow comparison points without treating
DeerFlow, Python, or any external agent framework as an implementation target.

## Benchmark Purpose

DeerFlow is a reference for mature agent-product behavior:

- long-running research runs;
- structured progress events;
- controlled web/search tools;
- workspace-backed artifacts;
- retry and recovery loops;
- subtask decomposition;
- evidence and citation tracking;
- operator-visible traces.

Aithru Agent should match the product qualities that matter while keeping its
own architecture:

```txt
native TypeScript harness core
  -> Aithru contracts
  -> Aithru capability router
  -> Aithru stream and trace
  -> Platform / Workbench / Core boundaries
```

## What We Reuse Conceptually

- Research should produce inspectable evidence, not just prose.
- Tool failures should be recoverable when policy allows.
- Long runs should expose progress, stale waits, and useful operator actions.
- Workspace writes should be explicit, version-aware, and traceable.
- Reports and artifacts should be generated from persisted run state.
- Subagents should be scoped workers, not workflow branches.

## What We Do Not Reuse

- DeerFlow package structure.
- DeerFlow runtime semantics.
- Any Python backend process.
- Any external framework as the owner of Agent runs, tools, stream, trace,
  memory, workspace, approvals, or workflow semantics.

## Native TS Acceptance Targets

Aithru's native backend is healthy against this benchmark when:

- model turns can stream text, usage, tool calls, and tool results;
- every real action crosses `AithruCapabilityRouter`;
- failed tools emit structured recovery metadata where appropriate;
- web/search/workflow providers are controlled external capabilities;
- external runs can pause, resume, fail, cancel, and report stale waits;
- workspace, artifact, approval, memory, subagent, and sandbox events are
  replayable from `AgentStreamEvent`;
- trace spans are projected from events rather than imported from a framework;
- the backend verifies with TypeScript tests and examples only.

## Related Specs

- [Agent Harness Design](./00-agent-harness-design.md)
- [Complete Harness Architecture](./02-complete-harness-architecture.md)
- [Capability Router](./05-capability-router.md)
- [Native TS Backend Replacement](./superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md)
