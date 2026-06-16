# Python Pydantic AI Agent Backend Design

Status: approved product/architecture design

Date: 2026-06-16

## Summary

`aithru-agent` will be rebuilt as a Python-first Agent backend.

The new backend will use Pydantic AI as the default Agent harness engine, while
Aithru continues to own product contracts, API semantics, run state, event
streaming, trace projection, approvals, workspaces, artifacts, platform
authorization, and capability boundaries.

The existing TypeScript backend and package implementation are no longer the
target runtime architecture. They may be used as migration reference material,
but the first production-oriented backend should be implemented in Python.

```txt
Aithru Agent Backend =
  FastAPI control plane
  + Pydantic AI harness worker
  + Aithru capability boundary
  + Aithru event stream / trace / approval / workspace model
```

## Core Decision

Use Pydantic AI as the default backend harness implementation.

Pydantic AI is responsible for:

- model loop mechanics;
- tool calling mechanics;
- structured output;
- streaming agent events;
- deferred tool calls and approval-compatible pauses;
- optional OpenTelemetry instrumentation.

Aithru remains responsible for:

- Agent Thread, Message, Run, Todo, Tool, Approval, Workspace, Artifact, Memory,
  and Trace product contracts;
- HTTP API shape;
- persistence;
- permission and approval boundaries;
- capability routing;
- event stream and replay;
- trace projection;
- platform identity, scopes, audit, and redaction;
- Workbench/Core integration boundaries.

Pydantic AI types and internal graph concepts must not become public Aithru API
objects.

## Commercial Constraints

The backend must remain friendly for commercial and private deployments.

Rules:

- Aithru-owned code remains Apache-2.0.
- Third-party runtime dependencies should be MIT, Apache-2.0, BSD, or similarly
  permissive.
- Do not add AGPL, SSPL, BUSL, Commons Clause, or source-available runtime
  dependencies.
- Do not require a hosted tracing, hosted agent runtime, or hosted memory
  service.
- Pydantic Logfire, Phoenix, LangSmith, SigNoz, or other observability backends
  may be optional exporters only.
- The model provider must be configurable. OpenAI, Anthropic, Bedrock, Gemini,
  Mistral, local OpenAI-compatible servers, and other providers must remain
  possible.
- Prompt, event, trace, tool result, approval, workspace, and artifact data must
  be stored by Aithru, not only inside a third-party framework.

## Product Target

The first backend stage should be functionally comparable to DeerFlow-style
agent execution:

```txt
user goal
  -> Agent Run
  -> runtime todos / plan
  -> Pydantic AI reasoning
  -> controlled tool calls
  -> workspace read/write
  -> artifact creation
  -> approval pause/resume when needed
  -> replayable event stream
  -> trace projection
  -> final answer / report
```

This does not make Agent a Workflow system. Runtime todos and tool sequences are
Agent harness state, not `WorkflowSpec`, not Workbench nodes, and not a graph
editor.

## Non-Goals For Stage 1

Stage 1 will not implement:

- Workbench `WorkflowSpec` authoring or scheduling;
- a workflow graph editor;
- browser UI;
- production-grade sandbox isolation beyond the restricted local provider;
- hosted long-term memory beyond the stage-1 memory store;
- MCP integration;
- external Workflow Capability HTTP integration;
- distributed queue infrastructure as a hard dependency;
- multi-tenant production database schema beyond the first store interface.

These can be added after the Python backend proves the core Agent run loop.

## Repository Direction

The TypeScript implementation can be deleted during the backend rewrite.

Expected removals:

```txt
apps/agent-server
packages/agent-core
packages/agent-stream
packages/agent-skills
packages/agent-workspace
packages/agent-tools
packages/agent-harness
packages/agent-trace
examples/harness-basic.ts
pnpm-workspace.yaml
tsconfig*.json
```

The TypeScript source may be inspected during migration, but should not remain
as the main backend runtime.

Future frontend or SDK code can consume generated OpenAPI and JSON Schema
contracts from the Python backend instead of depending on TypeScript package
contracts as the source of truth.

## Target Directory Structure

```txt
backend/
  pyproject.toml
  uv.lock
  README.md

  src/
    aithru_agent/
      __init__.py

      api/
        main.py
        dependencies.py
        routes/
          health.py
          threads.py
          messages.py
          runs.py
          events.py
          approvals.py
          workspaces.py
          artifacts.py

      worker/
        main.py
        runner.py
        queue.py

      domain/
        ids.py
        actor.py
        thread.py
        message.py
        run.py
        todo.py
        tool.py
        approval.py
        workspace.py
        artifact.py
        memory.py
        skill.py
        errors.py

      application/
        run_service.py
        thread_service.py
        approval_service.py
        workspace_service.py
        artifact_service.py
        event_projection.py

      harness/
        engine.py
        context_builder.py
        model_registry.py
        result_types.py
        drivers/
          scripted/
            driver.py
          pydantic_ai/
            driver.py
            agent_factory.py
            deps.py
            tool_bridge.py
            event_mapper.py
            usage_mapper.py

      capabilities/
        router.py
        policy.py
        descriptors.py
        local_tools/
          workspace.py
          artifact.py
          todo.py
        workflow_capability/
          client.py
          adapter.py

      stream/
        events.py
        writer.py
        store.py
        sse.py

      trace/
        spans.py
        projector.py

      workspace/
        provider.py
        memory_provider.py
        fs_provider.py

      artifacts/
        service.py
        store.py

      skills/
        manifest.py
        resolver.py
        loader.py

      persistence/
        protocols.py
        memory/
          store.py
        postgres/
          store.py
          migrations/

      platform/
        actor_context.py
        scopes.py
        audit.py
        config.py

      observability/
        logging.py
        metrics.py
        redaction.py

      settings.py

  tests/
    unit/
    integration/
    contract/
    e2e/
```

## Layer Responsibilities

### `api`

The FastAPI control plane.

Responsibilities:

- accept authenticated Agent API requests;
- validate request bodies;
- resolve actor/org/scope context;
- start, cancel, resume, and inspect runs;
- expose event replay and SSE streams;
- expose workspace and artifact APIs;
- avoid direct model, tool, or Pydantic AI execution logic.

### `worker`

The Agent execution process.

Responsibilities:

- consume run requests;
- create one execution task per run;
- support cancellation;
- support approval pause/resume;
- write events as the run progresses;
- hide whether execution is in-process or queue-backed.

Stage 1 may use an in-process queue. The queue interface should allow later
replacement with Redis, Temporal, Celery, DBOS, or another durable runner.

### `domain`

Pure Aithru product contracts.

Responsibilities:

- define Agent Thread, Message, Run, Todo, Tool, Approval, Workspace, Artifact,
  Skill, Memory, Actor, and Error models;
- remain independent of FastAPI, Pydantic AI, database clients, and provider
  SDKs;
- provide JSON-serializable schemas used by API, persistence, and stream code.

### `application`

Use-case orchestration.

Responsibilities:

- implement thread, run, approval, workspace, and artifact application services;
- call worker, store, and event writer through interfaces;
- keep HTTP-specific logic out of business operations.

### `harness`

The Agent harness abstraction and drivers.

Responsibilities:

- define the Aithru harness driver interface;
- build model context;
- inject bounded thread message summaries;
- inject bounded workspace file summaries when workspace read policy allows;
- call Pydantic AI through the `pydantic_ai` driver;
- map Pydantic AI output/events into Aithru events;
- expose a scripted driver for deterministic tests.

Only `harness/drivers/pydantic_ai` may depend directly on Pydantic AI.

### `capabilities`

The controlled execution boundary.

Responsibilities:

- list available tools;
- enforce skill/run policy;
- validate tool input;
- check risk and approval requirements;
- execute local Agent tools;
- later call Workflow Capability APIs;
- normalize tool results for the harness and event stream.

No Pydantic AI tool function may directly execute filesystem, network,
database, shell, browser, Workbench, or Platform operations. Every real action
must enter through the capability router.

### `stream`

The canonical Agent event log.

Responsibilities:

- define `AgentStreamEvent`;
- append events with sequence numbers;
- support replay by run;
- support SSE encoding;
- remain the source of truth for timeline and trace projection.

Pydantic AI native events are implementation input, not the product event
format.

### `trace`

Trace projection.

Responsibilities:

- project `AgentStreamEvent` into `AgentTraceSpan`;
- provide data for run timeline and debugging visualization;
- optionally correlate with OpenTelemetry spans.

The canonical trace starts from Aithru events. OTel is an exporter/importer
layer, not the source of truth.

### `workspace`

Agent workspace abstraction.

Responsibilities:

- provide scoped file read/write/list/delete operations;
- support in-memory storage for tests;
- support filesystem-backed storage for local/dev use;
- reserve a path for object-storage-backed implementations.

### `artifacts`

Durable task outputs.

Responsibilities:

- create report, markdown, JSON, file, patch, and decision artifacts;
- link artifacts to runs and workspaces;
- emit artifact events;
- provide retrieval APIs.

### `skills`

Skill loading and policy input.

Responsibilities:

- parse skill manifests;
- resolve selected skills;
- expose instructions and allowed tools to the harness;
- keep skills as reusable Agent capabilities, not workflows.

### `persistence`

Storage interfaces and implementations.

Responsibilities:

- define store protocols;
- provide memory stores for stage 1;
- provide Postgres-ready boundaries;
- keep persistence replaceable without changing harness code.

### `platform`

Platform integration boundary.

Responsibilities:

- actor context;
- organization context;
- scopes;
- audit;
- delegated identity;
- configuration.

Stage 1 can provide standalone defaults, but the interface must support hosted
Platform mode.

### `observability`

Operational logging, metrics, and redaction.

Responsibilities:

- structured logs;
- event redaction;
- token/cost metrics;
- optional OpenTelemetry export;
- no required hosted observability service.

## Execution Flow

```txt
POST /api/agent/runs
  -> API validates actor and input
  -> RunService creates AgentRun
  -> EventWriter emits run.created
  -> Worker queue receives run request
  -> Worker starts PydanticAIHarnessDriver
  -> ContextBuilder builds instructions/messages/tools
  -> Pydantic AI starts model loop
  -> Pydantic event mapper emits model/message/tool events
  -> Pydantic tool call enters AithruToolBridge
  -> CapabilityRouter prepares and executes the tool
  -> Tool result returns to Pydantic AI
  -> Model continues reasoning
  -> Artifact/final answer created
  -> EventWriter emits run.completed
```

## API Surface For Stage 1

```txt
GET    /api/agent/health

POST   /api/agent/threads
GET    /api/agent/threads
GET    /api/agent/threads/{thread_id}
POST   /api/agent/threads/{thread_id}/messages
GET    /api/agent/threads/{thread_id}/messages

POST   /api/agent/runs
GET    /api/agent/runs
GET    /api/agent/runs/{run_id}
GET    /api/agent/runs/{run_id}/events
GET    /api/agent/runs/{run_id}/trace
GET    /api/agent/runs/{run_id}/tools
GET    /api/agent/runs/{run_id}/subagents
GET    /api/agent/runs/{run_id}/stream
POST   /api/agent/runs/{run_id}/cancel
POST   /api/agent/runs/{run_id}/resume

GET    /api/agent/approvals
GET    /api/agent/approvals/{approval_id}
POST   /api/agent/approvals/{approval_id}/resolve

GET    /api/agent/workspaces/{workspace_id}/files
GET    /api/agent/workspaces/{workspace_id}/files/{path:path}
PUT    /api/agent/workspaces/{workspace_id}/files/{path:path}
DELETE /api/agent/workspaces/{workspace_id}/files/{path:path}

GET    /api/agent/artifacts
GET    /api/agent/artifacts/{artifact_id}

POST   /api/agent/memory
GET    /api/agent/memory

POST   /api/agent/subagents
GET    /api/agent/subagents
GET    /api/agent/subagents/{key}
```

## Local Tools For Stage 1

Stage 1 tools should be small and sufficient for a DeerFlow-like file/report
agent.

```txt
workspace.list_files
workspace.read_file
workspace.write_file
workspace.delete_file
todo.create
todo.update
artifact.create
artifact.finalize
memory.search
memory.remember
subagent.delegate
sandbox.run_python
```

Tool rules:

- every tool has a descriptor;
- every tool declares risk level;
- every tool declares required scopes;
- write/delete operations require policy checks and may require approval;
- tool inputs and outputs are summarized/redacted before user-facing events;
- large outputs are written to workspace/artifacts and summarized.

## Pydantic AI Event Mapping

Pydantic AI can expose execution details through:

- streaming events;
- function tool call events;
- function tool result events;
- final result events;
- graph iteration nodes;
- OpenTelemetry spans.

Aithru should map these into product events.

Example mapping:

| Pydantic AI signal | Aithru event |
| --- | --- |
| run begins | `model.started` |
| text delta | `message.delta` |
| tool call event | `tool.proposed` |
| bridge begins execution | `tool.started` |
| bridge returns success | `tool.completed` |
| bridge returns failure | `tool.failed` |
| deferred approval required | `approval.requested`, `run.paused` |
| deferred approval resolved | `approval.resolved`, `run.resumed` |
| final result | `message.completed`, `run.completed` |
| model/provider error | `model.failed`, `run.failed` |

Pydantic AI graph node names may be included in debug visibility events or
trace metadata, but must not become public product concepts.

## Visualizing Each Step

The UI or CLI should visualize runs from Aithru events, not Pydantic AI native
events.

User-facing timeline:

```txt
Run started
Created plan
Reading workspace files
Analyzing input
Writing report
Creating artifact
Final answer
Run completed
```

Developer/debug timeline:

```txt
model request
model response
tool call arguments
tool policy decision
tool execution
tool result summary
token usage
latency
error/retry metadata
```

Do not rely on or expose hidden chain-of-thought. If a provider emits thinking
or reasoning deltas, the event mapper must apply provider policy and Aithru
redaction rules before storing or streaming them.

## Approval Model

Stage 1 supports Agent-owned approvals for local tools.

Approval flow:

```txt
Pydantic AI proposes tool call
  -> AithruToolBridge
  -> CapabilityRouter.prepare
  -> approval required
  -> approval.requested
  -> run.paused
  -> user resolves approval
  -> approval.resolved
  -> run.resumed
  -> CapabilityRouter.execute
  -> tool result returns to Pydantic AI
```

Pydantic AI deferred tools can be used internally to represent pause/resume,
but the persisted approval object and public API belong to Aithru.

If a local tool returns `failed` or `denied` after execution begins, the bridge
must emit `tool.failed`/`tool.denied` and surface an Aithru error so the worker
projects `model.failed` and `run.failed`. Tool failures must not be silently
converted into successful model context.

## Event Types For Stage 1

Stage 1 must support these event families:

```txt
run.created
run.started
run.paused
run.resumed
run.completed
run.failed
run.cancelled

message.created
message.delta
message.completed
message.failed

todo.created
todo.updated
todo.completed
todo.blocked
todo.cancelled

model.started
model.completed
model.failed

tool.proposed
tool.started
tool.completed
tool.failed
tool.denied

approval.requested
approval.resolved
approval.expired

workspace.file.created
workspace.file.updated
workspace.file.deleted
workspace.file.read
workspace.snapshot.created

artifact.created
artifact.updated
artifact.finalized
```

## Persistence For Stage 1

Stage 1 should implement in-memory stores first, behind interfaces:

- run store;
- thread store;
- message store;
- event store;
- approval store;
- workspace file store;
- artifact store.

Postgres-oriented interfaces should exist early, but migrations can follow once
the in-memory behavior is verified.

## Testing Strategy

Stage 1 should be test-first.

Required test areas:

- domain model serialization;
- event ordering and replay;
- SSE replay after sequence;
- capability policy allow/deny/approval;
- workspace local tools;
- artifact local tools;
- todo local tools;
- Pydantic AI event mapper;
- Pydantic AI tool bridge;
- run create/start/complete;
- approval pause/resume;
- cancellation;
- failure projection;
- API contract tests;
- e2e DeerFlow-like file/report task.

The scripted harness driver should remain available for deterministic tests
without a real model provider.

## First Acceptance Demo

The first completed backend should pass this demo:

```txt
Input:
  A workspace contains one or more source files.

User goal:
  Analyze the workspace files and create a concise report.

Expected behavior:
  1. API creates an Agent run.
  2. Worker starts a Pydantic AI-backed harness run.
  3. Agent creates or updates todos.
  4. Agent lists and reads workspace files through Aithru tools.
  5. Agent writes /reports/report.md through Aithru tools.
  6. Agent creates a report artifact.
  7. Agent emits message and timeline events.
  8. Agent completes with a final answer.
  9. Client can replay the full event stream.
  10. Trace projection shows model and tool spans.
```

The event stream must be sufficient to visualize each significant step.

## Migration Plan

Recommended migration order:

1. Add Python backend skeleton and test tooling.
2. Port Aithru domain contracts to Python.
3. Implement stream events, writer, in-memory event store, and SSE encoding.
4. Implement run/thread/message/approval/workspace/artifact stores.
5. Implement local capability router and local tools.
6. Implement scripted harness driver.
7. Implement Pydantic AI driver, tool bridge, and event mapper.
8. Implement FastAPI routes.
9. Add e2e file/report demo.
10. Remove TypeScript backend/packages once Python parity is reached.
11. Update README and architecture docs to make Python the backend source of
    truth.

## Design Guardrails

- Agent runtime state is not Workflow state.
- Pydantic AI graph nodes are not Workbench nodes.
- Pydantic AI tools must not directly execute real actions.
- Aithru `AgentStreamEvent` remains the product event source of truth.
- Aithru trace remains a projection from Aithru events.
- Approval records belong to Aithru for Agent-owned local tools.
- Workflow capability approvals remain Workflow-owned when added later.
- Pydantic AI instrumentation is optional and exportable.
- Model providers are configurable.
- Sensitive data is redacted before user-facing events and logs.

## Open Implementation Choice

Stage 1 can run API and worker in the same process using an in-process queue.
The interfaces must still treat worker execution as separable so the production
deployment can later split API and worker processes without changing public API
contracts.
