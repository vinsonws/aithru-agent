# Aithru Agent Backend

Python-first backend for Aithru Agent.

This backend owns the Agent API, worker runtime, event stream, trace projection,
workspace, artifacts, approvals, and capability boundary. Pydantic AI powers the
default harness driver, and `pydantic-ai-harness` is available for internal
capability composition, but neither dependency defines public Aithru product
contracts.

## Run

```bash
uv run pytest
uv run python examples/file_report_agent.py
uv run python examples/deep_research_agent.py
uv run python examples/controlled_web_research_agent.py
uv run uvicorn aithru_agent.api.main:app --reload
```

`POST /api/runs` creates queued runs by default. A worker executes queued
runs.

For one-process development, use the in-memory default. For an API process and
worker process sharing state, use SQLite:

```bash
export AITHRU_AGENT_PERSISTENCE_BACKEND=sqlite
export AITHRU_AGENT_SQLITE_PATH=.aithru/agent.sqlite

uv run uvicorn aithru_agent.api.main:app --reload
uv run aithru-agent-worker --once
uv run aithru-agent-worker --loop --poll-interval 1
```

The worker can also drain a specific SQLite file directly:

```bash
uv run aithru-agent-worker --once --sqlite-path .aithru/agent.sqlite
uv run aithru-agent-worker --loop --poll-interval 1 --sqlite-path .aithru/agent.sqlite
```

## Current Capabilities

- FastAPI Agent control plane.
- Optional Bearer token authentication via `AITHRU_AGENT_API_TOKEN`, with run scope limits from `AITHRU_AGENT_API_SCOPES`.
- Pydantic platform governance contracts for actor identity, scope grants,
  authorization decisions, capability audit metadata, and redaction receipts.
- Terminal tool events carry safe `authorization_decision` and `audit`
  payloads, and run capability audit APIs project those entries for replay/UI
  inspection through the typed OpenAPI `AgentCapabilityAuditLog` response
  schema.
- Trusted `X-Aithru-Org-Id` and `X-Aithru-User-Id` headers bind identity and filter run, memory, skill, and subagent resources.
- Queued Agent runs with worker execution.
- In-process queue deduplicates pending run ids; persistent stores can still
  claim queued runs when a queued notification is stale or missing.
- Running runs carry a Pydantic `AgentRunClaim` lease with worker id, claim
  time, heartbeat time, expiration, and attempt count. Active leases can be
  renewed by the owning worker; expired leases can be reclaimed from in-memory
  or SQLite persistence; stale takeovers emit audit `run.claim.reclaimed`
  events.
- Worker execution uses an internal Pydantic `AgentWorkerHeartbeatPolicy` to
  renew the active claim while a long-running run is still executing, preventing
  duplicate stale-lease takeover without introducing workflow scheduler
  behavior.
- Worker processes can use an internal Pydantic `AgentWorkerLoopPolicy` through
  `run_loop()` or `aithru-agent-worker --loop` to keep polling between idle
  ticks and pick up delayed retry runs after `next_retry_at`. The loop calls
  existing claim/recovery primitives and does not introduce workflow scheduler
  behavior.
- Runs may carry an optional Pydantic `retry_policy` and `retry_state`.
  Recoverable runtime/model failures can be requeued with bounded backoff and
  `run.retry.scheduled` events; exhausted attempts emit `run.retry.exhausted`
  before terminal `model.failed` / `run.failed`. `AgentError` policy,
  authorization, and tool-boundary failures remain terminal by default. This is
  harness runtime state, not workflow scheduler behavior.
- In-memory and SQLite persistence backends.
- Agent stream events, SSE formatting, and trace projection.
- Route-grouped FastAPI control plane under `/api/threads`, `/api/runs`, and
  related resource paths.
- Run stream follow mode waits for new SSE events until terminal run state or timeout.
- Run event and trace inspection routes expose typed OpenAPI `AgentStreamEvent`
  and `AgentTraceSpan` array schemas for replay/debug clients.
- Event writer redaction for common sensitive payload keys before replay or SSE output.
- Run snapshot inspection with events, trace, todos, approvals, workspace file summaries, artifacts, subagent runs, a derived run inspection summary, a derived research recovery summary, a research execution snapshot, a research evidence ledger, a research quality gate, research continuation suggestions, research continuation lineage, and durable resume-state projection through the typed OpenAPI `RunSnapshotResponse` schema.
- Workspace files keep Pydantic write/delete version history. Read-only
  workspace snapshot and diff endpoints expose metadata-only inventory and
  changed/added/deleted path summaries for audit/UI inspection without storing
  Agent workflow checkpoints.
- Workspace snapshot restore uses internally retained write-version content and
  returns a Pydantic restore result. It applies restore as new write/delete
  versions, so history remains immutable and auditable.
- Workspace snapshot, diff, restore, file list, and file-version routes publish
  typed OpenAPI response schemas: `AgentWorkspaceSnapshot`,
  `AgentWorkspaceDiff`, `AgentWorkspaceRestoreResult`, `AgentWorkspaceFile[]`,
  and `AgentWorkspaceFileVersion[]`.
- `POST /api/workspaces/{workspace_id}/uploads` accepts base64 Pydantic upload
  requests for `/uploads/...`, writes bytes through the workspace store, and
  returns `AgentWorkspaceUploadResult`.
- `workspace.patch_file` applies explicit Pydantic text edits through the
  capability router, honors workspace path/write policy, and persists the
  patched content as a normal new workspace file version. The control-plane
  `POST /api/workspaces/{workspace_id}/files/{path}/patch` endpoint uses the
  same edit contract and returns `AgentWorkspacePatchResult`.
- Workspace file read, write, delete, and promote control-plane routes publish
  typed response schemas: `AgentWorkspaceFileReadResult`,
  `AgentWorkspaceFile`, `AgentWorkspaceFileDeleteResult`, and
  `AgentArtifactPromotionResult`.
- `sandbox.read_file` exposes a controlled sandbox-side Agent Workspace read
  primitive. It requires `agent.sandbox.execute` and `agent.workspace.read`,
  honors workspace allowed paths, and returns Pydantic content metadata with
  `content_encoding`, `size`, `returned_bytes`, and `truncated`.
- `sandbox.list_files` exposes controlled sandbox-side Agent Workspace metadata
  listing. It requires `agent.sandbox.execute` and `agent.workspace.read`,
  honors workspace allowed paths and optional prefix filtering, returns
  `SandboxFileListResult`, and never returns file contents.
- `sandbox.write_file` exposes the paired controlled sandbox-side Agent
  Workspace write primitive. It requires `agent.sandbox.execute` and
  `agent.workspace.write`, is governed as write risk for approval policy,
  persists through the workspace store, emits `workspace.file.created`, and
  returns Pydantic file metadata with overwrite status.
- `sandbox.patch_file` exposes controlled sandbox-side text editing through the
  same Pydantic patch contract as `workspace.patch_file`. It requires sandbox
  execution plus workspace write scopes, is write-risk and approval-aware,
  writes a new workspace version, emits `workspace.file.created`, and returns
  `AgentWorkspacePatchResult`.
- `sandbox.delete_file` exposes controlled sandbox-side Agent Workspace
  deletion. It requires sandbox execution plus workspace write scopes, is
  write-risk and approval-aware, removes only allowed workspace files through the
  store, emits `workspace.file.deleted`, and returns Pydantic deletion metadata.
- `sandbox.diff` exposes controlled sandbox-side metadata diffs over Agent
  Workspace snapshots. It requires sandbox execution plus workspace read scopes,
  returns `AgentWorkspaceDiff`, filters changes by workspace allowed paths, and
  never returns file contents.
- `sandbox.promote_file` exposes controlled sandbox-side promotion from an
  existing Agent Workspace file to a managed artifact. It requires sandbox
  execution, workspace read, and artifact write scopes, is write-risk and
  approval-aware, emits `artifact.created`, and returns
  `AgentArtifactPromotionResult`.
- Workspace files can be promoted to managed artifacts through the API control
  plane. Promotion stores a workspace pointer plus source version/hash metadata
  and optional Pydantic artifact retention policy.
- Artifact list APIs support Pydantic-validated lifecycle filters for run,
  workspace, artifact type, retention mode, and finalized state, plus
  `include_meta` pagination/order metadata for output panels. The list, detail,
  and download metadata routes expose typed OpenAPI response schemas:
  `AgentArtifact[] | AgentArtifactListPage`, `AgentArtifact`, and
  `AgentArtifactDownloadInfo`.
- Run export APIs return a Pydantic bundle of run facts, events, trace spans,
  todos, approvals, artifacts, and workspace snapshot for audit/replay
  inspection without creating workflow checkpoints, and expose the typed
  OpenAPI `AgentRunExportBundle` response schema.
- Run export artifact APIs can persist that bundle as workspace JSON and create
  a managed `json` artifact pointer with optional retention metadata through
  the typed `AgentRunExportArtifactResult` response schema.
- Artifact download APIs expose Pydantic download metadata and a force-download
  endpoint with stable attachment filenames for audit bundles and generated
  outputs. Content preview and forced download routes remain managed file
  responses, not raw host filesystem access.
- Run detail and list responses include a derived `summary` with health, typed
  attention reasons, count, research-degraded signals, and derived external
  Workflow capability run diagnostics for lightweight inspection. The same
  projection also includes sandbox run diagnostics and workspace side-effect
  counts from `sandbox.completed` / `sandbox.failed` events. Sandbox failures,
  workspace side effects, artifact promotions, and persistence errors flow into
  summary `attention_reasons`, which drive `needs_attention`. Each sandbox
  diagnostic also carries typed operator action hints for error inspection,
  workspace output review, artifact promotion review, workspace policy review,
  and explicit retry. The same hints are flattened into summary-level
  `sandbox_operator_actions` and `sandbox_operator_action_count` fields for run
  list rows. The summary is included in full run snapshots and is available as
  `GET /api/runs/{run_id}/summary` and
  `GET /api/threads/{thread_id}/runs/{run_id}/summary` with a typed OpenAPI
  `RunInspectionSummary` response model.
- Operator action follow-up APIs can turn a selected sandbox operator action
  kind into an explicit queued Agent Run at
  `POST /api/runs/{run_id}/operator-actions/follow-up` and
  `POST /api/threads/{thread_id}/runs/{run_id}/operator-actions/follow-up`.
  The child run inherits the source identity/thread/workspace and records
  structured `harness_options.operator_follow_up` provenance. The source run
  receives an `operator_action.follow_up.created` audit event; the hint itself
  is not executed automatically. The creation routes expose the typed OpenAPI
  `OperatorFollowUpRunResult` response schema. Operator follow-up lineage APIs
  expose source/child links at `GET /api/runs/{run_id}/operator-actions/lineage` and
  the thread-scoped alias, and full run snapshots include the same
  `operator_follow_up_lineage` projection. The lineage routes expose the typed
  OpenAPI `OperatorFollowUpLineageSnapshot` response schema.
- Run list endpoints support Pydantic-validated filters for `status`,
  `skill_id`, `health`, `needs_attention`, `external_run_stale`,
  `sandbox_failed`, `sandbox_side_effects`, `needs_operator_action`, and
  `sandbox_operator_action_kind`, plus operator follow-up child filters
  `operator_follow_up`, `operator_follow_up_source_run_id`, and
  `operator_follow_up_action_kind`, including thread-scoped lists.
- Run list endpoints support Pydantic-validated `limit`, `offset`, `order_by`,
  and `order_direction` parameters for explicit pagination and ordering,
  including ordering by `sandbox_operator_action_count`.
- Run list endpoints keep array responses by default and can return a
  Pydantic page object with `items`, `total`, `count`, `limit`, and `offset`
  plus `sandbox_operator_action_counts`,
  `operator_follow_up_action_counts`, and
  `operator_follow_up_source_run_counts` when `include_meta=true`. The same
  array-or-`RunListPage` response contract is exposed in OpenAPI for global and
  thread-scoped run lists, and both default array items and page `items` use the
  typed `RunListItem` schema with a `RunInspectionSummary`.
- Native runs build an internal Pydantic `AgentRunContextPacket` from recent
  thread messages, runtime todos, run artifacts, event-derived tool result
  summaries, scoped memory recall, and resume state for compact model context
  engineering.
- Deep Research context packets can include a bounded Pydantic research
  continuation context with step status, evidence summaries, limitations, report
  artifact references, section coverage, next actions, and structured action
  hints derived from existing todos, artifacts, and `research.create_report`
  events. Section coverage marks covered and missing report subquestions, and
  action hints can carry target section ids for focused evidence repair. These
  facts are prompt context for controlled continuation, not scheduled workflow
  steps or direct model-side execution.
- Explicit Deep Research continuation runs can load source-run research context
  into that packet when the source run shares the same organization, actor,
  thread, and workspace boundary. The packet carries the source run id and
  target section ids alongside bounded evidence, limitations, report artifacts,
  and section coverage for model-visible continuity.
- Non-empty context packets emit debug `context.packet.built` events with
  counts, deterministic budget usage, dropped-context counts including memory,
  and truncation status.
- Run memory recall APIs expose the same scoped Pydantic `AgentMemoryRecall`
  projection at `/api/runs/{run_id}/memory-recall` and the thread-scoped alias
  without exposing unrestricted memory search or the full context packet, and
  publish the typed OpenAPI `AgentMemoryRecall` response schema.
- Memory entries support a structured Pydantic retention policy with
  `retained`, `ephemeral`, and `expires_at` modes; expired entries are filtered
  from default memory list/search/recall paths, and `DELETE /api/memory/{id}`
  returns a Pydantic forget result after identity checks.
- Completed memory-write runs create deterministic pending memory candidates,
  not durable memory entries. `GET /api/memory-candidates` lists visible
  candidates, approval writes a normal scoped `AgentMemoryEntry`, and rejection
  only resolves the candidate.
- Private memory visibility is enforced through a Pydantic policy at API,
  `memory.search`, and run-recall boundaries: private entries require owner or
  user-scope ownership to match the current actor, while shared/org/unset
  visibility remains governed by existing org and scope checks.
- Control-plane resource APIs for threads, approvals, memory entries, thread
  messages, and skills expose typed OpenAPI response schemas: `AgentThread`,
  `ThreadListPage`, `UpdateThreadRequest`, `AgentThreadSummary`,
  `AgentThreadSummaryMessage`, `AgentThreadSummaryRun`,
  `AgentThreadWorkbench`, `AgentThreadWorkbenchRun`,
  `AgentThreadDashboardPage`, `AgentThreadDashboardItem`, `AgentApproval`,
  `AgentRun`, `AgentMemoryEntry`, `AgentMemoryForgetResult`,
  `AgentMemoryCandidate`, `AgentMemoryCandidateApprovalResult`, `AgentMessage`,
  and `AgentSkill`. Thread lists support active/archive filtering, ordering,
  and opt-in pagination metadata. `GET /api/threads/dashboard` derives queue
  rows with latest-run attention and degraded-research rollups from visible
  harness facts. Thread lifecycle updates can rename or archive a thread.
  `GET /api/threads/{thread_id}/summary` derives latest message/run, activity,
  and active/waiting counts from stored harness facts.
  `GET /api/threads/{thread_id}/workbench` combines the visible thread,
  summary, bounded run cards, and one selected run snapshot for conversation
  dashboards, not workflow definitions or scheduler state.
- Completed runs store a result summary with final content, artifact ids, and message references.
- Runtime user input for active threaded runs through persisted messages and stream events.
- Agent-requested user input through `input.request`, `waiting_input` run state,
  `input.requested` / `input.received` events, and requeue-on-input resume.
- Worker recovery uses a Pydantic `RunRecoveryDecision` after normal queue
  claims are exhausted. It can requeue received input, apply already-resolved
  approval decisions, continue parents whose delegated children completed with
  textual results or bounded artifact summaries, and fail parents whose
  delegated children failed or were cancelled without introducing workflow
  scheduler behavior.
- Run tree inspection uses a Pydantic `RunTreeSnapshot` at
  `/api/runs/{run_id}/tree` and `/api/threads/{thread_id}/runs/{run_id}/tree`
  to show parent/child runs, subagent delegations, depth, status counts, and
  artifact counts without creating workflow graph semantics. These routes expose
  the typed OpenAPI `RunTreeSnapshot` response schema. Nodes also expose
  typed attention reasons, research degraded status, and descendant attention
  counters so callers can locate failed, waiting, degraded, or sandbox-sensitive
  branches without replaying every event by hand. Nodes and tree summaries also
  expose sandbox failure, workspace side-effect, artifact-promotion,
  persistence-error, and operator-action counts for dashboard triage.
- Health, subagent spec, run tool inspection, and run subagent inspection routes
  expose typed OpenAPI response schemas: `AgentHealthResponse`,
  `AgentSubagentSpec`, `AgentToolDescriptor`, and `AgentSubagentRun`. These are
  harness inspection/delegation contracts, not workflow graph or scheduler
  contracts.
- Completed assistant replies are persisted back to their Agent Thread for future run context.
- Local workspace, todo, artifact, research report, Workbench draft, memory,
  subagent, and sandbox tools behind the capability router.
- Sandbox execution results include a Pydantic execution summary with timeout,
  exit code, retained output sizes, truncation flags, result type, timeout
  status, and error code. The same summary is emitted on sandbox completion or
  failure events and projected into sandbox trace span refs for audit/debug
  surfaces. `sandbox.run_python` also returns a Pydantic diagnostics object and
  emits it on completion/failure events, summarizing final status, execution,
  declared workspace outputs, persisted files, artifact promotions, and
  workspace persistence errors. Run summaries and snapshots project those
  diagnostics into dashboard-friendly counts, ordered entries, and typed
  operator action hints without executing those hints automatically.
- Sandbox code may declare `workspace_files` as structured output. Those files
  are persisted only by the local sandbox tool through the Agent store, after
  `agent.workspace.write` and workspace allowed-path checks, and emit
  `workspace.file.created` events. A declared workspace file can also request
  managed artifact promotion, which uses the existing workspace-file promotion
  store path and requires `agent.artifact.write`.
- Sandbox-capable runs can call `sandbox.read_file` to read current Agent
  Workspace files through the same capability boundary. The tool never exposes
  host filesystem APIs, requires workspace read scope, applies allowed-path
  policy, and marks byte content as base64 in its Pydantic result.
- Sandbox-capable runs can call `sandbox.list_files` to inspect current
  workspace file metadata before choosing a read, patch, diff, or promotion
  target. The tool is read-only, prefix-filtered, allowed-path filtered, and
  returns bounded Pydantic metadata without content.
- Sandbox-capable runs can also call `sandbox.write_file` to write current Agent
  Workspace files through the same boundary. The tool is write-risk,
  approval-aware, requires workspace write scope, applies allowed-path policy,
  and writes versioned workspace files instead of provider-local files.
- Sandbox-capable runs can call `sandbox.patch_file` for explicit text
  replacements using the existing Pydantic patch request/result contracts. The
  tool is text-only, write-risk, approval-aware, allowed-path checked, and
  produces a new versioned workspace file.
- Sandbox-capable runs can call `sandbox.delete_file` to remove an allowed
  workspace file through the same capability boundary. The tool is write-risk,
  approval-aware, emits deletion events, and returns version-aware Pydantic
  deletion metadata.
- Sandbox-capable runs can call `sandbox.diff` to inspect metadata changes
  between workspace versions. The tool is read-only, allowed-path filtered, and
  returns the existing Pydantic workspace diff contract rather than raw file
  contents.
- Sandbox-capable runs can call `sandbox.promote_file` to turn an existing
  allowed workspace file into a managed artifact. The tool uses the existing
  store promotion path, binds the artifact to the current run, carries sandbox
  source metadata, and returns the Pydantic artifact promotion result.
- Workbench draft creation is available as `workbench.workflow_draft.create`.
  It creates a structured, non-executable `workflow_draft` artifact behind
  `agent.artifact.write` and `agent.workbench.write`; Workbench remains
  responsible for validating, saving, versioning, and running any formal
  `WorkflowSpec`.
- Workflow product capabilities can be exposed through injected
  `WorkflowCapabilityProvider` adapters. They are listed as
  `workflow_capability` tools, execute through the capability router, and return
  provider-owned external run references for trace and UI surfaces without
  making Agent a workflow graph executor.
- Settings can install a controlled HTTP JSON Workflow capability provider from
  a Pydantic capability catalog, one allowlisted endpoint, timeout, and bounded
  response size. The provider posts typed invocation payloads and validates
  typed results; Agent still does not store Workbench credentials or execute
  `WorkflowSpec` graphs.
- Workflow-owned capability approvals pause runs with a Pydantic
  `current_external_approval` reference and `external_approval.*` stream events.
  They do not create Agent-owned `AgentApproval` records; resolving the external
  reference requeues approved runs or fails rejected runs.
- Asynchronous Workflow capability runs pause runs with a Pydantic
  `current_external_run` reference and `waiting_external_run` status. The
  run-scoped external-run resolve API records completed, failed, or cancelled
  provider-owned CapabilityRun results without making Agent a Workflow scheduler.
  Completed external results requeue the Agent Run through the worker queue for
  the next harness continuation.
- Completed asynchronous CapabilityRun output is folded into the next internal
  context packet as bounded `tool_results` context, including capability key and
  external run id, so model continuation can see provider output without Agent
  duplicating Workflow execution state.
- Duplicate provider callbacks for the same terminal CapabilityRun status are
  idempotent and do not duplicate `external_run.*` facts. Conflicting terminal
  callbacks are rejected instead of overwriting the existing provider-owned
  outcome. The run-scoped resolve endpoint returns a Pydantic
  `ResolveExternalRunResponse` with the run fields plus capability run id,
  terminal status, idempotency, and fresh-requeue metadata.
- Waiting asynchronous CapabilityRuns project an `active_external_run` summary
  with wait age and stale status, and run lists can filter with
  `external_run_stale=true` for UI/operator attention without Agent polling,
  cancelling, retrying, or scheduling the external Workflow run.
- Stale active external-run summaries include Pydantic operator action hints for
  checking provider status, redelivering a completed callback, or manually
  resolving failed/cancelled status through the existing control-plane endpoint.
  These hints do not execute automatically.
- Failed or cancelled asynchronous CapabilityRuns are projected into run
  summaries as Pydantic diagnostics with capability key, external run id, tool
  call id, error/comment, and source event sequence.
- Unknown or cross-organization run skills are rejected before run creation, execution, or approval resume so missing policy cannot fall back to unrestricted execution.
- Run tool inspection validates the run skill boundary before exposing available tools.
- Runs attached to Agent Threads must stay inside the thread organization and owner boundary.
- Run and message APIs validate Agent Thread references before writing related state.
- Workspace file APIs validate workspace references before reading or writing files.
- HTTP workspace writes validate text content before entering persistence.
- Run event and stream reads validate run references before replay.
- Run `join`, `stream`, and `cancel` endpoints are available on new run paths
  without moving run state out of Aithru.
- `AgentWorkerRunner.join_run()` owns run join waiting, and store updates
  validate run status values back into Aithru domain enums.
- Memory tools emit read/write events and trace spans.
- Memory tools bind user/thread/workspace/organization/skill scope ids to the current run context.
- Memory list/search/recall paths omit expired retained entries by default, and
  the API can include expired entries only when explicitly requested for
  inspection.
- Private memory does not cross actor boundaries in API reads, tool search, or
  context-packet recall.
- Todo and artifact mutation tools bind object ids to the current run context.
- Capability router denials distinguish known tools with missing scopes from
  truly unknown tools, and successful or denied tool results carry structured
  authorization and audit metadata.
- `input.request` pauses the current threaded run for user input without
  bypassing the capability router. User input through `/api/runs/{run_id}/input`
  persists a thread message, emits `input.received`, changes the run back to
  `queued`, and re-enqueues it for worker execution.
- `/api/runs/{run_id}/snapshot` includes a Pydantic `resume` projection for the
  latest input, approval, external Workflow capability run, or subagent pause.
  It records pause/resume event sequences, relevant ids, and persisted
  approval-history availability without adding workflow or scheduler semantics.
- Completed delegated child text results and bounded artifact summaries can
  resume the parent model through an explicit `resume_subagent` continuation
  hook. Raw artifact payloads are not blindly replayed into recovery context.
- Completed delegated children persist a structured Pydantic
  `AgentSubagentResultSummary` on the subagent run and `subagent.completed`
  event, including bounded child text, artifact ids, artifact summaries, output
  counts, and message refs for API, trace, and recovery surfaces.
- `AgentRunContextPacket` is attached to internal Pydantic runtime deps and
  rendered into the system instructions as bounded context. It includes
  deterministic compressed summaries for dropped older context and budget usage
  metadata. It can also summarize prior `tool.completed` outputs such as
  `web.fetch`, `web.search`, and `research.create_report` without copying raw
  tool payloads into debug events. It can recall current-run readable memory
  from user, thread, workspace, organization, and skill scopes when the run has
  `agent.memory.read` or `*`, render retained items under `Relevant memory:`,
  and account for dropped/truncated memory in the packet budget. The run memory
  recall endpoint reuses this scoped projection for inspection, while the full
  context packet remains internal and does not persist Agent plans as workflows.
- `research.create_plan` creates Pydantic-validated research sections and
  runtime Agent todos for search/fetch/synthesis/report work; sections are
  planning metadata for UI, prompt context, and audit, not workflow nodes.
- `research.create_report` renders Pydantic-validated research sources into a
  markdown `report` artifact without bypassing the capability router.
- Research reports include structured Pydantic evidence rows with stable
  citation numbers, source URLs, snippets, fetched excerpts, and markdown
  Evidence tables.
- Research report sources are deduplicated by normalized URL, sorted by
  computed source quality, and exposed with Pydantic quality labels, scores,
  reasons, and artifact quality summary metadata.
- Research report sources and evidence rows can carry a typed `section_id`.
  Reports render section-aware evidence tables and artifact metadata stores
  Pydantic section summaries for inspection. These sections are report metadata,
  not workflow branches or scheduled child tasks.
- Research reports can be `complete`, `partial`, or `insufficient_evidence`.
  Partial/degraded reports carry Pydantic limitations and markdown limitation
  sections so failed search/fetch/source collection remains auditable.
- `research.create_report` can auto-add Pydantic limitations from blocked
  default Deep Research runtime todos when the model does not provide explicit
  limitations, allowing insufficient-evidence reports to be created after
  source-collection failures.
- Completed `web.search`, `web.fetch`, and `research.create_report` calls can
  advance matching Deep Research runtime todos to `done` and emit
  `todo.updated` events.
- Failed `web.search` and `web.fetch` calls emit dedicated `web.*.failed`
  events with structured limitations, project failed web trace spans, and mark
  matching Deep Research runtime todos as `blocked`.
- Failed controlled web search/fetch calls return Pydantic-shaped recoverable
  failure payloads to the model so a run can continue toward a degraded report.
  Non-web tool failures remain non-recoverable and raise `TOOL_FAILED`.
- Tool failure recoverability is controlled by
  `AgentToolDescriptor.failure_policy`. Descriptors default to `fail_run`, while
  controlled web descriptors explicitly opt into `return_recoverable`.
- Run snapshots expose a derived `research` object with degraded report status,
  failed web calls, blocked research todos, report artifact evidence/source
  counts, and structured limitations. This is projected from existing
  event/todo/artifact/trace state rather than stored as a workflow definition.
- `/api/runs/{run_id}/snapshot` exposes the complete inspection payload as
  `RunSnapshotResponse`, tying the run, summary, events, trace, todos,
  approvals, workspace files, artifacts, research projections, lineage, resume
  state, and subagents into one typed read-only dashboard contract.
- `/api/runs/{run_id}/events`, its thread-scoped alias, and
  `/api/runs/{run_id}/trace` expose typed `AgentStreamEvent[]` and
  `AgentTraceSpan[]` response schemas, keeping replay and trace inspection as
  read-only harness facts rather than workflow graph state.
- Research execution snapshot APIs expose typed research sections/subquestions,
  ordered Deep Research runtime steps, plan query/objective, todo status, web
  success/failure counts, report artifact ids, and the same degraded summary at
  `/api/runs/{run_id}/research/execution` and
  `/api/threads/{thread_id}/runs/{run_id}/research/execution`. This remains a
  read-only Pydantic projection over harness facts.
- Research evidence ledger APIs expose structured report sources, evidence rows,
  source quality, section coverage, limitations, counts, and report artifact references at
  `/api/runs/{run_id}/research/evidence` and
  `/api/threads/{thread_id}/runs/{run_id}/research/evidence`. The ledger is
  projected from `research.create_report` tool output events and artifact
  metadata instead of parsing markdown, and it can identify missing report
  sections when a planned subquestion has no evidence and weak sections when a
  covered subquestion has no high-quality evidence.
- Research review APIs expose a Pydantic quality gate at
  `/api/runs/{run_id}/research/review` and
  `/api/threads/{thread_id}/runs/{run_id}/research/review`. The review reuses
  the execution snapshot and evidence ledger to report pass/warn/fail status,
  score, readiness, finding codes, and counts for missing evidence, blocked
  steps, web failures, limitations, source quality, and weak research sections.
  It is a read-only projection and does not persist review workflow state.
- Research continuation APIs expose typed next-action suggestions at
  `/api/runs/{run_id}/research/continuation` and
  `/api/threads/{thread_id}/runs/{run_id}/research/continuation`. Suggestions
  include priorities, related review finding codes, suggested tool names, and
  research phases for collecting sources, retrying controlled web steps,
  addressing limitations, and regenerating the report. Suggestions can also
  carry target section ids for missing or weak subquestion evidence. They are
  read-only remediation hints, not scheduled workflow steps or model-side tool
  execution.
- Research continuation run APIs create explicit queued continuation runs at
  `POST /api/runs/{run_id}/research/continue` and
  `POST /api/threads/{thread_id}/runs/{run_id}/research/continue`. The created
  run inherits the source thread, workspace, skill, and scopes, and receives
  bounded continuation instructions plus structured
  `harness_options.research_continuation` target metadata. These routes expose
  the typed OpenAPI `ResearchContinuationRunResult` response schema. This is an
  operator/control-plane action, not automatic scheduling.
- When those continuation runs execute, the internal context packet can reuse
  the source run's bounded research report facts and target sections, provided
  the source and child remain inside the same identity/thread/workspace
  boundary.
- Research continuation lineage APIs expose event-derived audit links at
  `/api/runs/{run_id}/research/lineage` and
  `/api/threads/{thread_id}/runs/{run_id}/research/lineage`. A continuation
  child can show its source run and selected actions, while a source run can
  list created continuation children. The lineage is projected from
  `run.created` and `research.continuation.created` events rather than stored as
  workflow branches or scheduler state.
- Deep Research dashboard APIs expose typed OpenAPI response schemas:
  `ResearchExecutionSnapshot`, `ResearchEvidenceLedger`,
  `ResearchReviewSnapshot`, `ResearchContinuationSnapshot`, and
  `ResearchContinuationLineageSnapshot`.
- Run detail/list summaries expose `health`, `needs_attention`, typed
  `attention_reasons`, event/todo/artifact/approval/failed-trace counts, and
  research degraded status so list views can surface failed, degraded, or
  sandbox-sensitive runs without reassembling the stream.
- Run creation, wait, join, cancel, detail, and input routes expose typed
  OpenAPI response schemas: `AgentRun`, `RunDetailResponse`, and
  `AgentMessage`. Run detail remains a read-only harness inspection projection
  over stored run state plus summary, not a workflow checkpoint or graph
  snapshot.
- `GET /api/runs/{run_id}/summary` and the thread-scoped alias expose the same
  Pydantic `RunInspectionSummary` contract directly for lightweight dashboards.
- `GET /api/threads/{thread_id}/summary` exposes the Pydantic
  `AgentThreadSummary` contract directly for conversation sidebars and thread
  dashboards.
- `GET /api/threads/dashboard` exposes the Pydantic `AgentThreadDashboardPage`
  contract for conversation queues, including thread summaries, latest run
  cards, attention/degraded-research filters, and typed
  `AgentThreadDashboardActionHint` rows for input, approval, research
  continuation, and sandbox follow-up actions. The hints point to existing
  APIs, include `thread_path` values when a thread-scoped action route exists,
  and do not create workflow queue records or scheduler commands.
- `GET /api/threads/{thread_id}/workbench` exposes the Pydantic
  `AgentThreadWorkbench` contract for opening a thread dashboard with run cards
  and the selected run snapshot in one response. Each run card carries the same
  typed action hints and counts as dashboard rows, giving clients consistent
  read-only pointers to input, approval, research continuation, and sandbox
  follow-up APIs. When a user resolves an input hint, the resumed run keeps the
  input audit in the selected snapshot while dashboard/workbench action counts
  clear.
- `GET /api/runs` and `GET /api/threads/{thread_id}/runs` can filter by run
  `status`, `skill_id`, summary `health`, `needs_attention`,
  `external_run_stale`, `sandbox_failed`, `sandbox_side_effects`,
  `needs_operator_action`, `sandbox_operator_action_kind`,
  `operator_follow_up`, `operator_follow_up_source_run_id`, and
  `operator_follow_up_action_kind` for dashboard retrieval. `needs_attention`
  is derived from summary `attention_reasons`, including health and sandbox
  diagnostic reasons.
- The same list endpoints can page with `limit` and `offset` and order by
  `started_at`, `completed_at`, `status`, summary `health`, or
  `sandbox_operator_action_count`.
- Passing `include_meta=true` changes those list responses to a page object with
  `items`, `total`, `count`, `limit`, `offset`, `order_by`, and
  `order_direction`, plus `sandbox_operator_action_counts`,
  `operator_follow_up_action_counts`, and
  `operator_follow_up_source_run_counts` for operator queues; default responses
  remain arrays for compatibility. OpenAPI declares the same query parameters
  and array-or-`RunListPage` response shape for both global and thread-scoped
  run list routes.
- Operator action follow-up APIs create explicit queued child runs from a
  selected sandbox operator action kind and record
  `harness_options.operator_follow_up` plus a source-run
  `operator_action.follow_up.created` event. They are control-plane creation
  APIs, not model-side tool execution. Operator follow-up lineage APIs project
  those events into source and child links for dashboards without persisting
  workflow branches.
- Workspace tools enforce skill path policy at execution time.
- Workspace patch tools return structured replacement and version metadata
  instead of giving models raw filesystem access. Workspace patch APIs expose
  the same Pydantic contract for UI/operator edits.
- Workspace upload APIs keep user-provided files in the versioned workspace
  under `/uploads/...` without granting models direct filesystem writes.
- Skill approval policy contributes execution-time approval requirements.
- Skill packages can be loaded from `SKILL.md` with enabled/disabled state,
  allowed tools, denied tools, and capability-style instruction injection.
- Default runtime includes a built-in `deep-research` skill unless a custom
  skill resolver is injected. It allows `research.create_plan`,
  `research.create_report`, and any currently configured controlled web tools.
- `examples/deep_research_agent.py` exercises the built-in `deep-research`
  skill end to end, creating runtime todos, a report artifact, events, and
  trace spans without requiring external web access.
- `examples/controlled_web_research_agent.py` exercises `deep-research` with
  opt-in controlled HTTP search/fetch against an allowlisted local provider, and
  emits `web.search.completed` / `web.fetch.completed` events, todo progress
  updates, and web trace spans.
- Runtime subagent delegation with parent/child run links, events, and trace spans.
- Model-facing `task(description, prompt, subagent_type)` tool with inline MVP
  child-run join and `waiting_subagent` parent status.
- Subagent delegation validates requested child skills and prevents child scope escalation beyond the parent run.
- Delegated child completion, failure, and cancellation are projected back to the parent run.
- Completed delegated child results expose structured text/artifact summaries on
  subagent run APIs, completion events, run-tree delegation entries, and trace
  span refs without making subagents into workflow graph branches.
- Run cancellation rejects terminal runs and preserves completed/failed audit state.
- Restricted local Python sandbox execution with stdout/stderr events, Pydantic
  execution summaries and run diagnostics, controlled workspace reads, declared
  workspace-file/artifact recovery, and trace spans.
- Per-run harness options for model selection, model-profile selection, model
  capabilities, cost policy, and additional run instructions.
- Organization-scoped model profile registry APIs under `/api/model-profiles`
  provide typed create/list/get/patch/enable/disable management for provider
  model ids, vision/thinking capability flags, required selection scopes, token
  ceilings, and cost policy. `POST /api/runs` resolves
  `harness_options.model_profile_key` through that registry before queuing.
  Non-default raw model overrides are rejected by the product API so runs
  cannot bypass profile policy. Research continuation and operator follow-up
  runs revalidate inherited profiles before creation.
- Pydantic AI prompt context with skill instructions, thread summaries, readable memory, and workspace file summaries.
- Pydantic AI harness driver with controlled tool bridge.
- Phase 1 `pydantic-ai-harness` compatibility probe covering the internal
  dependency import and Pydantic AI runtime APIs used by Aithru.
- Internal `aithru_agent.agent.capabilities` package with `AithruToolset` and
  `AithruBoundaryCapability` for Pydantic-native tool assembly behind the
  Aithru Capability Router.
- `AgentRuntime.build_agent()` assembles Aithru tools through the internal
  boundary capability instead of direct raw Pydantic function tools.
- Active run skills add `SkillInstructionCapability` while tool exposure remains
  constrained by the Aithru run context and capability router.
- Pydantic AI usage counts are emitted as debug `model.usage` events,
  projected into model trace spans, and rolled into run usage summaries with
  token and model-cost budget status when a profile supplies cost policy.
- Pydantic AI tools expose Aithru descriptor input schemas directly to the model.
- Approval pause/resume semantics for risky Pydantic AI tool calls, including model continuation after approved tools.
- Pydantic AI approval resume state is persisted on approval metadata for worker restart recovery.
- Optional external tool catalogs for `web.search`, `web.fetch`, and
  `mcp.<server>.<tool>` are Pydantic-validated and installed only when enabled
  through settings or injected providers. Settings-installed MCP catalogs use a
  safe unavailable executor by default, or an explicit controlled HTTP JSON
  executor when endpoint metadata and allowed hosts are configured.
- Injected Workflow capability providers expose Pydantic-validated
  `workflow_capability` tool descriptors and return `AgentExternalRunRef`
  metadata. The Pydantic AI bridge streams `external_run.created`,
  terminal `external_run.*`, running external-run pauses, and Workflow-owned
  `external_approval.requested` references when supplied by the provider.
- Settings-installed Workflow capability providers can use
  `http_json` execution with `AITHRU_AGENT_WORKFLOW_CAPABILITIES_JSON`,
  `AITHRU_AGENT_WORKFLOW_CAPABILITY_ENDPOINT_URL`, and explicit allowed hosts.
  Responses are validated as `WorkflowCapabilityResult`.
- `POST /api/runs/{run_id}/external-approval/resolve` resolves a
  Workflow-owned approval reference without touching `/api/approvals`.
- `POST /api/runs/{run_id}/external-run/resolve` resolves a provider-owned
  asynchronous CapabilityRun reference and requeues, fails, or cancels the Agent
  run around that external result. Completed results are also placed on the
  in-process worker queue so the next worker turn can consume the context packet.
  Duplicate terminal callbacks are accepted as idempotent responses without
  declaring a fresh requeue.

## External Tool Settings

External providers are disabled by default.

```bash
export AITHRU_AGENT_EXTERNAL_WEB_ENABLED=true
export AITHRU_AGENT_EXTERNAL_WEB_EXECUTOR=http
export AITHRU_AGENT_EXTERNAL_WEB_SEARCH_EXECUTOR=http_json
export AITHRU_AGENT_EXTERNAL_WEB_SEARCH_ENDPOINT_URL=https://search.example.com/api/search
export AITHRU_AGENT_EXTERNAL_WEB_ALLOWED_HOSTS=example.com,www.example.com
export AITHRU_AGENT_EXTERNAL_WEB_TIMEOUT_MS=5000
export AITHRU_AGENT_EXTERNAL_WEB_MAX_FETCH_BYTES=100000
export AITHRU_AGENT_EXTERNAL_MCP_EXECUTOR=http_json
export AITHRU_AGENT_EXTERNAL_MCP_ALLOWED_HOSTS=tools.example.com
export AITHRU_AGENT_EXTERNAL_MCP_TIMEOUT_MS=5000
export AITHRU_AGENT_EXTERNAL_MCP_MAX_RESPONSE_BYTES=100000
export AITHRU_AGENT_EXTERNAL_MCP_SERVERS_JSON='[
  {
    "key": "search",
    "metadata": {
      "endpoint_url": "https://tools.example.com/mcp/search"
    },
    "tools": [
      {
        "name": "query",
        "description": "Search documents.",
        "risk_level": "read",
        "approval_policy": "on_risk"
      }
    ]
  }
]'
```

The settings publish controlled tool descriptors through the Aithru Capability
Router. Real provider execution must still be wired through an executor; without
one, calls return a safe failed result rather than reaching the network or an
external service directly.

The built-in `http` web executor supports `web.fetch`. The built-in `http_json`
search executor calls a configured JSON endpoint for `web.search`; the endpoint
must return an object with a `results` array of `{ title, url, snippet?,
source?, published_at? }` entries. Both paths require explicit allowed hosts,
apply timeout and byte limits, and return redacted tool results.
Successful web calls emit lightweight `web.search.completed` and
`web.fetch.completed` stream events for timeline and trace projection. Failed
web calls emit `web.search.failed` or `web.fetch.failed` with the controlled
provider error, structured limitation, and matching query/URL reference. Fetch
events include metadata such as URL, status code, content length, and truncation
state, not the full fetched body. These Web failures are model-visible as
recoverable failure payloads; the generic `tool.failed` event is still emitted
for audit and trace projection.

The built-in `http_json` MCP executor posts a normalized `MCPToolInvocation` to
the configured server `metadata.endpoint_url` and validates the JSON response as
an `MCPToolResult`. It requires `AITHRU_AGENT_EXTERNAL_MCP_ALLOWED_HOSTS`, per
server endpoint metadata, timeout limits, and response byte limits. The MCP
catalog still only becomes callable after the normal capability router checks
tool scopes, skill allowlists, approval policy, audit metadata, and redaction.
