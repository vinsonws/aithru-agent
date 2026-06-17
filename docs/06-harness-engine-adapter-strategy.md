# Harness Engine Adapter Strategy

Status: target strategy

This document defines how Aithru Agent should use third-party harness/runtime frameworks without giving up Aithru-owned product contracts, permission boundaries, stream protocol, trace model, or Workbench/Core integration.

## Decision

Aithru Agent should not fully self-implement a DeerFlow/DeepAgents-level harness from scratch unless third-party options fail the required adapter tests.

Instead, Aithru Agent should own:

- Agent product model;
- Agent stream protocol;
- Agent trace model;
- Skill package semantics;
- Workspace/artifact model;
- Capability Router;
- approval and redaction boundaries;
- Platform integration;
- Workbench/Core integration.

Third-party frameworks may implement or assist:

- model loop;
- planning loop;
- multi-agent orchestration;
- durable execution;
- memory mechanics;
- structured generation;
- human-in-the-loop runtime mechanics;
- framework-specific observability;
- model/provider adapters.

## One-line strategy

```txt
Aithru owns the harness protocol and capability boundary.
Third-party libraries may power the harness engine through adapters.
```

## Why not fully self-implement?

A complete AI harness includes many fast-moving mechanisms:

- model provider adapters;
- tool-calling protocols;
- streaming formats;
- durable execution;
- interrupt/resume;
- memory;
- subagents;
- context compression;
- sandbox integration;
- tracing and evaluation;
- MCP/A2A style integrations;
- UI streaming conventions;
- observability and eval workflows.

Building all of this from scratch is possible, but long-term maintenance would distract from Aithru's product value: platform permissions, business subsystems, Core capabilities, Workbench workflows, and enterprise governance.

Therefore Aithru should own the stable product boundary and use framework adapters where they reduce risk.

## Non-negotiable Aithru-owned layers

These must not be delegated to a third-party harness framework:

### 1. Product contracts

Aithru owns:

```txt
AgentThread
AgentMessage
AgentSkill
AgentRun
AgentTodo
AgentWorkspace
AgentArtifact
AgentToolDescriptor
AgentApproval
AgentMemoryEntry
AgentStreamEvent
AgentTraceSpan
```

A framework may have its own internal concepts, but those must be mapped into Aithru-owned contracts.

### 2. Stream protocol

Aithru owns `AgentStreamEvent`.

Framework-specific streams must be adapted into Aithru events:

```txt
framework event/token/tool update
  -> adapter
  -> AgentStreamEvent
  -> EventStore
  -> EventBus/SSE
```

The UI must not depend directly on framework-native stream shapes.

### 3. Capability Router

All real actions must go through Aithru Capability Router.

Third-party framework tool calls must be intercepted and routed as:

```txt
framework tool proposal
  -> Aithru adapter normalizes call
  -> skill policy
  -> platform/core/workbench authorization
  -> approval gateway
  -> AithruCapabilityRouter
  -> concrete adapter
```

No framework may directly execute filesystem, shell, browser, network, Workbench, Core, or Platform operations.

### 4. Trace and observability

Aithru owns the trace plane.

Framework traces may be imported or exported, but Aithru's canonical trace is:

```txt
AgentStreamEvent append-only log
  -> AgentTraceSpan projection
  -> Aithru Trace UI
  -> optional exporters
```

LangSmith, Langfuse, Phoenix, OpenTelemetry, or framework-native tracing are optional exporters/adapters, not the source of truth.

### 5. Platform integration

Aithru Platform owns:

- actor context;
- org context;
- JWT verification;
- hosted app token flow;
- service clients;
- token exchange;
- delegated access;
- grants;
- connection policy;
- audit.

A third-party harness must not bypass these.

### 6. Workbench/Core integration

Workbench owns formal `WorkflowSpec` product behavior. Core owns deterministic workflow/tool contracts.

Agent may:

- be invoked by Workbench through explicit `agent.*` nodes;
- invoke Workbench workflows through explicit tools;
- use selected Core tools/nodes through explicit capability adapters.

A framework must not define Aithru formal workflow semantics.

## Engine adapter interface

Aithru should define one stable adapter interface.

```ts
export interface AgentHarnessEngine {
  kind: "native" | "mastra" | "langgraph" | "pydantic_worker" | "agentscope_worker" | "external";

  run(input: AgentHarnessRunInput): AsyncIterable<AgentStreamEvent>;

  resume(input: AgentHarnessResumeInput): AsyncIterable<AgentStreamEvent>;

  cancel(runId: string): Promise<void>;
}
```

All engines receive Aithru input and emit Aithru events.

## Engine input contract

```ts
type AgentHarnessRunInput = {
  actor: AgentActorContext;
  source: "chat" | "skill" | "api" | "workbench_node" | "delegated_task";
  goal: string;
  threadId?: string;
  skillId?: string;
  workspaceId?: string;
  messages?: AgentMessage[];
  input?: unknown;
  options?: {
    streamVisibility?: "user" | "debug" | "audit";
    maxTurns?: number;
    maxToolCalls?: number;
    maxSubagents?: number;
    timeoutMs?: number;
  };
};
```

## Engine port requirements

Every engine adapter must receive these ports instead of using framework defaults directly:

```ts
type AgentHarnessEnginePorts = {
  modelRegistry: AgentModelRegistry;
  capabilityRouter: AithruCapabilityRouter;
  workspaceProvider: AgentWorkspaceProvider;
  memoryProvider: AgentMemoryProvider;
  approvalGateway: AgentApprovalGateway;
  eventWriter: AgentEventWriter;
  artifactService: AgentArtifactService;
  subagentRunner?: AgentSubagentRunner;
  sandboxProvider?: AgentSandboxProvider;
};
```

Rules:

- Model calls go through `modelRegistry`.
- Tool calls go through `capabilityRouter`.
- File operations go through `workspaceProvider`.
- Memory operations go through `memoryProvider`.
- Approvals go through `approvalGateway`.
- Events go through `eventWriter`.
- Artifacts go through `artifactService`.
- Subagents go through `subagentRunner`.
- Sandbox calls go through `sandboxProvider`.

## Candidate frameworks

### ScriptedHarnessDriver

Aithru's deterministic test driver.

Purpose:

- prove Aithru protocols;
- keep a fallback engine;
- provide deterministic tests;
- avoid framework lock-in;
- make adapters easier to compare.

Should support at minimum:

- message streaming;
- tool proposal normalization;
- capability router calls through the worker;
- workspace write/read;
- artifact creation;
- structured events.

The scripted driver is not the production intelligence layer.

### PydanticAIHarnessDriver

Pydantic AI is the default Python harness driver.

Why use it:

- Python-native agent framework;
- commercially friendly permissive license;
- model-provider flexibility;
- strong Pydantic validation and structured output;
- streaming events;
- tool calling;
- approval-compatible deferred tool patterns;
- OpenTelemetry-compatible observability.

Risks:

- Pydantic AI internal graph concepts must not become Aithru product concepts;
- Pydantic AI tools must not directly execute filesystem, network, database,
  shell, browser, Workbench, Core, or Platform operations;
- Pydantic AI native streams must be adapted to `AgentStreamEvent`;
- hosted observability integrations must remain optional.

Expected use:

```txt
Pydantic AI
  -> PydanticAIHarnessDriver
  -> Aithru Tool Bridge
  -> Aithru CapabilityRouter
  -> Aithru AgentStreamEvent
```

### MastraHarnessEngine

Mastra is no longer the default backend candidate.

Why evaluate it:

- TypeScript-native;
- likely easier for Platform hosted app integration;
- aligns with web/server development;
- has agent/app framework orientation;
- may provide useful patterns for agents, memory, tools, workflows, streaming, workspaces, observability, and server integration.

Risks:

- Mastra workflow concepts must not become Aithru Workbench workflows;
- framework-native tool execution must be intercepted;
- framework-native stream must be adapted to `AgentStreamEvent`;
- framework-native memory/workspace must obey Aithru policy.

Expected use:

```txt
Mastra internals
  -> MastraHarnessEngine adapter
  -> Aithru AgentStreamEvent
  -> Aithru CapabilityRouter
```

### LangGraphHarnessEngine

LangGraph.js is the durable runtime candidate.

Why evaluate it:

- stateful long-running agents;
- durable execution;
- interrupt/resume;
- human-in-the-loop runtime mechanics;
- streaming;
- graph/state-machine runtime maturity.

Risks:

- graph concepts may conflict with Workbench if exposed;
- LangSmith integration should not become required;
- LangGraph state must remain internal implementation detail;
- Aithru stream/trace model must remain canonical.

Expected use:

```txt
LangGraph state machine
  -> LangGraphHarnessEngine adapter
  -> Aithru AgentRun / AgentStreamEvent
```

Do not expose LangGraph nodes/edges as Aithru Agent product objects.

### AgentScope worker

AgentScope is a candidate for multi-agent research, subagent patterns, evaluation, and tracing references.

Best fit:

- advanced multi-agent patterns;
- simulation/debate/research agents;
- evaluation and tracing reference;
- Python worker or specialized engine.

Risks:

- not the natural default for TS/Web hosted agent;
- may introduce another product model;
- must not bypass Aithru capability router.

Expected use:

```txt
Aithru SubagentRunner or external worker
  -> AgentScope worker
  -> normalized events/results
```

### Vercel AI SDK

AI SDK is best treated as UI/stream integration, not the complete harness.

Best fit:

- frontend chat hooks;
- UI message rendering;
- data stream compatibility;
- model provider utilities;
- lightweight tool UI parts.

Expected use:

```txt
Aithru AgentStreamEvent
  -> optional AI SDK UI data stream adapter
  -> agent-web rendering
```

## Recommended route

Default route:

```txt
1. Implement Python Aithru backend contracts.
2. Keep ScriptedHarnessDriver for deterministic tests.
3. Use PydanticAIHarnessDriver as the default real harness driver.
4. Build LangGraph adapter only if durable graph-style execution becomes necessary.
5. Treat AgentScope or other frameworks as optional specialized workers.
6. Keep AI SDK as UI stream adapter, not backend harness engine.
```

## PoC validation criteria

A framework adapter is acceptable only if it can satisfy these tests.

### 1. Aithru stream compatibility

Can the adapter emit:

- `run.*`;
- `message.*`;
- `todo.*`;
- `tool.*`;
- `workspace.*`;
- `artifact.*`;
- `approval.*`;
- `subagent.*`;
- `sandbox.*` events

as `AgentStreamEvent` without leaking framework-native concepts into the product UI?

### 2. Capability router enforcement

Can all framework tool calls be forced through `AithruCapabilityRouter`?

Failure case:

```txt
framework executes a tool directly without Aithru policy
```

If that cannot be prevented, the adapter is not acceptable.

### 3. Skill mapping

Can Aithru `AgentSkill` map cleanly to the framework's prompts/tools/agents/memory without losing:

- instructions;
- when-to-use;
- allowed tools;
- allowed subagents;
- workspace policy;
- memory policy;
- sandbox policy;
- approval policy;
- output expectations?

### 4. Workspace mapping

Can framework file/workspace behavior be redirected to `AgentWorkspaceProvider`?

If framework insists on unmanaged local filesystem writes, the adapter is not acceptable for trusted server use.

### 5. Pause/resume

Can the adapter support:

- approval pause;
- approval resume;
- cancel;
- replayable event stream;
- durable run state or compatible external store?

If not, it may still be acceptable for short-lived runs but not complete harness maturity.

### 6. Trace independence

Can the adapter run without LangSmith or any commercial hosted observability dependency?

Optional exporters are allowed. Required commercial trace dependencies are not acceptable.

### 7. Platform integration

Can actor context, orgId, scopes, delegation context, and authzVersion flow through the adapter and into every tool/sandbox/workspace/memory call?

### 8. Workbench boundary

Can Workbench workflows be called only through explicit Aithru tools, without exposing Workbench internals or allowing the framework to schedule `WorkflowSpec` graphs?

## Decision matrix

| Candidate | Primary value | Main risk | Recommended role |
| --- | --- | --- | --- |
| Native | Protocol control and fallback | Could grow into too much self-built harness | Minimal built-in engine |
| Mastra | TS/Web agent framework | Must isolate its workflow/tool/memory concepts | Primary PoC/default adapter candidate |
| LangGraph.js | Durable stateful runtime | Graph concepts and LangSmith gravity | Durable runtime adapter candidate |
| PydanticAI | Python typed agents/workers | Cross-language service complexity | Specialized Python worker/tool backend |
| AgentScope | Multi-agent/eval/tracing patterns | Python/runtime/product mismatch | Reference or specialized worker |
| AI SDK | UI streaming and chat rendering | Not complete harness | Frontend stream/UI adapter |

## What to avoid

Avoid:

- choosing one framework before Aithru contracts are stable;
- letting framework-native workflows become Aithru workflows;
- letting framework-native tools bypass Capability Router;
- using LangSmith as required trace store;
- putting platform credentials inside framework/tool context;
- making browser UI depend on framework stream internals;
- writing business features directly against a framework API instead of Aithru service APIs.

## Implementation plan

### Step 1: contracts first

Implement or finalize:

- Python `domain` contracts;
- `stream` protocol;
- workspace and artifact stores;
- capability router;
- local tools.

### Step 2: Scripted driver skeleton

Implement a deterministic scripted driver to prove:

- run creation;
- message streaming;
- todos;
- workspace file operations;
- fake tool calls;
- artifact creation;
- event replay.

### Step 3: Pydantic AI driver

Build a focused adapter proving:

- Pydantic AI model loop can run under the Aithru worker;
- Pydantic AI events map to Aithru event intents;
- Pydantic AI tool calls go through Aithru Tool Bridge and CapabilityRouter;
- Aithru workspace/artifact integration remains source-of-truth;
- no bypass of Aithru policy.

### Step 4: LangGraph PoC if needed

Only if durable execution/resume is not satisfied by the Python worker and
Pydantic AI approach.

Prove:

- interrupt/resume maps to Aithru approval;
- LangGraph stream maps to Aithru stream;
- LangGraph state remains internal;
- LangSmith is optional.

### Step 5: worker ecosystem

Add optional worker adapters for Python-heavy skills:

- PydanticAI worker;
- AgentScope worker;
- custom sandbox workers.

## Final rule

```txt
Aithru can outsource the mechanics of running an agent.
Aithru must not outsource the meaning, permission, trace, stream, or capability boundary of an agent.
```

The default engineering posture should be:

```txt
Use external harness engines where they reduce complexity.
Keep Aithru protocol, security, observability, and Workbench/Core integration first-class and framework-independent.
```
