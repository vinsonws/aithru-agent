# Aithru Agent Harness Design

Status: design reset / target architecture

This document resets the product and architecture direction of `aithru-agent`.

The previous implementation centered on `AgentTask`, `AgentPlan`, `AgentRuntime`, `ClassifyEngine`, `PlanRunReviewEngine`, and `DeepResearchEngine`. Those primitives remain useful, but they are not the final product center.

The new direction is:

```txt
Aithru Agent = Aithru-native DeepAgents-like AI harness
```

Aithru Agent should feel closer to Codex, Claude Code, ChatGPT Agent, or DeepAgents than to a workflow graph editor.

## One-line definition

```txt
Aithru Agent is a platform-hosted AI harness for skill-driven, tool-using, workspace-aware, permission-aware intelligent work.
```

## Core idea

Aithru Agent should provide:

- chat threads;
- real skills;
- long-running agent runs;
- runtime todos / plans;
- workspace files;
- artifacts;
- tool calls;
- subagents;
- sandboxed execution;
- memory;
- human approvals;
- review/evaluation;
- event streaming and traces.

The actual execution capability must depend on Aithru-controlled capability boundaries:

- Agent-owned local tools (workspace operations, artifact creation);
- Workflow product capabilities consumed through `CapabilityRun` APIs.
- Sandbox, memory, or MCP behavior through Agent-owned harness interfaces or
  additional Workflow product capabilities.

Workflow capabilities may be backed by Core nodes, but the backing details
belong to the Workflow product. Agent consumes the curated capability API and
stores linked external run references.

The model may propose actions, but it must never execute real actions directly.

## Non-goal: not a second workflow system

Aithru Agent can have workflow-like runtime state:

```txt
user goal
  -> skill selection
  -> todo / runtime plan
  -> tool call
  -> subagent task
  -> sandbox execution
  -> artifact
  -> review
  -> approval
```

That does not make it a Workbench workflow.

Formal workflows remain:

```txt
WorkflowSpec
  -> nodes
  -> edges
  -> validation
  -> branch semantics
  -> scheduler/runtime
  -> workflow run
```

Owned by Aithru Core and surfaced through Aithru Workbench.

Agent todos, plans, subagents, and workspace operations are runtime harness state. They must not become a draggable graph editor or a persisted workflow definition.

## Mental model

Use this analogy:

```txt
LangGraph / low-level runtime  -> DeepAgents / high-level agent harness
Aithru Core + Workbench         -> Aithru Agent / high-level AI harness
```

This is only an analogy. Aithru Core is a deterministic workflow kernel and Workbench is a workflow product surface. Aithru Agent should borrow the high-level harness shape from DeepAgents, while preserving Aithru permission, trace, redaction, approval, platform identity, and workflow boundaries.

## Target product surfaces

Aithru Agent is expected to be a Platform-hosted subsystem.

Recommended product navigation:

```txt
Chat
Skills
Workspace
Runs
Artifacts
Approvals
Tools
Memory
Settings
```

### Chat

Chat is the primary entry point.

A chat thread can:

- run a skill;
- create an agent run;
- produce artifacts;
- request approval;
- call a Workbench workflow as a tool;
- create a `WorkflowSpec` draft artifact that opens in Workbench.

The Platform-hosted chat surface should stay chat-first. The current UI
productization direction is documented in
`docs/superpowers/specs/2026-06-24-agent-chat-quiet-workbench-design.md`: the
center conversation is the primary work surface, while run activity, files,
approvals, and trace are available through a quiet right-side companion. This is
a harness UI projection over Agent Thread and Agent Run state, not workflow
graph editing or persisted workflow semantics.

Agent user-facing presentation is represented by backend-owned
`AgentPresentation` events, not frontend-owned display card schemas. Models may
request that scoped resources be presented and may express a preferred view or
lightweight UI effect, but the harness must validate the resource, view,
surface, action, effect, policy, and redaction boundary before emitting
`presentation.created` or `presentation.updated`. The frontend renders only
trusted presentation events and executes only bounded, whitelisted effects such
as opening a preview panel or focusing an approval. Prompt context may include a
compact ledger of backend-confirmed presentations so the model can truthfully
refer to what has been shown to the user without depending on arbitrary DOM
state. Display Card semantics are superseded by the Agent Presentation model in
`docs/superpowers/specs/2026-06-29-agent-presentation-model-design.md`.

### Skills

Skills are real reusable agent capabilities.

A skill contains:

- instructions;
- when-to-use description;
- enabled/disabled state;
- allowed tools;
- denied tools;
- allowed subagents;
- model/profile preferences;
- workspace policy;
- memory policy;
- sandbox policy;
- approval policy;
- input/output expectations;
- artifact expectations.

A skill is not a workflow graph. It may be invoked from Chat, API, delegated work, or a Workbench `agent.*` node.
Skill APIs, run creation, and run execution must resolve skills inside the
current organization boundary.

`allowedTools` is an upper bound. `deniedTools`, workspace, memory, sandbox,
approval, and subagent policies can further remove tools from a run's available
catalog.
Sandbox tools are unavailable unless the skill explicitly enables sandbox use.
The backend may ship built-in Aithru-native skills such as `deep-research`;
these are still ordinary skill contracts with allowed tools and policies, not
workflow graphs.

### Workspace

Workspace is the harness file/context surface.

It may contain:

- user-provided files;
- generated files;
- intermediate analysis files;
- patches;
- reports;
- JSON outputs;
- execution logs;
- workflow draft artifacts.

Workspace operations must be policy-gated and traceable.
Workspace file writes and deletes may produce Pydantic
`AgentWorkspaceFileVersion` records with global workspace version numbers,
per-file version numbers, media type, byte size, and content hashes. Workspace
snapshot and diff APIs may derive metadata-only `AgentWorkspaceSnapshot` and
`AgentWorkspaceDiff` projections from those records. These are audit and UI
inspection surfaces over workspace facts, not workflow checkpoints, restore
points, graph branches, or model-visible execution capabilities.
Workspace restore may use internally retained write-version content to recreate
a prior snapshot as new write/delete versions. A restore result should be a
Pydantic audit record of restored, deleted, and unchanged paths. Restore must be
a control-plane operation behind workspace authorization, not model-side
workflow checkpoint execution or graph rollback.
Workspace inspection and restore routes should expose those models directly in
OpenAPI, including typed file and file-version list schemas, so dashboard
clients can generate against metadata-only workspace contracts without treating
snapshots as execution checkpoints.
User uploads should enter the workspace through a control-plane API that
validates a Pydantic upload request, stores bytes under `/uploads/...`, and
returns structured upload/file-version metadata. Upload handling must remain
workspace state and must not grant model code direct host file access.
Workspace images may be attached to thread messages only as metadata
references: workspace id, normalized path, supported image media type, byte
size, and optional content hash. The backend should validate that the
referenced workspace is visible to the current actor, the file exists, the media
type is one of the conservative supported image types, and the size is within
the image cap. Message storage must not persist base64 image content.
Image bytes are available only through a controlled read path:
`GET /api/workspaces/{workspace_id}/images/{path}/view` for control-plane
clients and `workspace.view_image` for model-proposed inspection. Both paths
read only from Agent Workspace storage, return a typed base64
`AgentWorkspaceImageViewResult`, and preserve existing workspace visibility,
scope, allowed-tool, and allowed-path boundaries. Tool and prompt summaries
should carry image metadata, not raw base64, unless the immediate controlled
tool result is being returned to the model.
Runs may declare explicit model capabilities such as
`harness_options.model_capabilities.vision`. Prompt assembly may mention whether
attached workspace images are directly viewable by the model, but should direct
non-vision runs toward `workspace.view_image` instead of assuming provider-side
multimodal injection.
Product-level model selection should go through Aithru `AgentModelProfile`
contracts, not provider SDK objects. Model profiles are organization-scoped
control-plane records with provider/model identifiers, enabled state,
vision/thinking capabilities, required selection scopes, token ceilings, and
cost policy. `POST /api/runs` may select a profile through
`harness_options.model_profile_key`; the control plane resolves that profile
into the concrete run model and persisted harness options only after checking
organization visibility, enabled state, run scopes, requested model
capabilities, token ceilings, and cost ceilings. Continuation and operator
follow-up runs must revalidate the inherited profile before queuing.
Non-default raw `harness_options.model` values are not a product-level escape
hatch around profile governance.
`workspace.view_image` is a model-facing capability only for runs whose resolved
model capabilities include vision. Cost policy is projected from `model.usage`
events into run usage summaries and budget status; it is harness accounting
state, not a direct provider billing contract.
Model-proposed workspace patches should pass through the capability router as
explicit Pydantic text edit requests. Patch execution reads the current
workspace file, applies bounded replacements, writes a new version through the
workspace store, and returns structured version/replacement metadata; it must
not expose unrestricted filesystem patching to model code. Control-plane patch
APIs may expose the same Pydantic request/result contract for UI and operator
edits.
Control-plane workspace file read, write, delete, and promote APIs should also
publish typed Pydantic response schemas. These schemas describe workspace facts
and artifact promotion results; they do not grant model code raw host
filesystem access.
Sandbox-side workspace reads should also remain capability-boundary actions.
`sandbox.list_files` lists only current Agent Workspace file metadata, requires
sandbox execution and workspace read scopes, honors workspace allowed paths and
optional prefix filtering, returns a Pydantic `SandboxFileListResult`, and must
not return file contents or provider-local directory listings.
`sandbox.read_file` reads only current Agent Workspace files, requires both
sandbox execution and workspace read scopes, honors workspace allowed paths, and
returns a Pydantic result with content encoding, total size, returned bytes, and
truncation state. It must not expose host filesystem paths or sandbox provider
internals to model code.
Sandbox-side workspace writes must follow the same boundary. `sandbox.write_file`
writes only current Agent Workspace files, requires sandbox execution and
workspace write scopes, is governed as write risk for approval policy, honors
workspace allowed paths, emits workspace file events, and returns a Pydantic
result with workspace file metadata and overwrite status. It must not expose
provider-local filesystem writes to model code.
Sandbox-side text patches should reuse the same explicit edit contract as
workspace patches. `sandbox.patch_file` requires sandbox execution and workspace
write scopes, is governed as write risk for approval policy, honors workspace
allowed paths, applies Pydantic text replacements to current Agent Workspace
content, emits workspace file events, and returns `AgentWorkspacePatchResult`
version/replacement metadata. It must remain text-only and must not expose
provider-local patching to model code.
Sandbox-side deletion should delete only Agent Workspace files. `sandbox.delete_file`
requires sandbox execution and workspace write scopes, is governed as write risk
for approval policy, honors workspace allowed paths, deletes through the Agent
store, emits workspace deletion events, and returns Pydantic deletion metadata.
It must not expose provider-local file deletion to model code.
Sandbox-side workspace diffs should remain metadata projections over Agent
Workspace snapshots. `sandbox.diff` requires sandbox execution and workspace
read scopes, returns `AgentWorkspaceDiff`, filters changes by workspace
allowed paths, and must not return file contents, provider-local paths, or
workflow checkpoint semantics.
Sandbox-side artifact promotion should also stay behind the capability boundary.
`sandbox.promote_file` promotes only existing allowed Agent Workspace files,
requires sandbox execution, workspace read, and artifact write scopes, is
governed as write risk for approval policy, emits artifact events, and returns
`AgentArtifactPromotionResult`. It must not allow model-supplied run ids or
direct provider-local file promotion.
Workspace files may also be promoted to managed artifacts through a
control-plane operation. Promotion should preserve a pointer to the workspace
file and source metadata such as workspace id, path, workspace version,
file-version number, content hash, and byte size. It must not become a
model-visible bypass around workspace policy.

### Runs

Runs represent intelligent execution, not formal workflow execution.
When a run is attached to a thread, the run and thread must share the same
organization and owner boundary.

A run should show:

- selected skill;
- runtime todos;
- subagent tasks;
- tool calls;
- sandbox executions;
- workspace file changes;
- artifacts;
- approvals;
- trace events;
- errors and recovery paths.

### Artifacts

Artifacts are outputs of intelligent work:

- markdown;
- reports;
- JSON;
- decisions;
- patches;
- files;
- workflow drafts;
- charts or structured analysis outputs.

Workbench draft artifacts are review handoffs, not Agent-owned workflows. The
Agent may create structured, non-executable draft content for Workbench to open
or validate later, but it must not save a `WorkflowSpec`, schedule a workflow,
execute graph nodes, or persist graph semantics as harness state.

Artifacts may carry a Pydantic retention policy for retained, ephemeral, or
time-expiring outputs. Retention metadata is an artifact lifecycle contract; it
is not a workflow scheduler, checkpoint policy, or model-side deletion grant.
Artifact list APIs expose Pydantic filters for run, workspace, artifact type,
retention mode, and finalized state, with optional page metadata for dashboard
output panels. The list and detail routes publish typed OpenAPI response
schemas for `AgentArtifact[] | AgentArtifactListPage` and `AgentArtifact`.
Artifacts without explicit retention metadata should be treated as retained for
list filtering and lifecycle inspection.
Artifact download-info APIs expose Pydantic metadata for filename, media type,
content length, disposition, and source workspace path through
`AgentArtifactDownloadInfo`. Separate content preview and download endpoints
deliver managed artifact bytes/text without granting models a new file access
path or raw host filesystem access.

### Approvals

Approvals guard risky agent actions:

- write operations;
- external calls;
- code/sandbox execution;
- sensitive data access;
- Workbench workflow execution;
- exports;
- delegated/background actions.

Agent approvals are distinct from Workbench human-approval workflow pauses, but both must remain auditable.
Approval list/detail and approval-resolution APIs should publish typed Pydantic
OpenAPI response schemas (`AgentApproval` and run-shaped resume responses) for
operator UI clients. These contracts expose harness approval state only; they
must not define Workflow approval nodes or scheduler behavior.

### Tools

Tools are capability descriptors the harness can request.

Tools may be backed by:

- Core tool executors;
- Core node adapters;
- Workbench workflows;
- Platform subsystem APIs;
- sandbox executors;
- workspace/memory providers;
- optional external tool adapters for MCP-like, search, fetch, or hosted
  provider tools.

Tools must expose risk, scopes, input schema, output schema, and approval requirements.
Capability routing should return Pydantic governance projections for every
known tool decision: typed actor context, required/granted/missing scopes,
authorization status, and audit metadata for prepare/execute outcomes. Missing
scope denials must remain explicit authorization denials, not be hidden as
unknown tools. Stream/event payload redaction should produce a Pydantic receipt
for sensitive keys while preserving existing redacted payload behavior.
Terminal tool events should persist safe governance payloads with
`authorization_decision` and `audit` keys, avoiding sensitive names such as
`authorization` in event payloads. A read-only run capability-audit API can
project these validated Pydantic audit entries from the event stream for UI,
replay, and export surfaces through an `AgentCapabilityAuditLog` OpenAPI
response schema.
Run tool inspection APIs should expose the available `AgentToolDescriptor[]`
as a typed OpenAPI response after run visibility and skill policy checks. The
descriptor surface is for operator/UI inspection and client generation; it must
not give models a direct execution path around the capability router.

## Target concepts

### AgentThread

```ts
type AgentThread = {
  id: string;
  orgId: string;
  ownerUserId: string;
  title: string;
  status: "active" | "archived";
  defaultSkillId?: string;
  workspaceId: string;
  createdAt: string;
  updatedAt: string;
};
```

Thread create/list/detail/update control-plane APIs should publish
`AgentThread`, `ThreadListPage`, `UpdateThreadRequest`, and
`AgentThreadSummary` as typed Pydantic OpenAPI contracts. A thread workbench
API may also publish `AgentThreadWorkbench` for frontend thread dashboards, and
a thread dashboard API may publish `AgentThreadDashboardPage` and
`AgentThreadDashboardActionHint` for conversation queues. List operations may
filter active/archived threads and opt into pagination/order metadata for
conversation sidebars. Dashboard operations may filter visible threads by
latest-run attention or degraded research status and may derive ordered
next-action hints for input, approval, research continuation, and sandbox
follow-up actions. Hints may include thread-scoped `thread_path` values for
actions such as threaded input submission, and resolved input hints should
disappear from dashboard/workbench projections while the resume audit remains in
the selected run snapshot. Update operations may rename a thread or move it
between active/archived status. The thread summary endpoint may derive latest
message, latest run, activity time, and active/waiting run counts from stored
messages and runs. The workbench endpoint may combine that summary with bounded
run cards, the same typed action hints used by dashboard rows, and one selected
`RunSnapshotResponse`. Dashboard pages may combine thread summaries with the
latest run card and read-only pointers to existing APIs. These must remain
read-only projections over harness facts.
Threads, summaries, dashboard rows, and workbench views remain harness
conversation state and must not become workflow definitions, scheduler inputs,
checkpoints, or graph nodes.

### AgentSkill

```ts
type AgentSkill = {
  id: string;
  orgId: string;
  key: string;
  name: string;
  description?: string;
  instructions: string;
  whenToUse?: string;
  enabled: boolean;
  allowedTools: string[];
  deniedTools: string[];
  allowedSubagents?: string[];
  memoryPolicy?: AgentMemoryPolicy;
  workspacePolicy?: AgentWorkspacePolicy;
  sandboxPolicy?: AgentSandboxPolicy;
  approvalPolicy?: AgentApprovalPolicy;
  inputSchema?: unknown;
  outputSchema?: unknown;
  version: string;
  status: "draft" | "published" | "deprecated";
};
```

### AgentRun

```ts
type AgentRun = {
  id: string;
  threadId?: string;
  skillId?: string;
  orgId: string;
  actorUserId: string;
  source: "chat" | "skill" | "api" | "workbench_node" | "delegated_task";
  goal: string;
  harnessOptions?: {
    model?: string;
    instructions?: string;
  };
  status:
    | "queued"
    | "running"
    | "waiting_approval"
    | "waiting_subagent"
    | "waiting_input"
    | "waiting_external_run"
    | "completed"
    | "failed"
    | "cancelled";
  workspaceId: string;
  result?: {
    content?: string;
    artifactIds: string[];
    messageId?: string;
    threadMessageId?: string;
  };
  startedAt: string;
  completedAt?: string;
};
```

### AgentTodo

```ts
type AgentTodo = {
  id: string;
  runId: string;
  title: string;
  description?: string;
  status: "pending" | "running" | "done" | "blocked" | "cancelled";
  createdBy: "agent" | "user" | "system";
  order: number;
};
```

Todos are runtime state. They are not Workbench nodes.

### AgentWorkspace

```ts
type AgentWorkspace = {
  id: string;
  orgId: string;
  threadId?: string;
  runId?: string;
  storageBackend: "memory" | "local" | "server" | "sandbox";
  retentionPolicyId?: string;
};
```

### AgentToolDescriptor

```ts
type AgentToolDescriptor = {
  name: string;
  description: string;
  kind:
    | "local_tool"
    | "external_tool"
    | "workflow_capability";
  inputSchema?: unknown;
  outputSchema?: unknown;
  requiredScopes: string[];
  riskLevel: "safe" | "read" | "write" | "dangerous";
  approvalPolicy?: "never" | "on_risk" | "always";
  failurePolicy?: "fail_run" | "return_recoverable";
};
```

### AgentSubagentSpec

```ts
type AgentSubagentSpec = {
  key: string;
  name: string;
  instructions: string;
  allowedTools: string[];
  workspacePolicy?: AgentWorkspacePolicy;
  memoryPolicy?: AgentMemoryPolicy;
};
```

Subagents are harness-level specialized workers. They are not Workbench nodes.
Subagent spec APIs should expose `AgentSubagentSpec` response schemas, and run
subagent inspection should expose `AgentSubagentRun[]`. These contracts describe
delegation resources and child-run links, not Workflow graph nodes, branches, or
scheduler semantics.

## Aithru Capability Router

The harness should call all real actions through a capability router.

```ts
interface AithruCapabilityRouter {
  listTools(context: AgentRunContext): Promise<AgentToolDescriptor[]>;

  callTool(
    request: AgentToolCallRequest,
    context: AgentRunContext,
  ): Promise<AgentToolCallResult>;
}
```

Backend adapters:

- `local_tool` adapters for Agent-owned tools (workspace, todo, artifact,
  research runtime todo planning, research report artifact generation, memory,
  subagent delegation, restricted sandbox execution);
- `external_tool` adapters for Agent-owned external provider boundaries such as
  MCP-like tool catalogs, web/search/fetch providers, or hosted integrations;
- `workflow_capability` adapters that consume Workflow product capability APIs.

Workflow capabilities may be backed by Core nodes, but the backing details
belong to the Workflow product. The Agent adapter exposes curated capabilities
as Pydantic-validated tool descriptors, invokes provider-owned capability runs,
and records `AgentExternalRunRef` metadata plus `external_run.*` trace events.
It must not parse `WorkflowSpec`, execute graph nodes, or turn capability runs
into Agent-owned workflow state. External provider tools must enter Agent through
`external_tool` adapters and still expose risk, scopes, input/output schemas,
approval policy, and redaction behavior before execution.
Configured Workflow capability providers may use one controlled HTTP JSON
CapabilityRun endpoint, explicit allowed hosts, timeout, response-size limits,
and typed Pydantic request/response contracts. This is a product API boundary,
not a model-visible network primitive or a path to Workbench internals.
If a Workflow capability returns a Workflow-owned approval requirement, Agent
stores only a structured `current_external_approval` reference on the run and
streams `external_approval.*` events. It must not duplicate that approval into
the Agent approval table. Resolving the external reference can requeue or fail
the Agent run, while the Workflow product remains the approval source of truth.
If a Workflow capability returns an asynchronous running CapabilityRun, Agent
stores only a structured `current_external_run` reference and pauses in
`waiting_external_run`. A run-scoped external-run resolve API can later record
completed, failed, or cancelled provider results and requeue or terminate the
Agent run. Completed callbacks enqueue the requeued Agent Run for worker
continuation, but Agent must not schedule, poll, or execute the underlying
`WorkflowSpec`. Completed external run output may be summarized into the next
bounded Pydantic context packet as tool-result context so the model can continue
with the provider result while Workflow remains the execution source of truth.
Duplicate callbacks for the same terminal provider status are handled
idempotently by looking up existing `external_run.*` terminal events. Conflicting
terminal callbacks are rejected and do not create a second terminal fact. The
resolve response can remain run-shaped while adding typed metadata for the
CapabilityRun id, terminal status, idempotency, and whether the Agent Run was
freshly requeued.
While waiting, Agent may derive an `active_external_run` summary with wait age
and stale status for run lists and dashboards. This is an observability
projection only; it does not authorize Agent to poll, cancel, retry, or schedule
the provider-owned Workflow execution. Stale diagnostics may include operator
action hints that point at existing control-plane resolution paths, but those
hints are inert metadata until an operator or trusted system calls the API.
MCP-like provider catalogs may use a controlled `http_json` executor only when
settings explicitly enable it, allowed hosts are configured, and each enabled
server declares a trusted `metadata.endpoint_url`. The executor posts the typed
`MCPToolInvocation`, validates the JSON response as an `MCPToolResult`, applies
timeout/byte limits, and remains downstream of scope, skill, approval, audit,
and redaction policy. It is not a general-purpose model network primitive.
Controlled web search/fetch providers emit lightweight `web.search.completed`,
`web.fetch.completed`, `web.search.failed`, and `web.fetch.failed` events for
research timelines and trace projection. Fetched body content remains in the
tool result and downstream artifacts rather than being duplicated into the web
stream event. Failed web events also let the harness mark matching research
runtime todos as `blocked` and carry structured Pydantic research limitations.
When `research.create_report` is called without explicit limitations, it can
derive limitations from blocked default research todos so degraded reports remain
auditable. Controlled web failures can also return model-visible recoverable
failure payloads so the run may continue toward a degraded report. Ordinary
non-web tool failures remain non-recoverable unless their Aithru
`AgentToolDescriptor.failurePolicy` explicitly opts into recoverability. These
behaviors do not introduce Agent-owned workflow semantics or scheduler behavior.
General tool self-correction is modeled as a Tool Result Recovery Loop, not as a
worker-level whole-run retry or an Agent-owned plan state machine. Recoverable
adapter failures carry typed recovery metadata on `AgentToolCallResult`; the
Pydantic tool bridge may return a compact redacted recovery payload to the model
when descriptor policy and retry budget allow it. Every corrected attempt is a
new model-proposed tool call through the Capability Router. Policy denials,
approval requirements, and fatal harness errors remain non-recoverable unless an
explicit controlled path says otherwise. The detailed design is
`docs/superpowers/specs/2026-06-29-tool-result-recovery-loop-design.md`.
Run snapshots may derive a research-specific summary from existing events,
runtime todos, report artifacts, and trace spans. That summary can show degraded
status, failed web calls, blocked research todos, report evidence/source counts,
and structured limitations for UI and audit inspection. It remains a projection
of harness facts, not a persisted workflow state machine.
The primary run snapshot endpoint should publish a typed Pydantic
`RunSnapshotResponse` OpenAPI schema for dashboard clients. That response can
compose the run, inspection summary, events, trace spans, todos, approvals,
workspace file summaries, artifacts, research projections, lineage, resume
state, and subagent runs, while remaining a read-only projection over harness
facts rather than a workflow checkpoint, branch graph, or scheduler input.
Run event and trace inspection routes should also publish typed Pydantic array
schemas: `AgentStreamEvent[]` for event replay and `AgentTraceSpan[]` for trace
inspection. These schemas expose persisted harness observability facts for
clients; they must not imply Agent-owned workflow graph state or scheduler
semantics.
Run APIs may also derive a Pydantic research execution snapshot from the same
facts. That projection can expose the latest research plan query/objective,
typed research sections/subquestions, ordered runtime step statuses, web
success/failure counts, report artifact ids, and the degraded research summary
for UI progress and resume inspection. Sections are planning metadata over the
run's research question, not child tasks. The projection must remain read-only
API state and must not become a persisted Agent-owned workflow graph, branch
model, or scheduler state.
Run APIs may also derive a Pydantic research evidence ledger from structured
`research.create_report` tool output events and current report artifact
metadata. The ledger can expose sources, evidence rows, source quality, section
coverage, limitations, report artifact references, and counts for UI and audit
inspection. Section ids can connect evidence back to research-plan subquestions
and identify missing subquestions when a section has no evidence or weak
subquestions when a covered section has no high-quality evidence, but they
remain report metadata; they are not branch ids, child-run edges, or scheduler
dependencies. The ledger should not parse markdown as its source of truth and
should not become a workflow checkpoint.
Run APIs may also derive a Pydantic research review snapshot from the execution
snapshot and evidence ledger. That quality gate can expose pass/warn/fail
status, score, answer readiness, typed finding codes, and counts for missing
evidence, blocked steps, web failures, limitations, report artifacts, and
source quality, including weak section counts. It is an inspection projection
over already persisted harness facts, not a persisted review workflow, workflow
scheduler state, or model-side permission to proceed.
Run APIs may also derive Pydantic research continuation suggestions from that
review. Suggested actions can name remediation intent, priority, related
finding codes, suggested tool names, relevant research phases, and target
section ids for missing or weak subquestion evidence. These are read-only hints
for UI, operators, or future controlled runs; they must not become persisted
plan steps, workflow edges, scheduler commands, or direct model-side tool
execution.
The control plane may expose an explicit "continue research" operation that
uses those suggestions to create a new queued Agent Run in the same thread and
workspace with bounded run instructions and structured target metadata such as
selected action ids and target section ids. That operation must remain a
user/API action that enters the normal run queue and capability router; it must
not become automatic workflow scheduling, a graph branch, or direct model-side
tool execution.
Run APIs may also derive a Pydantic research continuation lineage projection
from the child `run.created` metadata and source-run
`research.continuation.created` audit events. That projection can show which
source run created a continuation child, selected action ids, and current run
status/goal labels for inspection. It must remain read-only audit data over the
event log and must not become a persisted branch graph, workflow edge model, or
scheduler dependency.
The control-plane OpenAPI contract should expose the execution, evidence,
review, continuation, and lineage projections as typed Pydantic response schemas
for dashboard clients.
The internal context packet may derive a separate Pydantic research continuation
context for the model prompt. That context can summarize current research step
status, cited evidence, section coverage, limitations, report artifact
references, and next actions from existing todos/events/artifacts so resumed
runs can continue from known evidence and target missing subquestions. It may
also carry typed action hints with remediation priority, suggested tools, and
research phases, including target section ids for evidence repair, but those
remain bounded prompt context, not a public API contract, WorkflowSpec, direct
execution grant, or scheduler state.
For explicit continuation runs, that context may read bounded research facts
from the source run named in Pydantic harness options when the source run shares
the same organization, actor, thread, and workspace. This preserves continuity
for evidence repair while keeping lineage as metadata rather than a workflow
branch or dependency edge.
Run list and detail API responses may expose an even lighter derived inspection
summary for dashboard use: health, whether attention is needed, typed attention
reasons, basic event/todo/artifact/approval counts, failed trace count, research
degraded status, and provider-owned external CapabilityRun diagnostics. The
summary may also project sandbox run diagnostics from `sandbox.completed` and
`sandbox.failed` events, including workspace side-effect and artifact-promotion
counts. Sandbox failures, workspace side effects, artifact promotions, and
persistence errors may contribute typed attention reasons, with
`needs_attention` derived from those reasons. Sandbox diagnostics may also carry
typed operator action hints that point to existing control-plane inspection,
workspace review, artifact review, policy review, or explicit retry surfaces.
Those hints must not execute automatically or bypass capability policy. The run
summary may also flatten sandbox operator hints into top-level action and count
fields for dashboard rows. The summary is an API projection over harness facts
and does not become a domain `AgentRun` field. A dedicated run summary endpoint
and full run snapshot responses may expose the same projection directly as the
typed `RunInspectionSummary` OpenAPI contract for dashboard and operator UI
surfaces.
Run lifecycle APIs should publish typed Pydantic response contracts:
`AgentRun` for create/wait/join/cancel state, `RunDetailResponse` for run detail
with the derived summary, and `AgentMessage` for user input. The detail response
is a read-only inspection view over harness facts; it must not be treated as a
workflow checkpoint, graph snapshot, or scheduler input.
Run APIs may also allow an operator to explicitly create a queued follow-up run
from a selected sandbox operator action kind. That follow-up should record
structured Pydantic provenance in `harness_options.operator_follow_up`, write an
audit event on the source run, and enter the normal worker queue. It must remain
a control-plane run creation operation; selecting an operator action must not
execute the hinted action directly or bypass capability policy. Creation
responses should expose a typed `OperatorFollowUpRunResult` contract. Follow-up
lineage may be projected from the child `run.created` provenance and the source
audit event so source runs can list created children and child runs can identify
their source/action context without adding workflow branch semantics. Lineage
routes should expose that projection as the typed
`OperatorFollowUpLineageSnapshot` OpenAPI schema.
Run list APIs may filter by stored run fields such as status and skill id, and
by derived inspection fields such as health, attention state, stale external
run status, sandbox failures, sandbox workspace side effects, operator-action
presence, and operator-action kind. They may also filter operator follow-up
children by the presence of `harness_options.operator_follow_up`, source run id,
and action kind. Filtering by derived fields should be implemented in the
API/control-plane projection layer, not by persisting a second status machine.
Attention filtering should use the typed summary reasons rather than a separate
mutable queue.
Run list APIs may also expose explicit pagination and ordering parameters, such
as `limit`, `offset`, `orderBy`, and `orderDirection`, over stored run timestamps
or derived projection fields such as sandbox operator-action count. Defaults
should preserve existing list behavior; sorting and slicing should only happen
when requested.
When clients need pagination controls, run list APIs may offer an opt-in page
response with `items` and metadata such as total matching rows, returned count,
limit, offset, sandbox operator-action counts by kind, and operator follow-up
counts by action kind and source run id. The default array response should
remain available for simple clients and compatibility. The control-plane
OpenAPI contract should expose both response shapes through typed `RunListItem`
rows, where each row carries `AgentRun` fields plus a `RunInspectionSummary`.
It should also declare the full query parameter set so Workbench clients can
generate against the same tested run list contract without treating the list as
a workflow queue or scheduler contract.
Run export APIs may bundle the current run record, stream events, projected
trace spans, runtime todos, approvals, artifacts, and a metadata-only workspace
snapshot into a Pydantic `AgentRunExportBundle`. This is a read-only audit and
replay-inspection surface over harness facts, not a persisted workflow
checkpoint, graph branch, or scheduler input. Export routes should expose that
bundle as their typed OpenAPI response schema.
Control-plane APIs may persist an export bundle as a workspace JSON file and
managed artifact. The artifact should point back to the workspace file and carry
source metadata through a typed `AgentRunExportArtifactResult`, but this archive
action must not become a model-side workflow checkpoint or a scheduler input.
Run snapshot APIs may also derive a Pydantic resume-state projection from
existing run status, stream events, approvals, and subagent runs. The projection
can describe the latest input, approval, or subagent pause, whether it is still
resumable, relevant ids, and pause/resume event sequence numbers. It is durable
audit context over harness facts, not a persisted workflow checkpoint or
scheduler contract.
Worker recovery may derive a separate Pydantic decision from the same persisted
facts after normal queued-run claims are exhausted. Safe automatic actions are
limited to applying received input, applying already-resolved approvals,
continuing parents whose delegated child completed with textual `result.content`
or bounded artifact summaries, or failing parents whose delegated child run
failed or was cancelled. Artifact-backed recovery must pass summaries rather than
blindly replay raw artifact payloads, and must not be treated as WorkflowSpec
scheduling state.
Running Agent Runs may carry a Pydantic claim lease with worker id, claimed
time, heartbeat time, lease expiration, and attempt count. Store-level claim
operations may renew active claims for the owning worker, reclaim expired
running leases, or reclaim legacy running runs without a claim, while active
leases block duplicate workers. Stale takeovers should emit audit
`run.claim.reclaimed` events with previous and new worker ids. The lease is
runtime ownership/audit state for harness recovery, not an Agent workflow
scheduler or retry graph.
Worker services may use an internal Pydantic heartbeat policy to renew active
claims while a long-running run is still executing. Heartbeats update the
existing claim lease through the store boundary and stop when execution
completes, fails, pauses, or requeues. They are worker ownership facts, not a
WorkflowSpec scheduler, graph branch, or model-visible tool capability.
Worker processes may also use an internal Pydantic loop policy to keep polling
between idle ticks. The loop repeatedly calls existing worker/store primitives,
so queued runs, retry backoff readiness, paused-run recovery, and claim
heartbeats keep their current ownership boundaries. It may stop through an
operator-provided limit, stop event, or idle timeout; it must not become an
Agent workflow scheduler, WorkflowSpec executor, or graph runtime.
Agent Runs may also carry optional Pydantic retry policy and retry state.
Recoverable runtime/model failures may be requeued with bounded backoff, while
policy, authorization, and capability-boundary `AgentError`s remain terminal by
default. Retry scheduling should emit `run.retry.scheduled`; exhausted attempts
should emit `run.retry.exhausted` before terminal failure. This is bounded
harness runtime recovery state, not WorkflowSpec scheduling, graph branching, or
an Agent-owned workflow scheduler.
Run tree inspection may derive a Pydantic projection from persisted runs,
subagent runs, and artifacts. The projection may include parent/child run nodes,
delegation records, depth, statuses, and artifact counts for observability. It
may also roll descendant failed, cancelled, waiting-input, waiting-approval, and
research-degraded signals up to ancestor nodes with typed attention reasons and
counts. It may also project sandbox diagnostics from existing sandbox events,
expose direct sandbox counts on nodes, and roll descendant sandbox failures,
workspace side effects, artifact promotions, and persistence errors into
ancestor attention reasons plus tree-level aggregate counts. Tree nodes and
summaries may also expose sandbox operator-action counts so operators can see
which branch has suggested follow-up work without expanding every diagnostic.
The API should expose this projection as a typed `RunTreeSnapshot` OpenAPI
response schema. It must remain a read-only harness inspection surface, not an
Agent workflow graph, branch model, editor, or scheduler contract.
Agent runs may pause for user input through a capability-routed
`input.request` tool. The pause is harness runtime state (`waiting_input`), not a
workflow node. User input enters through the thread input API, is persisted as a
message, emits `input.received`, and can requeue the run for worker execution.
Native runs may also build a Pydantic `AgentRunContextPacket` from existing
harness facts: recent thread messages, runtime todos, run artifacts,
event-derived tool result summaries, scoped memory recall, plus resume-state
hints. The packet is injected into model instructions as bounded context,
applies deterministic budget accounting, and can include compressed summaries
for older context dropped by count limits. Prior tool outputs enter as
summaries projected from `tool.completed` events; memory enters as bounded
`AgentMemoryRecall` items only when the run has readable memory scope
(`agent.memory.read` or `*`) and only for current user/thread/workspace,
organization, and skill identities in local provider mode. When the long-term
memory provider is `mem0`, run context must recall only Mem0 results and must
not merge legacy local `AgentMemoryEntry` rows into model-visible context.
Completed threaded runs may also persist bounded semantic context summaries
through runtime processors so future context packets can reuse the latest
durable summary when older thread messages are dropped. Those summaries are
harness facts for prompt continuity, not workflow checkpoints, graph state,
branch semantics, scheduler input, or model-side execution grants. Models do
not gain a direct execution path through this context. The packet can emit a
debug `context.packet.built` event with counts, budget usage,
dropped-context counts including memory, and truncation status. It is an
internal context-engineering projection, not a public Aithru API contract,
persisted plan, scheduler input, or WorkflowSpec.
A read-only run inspection endpoint may expose the `AgentMemoryRecall`
projection itself so UI/debug tools can see which scoped memory items would be
available to the run; that endpoint must reuse the same run-identity and scope
rules and must not expose arbitrary memory search or full prompt context. The
response should be the typed `AgentMemoryRecall` OpenAPI contract.
Memory entries may carry a Pydantic retention policy with retained, ephemeral,
or expires-at modes. Expired memory must be filtered from model-facing
list/search/recall paths by default, and forgetting must pass through an
identity-checked API/store boundary rather than giving models direct delete
access.
Memory visibility must be enforced where actor context exists. Private memory
requires the entry owner, or user-scoped memory id, to match the current actor
for API reads/deletes, `memory.search`, and context-packet recall; shared,
organization, and unset visibility still depend on existing org and scope
boundaries.
Mem0-native cross-thread memory is implemented behind a provider setting. When
the provider is set to `mem0`, Aithru uses Mem0 for semantic extraction, update,
search, and ranking, while the harness keeps ownership of identity mapping,
readable/writeable scopes, redaction, no-memory controls, lifecycle events, and
provider health. Mem0 writes are automatic by default after eligible run
completion, without per-memory approval. The compaction write setting is
reserved until the backend exposes an explicit compaction lifecycle hook.
Search results are converted into bounded `AgentMemoryRecallItem` context so
the model receives provider-neutral memory hints, not direct provider access.
Existing `AgentMemoryEntry` records remain useful only in local provider mode
or for offline migration/cleanup. In Mem0 mode, Aithru does not expose
`memory.search` or `memory.remember`, does not include local entries in run
recall, and returns `410 Gone` from local memory entry and memory candidate
review APIs. `AgentMemoryCandidate` remains a local-provider compliance path,
not a Mem0 long-term memory mechanism.
Control-plane memory APIs should publish typed Pydantic OpenAPI schemas for
`AgentMemoryEntry`, `AgentMemoryForgetResult`, `AgentMemoryCandidate`, and
`AgentMemoryCandidateApprovalResult` in local provider mode. Completed runs
with memory-write scope may create deterministic pending memory candidates in
local provider mode, but durable local memory writes still require an explicit
approval API transition. Thread-message, thread
summary, thread dashboard, thread workbench, and skill resource APIs should
likewise expose `AgentMessage`, `AgentThreadSummary`,
`AgentThreadDashboardPage`, `AgentThreadWorkbench`, and `AgentSkill` response
schemas so dashboard clients can generate against stable harness resources
without turning messages, summaries, dashboard rows, workbench views, or skills
into workflow graph state.

## Tool call pipeline

```txt
model proposes action
  -> harness parses and normalizes tool call
  -> skill policy check
  -> platform scope/authz check
  -> capability router
  -> approval gate if required
  -> concrete executor
  -> result normalization
  -> event stream
  -> trace redaction
  -> artifact/workspace update
```

Rules:

- Model adapters do not execute tools.
- Skills do not bypass allowed tool policy.
- Sandbox execution is always explicit and policy-gated.
- Workspace file writes are traceable.
- Workbench workflows are invoked through Workbench APIs, not imported internals.
- Core nodes exposed as tools must be explicitly allowlisted.
- Sensitive data must be redacted before long-term trace storage or user display.

## Workbench integration

### Workbench calls Agent

Workbench can call Agent through formal workflow nodes.

Future node shape:

```txt
agent.skill
agent.task
```

Recommended node config:

```ts
type AgentSkillNodeConfig = {
  skillId: string;
  inputMapping?: Record<string, string>;
  outputMapping?: Record<string, string>;
  workspaceMode?: "ephemeral" | "workflow_run";
  approvalMode?: "inherit_workflow" | "agent_policy" | "both";
  toolPolicyOverride?: unknown;
};
```

Workbench owns the outer workflow. Agent owns the intelligent behavior inside the node.

### Agent calls Workflow product

Agent can call Workflow product capabilities and workflows as tools:

```txt
Agent Harness
  -> workflow.invokeCapability tool
  -> Workflow product creates a CapabilityRun
  -> Agent receives result/artifact/trace summary
```

```txt
Agent Harness
  -> workbench.runWorkflow tool
  -> Workbench runs WorkflowSpec
  -> Agent receives result/artifact/trace summary
```

Agent does not parse, schedule, or execute workflow graphs. Agent also does not
execute raw workflow nodes directly. Deterministic standalone actions should be
exposed by the Workflow product through curated capabilities and CapabilityRun
APIs.
The backend supports injected Workflow capability providers and a settings
configured controlled HTTP JSON provider through `WorkflowCapabilityAdapter`.
Both use the same typed provider contract.
Workflow-owned approval waits use `current_external_approval` and a run-scoped
external approval resolve API; they do not create Agent-owned approval records.
Asynchronous CapabilityRun waits use `current_external_run`,
`waiting_external_run`, and a run-scoped external-run resolve API; they do not
make Agent the owner of Workflow execution or scheduling. Completed external
run output is added to subsequent model context as bounded `tool_results`
context with external run metadata. Failed or cancelled external runs are
derived into run summaries as diagnostics over `external_run.*` events, not as
Agent-owned Workflow state.

See [Workflow Capability and Agent Integration](./08-workflow-capability-integration.md).

### Agent creates Workbench drafts

Agent can create a structured Workbench workflow draft artifact. The artifact is
non-executable handoff content: it can include a title, summary, suggested
steps, required inputs, risks, open questions, and provenance back to the source
run/workspace/thread. It is not a saved `WorkflowSpec` and does not contain
Agent-owned graph nodes, edges, scheduling, or execution semantics.

UI actions:

```txt
Open in Workbench
Validate in Workbench
Download WorkflowSpec JSON
```

Only Workbench validates, saves, versions, and runs formal workflows.

## Backend direction

The active implementation direction is Python-first:

```txt
backend/
  api/              FastAPI control plane
  application/      runtime assembly and use-case services
  capabilities/     capability router, policy, local tools, future Workflow capabilities
  domain/           Agent product contracts
  harness/          scripted and Pydantic AI harness drivers
  persistence/      store interfaces and implementations
  stream/           AgentStreamEvent writer/store/SSE
  trace/            event-to-span projection
  worker/           Agent run execution, pause/resume, cancellation
```

Pydantic AI is the default harness driver. It powers model loop mechanics, tool
calling mechanics, streaming, and structured output, but it does not define
public Aithru product contracts. Pydantic AI tool calls must enter Aithru's
capability router through the Aithru tool bridge.

Platform refactor Phase 1 adds `pydantic-ai-harness` as an internal backend
dependency for future Pydantic-native capability composition. The dependency is
not a public Aithru API surface: Pydantic AI and harness types must stay out of
`domain`, API schemas, and public contracts. The current compatibility probe
locks the Pydantic AI APIs used by Aithru runtime assembly, deferred approvals,
schema tools, and persisted message history while keeping runtime behavior
unchanged.

Platform refactor Phase 2 introduces an internal
`aithru_agent.agent.capabilities` package. `AithruToolset` converts Aithru
`AgentToolDescriptor` entries into Pydantic AI tools, and
`AithruBoundaryCapability` contributes that toolset plus boundary metadata and
approval enforcement hooks. Concrete tool execution still delegates to the
existing `PydanticAIToolBridge`, so real actions continue through
`AithruCapabilityRouter`.

Platform refactor Phase 3 moves `AgentRuntime.build_agent()` onto capability
assembly: the runtime now provides an `AithruBoundaryCapability` with an
`AithruToolset` instead of passing raw Pydantic function tools directly.
`AgentRuntime.run()` and approval resume still own event streaming, model
deltas, usage projection, deferred approval persistence, and final result
mapping as Aithru harness state.

Current runtime subagent support is harness state: `subagent.delegate` creates a
controlled child `AgentRun` with `source = "delegated_task"`, links it to the
parent run through `AgentSubagentRun`, and projects `subagent.started`,
`subagent.completed`, and `subagent.failed` events into the parent stream and
trace. Delegation validates requested child skills through the skill resolver
and child run scopes must not exceed parent run scopes. This is not a
WorkflowSpec, graph branch, or Workbench node.
When a delegated child completes, the parent-side `AgentSubagentRun` and
`subagent.completed` event carry an `AgentSubagentResultSummary` with bounded
child text, artifact ids, artifact summaries, derived output counts, and message
references. Recovery and run-tree inspection can use that typed summary without
turning subagent results into persisted workflow branch semantics.

Platform refactor Phase 4 adds model-facing `task(description, prompt,
subagent_type)` semantics on top of the same platform child-run model. The
`task` tool is an Aithru local tool exposed through the capability router; it
creates a visible child `AgentRun`, links an `AgentSubagentRun`, marks the
parent run `waiting_subagent` during the inline MVP join, executes the child
run, resumes the parent, and returns the child result to the parent model.
`subagent.delegate` remains the queued fire-and-observe delegation path.

Platform refactor Phase 5 upgrades skills into Aithru-owned packages. The
backend can load `skills/{public,custom}/skill-name/SKILL.md` packages with
optional `resources/`, `scripts/`, and `examples/` folders while retaining
legacy `skill.json` manifests. `AgentSkill` now carries enabled state plus
allowed and denied tool policy. Published and enabled skills can inject
instructions through an internal `SkillInstructionCapability`; concrete tool
availability is still narrowed by the Aithru capability router and run context.

Platform refactor Phase 6 splits the FastAPI control plane into route groups
under `backend/src/aithru_agent/api/routes/`. `api/main.py` is now only the app
factory, token middleware, dependency setup, and router registrar. Aithru
endpoints live under `/api/threads`, `/api/runs`, and related resource paths
for run creation, run stream joining, run joining, and cancellation. The old
prefixed compatibility aliases have been removed.

Platform refactor Phase 7 hardens the stage-1 run queue and join semantics
without adding production leases or retry infrastructure. The in-process queue
deduplicates pending run ids, `AgentWorkerRunner.join_run()` owns waiting for
terminal run state, approval/subagent resume paths have explicit runner hooks,
and memory/SQLite stores validate run status updates back into the domain enum.

Current sandbox support is a restricted local `sandbox.run_python` tool plus
controlled `sandbox.list_files`, `sandbox.read_file`, `sandbox.write_file`,
`sandbox.patch_file`, `sandbox.delete_file`, `sandbox.diff`, and `sandbox.promote_file`
workspace/artifact primitives. It does not expose shell access, imports,
raw host file APIs, or network APIs to model code; input enters through tool
payloads, and stdout/stderr plus completion/failure are emitted as `sandbox.*`
events and trace spans. Sandbox results also carry a Pydantic execution summary
with timeout, exit code, retained output sizes, truncation flags, result type,
timeout state, and error code so audit and trace views can inspect controlled
execution without parsing stdout. The local sandbox tool also attaches a
Pydantic run diagnostics object to `sandbox.run_python` outputs and completion
or failure events. Diagnostics are harness runtime state: they summarize final
status, the execution summary, declared workspace outputs, persisted workspace
files, artifact promotions, and workspace persistence errors without becoming a
workflow definition. Run summaries and snapshots can project those event
diagnostics into ordered API entries, aggregate counts, and typed operator
action hints for UI triage; summary projections may also provide flattened
action rollups for list and dashboard rows. Sandbox file listing,
reads, and diffs require
`agent.sandbox.execute` and `agent.workspace.read`, apply workspace allowed-path
policy, and return Pydantic metadata instead of provider paths or raw file
contents. Sandbox file writes, patches, and deletes require
`agent.sandbox.execute` and `agent.workspace.write`, are write-risk and
approval-aware, apply workspace allowed-path policy, write or delete through the
Agent store, and emit normal workspace file events.
`sandbox.promote_file` requires sandbox execution, workspace read, and artifact
write scopes, applies workspace allowed-path policy, binds promotion to the
current run, emits `artifact.created`, and returns the Pydantic artifact
promotion contract. Sandbox code may also declare `workspace_files`, but the
provider only returns those
declarations; the local tool persists them through the Agent store after
workspace-write scope and allowed-path checks and emits normal workspace file
events. Declared files may also request managed artifact promotion, but that
promotion must use the existing workspace-file promotion store path, require
artifact-write scope, and emit artifact events. Production-grade isolation can
later replace the local provider behind the same capability boundary.

## Migration direction

The active implementation remains the Python/FastAPI/Pydantic AI backend until a
replacement backend reaches parity. The approved replacement target is now a
native TypeScript backend with an Aithru-owned harness core rather than another
third-party agent framework.

See
`docs/superpowers/specs/2026-06-29-native-ts-agent-backend-replacement-design.md`
for the replacement design.

Replacement direction:

1. Add a `backend-ts/` implementation beside the current backend.
2. Do not start or depend on any Python backend process from the first runnable
   TypeScript backend.
3. Keep Aithru-owned contracts, stream events, trace projection, workspace,
   artifact, memory, approval, subagent, and capability-router semantics as the
   public product boundary.
4. Implement the Agent Harness core in TypeScript: run loop, model turn loop,
   tool proposal handling, approval/input/external-run pause and resume,
   context packet construction, subagent join semantics, retries, cancellation,
   and worker recovery.
5. Use model SDKs or direct HTTP calls only as low-level model I/O adapters.
   They must not execute tools, own memory/workspace state, or define public
   Aithru API contracts.
6. Do not use Mastra, LangGraph.js, Vercel AI SDK agent abstractions, Claude
   Agent SDK, or any similar framework as the harness core.
7. Route every real action through the Aithru Capability Router with policy,
   scope, approval, audit, event, trace, and redaction handling.
8. Keep Workbench/Core integration on explicit API/tool boundaries, without
   importing Workbench internals or creating Agent-owned WorkflowSpec semantics.
9. After TypeScript parity, remove or archive the Python backend and update
   README, AGENTS, backend docs, and verification commands to TS-first active
   backend wording.

## Verification checklist

- [ ] Is Aithru Agent clearly an AI harness, not a workflow editor?
- [ ] Are Skills reusable agent capabilities, not DAGs?
- [ ] Are todos/runtime plans observable state, not persisted workflow definitions?
- [ ] Do all real actions pass through the capability router?
- [ ] Are sandbox/code/file operations policy-gated and traceable?
- [ ] Does Workbench call Agent only through explicit `agent.*` node integration?
- [ ] Does Agent call Workbench only through Workbench APIs/tools?
- [ ] Do Platform org/user/scopes/authz/delegation/audit boundaries remain explicit?
- [ ] Do Core and Workbench avoid depending on Agent internals?
