# DeerFlow 2.0 Benchmark for Aithru Agent

Status: target capability benchmark

This document uses DeerFlow 2.0 as a benchmark for the target shape of Aithru Agent.

It does not mean Aithru Agent should copy DeerFlow code or depend on DeerFlow directly. The goal is to define the minimum product and architecture maturity that Aithru Agent should eventually reach as an AI harness.

## Benchmark statement

```txt
Aithru Agent should reach at least DeerFlow 2.0-level harness capability,
while replacing DeerFlow's local-trusted execution assumptions with Aithru Platform,
Aithru Core, and Aithru Workbench permission and capability boundaries.
```

Aithru Agent should be:

```txt
DeerFlow-like harness shape
+ Aithru Platform identity/authz/audit
+ Aithru Core capability contracts
+ Aithru Workbench workflow integration
+ Aithru-specific redaction, approval, and delegation boundaries
```

## Why DeerFlow matters

DeerFlow 2.0 is useful as a reference because it is not just a deep research demo. It represents a broader SuperAgent / AI harness shape:

- lead agent;
- skills;
- tools;
- subagents;
- sandboxed workspace;
- file operations;
- memory;
- context engineering;
- streaming gateway;
- full-stack UI;
- long-running task orientation.

This maps closely to the Aithru Agent target direction.

The key lesson is:

```txt
Agent is not an engine.
Agent is an execution environment for intelligent work.
```

## Non-goal: copying DeerFlow directly

Aithru Agent must not simply copy DeerFlow's runtime assumptions.

Aithru Agent is a Platform subsystem. It must preserve:

- organization context;
- user/service/delegated actor identity;
- app manifest permissions;
- platform grants;
- service clients and token exchange;
- connection policies;
- Aithru Core tool policy;
- Workbench workflow boundaries;
- audit events;
- redaction;
- approval gates;
- deployable server boundaries.

DeerFlow is a benchmark for harness completeness. Aithru defines the enterprise and platform control plane.

## Capability matrix

| Capability | DeerFlow-like expectation | Aithru Agent target |
| --- | --- | --- |
| Lead agent | One main agent coordinates the task. | `AgentHarness` owns run loop, context, todos, tools, subagents, approvals, artifacts, and streaming. |
| Chat thread | User interacts with an agent over time. | `AgentThread` + `AgentMessage` are first-class product objects under `orgId` and `actorUserId`. |
| Skills | Structured reusable agent capabilities. | `AgentSkill` is a real package/manifest concept with instructions, when-to-use, allowed tools, subagents, policies, examples, and output expectations. |
| Skill activation | Load relevant skill context only when useful. | `SkillResolver` and `SkillActivationMiddleware` choose explicit/user-selected or inferred skills without bloating context. |
| Todos / planning | Agent tracks multi-step progress. | `AgentTodo` is runtime state used for UI, trace, and recovery. It is not a Workbench node or `WorkflowSpec`. |
| Workspace filesystem | Agent reads/writes task files. | `AgentWorkspace` provides scoped virtual files, snapshots, diffs, artifacts, upload handling, and retention policy. |
| Outputs / artifacts | Agent produces durable outputs. | `AgentArtifact` supports reports, markdown, JSON, patches, files, decisions, charts, and `workflow_draft` artifacts. |
| Tools | Agent can call search/fetch/file/code/custom tools. | All tools are `AgentToolDescriptor` entries routed through `AithruCapabilityRouter`. |
| Sandbox | Code/file execution happens in an isolated environment. | `AgentSandboxProvider` is an explicit adapter. File writes, process execution, package install, and network access are policy-gated. |
| Subagents | Lead agent can spawn focused workers. | `SubagentSpec` and `SubagentRun` support scoped context, scoped tools, async execution, cancellation, and result merging. |
| Memory | Agent can use long-term state. | `AgentMemoryProvider` supports scoped memory with source, owner, confidence, visibility, retention, and authz policy. |
| Context engineering | Keep context useful and bounded. | `ContextBuilder` manages thread summary, skill context, workspace references, artifact summaries, tool result compression, and subagent isolation. |
| Streaming | UI sees live progress. | `AgentStreamEvent` is an append-only event stream covering message deltas, todos, tools, sandbox, workspace, artifacts, approvals, subagents, and run lifecycle. |
| Human approval | Risky actions can pause. | `ApprovalGateway` handles tool/workspace/sandbox/workbench/delegated actions, with platform audit and resume semantics. |
| Human input interrupt | Agent can ask the user for missing information. | `input.request` pauses a threaded run as `waiting_input`; `/api/runs/{run_id}/input` persists the reply and requeues the run. |
| UI | Full-stack app for chat, files, runs, outputs. | `agent-web` should be a Platform hosted app with Chat, Skills, Workspace, Runs, Artifacts, Approvals, Tools, Memory, Settings. |
| Deployment posture | Local trusted harness by default. | Aithru Agent must be server-deployable under Platform identity, grants, audit, and connection policies. |

## Target capabilities by area

### 1. Skills

Aithru Agent skills should be closer to a skill package than a simple engine config.

Target shape:

```txt
skills/
  pr-reviewer/
    skill.yaml
    instructions.md
    when-to-use.md
    examples/
    templates/
    rubrics/
    resources/
```

A skill should define:

- key, name, description, version, owner;
- instructions;
- when-to-use guidance;
- examples;
- allowed tools;
- allowed subagents;
- workspace rules;
- sandbox rules;
- memory rules;
- approval rules;
- output expectations;
- optional templates and resources.

Aithru-specific additions:

- org scope;
- app permission requirements;
- resource grants;
- publication status;
- skill versioning;
- audit metadata;
- Workbench node compatibility metadata.

The backend can include built-in skills such as `deep-research` for an
out-of-the-box DeerFlow-like research path. Built-ins remain normal AgentSkill
contracts and constrain tools through the same capability router.
The current backend includes a deterministic Deep Research example that runs
this skill through runtime todos, report artifact creation, event logging, and
trace projection without enabling uncontrolled web access.
It also includes a controlled-web research example that uses opt-in
allowlisted HTTP search/fetch, records dedicated web stream events, projects web
trace spans, and feeds fetched content into the final report artifact.
Completed search, fetch, synthesis, and report tool steps now advance matching
runtime todos to `done`, improving DeerFlow-like progress observability without
turning todos into workflow nodes.
Failed controlled web search/fetch calls emit dedicated failed web events,
project failed web trace spans, and mark matching runtime todos as `blocked`,
making source-collection failures visible before report synthesis.
Those failures now also map to structured Pydantic research limitations, and
report creation can derive limitations from blocked default research todos when
the model omits explicit limitations.
The controlled web failure result is recoverable and model-visible, so a
Deep Research run can continue into an `insufficient_evidence` artifact instead
of ending at the first search/fetch provider failure. This recovery is controlled
by tool descriptor failure policy, not by unconstrained model-side exception
handling.
Research reports also expose structured Pydantic evidence rows with citation
numbers, source URLs, snippets, fetched excerpts, and a markdown Evidence table.
Sources are deduplicated by normalized URL and labeled with computed quality
scores/reasons so downstream UI and agents can inspect evidence strength.
Reports can now carry section-aware evidence: sources and evidence rows may
include a `section_id`, generated markdown groups evidence by section, and
artifact metadata stores Pydantic section summaries. This closes more of the
DeerFlow-like "answer by subquestion" gap while keeping sections as report
metadata rather than execution branches.
Failed or incomplete source collection can still produce `partial` or
`insufficient_evidence` report artifacts with structured limitations, preserving
an auditable research trail instead of dropping the run on the floor.
The run snapshot API now also exposes a derived `research` summary that rolls up
degraded status, failed web calls, blocked research todos, report artifact
quality metadata, and structured limitations. This gives DeerFlow-like
inspection surfaces one stable field without promoting Agent todos into workflow
nodes.
The primary `/api/runs/{run_id}/snapshot` endpoint now exposes its complete
inspection payload as a typed OpenAPI `RunSnapshotResponse`, including run
metadata, summary, events, trace spans, todos, approvals, workspace files,
artifacts, research projections, lineage, resume state, and subagents. This
strengthens dashboard client generation while keeping snapshots read-only
harness facts rather than workflow checkpoints.
Run event and trace endpoints now expose typed OpenAPI arrays:
`AgentStreamEvent[]` for run event replay and `AgentTraceSpan[]` for trace
inspection. This closes another DeerFlow-like dashboard contract gap while
preserving Aithru's boundary that events and spans are observability facts, not
workflow graph state.
Research execution snapshot APIs now expose the latest research plan query,
typed research sections/subquestions, ordered runtime step statuses, web
success/failure counts, report artifact ids, and the same degraded summary at
run and thread-run paths. This closes more of the DeerFlow-like
progress-observability and research-decomposition gap while preserving Aithru's
rule that runtime todos and sections are harness state, not workflow nodes or
branch semantics.
Research evidence ledger APIs now expose structured report sources, evidence
rows, source quality labels, section coverage, limitations, counts, and report
artifact references without parsing markdown. They can identify missing
subquestion sections when a planned section has no evidence, and weak sections
when a covered section has no high-quality evidence. This moves Aithru Agent
closer to DeerFlow-like auditable research output while keeping the source of
truth in capability-routed tool events and artifacts.
Research review APIs now add a Pydantic quality gate over those execution and
evidence projections. The gate reports pass/warn/fail status, score, answer
readiness, typed finding codes, and counts for missing evidence, blocked steps,
web failures, limitations, source quality, and weak sections. This closes more
of the DeerFlow-like report self-check gap while staying a read-only projection
over harness facts rather than a workflow checkpoint or scheduler.
Research continuation APIs now turn failed/degraded review findings into typed
Pydantic next-action suggestions, such as collecting more sources, retrying
controlled search/fetch, addressing limitations, or regenerating the report.
Suggestions can target missing section ids, giving DeerFlow-like dashboards a
clearer path from "bad report" to "continue research here, for these
subquestions." They can also target weak section ids when a covered subquestion
needs stronger sources, without creating Agent-owned workflow steps or automatic
scheduler behavior.
The continuation run API can also turn selected suggestions into a new queued
Agent Run in the same thread and workspace, with continuation instructions
and structured target section metadata stored in Pydantic harness options. This
closes more of the DeerFlow-like "continue from here" loop while keeping
continuation explicit and routed through the normal capability boundary.
When that queued continuation later builds model context, it can load the
source run's bounded research facts, evidence, section coverage, limitations,
report artifacts, and target section ids if the source remains inside the same
identity/thread/workspace boundary. This makes the loop context-continuous
without introducing workflow branch semantics.
Continuation lineage APIs now expose read-only Pydantic audit links for that
loop: source runs list created continuation children, child runs show their
source run, and both carry selected action ids from stream events. This improves
DeerFlow-like traceability without adding workflow branch semantics. The Deep
Research dashboard endpoints now expose typed OpenAPI response schemas for
execution, evidence, review, continuation, and lineage projections.
The native context packet now also carries bounded research continuation context
for resumed Deep Research runs: current step status, cited evidence summaries,
section coverage, limitations, report artifact references, next actions, and
typed action hints with priority, suggested tools, and research phases. Covered
and missing section markers plus target section ids on action hints let resumed
runs target subquestion-level evidence gaps, improving DeerFlow-like
long-running research continuity while keeping plans, sections, and todos as
harness runtime state rather than workflow definitions.
For explicit continuation children, that packet also carries the source run id
and selected target section ids into model instructions so evidence repair can
resume with the prior run's bounded research state.
Run detail and list APIs expose a lighter `summary` for DeerFlow-like dashboards:
health, attention status, typed attention reasons, event/todo/artifact/approval
counts, failed trace count, research degradation, external Workflow capability
diagnostics, and sandbox diagnostics with workspace side-effect counts. Sandbox
failures, durable workspace side effects, artifact promotions, and persistence
errors now flow into the same `needs_attention` rollup so dashboard queues can
show both the flagged run and the reason. Sandbox diagnostics also include typed
operator action hints for inspecting the error, reviewing workspace outputs,
reviewing promoted artifacts, checking workspace policy, or explicitly creating
a retry run. Those hints are also rolled up into summary-level action and count
fields so dashboard rows can show suggested next steps directly.
`GET /api/runs/{run_id}/summary` and the thread-scoped alias expose that same
projection directly as a typed OpenAPI `RunInspectionSummary` contract, so
clients can sort or badge runs without fetching the full snapshot for every row.
Full run snapshots include the same summary for single-response inspection.
Those list APIs can now filter by status, skill id, derived health, attention
state, stale external run state, sandbox failures, and sandbox workspace side
effects, plus sandbox operator-action presence and action kind. This covers
common dashboard views such as queued runs, degraded research runs,
sandbox-failed runs, output-producing sandbox runs, and runs requiring operator
attention with explainable next-step hints.
They also support explicit pagination and ordering by run timestamps, status, or
derived health, plus sandbox operator-action count. With page metadata enabled,
responses include operator-action counts by kind for queue badges without
fetching and sorting every row client-side.
Operator-action follow-up APIs can now turn a selected sandbox action kind into
an explicit queued child Agent Run in the same workspace and thread, with
structured `harness_options.operator_follow_up` provenance and a source-run
audit event. This closes more of the DeerFlow-like operator loop while keeping
all real work inside normal run execution and capability policy. Lineage APIs
and snapshot fields now project those source/child links from events so
dashboards can navigate follow-up work without a workflow graph. The lineage
endpoints now expose a typed `OperatorFollowUpLineageSnapshot` OpenAPI response
schema. Run lists can filter those follow-up child runs by source run id and
action kind, giving Workbench a direct follow-up queue without persisting a
workflow branch model.
Page metadata also exposes follow-up action and source-run counts for queue
badges.
For pagination controls, clients can opt into a page-shaped response with
`items`, total matching rows, returned count, limit, offset, and ordering fields
instead of the default array response. OpenAPI now advertises the query
parameters plus the array-or-page response contract for both global and
thread-scoped run lists. Both default array entries and page `items` now use the
typed `RunListItem` schema, pairing `AgentRun` fields with the same
`RunInspectionSummary` used by detail and dashboard surfaces.
Run creation, wait, join, cancel, detail, and user-input APIs now expose typed
OpenAPI response schemas (`AgentRun`, `RunDetailResponse`, and `AgentMessage`).
This closes more of the DeerFlow-like run control surface for generated clients
while keeping run detail a read-only harness inspection projection rather than a
workflow checkpoint or graph snapshot.
Research continuation and operator follow-up creation APIs now expose typed
OpenAPI response schemas (`ResearchContinuationRunResult` and
`OperatorFollowUpRunResult`) while continuing to create explicit queued Agent
Runs only through the control plane.
Run export APIs now package a run with its events, trace spans, todos,
approvals, artifacts, and workspace snapshot into a Pydantic export bundle. This
adds a DeerFlow-like replay/audit surface without turning Agent runtime state
into workflow checkpoints or graph branches. OpenAPI exposes that surface as the
typed `AgentRunExportBundle` response schema.
Those export bundles can also be archived into workspace JSON and exposed as
managed artifacts, giving operators a downloadable/shareable audit package while
keeping export creation behind the control plane through the typed
`AgentRunExportArtifactResult` response schema.
Artifact download metadata and force-download endpoints now give generated
outputs stable filenames, media types, content lengths, and attachment headers,
which improves the DeerFlow-like handoff from internal run state to deliverable
files. Artifact list, detail, and download metadata routes now expose typed
OpenAPI response schemas (`AgentArtifact[] | AgentArtifactListPage`,
`AgentArtifact`, and `AgentArtifactDownloadInfo`) while content and forced
download routes remain managed file responses.
Run snapshots also expose a derived resume-state projection for the latest
input, approval, or subagent pause. It keeps pause/resume event sequences,
relevant ids, approval-history availability, and input/subagent status
inspectable after worker restarts without turning the pause into workflow
scheduling state.
Worker ticks can also derive a Pydantic recovery decision when the normal queue
is empty, allowing safe continuation for received input, resolved approvals, and
delegated children that completed or terminally failed. Text child results resume
the parent through an explicit model-continuation hook, and artifact-only child
outputs resume through bounded artifact summaries rather than an Agent-owned
scheduler.
Run claims now persist a Pydantic worker lease on running runs, including worker
identity, claim time, heartbeat time, expiration, and attempt count. Persistent
workers can renew their active claim and reclaim expired running leases while
active leases prevent duplicate execution. Stale takeovers emit audit
`run.claim.reclaimed` events, moving the backend closer to DeerFlow-style
long-running worker resilience without adding Agent-owned workflow scheduler
semantics.
Worker execution now also renews active claims through an internal Pydantic
heartbeat policy while long-running runs are still executing. This closes the
gap between persisted leases and practical long-task ownership, without giving
the Agent an owned workflow scheduler or graph runtime.
Worker processes can now also run with an internal Pydantic loop policy that
sleeps between idle polls and continues through delayed retry backoff windows.
That makes retry/backoff practical for long-lived workers while still relying on
existing claim/recovery primitives rather than introducing Agent-owned workflow
scheduling.
Runs can now also carry optional Pydantic retry policy and retry state.
Recoverable runtime/model failures can be requeued with bounded backoff,
`run.retry.scheduled` events, and final `run.retry.exhausted` audit before
terminal failure. Policy, authorization, and capability-boundary `AgentError`s
remain terminal by default, preserving Aithru's control-plane boundary while
closing another DeerFlow-like long-running-task resilience gap.
The run tree API adds a DeerFlow-like multi-agent inspection view over parent
and child Agent Runs, subagent delegation records, depth, status counts, and
artifact counts. It helps UI/debug tooling inspect distributed work while
preserving Aithru's boundary against Agent-owned workflow graph semantics. Tree
nodes now also roll descendant failed, waiting, and research-degraded signals up
to ancestors with typed attention reasons, making it easier to locate the
branch of a multi-agent task that needs intervention. They also expose direct
sandbox diagnostic counts on each node and aggregate sandbox failures,
workspace side effects, artifact promotions, persistence errors, and sandbox
operator-action counts at the tree summary level for DeerFlow-like dashboard
triage. OpenAPI exposes this inspection surface as the typed
`RunTreeSnapshot` response schema.
The native harness now builds a bounded Pydantic `AgentRunContextPacket` from
recent thread messages, runtime todos, run artifacts, scoped memory recall, and
resume-state hints. It tracks deterministic context budget usage and compresses
dropped older context into a short summary. It also projects recent
`tool.completed` outputs into bounded summaries so search/fetch/report evidence
can survive run resumes without replaying raw tool payloads. Scoped memory
recall brings readable user/thread/workspace/organization/skill memory into the
prompt with source, visibility, confidence, truncation, and inclusion reason.
This gives DeerFlow-like long-running tasks a compact context-engineering layer
without promoting Agent todos or plans into workflow definitions.

### 2. Tools and capability routing

DeerFlow-like tools must map to Aithru-controlled capability routing.

```txt
model proposes tool call
  -> harness normalizes call
  -> skill policy check
  -> platform scope/authz check
  -> approval gateway if required
  -> AithruCapabilityRouter
  -> concrete adapter
  -> result normalization
  -> event stream + audit + redaction
```

Target adapters:

- `core-tool-adapter`;
- `core-node-adapter`;
- `workbench-workflow-adapter`;
- `subsystem-api-adapter`;
- `workspace-adapter`;
- `research-report-adapter`;
- `memory-adapter`;
- `sandbox-adapter`;
- `mcp-adapter` for controlled MCP-like catalogs and HTTP JSON execution.

Rules:

- Model adapters never execute tools.
- Tools declare risk level and required scopes.
- Dangerous tools require approval or explicit policy.
- Tool results are structured and redacted before long-term trace storage.
- Aithru-specific router decisions now carry Pydantic actor, scope,
  authorization, and capability audit metadata, so missing-scope failures are
  inspectable policy denials rather than indistinguishable unknown-tool errors.
  Stream redaction can also return a Pydantic receipt describing redacted
  sensitive paths without exposing the original secret values.
  Terminal tool events now persist safe `authorization_decision` and `audit`
  payloads, and a run capability-audit API projects those entries for
  DeerFlow-like replay/debug surfaces with Aithru governance context through
  the typed `AgentCapabilityAuditLog` response schema.
- MCP-like catalogs can now execute through an explicit controlled HTTP JSON
  executor when the server has trusted `metadata.endpoint_url`, the host is
  allowlisted, and settings enable `http_json`. This closes part of the
  DeerFlow-like tool ecosystem gap while keeping concrete MCP calls behind
  scopes, skill policy, approvals, audit, redaction, timeout limits, and bounded
  response validation.
- Research planning creates runtime Agent todos, not workflow nodes or graph
  edges.
- Research report generation produces Agent artifacts from structured sources;
  it is not an Agent-owned workflow definition.
- Workbench workflows are invoked only through Workbench APIs/tools.
- Agent now has a provider-backed `WorkflowCapabilityAdapter` for injected
  Workflow product capabilities. It exposes scoped `workflow_capability` tools
  and external run references, but it still does not own Workbench graph
  execution or `WorkflowSpec` persistence.
- Workflow capability catalogs can now execute through one settings-configured,
  allowlisted HTTP JSON CapabilityRun endpoint with bounded Pydantic
  request/response validation.
- Workflow-owned capability approvals can now pause Agent runs through a
  structured external approval reference and resume through a run-scoped resolve
  API without duplicating approval records in Agent.
- Asynchronous Workflow capability runs can now pause Agent runs as
  `waiting_external_run` through a structured external run reference and resume,
  fail, or cancel through a run-scoped resolve API without turning Agent into a
  Workflow scheduler. Completed callbacks requeue the Agent Run so a worker can
  continue the harness turn after the provider finishes.
- Completed asynchronous Workflow capability output is now folded into the next
  bounded Pydantic context packet as recent tool-result context, so model
  continuation can use the external provider result.
- Duplicate terminal Workflow capability callbacks are now idempotent when they
  repeat the same status, while conflicting late terminal callbacks are rejected
  without writing duplicate external-run facts. The resolve API returns a typed
  Pydantic response that keeps `AgentRun` fields and adds idempotency plus
  fresh-requeue metadata for operator dashboards.
- Waiting asynchronous Workflow capability runs now expose an
  `active_external_run` summary with wait age and stale status, and run lists can
  filter by `external_run_stale=true` for DeerFlow-like operator dashboards
  without adding Agent-owned Workflow scheduling.
- Stale external-run summaries also include Pydantic operator action hints for
  common recovery paths, improving long-task operations while keeping execution
  explicit and control-plane routed.
- Failed and cancelled asynchronous Workflow capability runs now surface as
  structured Pydantic run-summary diagnostics, separating provider-owned
  failures from Agent-owned harness failures.

### 3. Subagents

Subagents should be first-class harness runtime objects.

A subagent should have:

- key and display name;
- instructions;
- allowed tools;
- workspace scope;
- memory scope;
- context budget;
- termination conditions;
- output contract;
- event stream projection;
- parent run link.

Subagent runs should be observable in the parent run timeline, but they are not Workbench nodes.

### 4. Workspace and files

Aithru Agent should have a DeerFlow-like workspace abstraction, but with Aithru policy controls.

Recommended virtual layout:

```txt
/input
/uploads
/workspace
/scratch
/reports
/patches
/artifacts
/workflow-drafts
/sandbox
```

Workspace operations:

- list;
- read;
- write;
- delete;
- diff;
- patch;
- snapshot;
- restore;
- promote to artifact;
- attach to thread;
- create a structured, non-executable Workbench draft artifact for review.

The current backend now records Pydantic workspace file versions for writes and
deletes in both in-memory and SQLite stores. It exposes read-only workspace
snapshots and metadata-only diffs so UIs and auditors can inspect generated file
history without replaying file contents or treating snapshots as workflow
checkpoints.
It can also restore a workspace to a prior snapshot by applying new auditable
write/delete versions from retained historical content. This moves the backend
closer to DeerFlow-style workspace recovery while preserving Aithru's boundary
against Agent-owned workflow checkpoint execution.
Workspace snapshot, diff, restore, file list, and file-version APIs now publish
typed OpenAPI response schemas, closing another DeerFlow-like file panel and
recovery-panel contract gap without making workspace snapshots executable
workflow state.
Workspace upload APIs now persist base64 Pydantic upload payloads under
`/uploads/...`, returning structured upload/file metadata and normal versioned
workspace records. This closes more of the DeerFlow-like "uploaded and generated
files" surface while keeping uploads in the control plane.
`workspace.patch_file` now gives models a DeerFlow-like file editing primitive
without raw filesystem access: edits are explicit Pydantic text replacements,
run through scope, skill, approval, and workspace path policy, and persist as a
new versioned workspace file with replacement metadata. The workspace patch API
uses the same Pydantic contract for UI/operator edits, closing more of the
DeerFlow-like workspace editing surface without turning workspace versions into
workflow checkpoints.
Workspace file read, write, delete, and promote APIs now publish typed OpenAPI
response schemas, closing more of the DeerFlow-like generated-files panel
contract while preserving control-plane authorization and avoiding raw
filesystem exposure to model code.
`sandbox.list_files` now gives sandbox-capable runs a DeerFlow-like workspace
browser primitive without raw directory access. It goes through the capability
router, requires sandbox execution and workspace read scopes, honors workspace
path policy and optional prefix filtering, and returns typed file metadata
without contents.
`sandbox.read_file` now gives sandbox-capable runs a DeerFlow-like file-read
primitive without direct filesystem access. Reads go through the capability
router, require both sandbox execution and workspace read scopes, honor
workspace path policy, and return Pydantic content metadata including encoding,
size, returned bytes, and truncation state.
`sandbox.write_file` now adds the paired DeerFlow-like file-write primitive
without direct filesystem access. Writes go through the capability router,
require sandbox execution and workspace write scopes, are governed as write risk
for approval policy, honor workspace path policy, and persist normal versioned
workspace files with Pydantic write metadata.
`sandbox.patch_file` now adds the DeerFlow-like text-edit primitive for sandbox
workflows without raw filesystem patching. It reuses the Pydantic workspace
patch request/result contracts, requires sandbox execution and workspace write
scopes, is governed as write risk for approval policy, honors workspace path
policy, and persists a new versioned workspace file with replacement metadata.
`sandbox.delete_file` now adds the DeerFlow-like file-removal primitive without
raw filesystem deletion. It requires sandbox execution and workspace write
scopes, is governed as write risk for approval policy, honors workspace path
policy, deletes through the Agent store, emits `workspace.file.deleted`, and
returns version-aware Pydantic deletion metadata.
`sandbox.diff` now adds the DeerFlow-like workspace comparison primitive without
raw filesystem diffing. It reuses the Pydantic `AgentWorkspaceDiff` contract,
requires sandbox execution and workspace read scopes, filters by workspace path
policy, and returns metadata-only added/modified/deleted changes.
`sandbox.promote_file` now closes the sandbox-side output handoff: a sandbox run
can promote an existing allowed workspace file to a managed artifact without raw
local file access. It requires sandbox execution, workspace read, and artifact
write scopes, is write-risk and approval-aware, emits `artifact.created`, binds
the artifact to the current run, and returns `AgentArtifactPromotionResult`.
`sandbox.run_python` now also exposes Pydantic run diagnostics for DeerFlow-like
debug and dashboard surfaces. Completion and failure payloads summarize final
status, the execution summary, declared workspace outputs, persisted workspace
files, artifact promotions, and workspace persistence errors without parsing
stdout/stderr or treating sandbox side effects as workflow steps. Run summaries
and snapshots now project those diagnostics into counts and ordered entries, so
dashboards can show sandbox output side effects and suggested operator next
steps without replaying every event or expanding every sandbox diagnostic. Run
lists can also filter and order those suggested steps directly for
operator-action queues.
Workspace files can now be promoted into managed artifacts through a control
plane API. Promoted artifacts retain a workspace pointer, source
version/file-version/hash metadata, and optional Pydantic retention policy,
which closes part of the DeerFlow-like output pipeline without exposing raw
local file promotion to model code.
Artifact listing can now filter by run, workspace, artifact type, retention
mode, and finalized state, with optional page metadata and ordering. This gives
the backend a DeerFlow-like outputs inventory surface for dashboards while
preserving Aithru authorization and lifecycle boundaries. The inventory,
detail, and download metadata surfaces are now typed OpenAPI contracts for
dashboard/client generation; raw content is still delivered only as managed
artifact responses.

Rules:

- Workspace writes are evented.
- File operations are scoped to workspace policy.
- Sandbox mounts are explicit.
- Retention is policy-controlled.
- Sensitive file contents are not leaked into debug UI by default.

### 5. Sandbox and controlled execution

Aithru Agent should eventually support code/script execution, but only through a provider boundary.

Target provider interface examples:

```txt
sandbox.runPython
sandbox.runNode
sandbox.executeCommand
sandbox.installPackage
sandbox.readFile
sandbox.writeFile
sandbox.diff
sandbox.patch
```

Rules:

- No direct model shell access.
- Network policy is explicit.
- File mount policy is explicit.
- Resource limits are explicit.
- Timeout is mandatory.
- Risky operations require approval.
- stdout/stderr are stream events.
- Completion/failure events carry typed execution summaries for timeout,
  exit code, retained output sizes, truncation, result type, and error code.
- Workspace listings from sandbox tools go through `sandbox.list_files`, require
  workspace read scope, apply allowed-path and prefix filtering, and return typed
  metadata instead of provider directory handles or file contents.
- Workspace reads from sandbox tools go through `sandbox.read_file`, require
  workspace read scope, apply allowed-path policy, and return typed content
  metadata instead of provider filesystem handles.
- Workspace writes from sandbox tools go through `sandbox.write_file`, require
  workspace write scope, apply allowed-path policy, trigger write-risk approval
  policy, and produce versioned workspace file events.
- Workspace text edits from sandbox tools go through `sandbox.patch_file`, reuse
  the Pydantic workspace patch contract, remain text-only, and produce
  version/replacement metadata.
- Workspace deletions from sandbox tools go through `sandbox.delete_file`,
  require workspace write scope, apply allowed-path policy, trigger write-risk
  approval policy, and produce typed deletion metadata.
- Workspace comparisons from sandbox tools go through `sandbox.diff`, reuse the
  Pydantic workspace diff contract, apply allowed-path filtering, and never
  return file contents.
- Workspace artifact promotion from sandbox tools goes through
  `sandbox.promote_file`, requires artifact-write scope, triggers write-risk
  approval policy, and returns the typed artifact promotion result.
- Generated files are declared as structured sandbox output and then written
  through Agent workspace scope/path policy, producing workspace events.
- Generated files can request managed artifact promotion only through the
  workspace-file promotion path and artifact-write scope.

### 6. Context engineering

Aithru Agent needs a real context system, not just recent message slicing.

Target components:

- `ContextBuilder`;
- `ContextBudget`;
- thread summarization;
- tool result compression;
- workspace file references;
- artifact summaries;
- skill context loading;
- memory snippets;
- subagent context isolation;
- final answer context assembly.

Rules:

- Subagents should not automatically see the full parent context.
- Large tool outputs should be written to workspace and summarized.
- Completed subtasks should be summarized and link to artifacts/files.
- Skill context should load progressively when relevant.

### 7. Memory

Memory should be scoped and explainable.

Memory scopes:

- thread;
- workspace;
- project;
- user;
- organization;
- skill.

Memory metadata:

- owner;
- source;
- confidence;
- visibility;
- retention;
- createdBy;
- createdAt;
- updatedAt;
- permission requirements.

Rules:

- No unbounded global black-box memory.
- Sensitive memory requires explicit permission and retention policy.
- Memory reads/writes are evented and auditable at the appropriate visibility.
- Context packet recall only includes current-run readable scopes, records why
  each item was included, and reports retained/dropped memory counts through the
  debug context event.
- Run memory recall APIs can expose the same bounded `AgentMemoryRecall`
  projection for inspection under run/thread-run routes, without giving models
  direct store access or adding global black-box memory search. The recall
  routes now publish the typed OpenAPI `AgentMemoryRecall` response schema.
- Structured memory retention supports retained, ephemeral, and expires-at
  policy modes. Expired memory is omitted from default list/search/recall paths,
  and the forget API removes visible entries through the control plane.
- Private memory visibility is an enforced Pydantic policy at API, tool, and
  recall boundaries: private entries only surface to the owning/current actor.
- Control-plane threads, approvals, memory entries, thread messages, and skills
  now expose typed OpenAPI response schemas (`AgentThread`,
  `ThreadListPage`, `UpdateThreadRequest`, `AgentThreadSummary`,
  `AgentThreadSummaryMessage`, `AgentThreadSummaryRun`,
  `AgentThreadWorkbench`, `AgentThreadWorkbenchRun`,
  `AgentThreadDashboardPage`, `AgentThreadDashboardItem`,
  `AgentThreadDashboardActionHint`, `AgentApproval`, `AgentRun`,
  `AgentMemoryEntry`, `AgentMemoryForgetResult`, `AgentMessage`, and
  `AgentSkill`). Thread lists can filter active/archive views and return
  pagination/order metadata for conversation sidebars. Thread dashboard reads
  add DeerFlow-like queue rows with latest-run attention, degraded-research
  rollups, and typed next-action hints for input, approval, research
  continuation, and sandbox follow-up. The hints point to existing APIs and are
  not workflow queue records or scheduler commands. They now also include
  thread-scoped `thread_path` values when a matching route exists, and input
  hint resolution clears dashboard/workbench action counts after the run
  resumes. Thread lifecycle updates can rename or archive conversations. Thread
  summary reads can show the latest message/run, last activity, and
  active/waiting run counts for DeerFlow-like conversation sidebars. Thread
  workbench reads combine the visible thread, summary, recent run cards with
  the same typed action hints as dashboard rows, and one selected
  `RunSnapshotResponse`, giving a frontend one stable
  conversation-opening payload while deriving that view from harness messages,
  runs, stream events, and artifacts, not workflow graph definitions.
- Health, subagent spec, run tool inspection, and run subagent inspection APIs
  now expose typed OpenAPI response schemas (`AgentHealthResponse`,
  `AgentSubagentSpec`, `AgentToolDescriptor`, and `AgentSubagentRun`). This
  makes tool/subagent panels easier to generate for a DeerFlow-like app while
  keeping tool execution capability-boundary controlled and subagents as
  harness child-run resources, not Workbench graph nodes.

### 8. Middleware-driven harness

Aithru Agent should avoid becoming one large while-loop.

Recommended middleware areas:

- actor context;
- thread loading;
- workspace mounting;
- upload handling;
- skill activation;
- context building;
- todo management;
- tool policy;
- approval;
- sandbox;
- tool recovery;
- memory;
- summarization;
- subagent limit;
- loop detection;
- artifact creation;
- audit;
- error normalization.

The harness kernel should be composable and testable.

### 9. Streaming gateway

Aithru Agent stream should be a structured run event stream, not only token deltas.

Required event groups:

- run lifecycle;
- message deltas;
- todo updates;
- model calls;
- tool calls;
- approval requests/resolutions;
- workspace file changes;
- artifact events;
- subagent events;
- sandbox stdout/stderr/file changes;
- memory events;
- audit/debug events.

Rules:

- Events are append-only.
- Run sequence is strictly increasing.
- Persist before publish.
- Support SSE replay with `afterSequence` or `Last-Event-ID`.
- Terminal event closes the stream.

## Aithru-specific extensions beyond DeerFlow

Aithru Agent should eventually exceed DeerFlow in platform governance.

| Area | Aithru extension |
| --- | --- |
| Identity | Platform actor context: user, service, delegated, org. |
| Authorization | Platform grants, scopes, resource authz, connection policy. |
| Audit | Every sensitive action emits platform/audit-compatible events. |
| Workbench | Agent can be called from formal workflows and can call formal workflows as tools. |
| Core | Capability routing reuses Core contracts, nodes, tools, trace, redaction, approval. |
| Subsystems | Agent can call other Aithru apps through token exchange/delegation. |
| Enterprise deployment | Server-side trusted host with fail-closed authz and no browser-held service credentials. |
| Redaction | Sensitive model/tool/workspace/sandbox values are redacted by policy. |

## Capability completion roadmap

Current implementation work should target all P0, P1, and P2 items in this
table. P3 items remain important, but they belong to a later productization or
ecosystem phase rather than the current backend parity plan.

| Capability | Current state | Gap | Suggested completion path | Priority |
| --- | --- | --- | --- | --- |
| Runtime Processor layer | Runtime behavior is implemented directly in worker, harness, API, and projection code. | Title generation, summarization, clarification, memory extraction, and usage aggregation could become scattered concerns. | Add a lightweight `runtime/processors` layer that the worker/run lifecycle can call for platform-state processors. | P0 |
| Run-tree usage / budget aggregation | Parent and child Agent Runs are persisted and inspectable through run trees. | Token/request/tool usage is not automatically aggregated across parent, child, and external runs, so run-tree budget control is incomplete. | Add `RunUsageSummary` or `RunTreeUsageSnapshot` projections and budget checks that include parent, descendants, and external capability runs. | P0 |
| Context semantic summarization | Context packets truncate, budget, and emit compressed-context notices; artifacts, tools, subagents, and research have bounded summaries. | There is no durable LLM semantic summary for long threads or dropped context. | Add a context summarization processor that persists reusable thread/run summaries and feeds them back into context packets. | P0 |
| Clarification preflight | `input.request` can pause a run as `waiting_input`, and user input can resume it. | The system does not automatically decide that an underspecified goal should ask a clarification before execution. | Add a clarification processor before or at the start of execution that can create a user input request instead of prematurely running. | P1 |
| Auto title generation | Threads support manual title creation, update, filtering, and ordering. | Thread titles are not generated automatically from goals or early messages. | Add a title processor that creates short thread titles from the run goal or first messages when no explicit title is present. | P1 |
| Async memory extraction | Memory CRUD, `memory.remember`, scoped recall, visibility, retention, and context injection exist. | Completed runs do not automatically produce long-term memory candidates. | Add a post-run memory extraction processor that writes approved memory or creates auditable memory candidates. | P1 |
| Vision / view image | Workspace uploads, media types, artifact content, and base64 binary handling exist. | There is no image-understanding tool, multimodal message attachment path, or provider-aware image prompt injection. | Design image attachments, media policy, model capability checks, and a controlled view-image capability as a separate multimodal slice. | P2 |
| File conversion | Workspace upload and file/artifact storage exist. | PDF, PPT, Excel, Word, and similar files are not automatically converted into model-readable markdown/text. | Add an upload/conversion processor that produces managed markdown/text workspace files or artifacts while preserving originals. | P2 |
| Skill management UI/API | Skill packages, built-in `deep-research`, skill listing/detail, and policy fields exist. | There is no user-facing install, enable/disable, version, configuration, or marketplace management surface. | Add skill registry management APIs and typed skill configuration models. | P2 |
| MCP/external tool config | Controlled MCP/HTTP capability providers exist behind the capability router. | Users cannot manage MCP server configuration, OAuth/cache/reset, or external tool settings through a product API. | Add external tool configuration APIs with secret boundaries, policy validation, and audit. | P2 |
| Multi-model config | Runtime settings can select model behavior at the backend level. | There is no product-level model profile registry, per-run model selection, or vision/thinking/cost policy surface. | Add typed model profiles and per-run model selection guarded by platform policy. | P2 |
| Frontend/Gateway | Backend APIs and OpenAPI contracts are broad; no standalone Agent UI is in this repository. | DeerFlow-like full app/gateway experience is missing. | Build a Platform-hosted UI and gateway experience for threads, runs, workspace, artifacts, approvals, skills, tools, and memory. | P3 |
| AIO sandbox experience | A controlled local sandbox provider and sandbox file/tool diagnostics exist. | It lacks a DeerFlow/AIO-style browser, shell, files, and editor environment. | Add a remote/production sandbox provider behind the same capability boundary. | P3 |
| IM/channel integrations | No IM adapters are implemented. | Slack, Telegram, Feishu, and similar entry channels are missing. | Add external channel adapters that create threads/runs through the control plane. | P3 |
| External observability exporters | Internal events, trace, capability audit, and run exports exist. | LangSmith, Langfuse, or similar external exporters are not integrated. | Add trace/export adapters that preserve Aithru redaction and audit rules. | P3 |
| Browser automation / real browsing | Controlled web search/fetch tools exist. | Full browser-use style navigation and interaction are missing. | Add a controlled browser capability with sandbox isolation, approval policy, and event redaction. | P3 |

## Target architecture comparison

```txt
DeerFlow 2.0
  lead agent
  skills
  tools
  subagents
  filesystem/sandbox
  memory
  streaming UI

Aithru Agent
  AgentHarness
  AgentSkill packages
  AithruCapabilityRouter
  SubagentRunner
  AgentWorkspace
  AgentSandboxProvider
  AgentMemoryProvider
  AgentStreamEvent gateway
  Platform authz/audit
  Core/Workbench capability adapters
```

## Implementation principles

1. Design for complete harness first; cut MVP from the full model later.
2. Keep Aithru product contracts independent from external harness libraries.
3. Treat DeerFlow as a benchmark, not a dependency.
4. Keep all real actions behind Aithru capability routing.
5. Do not expose Agent runtime plans as workflow graphs.
6. Keep Workbench integration explicit and narrow.
7. Make streaming, workspace, artifacts, approvals, and trace first-class from the beginning.
8. Use middleware-style runtime composition instead of a single monolithic loop.

## Phased target

### Phase 1: Harness skeleton

- Thread/message model;
- Skill package spec;
- Run/event model;
- Workspace abstraction;
- Todo runtime state;
- structured stream protocol;
- fake model/tool adapters;
- capability router interface.

### Phase 2: Work-capable harness

- real model adapter;
- workspace file tools;
- artifact pipeline;
- approval gateway;
- sandbox provider interface;
- subagent interface;
- memory provider interface;
- context builder and summarizer.

### Phase 3: Aithru integration

- Platform hosted token verification;
- app manifest and permissions;
- platform authz/audit integration;
- Core tool adapter;
- Core node adapter;
- Workbench workflow adapter;
- Platform subsystem API adapter.

### Phase 4: DeerFlow-level product maturity

- subagent orchestration;
- async subagents;
- sandbox-backed coding/data tasks;
- skill marketplace/library;
- context compression;
- durable run resume;
- workspace snapshots/diffs;
- advanced UI for chat/workspace/runs/artifacts/approvals.

## Acceptance benchmark

Aithru Agent reaches the DeerFlow-level target when it can:

- run a long multi-step task from chat;
- load a skill package relevant to the task;
- maintain a workspace with uploaded and generated files;
- create/update todos and stream progress;
- call policy-gated tools;
- spawn at least one scoped subagent;
- execute code or data processing through a controlled sandbox provider;
- create artifacts from outputs;
- request and resume from approval;
- request missing user input and resume the run;
- summarize or compress context;
- expose a replayable structured event stream;
- call a Workbench/Workflow product capability as a scoped tool;
- produce a structured, non-executable Workbench workflow draft artifact;
- inspect sandbox execution and workspace side effects through structured
  diagnostics;
- preserve Platform org/user/authz/audit/redaction boundaries.
