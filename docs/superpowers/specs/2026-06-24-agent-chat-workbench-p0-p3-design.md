# Agent Chat Workbench P0-P3 Design

Date: 2026-06-24

## Goal

Define the final-state product direction for Aithru Agent Chat as a Codex-style
agent workbench, then slice that direction into P0-P3 product phases.

This is a design specification, not an implementation plan. It intentionally describes
the desired product shape before reducing scope for engineering execution.

The selected direction is **Aithru Agent Workbench**: borrow the strongest interaction
patterns from Codex-style agent chat, while making Aithru's own strengths first-class:
skills, tools, workspace files, controlled execution, approvals, artifacts, memory,
subagents, and traceable intelligent work.

This design keeps Aithru Agent as an AI harness. It does not introduce agent-owned
workflow graph editing, persisted workflow definitions, workflow scheduling semantics,
or drag-and-drop plan nodes.

## Reference Inspiration

Codex is useful as a benchmark because it treats chat as a command surface for real
tasks rather than as a message-only assistant. Relevant patterns include:

- command-oriented composer and slash commands;
- goals, plans, status, review, and task controls;
- thread search and task inbox behavior;
- visible execution through activity, terminal, browser, files, diffs, and artifacts;
- settings for models, skills, MCP tools, permissions, sandboxing, and approvals;
- background threads, worktrees, automations, and long-running task surfaces.

Aithru should not become a clone. The final product should feel familiar to Codex users,
but the product center of gravity is different: Aithru is a platform-hosted AI harness
with capability governance and traceability as core product features.

## Product Principles

### Chat Is The Command Surface

The central chat remains the primary interaction model. The user should be able to start
with natural language, add structured context when useful, and continue a task without
leaving the conversation.

### Execution Is Readable

The user should always understand what the agent is doing, what it has already done,
what it needs from the user, and what result it produced. Raw trace remains available,
but it is not the default comprehension layer.

### Results Are Inspectable

Completion is not only an assistant message. A completed run should expose changed files,
generated artifacts, verification output, and a result summary that can be reviewed and
used as context for the next turn.

### Capabilities Are Governed

Models may propose actions, but real actions pass through Aithru capability routing,
policy, scope, approval, redaction, and trace boundaries. The UI should make this visible
without overwhelming normal use.

### Power Is Progressive

The default view is calm and chat-first. Advanced surfaces such as raw events, tool
payloads, capability configuration, approval policy, and trace details are available on
demand.

### Layout Is Stable

The app should feel like a serious workbench. Headers, composer, inbox rows, companion
tabs, cards, and controls should have stable dimensions and should not resize erratically
as runs stream events.

## Final Information Architecture

The final shell keeps the three-column structure already established in the product:

1. **Task Inbox** on the left.
2. **Chat Command Surface** in the center.
3. **Execution Companion** on the right.

Settings and manager pages remain available as modal or side-panel surfaces rather than
replacing the core chat workspace.

### Left: Task Inbox

The left side is not only a conversation list. It is a task inbox.

Primary groups:

- Running
- Waiting for me
- Failed
- Recently completed
- Pinned
- Automations

Rows show:

- human task title;
- status label;
- attention reason;
- latest result or blocker;
- changed file or artifact count when available;
- relative activity time.

Thread IDs and run IDs may appear in secondary debug context, but never as the primary
task title when a readable title is available.

### Center: Chat Command Surface

The center is where the user starts, directs, and continues work.

Core regions:

- run context header;
- message transcript;
- inline activity cards;
- goal bar;
- command composer.

The composer supports natural language first, then structured controls:

- slash commands;
- mode;
- model;
- skill;
- permission policy;
- context references;
- attachments or workspace file references;
- stop, continue, retry, and send actions.

### Right: Execution Companion

The right side is the normal execution understanding surface.

Final tabs:

- Activity
- Plan
- Tools
- Approvals
- Files
- Changes
- Artifacts
- Output
- Trace

The default tab is Activity. Trace is for audit and debugging, not everyday run
understanding.

### Global Surfaces

Final product surfaces outside the three columns:

- command palette;
- global search;
- capability center;
- model settings;
- skill manager;
- MCP/tool manager;
- permission policy manager;
- automation manager;
- memory manager.

## P0: Chat Task Loop

### Objective

P0 makes chat a reliable task entrypoint. The user can start a task, see the active run
state, stop or continue it, recover from failure, and provide input or approval when
needed.

This phase is the minimum complete product loop.

### User Value

The user should never wonder:

- Did my task start?
- Is the agent running?
- What model, skill, or permission policy is active?
- Why did it stop?
- What can I do next?

### Required UI

Run context header:

- editable thread title;
- goal chip or goal row;
- run status chip;
- selected model;
- selected workspace;
- selected permission policy;
- state-specific primary action.

Composer:

- multiline input;
- mode selector: Auto, Plan, Chat;
- model selector;
- skill selector;
- permission selector;
- context chip area;
- slash command affordance;
- stop button when a run is active;
- send button.

Task inbox:

- clear states for Running, Awaiting input, Approval needed, Failed, Completed;
- attention markers for runs needing user action.

Execution companion:

- Activity as the default tab;
- current status;
- current step or status reason;
- next useful action;
- failure category when failed.

### P0 Slash Commands

P0 commands are lightweight command templates, not a full command runtime.

- `/plan`: ask the agent to plan before acting.
- `/status`: summarize the current run state.
- `/retry`: generate a retry prompt from the last failed run.
- `/clear`: clear the composer.

### P0 Context Chips

Initial chips:

- `@file`
- `Model`
- `Skill`
- `Permission`

The `@file` chip may begin as UI state if full file attachment support is not ready. The
design should still reserve the place where workspace references become first-class.

### P0 State Model

Final-state fields to support:

- `run.goal`
- `run.mode`
- `run.selected_model_profile`
- `run.selected_skill`
- `run.permission_policy`
- `run.recoverable_actions`
- `run.status_reason`
- `thread.attention_state`

P0 can initially infer some fields from existing run metadata, but the final contract
should make them explicit.

### P0 Error Handling

Failures are classified into:

- model configuration;
- permission or approval;
- capability or tool;
- runtime;
- unknown.

Each category maps to a recovery action:

- model configuration: open model settings;
- permission or approval: review approval or permission policy;
- capability or tool: open capability details;
- runtime: retry or inspect trace;
- unknown: retry and view trace.

### P0 Acceptance Criteria

- The user can create a task, select mode/model/skill/permission, and start a run.
- Running runs can be stopped.
- Failed runs provide a useful recovery action.
- Waiting input and waiting approval appear once and are easy to act on.
- Inbox, header, composer, and companion use the same status vocabulary.
- The UI does not expose secrets or raw backend metadata.
- No agent-owned workflow graph or workflow editor behavior is introduced.

## P1: Readable Execution

### Objective

P1 makes execution trustworthy. It turns raw event streams into product-readable process:
plan, progress, tools, approvals, errors, and result movement.

### User Value

The user should be able to answer:

- What is the agent's plan?
- Which step is active?
- Which tools did it use?
- Is it blocked?
- What approval does it need?
- Why did it fail?

### Required UI

Execution companion tabs become richer:

- Activity: everyday progress and current state.
- Plan: plan steps and todos.
- Tools: summarized tool calls.
- Approvals: pending and historical approvals.
- Trace: raw event and span diagnostics.

Chat transcript shows compact activity cards only for high-signal execution moments. The
right companion remains the detailed process view.

### Plan And Todo Projection

The UI needs a projection layer that can produce:

- plan steps;
- todos;
- current step;
- blocked step;
- completed step;
- failed step.

Step statuses:

- pending;
- running;
- completed;
- failed;
- blocked.

Plan and todo information may come from explicit backend fields, structured stream
events, or structured assistant output during earlier implementation phases. The
final-state contract should prefer explicit fields.

### Activity Timeline

Activity items use product language:

- `Read 3 files`
- `Searched workspace`
- `Requested approval`
- `Generated artifact`
- `Verification failed`
- `Run completed`

Low-value repetitions are collapsed. Tool payloads remain hidden unless expanded.

### Tool Call Summary

Each tool call card shows:

- tool name;
- purpose;
- status;
- duration;
- risk level;
- required scopes;
- summarized input;
- summarized output;
- link to raw trace when available.

The summary must use redacted input and output. Sensitive values are never displayed by
default.

### Approval Center

Pending approvals show:

- requested action;
- reason;
- risk level;
- scope;
- affected resource;
- approve action;
- deny action.

Resolved approvals remain available in collapsed history.

### P1 State Model

Final-state fields to support:

- `run.plan.steps[]`
- `run.todos[]`
- `run.current_step`
- `activity_items[]`
- `tool_call.summary`
- `tool_call.risk_level`
- `tool_call.required_scopes[]`
- `approval.request_reason`
- `event.product_kind`
- `event.redacted_input`
- `event.redacted_output`
- `run.error.category`
- `run.usage`

### P1 Acceptance Criteria

- A user can understand an active run without reading raw trace.
- Plan, current step, tool calls, approvals, and errors have distinct surfaces.
- Repeated stream events are collapsed into readable activity.
- Trace remains available for debugging.
- Tool details are redacted by default.
- All real actions continue through the capability router.

## P2: Workspace Outputs

### Objective

P2 makes results inspectable. A run's output becomes a set of reviewable files, changes,
artifacts, verification outputs, and summaries.

### User Value

The user should be able to answer:

- What changed?
- What files were read, created, modified, or deleted?
- What artifacts were produced?
- Did verification pass?
- Can I ask a follow-up about this file or artifact?

### Required UI

Execution companion adds or strengthens:

- Files tab;
- Changes tab;
- Artifacts tab;
- Output tab.

Completed runs show a result summary card in the chat transcript.

### Files Impact View

Files are categorized as:

- read;
- created;
- modified;
- deleted;
- generated;
- attached.

Each file row shows:

- path or display name;
- category;
- source event or tool call;
- associated artifact when relevant;
- open or preview action;
- copy path action;
- use as context action.

Artifact source files and workspace files must be deduplicated.

### Changes Review

Changed files show:

- file path;
- change kind;
- diff preview;
- source tool call or run step;
- review state.

The final-state design allows accept, revert, and stage-like actions, but those actions
must be routed through controlled capabilities. Early implementation may keep diff
review read-only.

### Artifact Preview

Artifacts show:

- name;
- type;
- preview kind;
- size;
- creation time;
- source run;
- source event;
- download or open action;
- use as context action.

Text, Markdown, JSON, and CSV can preview inline. Images, PDFs, documents, spreadsheets,
and presentations may use specialized previewers as capability support grows.

### Terminal And Verification Output

Verification output is summarized into:

- command summary;
- exit status;
- duration;
- stdout summary;
- stderr summary;
- full output link or expansion.

Large output is summarized by default.

### Result Summary

Completed runs produce a unified result summary:

- what was done;
- files changed;
- artifacts produced;
- verification status;
- follow-up suggestions.

Failed runs produce a failed summary:

- completed steps;
- failed step;
- error category;
- recovery actions.

### P2 State Model

Final-state fields to support:

- `workspace_file.kind`
- `workspace_file.source_event_id`
- `workspace_file.source_tool_call_id`
- `file_change.diff`
- `file_change.patch_id`
- `file_change.review_state`
- `artifact.preview_kind`
- `artifact.source_run_id`
- `artifact.source_event_id`
- `verification.command`
- `verification.exit_code`
- `verification.duration_ms`
- `verification.stdout_summary`
- `verification.stderr_summary`
- `run.result_summary`
- `run.changed_files_count`
- `run.artifacts_count`

### P2 Acceptance Criteria

- Completed runs expose changed files, artifacts, and verification status.
- File and artifact references can be added back into the composer as context.
- Large outputs do not overwhelm the default UI.
- Diff and file views do not bypass capability boundaries.
- Sensitive paths, secrets, and raw payloads remain redacted unless explicitly safe.

## P3: Capability And Multi-Task Workbench

### Objective

P3 turns Aithru Agent from a single-task chat product into a governed, multi-task,
platform-hosted agent workbench.

### User Value

The user should be able to answer:

- What capabilities does this agent have?
- Which tools are enabled or blocked?
- What needs configuration?
- Which tasks are running in the background?
- Which runs are waiting for me?
- Which automations exist?
- Which subagents are working?

### Capability Center

The capability center manages:

- models;
- skills;
- tools;
- MCP servers;
- memory;
- workspace access;
- permission policies;
- automations.

Each capability shows:

- status;
- configuration health;
- required scopes;
- last error;
- whether secrets are configured;
- whether user approval is required.

Secret values are never displayed in clear text.

### Permission Policy

Default policy options:

- Read-only;
- Ask before write;
- Auto safe actions;
- Manual approvals.

High-risk actions always require explicit approval, even under permissive policies.

Each run shows the selected policy and any policy-driven blocks.

### Skill Runtime Surface

Skills become first-class in the composer and execution companion.

Skill detail shows:

- description;
- suggested prompts;
- required tools;
- required scopes;
- active instructions;
- expected artifacts;
- capability health.

The run companion shows which skill influenced the active run.

### MCP And Tool Health

Tool and MCP views show:

- server connection status;
- tool count;
- enabled state;
- required configuration;
- recent errors;
- last health check;
- available scopes.

Tool failure cards link back to the relevant configuration surface.

### Multi-Task And Background Runs

The task inbox becomes a multi-task control surface.

It supports:

- parallel running runs;
- background runs;
- waiting-for-me grouping;
- failed grouping;
- completed grouping;
- pinned tasks;
- task search.

The user can leave a thread and return later without losing run context.

### Subagents

Subagents are shown as controlled run participants, not graph nodes.

Subagent rows show:

- name;
- goal;
- status;
- current step;
- result summary;
- parent run.

They remain harness runtime state and do not become workflow definitions.

### Automations

Automations create standard Agent Runs from time-based or event-based triggers.

Automation rows show:

- name;
- trigger;
- enabled state;
- next run time;
- last run status;
- owner;
- permission policy.

Automation runs are still traceable, auditable, and approval-bound.

### Global Command And Search

Command palette supports:

- new task;
- open settings;
- switch thread;
- open capability center;
- open automations;
- open recent artifact;
- search threads and run summaries.

Search covers:

- thread title;
- message content;
- run summary;
- artifact metadata;
- file paths;
- capability names.

### P3 State Model

Final-state fields to support:

- `capability.id`
- `capability.kind`
- `capability.status`
- `capability.required_scopes[]`
- `capability.health`
- `permission_policy.id`
- `permission_policy.rules[]`
- `run.allowed_capabilities[]`
- `run.approval_policy`
- `subagent_runs[]`
- `automation.spec`
- `automation.next_run_at`
- `automation.last_run_summary`
- `global_search.indexed_entities[]`

### P3 Acceptance Criteria

- Users can see and manage active capabilities without exposing secrets.
- Permission policy is visible at run time and enforced by capability routing.
- Multiple tasks can run or wait without confusing the user.
- Automations create auditable Agent Runs.
- Subagents are visible as runtime participants, not editable graph nodes.
- Capability, approval, memory, and workspace controls reinforce the AI harness model.

## Cross-Phase Data Flow

The final-state run flow is:

1. User enters natural language and optional structured context.
2. Composer serializes goal, mode, model, skill, permission policy, and context references.
3. Backend creates an Agent Run under an Agent Thread.
4. Worker executes through the harness driver.
5. Real actions route through the Aithru capability router.
6. Stream events are written to the canonical event log.
7. Projection layers derive activity, plan, tool calls, approvals, files, artifacts,
   output, trace, and summaries.
8. UI renders the same run state in inbox, header, chat, and companion.
9. User can stop, approve, deny, reply, retry, follow up, inspect, or use outputs as
   context.

## Frontend Architecture Direction

The current feature boundaries are compatible with this design.

Expected frontend areas:

- `features/sidebar`: Task Inbox projection and rendering.
- `features/conversation`: run context header and route composition.
- `features/chat`: transcript, composer, slash commands, message actions, inline cards.
- `features/inspection`: Execution Companion and run detail tabs.
- `features/admin` or `features/manager`: Capability Center, settings, skills, tools,
  models, memory, and automations.

Projection helpers should stay pure and unit-tested. They convert backend contracts into
stable view models before rendering.

## Backend Contract Direction

The backend should expose product-level run state without leaking harness implementation
details.

Preferred contracts:

- thread dashboard with attention state and output counts;
- run snapshot with goal, status reason, plan, current step, summaries, and usage;
- activity projection or event fields that allow frontend projection;
- tool call summaries with redaction;
- approval requests with risk and scope;
- workspace impact records;
- artifact preview metadata;
- verification output summaries;
- capability and permission policy descriptors.

Model-provider types must remain internal to the harness layer and should not become public
Aithru API contracts.

## Security And Governance

This design depends on strict boundaries:

- No raw secrets in metadata.
- No unrestricted local execution from model output.
- No direct tool execution from the frontend.
- Tool actions go through capability routing.
- Risk level and required scope are visible.
- Sensitive tool input and output are redacted by default.
- High-risk actions require explicit approval.
- Automations and subagents remain auditable through standard run records.

## Testing Strategy

Each phase should add tests at the projection and interaction layer before broad visual
polish.

Recommended tests:

- status and recovery-action projection;
- slash command parsing;
- composer harness option serialization;
- inbox grouping and search;
- activity timeline projection;
- plan/todo projection;
- tool call summary redaction;
- approval action rendering;
- file/artifact deduplication;
- diff and output summary projection;
- capability health projection;
- permission policy rendering;
- i18n key coverage;
- responsive smoke tests for desktop and narrow layouts.

Backend changes should include API tests and worker/stream projection tests. Meaningful
backend changes should continue to pass the repository verification commands documented
in `AGENTS.md`.

## Phase Summary

P0 makes chat reliably drive tasks.

P1 makes execution readable and trustworthy.

P2 makes outputs inspectable and reusable.

P3 makes the platform capabilities, permissions, subagents, automations, and parallel
tasks manageable.

The sequence matters. P0 establishes the task loop. P1 makes that loop understandable.
P2 closes the result review loop. P3 turns the product into a governed multi-task
workbench.
