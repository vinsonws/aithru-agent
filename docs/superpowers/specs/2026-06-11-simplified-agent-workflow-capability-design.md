# Simplified Agent Workflow Capability Design

Status: approved design

Date: 2026-06-11

## Goal

Redesign `aithru-agent` so the Agent code follows
`docs/08-workflow-capability-integration.md` as the source of truth.

The new Agent is simpler:

```txt
Agent = AI Harness + Agent-owned local tools + Workflow capability client
```

It is not:

```txt
Agent = AI Harness + direct Core node executor + direct Core tool executor
      + Workbench workflow adapter + generic subsystem API adapter
```

## Core Decision

Aithru has two execution planes:

```txt
Workflow product = deterministic workflow and capability execution plane
Agent product    = AI harness and intelligent orchestration plane
```

Agent must consume deterministic external capabilities through the Workflow
product's curated `CapabilityCatalog` and first-class `CapabilityRun` APIs.
Agent must not import Workflow, Workbench, or Aithru Core runtime internals.

## Product Boundary

Agent owns:

- `AgentThread`
- `AgentMessage`
- `AgentRun`
- `AgentSkill`
- `AgentTodo`
- `AgentWorkspace`
- `AgentArtifact`
- `AgentApproval` for Agent-owned actions only
- `AgentStreamEvent`
- `AgentTraceSpan`
- Agent-owned local tools
- `WorkflowCapabilityAdapter`

Agent does not own:

- `WorkflowSpec`
- `WorkflowRun`
- `CapabilityRun` source of truth
- Core node execution
- Core tool execution
- Workbench workflow scheduling
- raw workflow node catalog
- Workflow-owned approval records

## Execution Boundary

Production deterministic external actions follow this path:

```txt
model proposes tool
  -> Agent Harness
  -> skill allowed-tool policy
  -> Agent capability router
  -> WorkflowCapabilityAdapter
  -> Workflow CapabilityCatalog / CapabilityRun API
  -> Workflow/Core executor
  -> CapabilityRun events
  -> Agent records linked external references
```

Agent must not execute backing Core nodes directly. If a Workflow capability is
backed by `core.httpRequest`, that backing detail belongs to the Workflow
product and remains outside Agent's execution model.

## Package Responsibilities

The first redesign should keep the existing package layout and shrink the
semantics inside it.

### `packages/agent-core`

Owns Agent product contracts only.

Required changes:

- Replace old tool kinds with:

  ```ts
  type AgentToolKind = "local_tool" | "workflow_capability";
  ```

- Remove these old production kinds:

  ```txt
  core_tool
  core_node
  workbench_workflow
  subsystem_api
  memory
  sandbox
  mcp
  ```

- Extend `AgentToolDescriptor.metadata` for local providers and Workflow
  capability references:

  ```ts
  metadata?: {
    provider?: "workspace" | "artifact" | "test";
    capabilityKey?: string;
    capabilityVersion?: string;
    externalApprovalOwner?: "workflow";
  };
  ```

### `packages/agent-stream`

Owns Agent run events.

Required changes:

- Add external run events:

  ```txt
  external_run.created
  external_run.updated
  external_run.completed
  external_run.failed
  external_run.cancelled
  ```

- Add external approval events:

  ```txt
  external_approval.requested
  external_approval.resolved
  ```

These events record linked Workflow-owned state. They do not make Agent the
source of truth for a `CapabilityRun` or Workflow approval.

### `packages/agent-workspace`

Owns Agent local workspace behavior.

Workspace tools are Agent-owned local tools. They remain useful for harness
workspace files, reports, patches, and artifacts. They do not imply access to
host filesystem or Workflow internals.

### `packages/agent-tools`

Owns Agent tool routing.

Required changes:

- Keep or rename `StaticCapabilityRouter`, but its production semantics become
  `local_tool` plus `workflow_capability` only.
- Convert `WorkspaceToolAdapter` descriptors to `kind: "local_tool"` with
  `metadata.provider = "workspace"`.
- Remove `FakeSearchToolAdapter` from production exports.
- Use test-only mock adapters for fake search/fetch behavior.
- Add `WorkflowCapabilityClient` and `WorkflowCapabilityAdapter`.

Recommended client interface:

```ts
interface WorkflowCapabilityClient {
  listCapabilities(): Promise<WorkflowCapabilityDescriptor[]>;
  createCapabilityRun(input: CreateWorkflowCapabilityRunInput): Promise<WorkflowCapabilityRunResult>;
  getCapabilityRun(runId: string): Promise<WorkflowCapabilityRun>;
  resolveCapabilityApproval(input: ResolveWorkflowCapabilityApprovalInput): Promise<void>;
}
```

The initial implementation may use a mock client for tests. Real HTTP/SSE
integration can follow after the Agent contracts are clean.

### `packages/agent-harness`

Owns the model loop, skill policy checks, tool proposals, Agent-owned local
approvals, and run pause/resume behavior.

Required changes:

- Keep `tool.proposed`.
- For `local_tool`, use existing Agent-owned approval and tool result events.
- For `workflow_capability`, emit external run and external approval reference
  events.
- Do not create an Agent approval record for a Workflow-owned approval.
- When a Workflow capability waits for approval, emit:

  ```txt
  external_approval.requested
  run.paused
  ```

- Resume should resolve or observe the Workflow-owned approval through the
  Workflow capability adapter, then continue the model loop.

### `packages/agent-trace`

Owns Agent trace projections.

Required changes:

- Add linked external run spans:

  ```ts
  kind: "external_run"
  ```

- Store references rather than copying Workflow traces:

  ```ts
  refs: {
    externalKind: "workflow_capability";
    externalRunId: string;
    capabilityKey: string;
  }
  ```

### `apps/agent-server`

Owns Agent HTTP/SSE APIs.

Required changes:

- Keep Agent APIs for runs, events, stream, threads, and Agent-owned approvals.
- `/approvals` remains scoped to Agent-owned approvals only.
- Do not proxy all Workflow approval operations through Agent server in the
  first redesign.
- External Workflow approval references are visible through Agent events.
- A future UI or client can resolve Workflow approvals through Workflow APIs.

## Tool Model

Agent exposes only two production tool kinds:

```ts
type AgentToolKind = "local_tool" | "workflow_capability";
```

### Local Tool

Local tools are Agent-owned harness tools.

Examples:

```txt
workspace.listFiles
workspace.readFile
workspace.writeFile
workspace.deleteFile
artifact.create
```

Local tool approvals are Agent-owned:

```txt
Agent local tool approval
  -> AgentApproval record
  -> Agent /approvals API
  -> approval.requested
  -> run.paused
  -> Agent resume
```

### Workflow Capability Tool

Workflow capability tools are deterministic capabilities exposed by the
Workflow product.

Examples:

```txt
workflow.http_download
workflow.fetch_json
workflow.send_email
```

Workflow capability approvals are Workflow-owned:

```txt
Workflow capability approval
  -> CapabilityRun approval record
  -> Workflow approval resolve API
  -> external_approval.requested in Agent events
  -> Agent stores reference only
```

## Event Semantics

Agent run events remain the source of truth for Agent harness behavior.

Agent records:

- Agent lifecycle events
- model events
- message events
- todo events
- local tool events
- local workspace/artifact events
- external Workflow capability references

Agent does not duplicate CapabilityRun event history.

Recommended external run event payload:

```json
{
  "kind": "workflow_capability",
  "capabilityKey": "http_download",
  "capabilityRunId": "caprun_123",
  "toolCallId": "tool_1",
  "correlationId": "corr_123"
}
```

Recommended external approval event payload:

```json
{
  "kind": "workflow_capability",
  "capabilityRunId": "caprun_123",
  "approvalId": "approval_123",
  "toolCallId": "tool_1",
  "correlationId": "corr_123"
}
```

## Failure Semantics

If a local tool fails, Agent emits `tool.failed`.

If a Workflow capability fails, Agent emits:

```txt
external_run.failed
tool.failed
```

The model loop receives the normalized tool failure and may decide whether to
continue, retry, or stop. The first implementation should keep this simple and
avoid adding retry orchestration.

If a Workflow capability waits for approval, Agent emits:

```txt
external_approval.requested
run.paused
```

Agent resumes after the Workflow-owned approval is resolved or after the
Workflow capability run reaches a terminal state.

## Documentation Updates

Update:

- `README.md`
- `docs/00-agent-harness-design.md`
- `docs/02-complete-harness-architecture.md`
- `docs/05-capability-router.md`
- `docs/08-workflow-capability-integration.md` if implementation details need
  clarification

Rewrite or delete old references in:

- `docs/ARCHITECTURE.md`
- `packages/agent-core/README.md`

Every document should say the same thing:

```txt
Agent does not directly consume Aithru Core runtime or raw Workbench internals.
Workflow product capabilities are the deterministic execution boundary.
```

## Implementation Phases

### Phase 1: Contract Simplification

- Change `AgentToolKind` to `local_tool | workflow_capability`.
- Remove old direct Core/Workbench/subsystem kinds.
- Add external run and external approval event types.
- Add external run trace span support.

### Phase 2: Router Refactor

- Convert workspace tools to `local_tool`.
- Remove production fake search/fetch adapter exports.
- Add `WorkflowCapabilityClient`.
- Add a mock `WorkflowCapabilityAdapter` for tests.

### Phase 3: Harness Event Integration

- Route `workflow_capability` calls through the adapter.
- Emit `external_run.*` events.
- Emit `external_approval.*` events for Workflow-owned approvals.
- Pause/resume Agent runs around Workflow-owned approval references.

### Phase 4: Server Semantics

- Keep `/approvals` Agent-owned only.
- Ensure run events expose external approval references.
- Avoid turning Agent server into a broad Workflow API proxy.

### Phase 5: Documentation Cleanup

- Remove old direct Core/Workbench adapter language.
- Align README and architecture docs with this design.
- Keep `08-workflow-capability-integration.md` as the canonical integration
  boundary.

## Acceptance Criteria

- Agent production tool kinds are only `local_tool` and
  `workflow_capability`.
- No Agent production code exposes `core_tool`, `core_node`,
  `workbench_workflow`, `subsystem_api`, `memory`, `sandbox`, or `mcp` as tool
  kinds.
- Workspace tools are modeled as Agent-owned local tools.
- Workflow capabilities are consumed through a Workflow capability client.
- Workflow-owned approvals are not duplicated as Agent approval records.
- Agent stream events can reference external CapabilityRuns and approvals.
- Agent trace can project linked external run spans.
- Existing harness approval/resume behavior still works for local tools.
- Tests cover local tool execution, Workflow capability success, Workflow
  capability failure, and Workflow-owned approval pause/resume.
