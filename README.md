# Aithru Agent

Aithru Agent is the Aithru-native AI harness backend for long-running,
tool-using, permission-aware intelligent work.

The backend is now Python-first:

```txt
FastAPI control plane
  + Pydantic AI harness driver
  + Aithru capability router
  + Agent event stream / trace / workspace / artifact / approval model
```

## Product Boundary

Aithru Agent is not a workflow system and does not own `WorkflowSpec`.

Formal workflow authoring, graph semantics, workflow scheduling, workflow run
storage, and workflow approvals belong to Aithru Core and Aithru Workbench.

Agent owns intelligent harness behavior:

- Agent Threads and Messages;
- Agent Runs;
- runtime Todos;
- controlled Agent Tools;
- Workspaces;
- Artifacts;
- Memory entries;
- Subagent delegation;
- Subagent `task(...)` child-run join semantics;
- Agent-owned Approvals;
- replayable Agent stream events;
- Agent trace projection;
- debug model usage events;
- Pydantic AI-backed harness execution.

## Backend

The active backend lives in:

```txt
backend/
  src/aithru_agent/
    api/              FastAPI routes
    application/      runtime assembly
    capabilities/     tool descriptors, policy, router, local tools
    domain/           Agent product contracts
    harness/          scripted and Pydantic AI drivers
    persistence/      in-memory and SQLite stores
    stream/           AgentStreamEvent writer/store/SSE
    trace/            event-to-span projection
    worker/           queued Agent run execution and worker CLI
```

Pydantic AI powers the default real harness path, and `pydantic-ai-harness` is
available as an internal capability composition dependency for the platform
refactor. The backend now assembles runtime tools through an internal Aithru
capability/toolset package, but neither dependency defines public Aithru product
contracts. Pydantic AI events, tool calls, and model output are adapted into
Aithru-owned events and tool boundaries.
The capability router now also projects Pydantic platform governance metadata:
run contexts derive typed actor identity, scope checks return explicit
authorization decisions, and tool results can carry audit metadata without
including raw model-proposed inputs.

Agent Skills are Aithru product packages. The backend supports `SKILL.md`
packages under `skills/{public,custom}/skill-name/` with enabled state and
allowed/denied tool policy; active skill instructions enter the runtime through
an internal capability-style path, while real tool access remains router-bound.
When no custom resolver is injected, the backend includes a built-in
`deep-research` skill that plans research, uses available controlled web tools,
and creates cited report artifacts.
The deterministic `backend/examples/deep_research_agent.py` script exercises
that built-in skill through runtime todos, report artifacts, stream events, and
trace spans without requiring external web access.
`backend/examples/controlled_web_research_agent.py` extends that path through
opt-in controlled HTTP search/fetch against an allowlisted local provider.
Report artifacts include structured Pydantic evidence rows and a markdown
Evidence table with stable citation numbers.
Sources are deduplicated by normalized URL and marked with Pydantic quality
labels, scores, reasons, and artifact quality summary metadata.
Sources and evidence rows may also carry a typed `section_id`, allowing reports
to render section-aware evidence tables and Pydantic section summaries without
turning sections into execution branches.
When source collection is incomplete, reports can be `partial` or
`insufficient_evidence` with structured limitations and audit-friendly markdown.
When report creation sees blocked default Deep Research todos and no explicit
limitations, it can auto-add Pydantic limitations so degraded reports remain
creatable and auditable.
Completed search/fetch/report tool steps update matching Deep Research runtime
todos and emit `todo.updated` events for the run timeline.
Failed controlled web search/fetch calls emit `web.*.failed` events, failed web
trace spans, structured limitations, and `blocked` research todo updates without
introducing Agent-owned workflow semantics.
Those controlled web failures are returned to the model as Pydantic-shaped
recoverable failure payloads, allowing Deep Research runs to continue into
degraded report creation while ordinary non-web tool failures still fail the
run.
Recoverability is controlled by each Aithru `AgentToolDescriptor.failure_policy`;
Web search/fetch descriptors opt in, while local tools default to failing the
run.
Run snapshots now include a derived `research` summary that rolls up degraded
report status, failed web steps, blocked research todos, report artifact quality
metadata, and structured limitations from the existing event/todo/artifact/trace
facts.
`GET /api/runs/{run_id}/snapshot` now exposes the full inspection payload as a
typed OpenAPI `RunSnapshotResponse`, covering run metadata, summary, events,
trace spans, todos, approvals, workspace files, artifacts, research projections,
lineage, resume state, and subagents. It remains a read-only harness inspection
projection, not a workflow checkpoint or graph snapshot.
Run event and trace inspection endpoints now expose typed OpenAPI arrays:
`AgentStreamEvent[]` for global and thread-scoped event routes, and
`AgentTraceSpan[]` for run trace. These are read-only replay/observability
facts for dashboard clients, not workflow graph state.
`GET /api/runs/{run_id}/research/execution` and its thread-scoped alias expose a
Pydantic `ResearchExecutionSnapshot` with the research plan query, typed
research sections/subquestions, ordered runtime step statuses, web
success/failure counts, report artifact ids, and the same degraded summary for
UI/resume inspection. It remains a read-only projection over harness facts, not
a workflow definition.
`GET /api/runs/{run_id}/research/evidence` and its thread-scoped alias expose a
Pydantic evidence ledger with structured sources, evidence rows, source quality,
section coverage, limitations, report artifact references, and counts from the
latest `research.create_report` event. The ledger is projected from structured
tool output and artifact metadata rather than parsed from markdown, and it can
identify missing report sections when a planned subquestion has no evidence and
weak sections when a covered subquestion has no high-quality evidence.
`GET /api/runs/{run_id}/research/review` and its thread-scoped alias expose a
Pydantic research quality gate over the existing execution snapshot and evidence
ledger. It reports pass/warn/fail status, score, report readiness, finding
codes, and counts for missing evidence, blocked steps, web failures,
limitations, source quality, and weak research sections without adding
persisted review workflow state.
`GET /api/runs/{run_id}/research/continuation` and its thread-scoped alias
expose Pydantic continuation suggestions derived from the quality gate. It
returns typed next actions, priorities, related finding codes, suggested tools,
research phases, and target section ids for repairing degraded reports without
scheduling or executing those actions.
`POST /api/runs/{run_id}/research/continue` and its thread-scoped alias create
an explicit queued continuation Agent Run from selected continuation actions.
The new run reuses the source run thread, workspace, skill, and scopes, and
stores bounded continuation instructions plus structured
`harness_options.research_continuation` target metadata; it is a control-plane
action, not automatic workflow scheduling. The response publishes the typed
OpenAPI `ResearchContinuationRunResult` schema, preserving selected actions and
created run metadata for clients.
When the continuation run is later executed, its internal context packet can
load the source run's bounded research evidence, section coverage, limitations,
report artifacts, and target section ids, as long as the source run remains in
the same organization, actor, thread, and workspace boundary.
`GET /api/runs/{run_id}/research/lineage` and its thread-scoped alias expose
the event-derived continuation lineage for audit: a child run can show its
source run, and a source run can list created continuation children. The
lineage is a read-only projection over `run.created` and
`research.continuation.created` events, not a workflow branch model. These
Deep Research dashboard endpoints expose typed OpenAPI response schemas:
`ResearchExecutionSnapshot`, `ResearchEvidenceLedger`, `ResearchReviewSnapshot`,
`ResearchContinuationSnapshot`, and `ResearchContinuationLineageSnapshot`.
Snapshots also include a Pydantic `resume` projection for the latest
input/approval/subagent pause, including pause/resume event sequences and
relevant ids for durable audit after worker restarts.
When no queued run is available, the worker can use a Pydantic recovery decision
to continue paused runs whose persisted facts are already safe to apply: received
input, resolved approvals, completed delegated children with textual results, or
completed delegated children with bounded artifact summaries. Failed/cancelled
delegated children can fail their parent without being treated as workflow
scheduling state.
Completed subagents also persist a Pydantic `AgentSubagentResultSummary` on the
delegation record and `subagent.completed` event. The summary carries bounded
child text, artifact ids, artifact summaries, and derived output counts for API
inspection and recovery without replaying raw artifact payloads into traces.
Workers also write a Pydantic `AgentRunClaim` lease onto running runs with
worker id, claim time, heartbeat time, expiration, and attempt count. Persistent
stores can renew active claims for the owning worker and reclaim expired running
leases while active leases block duplicate execution. Worker execution now
starts an internal Pydantic heartbeat policy that renews the active claim during
long-running runs. Stale takeovers emit an audit `run.claim.reclaimed` event;
this is harness runtime state for recovery, not an Agent workflow scheduler.
Worker processes can also run with a Pydantic loop policy that sleeps between
idle polls and continues calling existing worker/store primitives, so delayed
retry runs are picked up after `next_retry_at` without adding Agent-owned
workflow scheduling.
Runs can also carry an optional Pydantic `retry_policy` and `retry_state`.
Recoverable runtime/model failures can be requeued with bounded backoff and
`run.retry.scheduled` audit events; exhausted attempts emit
`run.retry.exhausted` before terminal failure. Policy, authorization, and tool
boundary `AgentError` failures remain terminal by default. Retry state is
harness runtime state, not workflow scheduling semantics.
`GET /api/runs/{run_id}/tree` exposes a Pydantic run tree projection with
parent/child run nodes, subagent delegation links, status counts, depth, and
artifact counts for multi-agent inspection. It is an observability surface over
persisted harness facts, not a workflow graph or scheduler. The projection also
rolls descendant failed/waiting/degraded and sandbox diagnostic signals up to
ancestors with typed attention reasons so UI/debug tools can jump to the branch
that needs operator attention. Tree nodes expose direct sandbox counts, and the
tree summary aggregates sandbox failures, workspace side effects, artifact
promotions, persistence errors, and sandbox operator action counts for
dashboard triage. Delegation entries include the same structured subagent result
summary when one is available. The global and thread-scoped tree routes expose
the typed OpenAPI `RunTreeSnapshot` response schema.
Run detail and list responses also include a lightweight Pydantic `summary`
with health, typed attention reasons, count, and research-degraded signals for
dashboard-style inspection without requiring a full snapshot fetch.
Run creation, wait, join, cancel, and input routes now publish typed OpenAPI
response schemas: `AgentRun` for lifecycle state, `RunDetailResponse` for
detail responses that include the derived summary, and `AgentMessage` for
persisted user input.
`GET /api/runs/{run_id}/summary` and its thread-scoped alias expose that
projection directly as the OpenAPI `RunInspectionSummary` schema. The same
summary now derives external Workflow capability run diagnostics from
`external_run.*` events, so failed or cancelled provider-owned CapabilityRuns
can be shown separately from Agent-owned failures. It also derives sandbox
diagnostics from `sandbox.completed` and `sandbox.failed` events, including
workspace side-effect and artifact-promotion counts. Sandbox failures,
workspace side effects, artifact promotions, and persistence errors contribute
typed `attention_reasons`, so `needs_attention` dashboard queues can explain
why a run needs operator review. Each sandbox diagnostic also includes typed
operator action hints for inspecting errors, reviewing workspace outputs,
checking artifact promotions, reviewing workspace policy, or explicitly starting
a retry run; these hints do not execute automatically. The summary also flattens
those hints into top-level `sandbox_operator_actions` and
`sandbox_operator_action_count` fields so list rows can show suggested next
steps without expanding each diagnostic. Full run snapshots include the same
summary projection for single-response inspection. Run lists can filter by
`sandbox_failed=true`, `sandbox_side_effects=true`,
`needs_operator_action=true`, and `sandbox_operator_action_kind=...` for
sandbox-specific queues. With `include_meta=true`, run list pages also include
`sandbox_operator_action_counts` so dashboards can badge suggested next-step
types across the current result set.
Operators can explicitly turn one of those sandbox action hints into a queued
follow-up Agent Run through `POST /api/runs/{run_id}/operator-actions/follow-up`
or the thread-scoped alias. The created run records structured
`harness_options.operator_follow_up` provenance and emits
`operator_action.follow_up.created` on the source run; it does not execute the
hint automatically. The response publishes the typed OpenAPI
`OperatorFollowUpRunResult` schema. `GET /api/runs/{run_id}/operator-actions/lineage` and the
thread-scoped alias expose the event-derived source/child links, and full run
snapshots include the same `operator_follow_up_lineage` projection. The lineage
endpoints publish the typed OpenAPI `OperatorFollowUpLineageSnapshot` response
schema for UI clients.
Run lists can also filter follow-up children with
`operator_follow_up=true`, `operator_follow_up_source_run_id=...`, and
`operator_follow_up_action_kind=...`, all derived from that Pydantic provenance
rather than a separate queue table. Metadata pages include
`operator_follow_up_action_counts` and `operator_follow_up_source_run_counts`
for follow-up queue badges.
Workspaces now record Pydantic file versions for each write/delete and expose
metadata-only `AgentWorkspaceSnapshot` and `AgentWorkspaceDiff` projections.
These support audit and UI inspection of generated files without copying file
contents into diff responses or turning snapshots into workflow checkpoints.
Workspace snapshots can also be restored through a control-plane API. Restore
uses internally retained write-version content and creates new auditable
write/delete versions instead of mutating history in place.
Workspace snapshot, diff, restore, file list, and file-version routes now expose
typed OpenAPI schemas: `AgentWorkspaceSnapshot`, `AgentWorkspaceDiff`,
`AgentWorkspaceRestoreResult`, `AgentWorkspaceFile[]`, and
`AgentWorkspaceFileVersion[]`.
Control-plane uploads can now persist base64 Pydantic payloads under
`/uploads/...` through `POST /api/workspaces/{workspace_id}/uploads`, returning
`AgentWorkspaceUploadResult` and normal workspace file version metadata.
Supported workspace images can now be attached to thread messages as
metadata-only `workspace_image` references and viewed through the controlled
`GET /api/workspaces/{workspace_id}/images/{path}/view` API or
`workspace.view_image` tool. Both paths read from Agent Workspace storage,
enforce visibility/media/size policy, and avoid adding raw image bytes to normal
prompt summaries.
Models can now propose `workspace.patch_file` text edits through the capability
router. Patch requests use Pydantic edit contracts, honor workspace path policy
and write approval policy, and persist the result as a normal new workspace file
version with structured replacement metadata. The control-plane
`POST /api/workspaces/{workspace_id}/files/{path}/patch` endpoint uses the same
patch contract and returns `AgentWorkspacePatchResult` for UI/operator edits.
Workspace files can be promoted to managed artifacts through a control-plane
API. Promotion keeps the artifact content as a workspace pointer, records source
path/version/hash metadata, and can attach a Pydantic artifact retention policy
without granting models direct file promotion privileges.
Workspace file read, write, delete, and promote routes now publish typed
OpenAPI response schemas: `AgentWorkspaceFileReadResult`, `AgentWorkspaceFile`,
`AgentWorkspaceFileDeleteResult`, and `AgentArtifactPromotionResult`.
Artifact list endpoints can filter by `run_id`, `workspace_id`, `type`,
`retention_mode`, and `finalized`, and can return `include_meta=true`
pagination metadata with explicit ordering. Artifacts without an explicit
retention policy are treated as retained for lifecycle filtering.
Artifact delivery endpoints expose Pydantic download metadata and a
force-download route, so JSON audit bundles and generated files can be handed to
operators with stable filenames and attachment headers.
Artifact list, detail, and download metadata routes now publish typed OpenAPI
response schemas: `AgentArtifact[] | AgentArtifactListPage`, `AgentArtifact`,
and `AgentArtifactDownloadInfo`. Content preview and forced download routes
remain managed file responses, not raw host filesystem access.
`GET /api/runs/{run_id}/export` returns a Pydantic run export bundle with the
run, events, trace spans, todos, approvals, artifacts, and workspace snapshot
for audit and replay-style inspection. It is a read-only projection over
harness facts, not a workflow checkpoint or graph snapshot. The endpoint and its
thread-scoped alias expose the typed OpenAPI `AgentRunExportBundle` response
schema.
`POST /api/runs/{run_id}/export/artifact` persists that bundle as workspace
JSON and creates a managed `json` artifact pointer with source metadata and
optional retention. The global and thread-scoped archive routes expose the
typed `AgentRunExportArtifactResult` response schema.
Run list endpoints can filter by `status`, `skill_id`, `health`,
`needs_attention`, sandbox operator-action fields, and operator follow-up child
fields, including thread-scoped run lists. The `needs_attention` filter is
driven by typed summary `attention_reasons`, including health and sandbox
diagnostic reasons.
They also accept explicit `limit`, `offset`, `order_by`, and `order_direction`
parameters for dashboard pagination and ordering, including ordering by
`sandbox_operator_action_count`.
By default they still return an array; callers can pass `include_meta=true` to
receive a Pydantic page object with `items`, `total`, `count`, `limit`, and
`offset` plus optional queue metadata, including sandbox action and follow-up
action/source counts. OpenAPI now exposes that dual array-or-`RunListPage`
contract with typed `RunListItem` rows whose `summary` is the same
`RunInspectionSummary` projection used by detail and dashboard routes. The run
list query parameters remain declared for UI clients without turning list rows
into workflow queue or scheduler state.
The native harness also builds an internal Pydantic `AgentRunContextPacket`
from recent thread messages, runtime todos, report artifacts, event-derived tool
result summaries, scoped memory recall, and resume state. That packet applies
deterministic context budgets, summarizes dropped older context, is injected
into model instructions, and emits a debug `context.packet.built` event with
counts, budget usage, dropped memory count, and truncation state when it
contains useful context; it is not a public API contract or workflow definition.
For Deep Research runs, the packet can also include a bounded Pydantic research
continuation context with current step status, cited evidence summaries,
section coverage, limitations, report artifact references, next actions, and
structured action hints derived from existing todos, artifacts, and
`research.create_report` events. Section coverage identifies covered and missing
subquestions, and action hints can name target section ids so the next model
turn can focus evidence repair without granting direct execution or turning
research plans into workflow state.
Explicit continuation runs can also receive that research context from their
source run, with the source run id and target section ids rendered into model
instructions for bounded long-running research continuity.
Memory recall is bounded to the current run identity and readable scopes
(`user`, `thread`, `workspace`, `organization`, and `skill`), and each retained
item carries source, visibility, confidence, and a short reason for why it was
included.
Memory entries can carry a Pydantic retention policy (`retained`, `ephemeral`,
or `expires_at`); expired entries are filtered from default memory list/search
and run recall paths, while `DELETE /api/memory/{memory_id}` provides a
governed forget path.
Completed runs with memory-write scope create deterministic pending memory
candidates instead of directly writing durable memory. Operators can review
them through `GET /api/memory-candidates`; approving a pending candidate writes
a normal scoped `AgentMemoryEntry`, while rejecting it only resolves the
candidate.
Mem0-native long-term memory is implemented behind a settings toggle. When
enabled, Aithru maps org/user/agent/run identities into Mem0, searches Mem0
before a run, injects bounded provider-neutral recall items into the context
packet, and adds eligible completed turns to Mem0 automatically without
per-memory approval. In that mode the existing key/value memory entry and
candidate models remain available for local pinned memory, compatibility, and
optional compliance review rather than acting as the canonical long-term memory
engine.

Mem0-native long-term memory can be enabled with:

```bash
AITHRU_AGENT_LONG_TERM_MEMORY_PROVIDER=mem0
AITHRU_AGENT_MEM0_MODE=platform
AITHRU_AGENT_MEM0_API_KEY=...
AITHRU_AGENT_MEM0_APP_ID=aithru-agent
AITHRU_AGENT_MEM0_TOP_K=8
```

When enabled, run context searches Mem0 before model execution and completed
runs add bounded user/assistant turns to Mem0 after completion. Mem0 writes are
automatic by default; local memory candidates remain available only in local
provider mode or an explicit compliance configuration.
`AITHRU_AGENT_MEM0_ADD_ON_COMPACTION` is reserved for a future compaction
lifecycle hook and defaults to disabled in the current backend.
Private memory visibility is enforced at actor-aware boundaries: API reads and
deletes, `memory.search`, and run recall only expose private entries when the
entry owner or user-scoped memory id matches the current actor.
`GET /api/runs/{run_id}/memory-recall` exposes that same bounded recall as a
read-only inspection projection for UI/debugging; it does not expose a
model-side store read path or the full context packet. The global and
thread-scoped recall routes publish the typed OpenAPI `AgentMemoryRecall`
response schema.
Agents can call `input.request` to pause a threaded run in `waiting_input`.
`POST /api/runs/{run_id}/input` and
`POST /api/threads/{thread_id}/runs/{run_id}/input` persist the user message,
emit `input.received`, and requeue the run so the worker can continue.
Control-plane resource APIs for threads, approvals, memory, thread messages,
and skills now publish typed OpenAPI response schemas: `AgentThread`,
`ThreadListPage`, `UpdateThreadRequest`, `AgentThreadSummary`,
`AgentThreadSummaryMessage`, `AgentThreadSummaryRun`, `AgentThreadWorkbench`,
`AgentThreadWorkbenchRun`, `AgentThreadDashboardPage`,
`AgentThreadDashboardItem`, `AgentThreadDashboardActionHint`,
`AgentApproval`, `AgentRun`, `AgentMemoryEntry`, `AgentMemoryForgetResult`,
`AgentMemoryCandidate`, `AgentMemoryCandidateApprovalResult`, `AgentMessage`,
and `AgentSkill`. Thread lists support active/archive
filtering, ordering, and opt-in pagination metadata;
`GET /api/threads/dashboard` exposes a page of thread dashboard rows with
latest-run attention, degraded-research rollups, and ordered next-action hints
for input, approval, research continuation, and sandbox follow-up queue views.
Those hints point to existing control-plane APIs, include thread-scoped
`thread_path` values when a thread route exists, and clear from dashboard and
workbench projections after the underlying input/resume action is handled. They
remain read-only projections, not workflow queue records or scheduler commands.
Lifecycle updates can rename or archive a thread through the control plane.
`GET /api/threads/{thread_id}/summary` derives a read-only sidebar/dashboard
summary from thread messages and runs, including latest message, latest run,
activity time, and active/waiting counts. `GET /api/threads/{thread_id}/workbench`
combines that thread summary with bounded run cards, the same typed
next-action hints used by dashboard rows, and one selected `RunSnapshotResponse`
for DeerFlow-like conversation screens. These routes expose harness state for
UI/SDK clients without turning threads, approvals, memory, messages, skills,
summaries, dashboard rows, action hints, or workbench views into workflow
definitions.
Health, subagent spec, run tool inspection, and run subagent inspection routes
also publish typed OpenAPI response schemas: `AgentHealthResponse`,
`AgentSubagentSpec`, `AgentToolDescriptor`, and `AgentSubagentRun`. Tool and
subagent inspection remains read-only harness state, not workflow graph nodes or
scheduler state.

## Capability Boundary

Models may propose actions, but real actions must go through Aithru tools:

```txt
model / Pydantic AI
  -> Aithru Tool Bridge
  -> Capability Router
  -> policy / scope / approval
  -> local tool or future Workflow Capability API
  -> AgentStreamEvent / trace / artifact
```

Stage 1 local tools:

```txt
workspace.list_files
workspace.read_file
workspace.view_image
workspace.write_file
workspace.patch_file
workspace.delete_file
task
todo.create
todo.update
artifact.create
artifact.finalize
research.create_plan
research.create_report
workbench.workflow_draft.create
memory.search
memory.remember
subagent.delegate
sandbox.list_files
sandbox.read_file
sandbox.write_file
sandbox.patch_file
sandbox.delete_file
sandbox.diff
sandbox.promote_file
sandbox.run_python
```

The current sandbox tool uses a restricted local Python provider behind the
capability router. Results include a Pydantic execution summary with timeout,
exit code, output sizes, truncation flags, result type, timeout status, and
error code; that summary is also emitted on sandbox events and trace spans for
audit/replay surfaces. `sandbox.run_python` also returns a Pydantic diagnostics
object and emits it on sandbox completion/failure events; diagnostics summarize
the final status, execution summary, declared workspace outputs, persisted
workspace files, artifact promotions, and any workspace persistence error. They
also include typed operator action hints pointing to existing control-plane
inspection/retry surfaces. Run summary and snapshot projections surface those
diagnostics for UI/debug views without replaying the full event stream.
Sandbox code can also return declared `workspace_files`; the provider only
serializes those declarations, and the local tool persists them through the
current Agent Workspace after workspace write scope and allowed-path checks.
Declared workspace files may also request artifact promotion; promotion still
uses the Agent store's workspace-file promotion path and requires
`agent.artifact.write`.
`sandbox.list_files` gives sandbox-capable runs a controlled metadata listing
of current Agent Workspace files without returning file contents. It requires
`agent.sandbox.execute` and `agent.workspace.read`, honors workspace allowed
paths and optional prefix filtering, and returns a Pydantic
`SandboxFileListResult`.
`sandbox.read_file` gives sandbox-capable runs a controlled Agent Workspace read
primitive without exposing host filesystem APIs. It requires both
`agent.sandbox.execute` and `agent.workspace.read`, honors workspace allowed
paths, and returns Pydantic metadata including `content_encoding`, `size`,
`returned_bytes`, and `truncated`.
`sandbox.write_file` is the paired controlled write primitive. It requires
`agent.sandbox.execute` and `agent.workspace.write`, is marked as write risk for
approval policy, honors workspace allowed paths, writes through the workspace
store, emits normal workspace file events, and returns Pydantic file metadata
with overwrite status.
`sandbox.patch_file` applies structured Pydantic text replacements through the
same boundary. It is write-risk and approval-aware, requires workspace write
scope, produces a new versioned workspace file, emits a workspace event, and
returns `AgentWorkspacePatchResult` replacement/version metadata.
`sandbox.delete_file` removes an existing Agent Workspace file through the same
boundary. It requires sandbox execution and workspace write scopes, is write-risk
and approval-aware, honors workspace allowed paths, emits
`workspace.file.deleted`, and returns Pydantic deletion metadata.
`sandbox.diff` exposes a controlled metadata diff over Agent Workspace
snapshots. It requires sandbox execution and workspace read scopes, returns
`AgentWorkspaceDiff`, filters changes by workspace allowed paths, and never
returns file contents or provider-local filesystem handles.
`sandbox.promote_file` promotes an existing Agent Workspace file to a managed
artifact through the sandbox capability boundary. It requires sandbox execution,
workspace read, and artifact write scopes, is governed as write risk for approval
policy, honors workspace allowed paths, emits `artifact.created`, and returns
`AgentArtifactPromotionResult`.

`workbench.workflow_draft.create` produces a structured, non-executable
Workbench draft artifact for operator review. It requires both
`agent.artifact.write` and `agent.workbench.write`, stores Pydantic draft
content under the `workflow_draft` artifact type, and does not create, save,
schedule, or run a `WorkflowSpec`.

Optional external tool catalogs can also enter through the capability router:

```txt
web.search
web.fetch
mcp.<server>.<tool>
```

They are disabled by default. Set `AITHRU_AGENT_EXTERNAL_WEB_ENABLED=true` to
expose the built-in Web search/fetch catalog, and set
`AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON` to a JSON array of MCP-like server
catalogs. These settings only publish controlled tool descriptors; concrete
Web/MCP execution still requires a provider executor and otherwise fails safely
behind the router. The built-in controlled HTTP executor can execute
`web.fetch` when `AITHRU_AGENT_EXTERNAL_WEB_EXECUTOR=http` and
`AITHRU_AGENT_EXTERNAL_WEB_ALLOWED_HOSTS` explicitly allow the target host;
`web.search` can call a configured JSON search endpoint when
`AITHRU_AGENT_EXTERNAL_WEB_SEARCH_EXECUTOR=http_json` and
`AITHRU_AGENT_EXTERNAL_WEB_SEARCH_ENDPOINT_URL` points at an allowlisted host.
MCP-like tools can call a controlled HTTP JSON endpoint when
`AITHRU_AGENT_EXTERNAL_MCP_EXECUTOR=http_json`,
`AITHRU_AGENT_EXTERNAL_MCP_ALLOWED_HOSTS` allow the endpoint host, and each
enabled MCP server catalog includes `metadata.endpoint_url`. The executor posts
the normalized `MCPToolInvocation` and validates the response as an
`MCPToolResult`; model calls still pass through scope, skill, approval, audit,
and redaction policy first.
Successful web calls emit `web.search.completed` and `web.fetch.completed`
events for traceable research timelines. Failed web calls emit
`web.search.failed` or `web.fetch.failed` with controlled provider errors.

Workflow product capabilities can be installed through injected
`WorkflowCapabilityProvider` adapters. They appear as `workflow_capability`
tools with Pydantic input/output schemas, required scopes, risk, approval
policy, audit metadata, and `external_run.*` trace events. Agent receives
provider-owned `CapabilityRun` references; it still does not parse, schedule,
save, or execute workflow graphs itself.
Configured Workflow capability catalogs can also call one controlled HTTP JSON
CapabilityRun endpoint when `AITHRU_AGENT_WORKFLOW_CAPABILITY_EXECUTOR=http_json`,
`AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON` defines the curated catalog, and
`AITHRU_AGENT_WORKFLOW_CAPABILITY_ALLOWED_HOSTS` allow the endpoint host. The
client posts typed `WorkflowCapabilityInvocation` JSON and validates bounded
responses as `WorkflowCapabilityResult`; it is not a general-purpose network
tool or Workbench credential store.
When a Workflow capability waits for a Workflow-owned approval, Agent records a
Pydantic `current_external_approval` reference on the run, emits
`external_approval.requested`, pauses in `waiting_approval`, and creates no
`AgentApproval` row. `POST /api/runs/{run_id}/external-approval/resolve`
records the external decision and requeues or fails the run around that
provider-owned state.
When a Workflow capability returns an asynchronous `running` CapabilityRun,
Agent records a Pydantic `current_external_run` reference, emits
`external_run.created`, pauses in `waiting_external_run`, and waits for
`POST /api/runs/{run_id}/external-run/resolve` to mark the provider-owned run
completed, failed, or cancelled. Completed external run callbacks requeue the
Agent Run through the worker queue for the next harness continuation; Agent does
not poll, schedule, or own the Workflow execution graph.
Completed external run output is carried into the next model continuation as
bounded `tool_results` context with the capability key and external
CapabilityRun id, so the model can use the provider result without Agent
becoming the Workflow state owner.
Duplicate provider callbacks for the same terminal status are idempotent and do
not write duplicate `external_run.*` events. Conflicting terminal callbacks are
rejected so a late provider failure cannot overwrite an already completed
CapabilityRun fact. The resolve endpoint returns a Pydantic
`ResolveExternalRunResponse` that preserves top-level `AgentRun` fields and adds
the external CapabilityRun id, terminal status, idempotency flag, and whether the
Agent Run was freshly requeued.
Waiting external runs also project an `active_external_run` summary with wait
age and stale status; `/api/runs?external_run_stale=true` can find runs whose
provider-owned CapabilityRun appears stuck without Agent polling, cancelling, or
rescheduling that Workflow execution. Stale summaries include derived operator
action hints such as checking provider status, redelivering a completed callback,
or manually resolving failed/cancelled status through the existing control-plane
endpoint; these hints are not executed automatically.
Failed and cancelled external runs are projected into run summaries as
Pydantic diagnostics with capability key, external run id, tool call id, error,
comment, and event sequence.

## Run Locally

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
uv run uvicorn aithru_agent.api.main:app --reload
```

For API and worker processes sharing queued runs:

```bash
export AITHRU_AGENT_PERSISTENCE_BACKEND=sqlite
export AITHRU_AGENT_SQLITE_PATH=.aithru/agent.sqlite

uv run uvicorn aithru_agent.api.main:app --reload
uv run aithru-agent-worker --once
uv run aithru-agent-worker --loop --poll-interval 1 --sqlite-path .aithru/agent.sqlite
```

## HTTP API

Primary stage-1 endpoints:

```txt
GET    /api/health
POST   /api/threads
GET    /api/threads        # status/include_meta/order_by/order_direction/limit/offset
GET    /api/threads/dashboard
PATCH  /api/threads/{thread_id}
GET    /api/threads/{thread_id}/summary
GET    /api/threads/{thread_id}/workbench
POST   /api/threads/{thread_id}/messages
GET    /api/threads/{thread_id}/messages
POST   /api/threads/{thread_id}/runs
POST   /api/threads/{thread_id}/runs/stream
GET    /api/threads/{thread_id}/runs
GET    /api/threads/{thread_id}/runs/{run_id}
GET    /api/threads/{thread_id}/runs/{run_id}/summary
GET    /api/threads/{thread_id}/runs/{run_id}/tree
GET    /api/threads/{thread_id}/runs/{run_id}/memory-recall
GET    /api/threads/{thread_id}/runs/{run_id}/research/execution
GET    /api/threads/{thread_id}/runs/{run_id}/research/evidence
GET    /api/threads/{thread_id}/runs/{run_id}/research/review
GET    /api/threads/{thread_id}/runs/{run_id}/research/continuation
GET    /api/threads/{thread_id}/runs/{run_id}/research/lineage
POST   /api/threads/{thread_id}/runs/{run_id}/research/continue
POST   /api/threads/{thread_id}/runs/{run_id}/operator-actions/follow-up
GET    /api/threads/{thread_id}/runs/{run_id}/operator-actions/lineage
GET    /api/threads/{thread_id}/runs/{run_id}/capability-audit
GET    /api/threads/{thread_id}/runs/{run_id}/export
POST   /api/threads/{thread_id}/runs/{run_id}/export/artifact
GET    /api/threads/{thread_id}/runs/{run_id}/stream
GET    /api/threads/{thread_id}/runs/{run_id}/join
POST   /api/threads/{thread_id}/runs/{run_id}/cancel
POST   /api/runs/stream
POST   /api/runs/wait
POST   /api/runs
GET    /api/runs
GET    /api/runs/{run_id}
GET    /api/runs/{run_id}/summary
GET    /api/runs/{run_id}/events
GET    /api/runs/{run_id}/capability-audit
GET    /api/runs/{run_id}/trace
GET    /api/runs/{run_id}/snapshot
GET    /api/runs/{run_id}/memory-recall
GET    /api/runs/{run_id}/research/execution
GET    /api/runs/{run_id}/research/evidence
GET    /api/runs/{run_id}/research/review
GET    /api/runs/{run_id}/research/continuation
GET    /api/runs/{run_id}/research/lineage
POST   /api/runs/{run_id}/research/continue
POST   /api/runs/{run_id}/operator-actions/follow-up
GET    /api/runs/{run_id}/operator-actions/lineage
GET    /api/runs/{run_id}/export
POST   /api/runs/{run_id}/export/artifact
GET    /api/runs/{run_id}/tree
GET    /api/runs/{run_id}/tools
GET    /api/runs/{run_id}/subagents
GET    /api/runs/{run_id}/stream
POST   /api/runs/{run_id}/input
POST   /api/runs/{run_id}/cancel
POST   /api/runs/{run_id}/resume
POST   /api/runs/{run_id}/external-approval/resolve
POST   /api/runs/{run_id}/external-run/resolve
GET    /api/approvals
GET    /api/approvals/{approval_id}
POST   /api/approvals/{approval_id}/resolve
GET    /api/workspaces/{workspace_id}/snapshot
GET    /api/workspaces/{workspace_id}/diff
POST   /api/workspaces/{workspace_id}/restore
POST   /api/workspaces/{workspace_id}/uploads
GET    /api/workspaces/{workspace_id}/images/{path}/view
GET    /api/workspaces/{workspace_id}/files
GET    /api/workspaces/{workspace_id}/files/{path}
GET    /api/workspaces/{workspace_id}/files/{path}/versions
POST   /api/workspaces/{workspace_id}/files/{path}/patch
POST   /api/workspaces/{workspace_id}/files/{path}/promote
PUT    /api/workspaces/{workspace_id}/files/{path}
DELETE /api/workspaces/{workspace_id}/files/{path}
GET    /api/artifacts
GET    /api/artifacts/{artifact_id}
GET    /api/artifacts/{artifact_id}/content
GET    /api/artifacts/{artifact_id}/download-info
GET    /api/artifacts/{artifact_id}/download
POST   /api/memory
GET    /api/memory
DELETE /api/memory/{memory_id}
GET    /api/memory-candidates
POST   /api/memory-candidates/{candidate_id}/approve
POST   /api/memory-candidates/{candidate_id}/reject
POST   /api/subagents
GET    /api/subagents
GET    /api/subagents/{key}
GET    /api/skills
GET    /api/skills/{skill_id_or_key}
POST   /api/model-profiles
GET    /api/model-profiles
GET    /api/model-profiles/{profile_id_or_key}
PATCH  /api/model-profiles/{profile_id_or_key}
POST   /api/model-profiles/{profile_id_or_key}/enable
POST   /api/model-profiles/{profile_id_or_key}/disable
```

Run streams replay existing events by default. Add `follow=true` to wait for new
SSE events until the run reaches a terminal state or the stream timeout expires.
Completed runs expose `result.content`, `result.artifact_ids`, and message
references on the run record and in the `run.completed` event payload.
`POST /api/runs` accepts optional `harness_options.model_profile_key`,
`harness_options.model_capabilities`, `harness_options.model_cost_policy`, and
`harness_options.instructions` fields for governed model selection and extra
run instructions. Non-default raw `harness_options.model` values must go
through a model profile; profiles are organization-scoped Aithru contracts, not
Pydantic AI public objects. Profile selection checks enabled state, required
run scopes, vision/thinking capability requests, token ceilings, and cost
ceilings before a run is queued. Continuation and operator follow-up runs
revalidate inherited profiles.

Set `AITHRU_AGENT_API_TOKEN` to require `Authorization: Bearer <token>` on Agent
API endpoints. Health remains public for readiness checks. Set
`AITHRU_AGENT_API_SCOPES` to a comma-separated scope allowlist; run creation
inherits those scopes when no scopes are provided and rejects scope escalation.
When present, `X-Aithru-Org-Id` and `X-Aithru-User-Id` are treated as the
authenticated platform identity for thread and run creation. Thread and run
read APIs, associated approvals/artifacts/workspaces, user memory, and subagent
spec APIs are filtered to that trusted identity when those headers are present.
Capability execution preserves that boundary by returning structured
authorization decisions for missing scopes instead of hiding known tools as
unknown, and stream payload redaction records Pydantic receipts for sensitive
keys such as tokens and secrets.
Terminal `tool.*` events now include safe `authorization_decision` and `audit`
payloads, and `/api/runs/{run_id}/capability-audit` projects those validated
Pydantic audit entries for UI, replay, and export inspection through the typed
OpenAPI `AgentCapabilityAuditLog` response schema.

## Verification

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

## Key Design Docs

- [Agent Harness Design](./docs/00-agent-harness-design.md)
- [Harness Engine Adapter Strategy](./docs/06-harness-engine-adapter-strategy.md)
- [Workflow Capability Integration](./docs/08-workflow-capability-integration.md)
- [Python Pydantic AI Backend Design](./docs/superpowers/specs/2026-06-16-python-pydantic-ai-agent-backend-design.md)
