# Agent Chat Quiet Workbench Design

Date: 2026-06-24

## Goal

Refine the Aithru Agent chat surface so the center conversation remains the
primary work surface while execution state stays available through a quiet,
collapsible right companion.

This design is a refinement of the existing three-column Agent Chat Workbench
direction. It focuses only on the center conversation and the right run
companion. It does not introduce workflow graph editing, persisted workflow
definitions, workflow scheduling, Agent-owned graph semantics, or
plan-as-workflow behavior.

## Selected Direction

Use a **Quiet Chat Workbench**.

The user should feel like they are working in a capable chat product first, not
an operator console. The right side behaves like a status light and detail
drawer: always nearby, quiet by default, useful when opened.

Chosen decisions:

- Chat-first overall posture.
- Right companion collapsed by default.
- Right collapsed state shows only status icon, todo progress, and attention
  badge.
- Right companion never auto-expands for approvals, input requests, or failures.
- Center chat uses modern chat bubbles.
- Tool calls remain in the chat flow, but default to collapsed summary cards.
- Composer uses a natural input with one configuration summary chip.
- Expanded right companion keeps four core tabs: Activity, Files, Approvals,
  and Trace.

## Product Principles

- Conversation stays central. Normal use should happen in the chat flow.
- Execution is visible without being loud. The user should know when the agent
  is running, waiting, blocked, or done without reading raw events.
- Action points appear where the user is already looking. Input requests,
  approvals, failures, and result summaries must appear inline in the center
  chat.
- Detail lives on demand. Trace, raw payloads, capability audit details, and
  longer file/output inspection stay in the right companion.
- Layout stays stable. Headers, message rows, composer, collapsed rail, tabs,
  and cards should not resize erratically as runs stream.
- Capability governance remains visible but not noisy. Permission policy,
  approval state, risk, redaction, and traceability are shown in product terms.

## Scope

In scope:

- frontend UI design for the center chat surface;
- frontend UI design for the right run companion;
- message, tool, inline request, composer, and right-panel interaction rules;
- event projection rules from existing Agent Thread, Run, Message,
  AgentStreamEvent, Workspace, Artifact, Approval, and Trace concepts;
- documentation of the selected product behavior.

Out of scope:

- backend workflow semantics;
- Agent-owned workflow graph editing;
- new workflow scheduling behavior;
- persisted AgentPlan-as-workflow definitions;
- unrestricted local, browser, network, database, or credential access;
- replacing the existing capability router, approval, redaction, or trace
  boundaries;
- redesigning the left task inbox except where it affects center/right
  attention state.

## Current State

The frontend already has the main building blocks:

- `ConversationPage`
- `ConversationHeader`
- `RunGoalBar`
- `ChatPanel`
- `ChatComposer`
- `AgentActivityCard`
- `ToolCallCard`
- `InlineRequestCard`
- `RunCompanion`
- Activity, Files, Approvals, and Trace tabs

Current behavior is close to the P0 workbench direction, but the center and
right side are still a little more tool-surface-like than the chosen quiet chat
posture. The main refinement is to reduce default visual control density while
keeping action state obvious.

## Overall Layout

The shell remains three columns:

1. Left task inbox.
2. Center chat command surface.
3. Right run companion.

The center column is the primary stage. The right companion is collapsed by
default on desktop and hidden or drawer-like on narrow screens. Opening or
closing the right companion may change the available chat width, but it should
not change the conceptual structure of the center column.

## Center Chat Surface

### Message Style

Use modern chat bubbles:

- user messages align right in compact primary-colored bubbles;
- assistant messages align left in readable cards or low-contrast surfaces;
- markdown, code blocks, tables, links, and lists remain first-class;
- assistant streaming shows a small inline cursor or loading state;
- message actions stay visible on hover or focus and do not dominate the row.

The center chat should read like a conversation that can do work, not like a raw
execution log.

### Tool Call Cards

Tool calls appear inline in the chat, but default collapsed.

Each collapsed card should show:

- tool name in human-readable form;
- lifecycle status: proposed, running, completed, failed, denied, or waiting
  approval;
- risk or approval marker when relevant;
- short input/output summary after redaction;
- affordance to expand for a bounded detail preview;
- affordance to open the right companion for full trace or audit context.

The chat card must not expose unrestricted raw payloads, secrets, credentials,
or host paths. Full diagnostic detail belongs in the right Trace tab.

### Inline Action Cards

The center chat owns user action points.

Inline cards are required for:

- input requests;
- approval requests;
- external approval requests;
- failed run recovery;
- final artifact or output summary;
- continuation or retry prompts when available.

These cards should be visually stronger than ordinary tool summaries because
they define the next user action. They may link to the right companion, but the
user should be able to respond or decide from the center chat.

### Activity Summary

The chat may include one lightweight activity summary card for the active run.

It should show:

- current action or run state;
- todo progress when available;
- short status detail;
- token or usage summary only when useful.

It should not become a full timeline. The full activity narrative remains in
the right Activity tab.

### Empty State

The empty state should not become a marketing or instruction page. It should
provide a small set of task template chips that prefill the composer, such as:

- review code;
- plan a change;
- explain a file;
- inspect current run status.

## Composer

Use a natural composer with a configuration summary chip.

Default visible surface:

- multiline input;
- attach button;
- context button or chip;
- send button;
- stop button when a run is active;
- one compact configuration summary chip.

The summary chip should read like:

```txt
Auto / Default model / Ask approval
```

Clicking the summary chip expands detailed controls:

- Mode: Auto, Plan, Chat;
- Model profile;
- Skill;
- Permission policy.

The detailed row can collapse again after selection or when focus leaves the
composer. Permission policy must remain understandable in the collapsed summary.

Slash commands remain lightweight templates, not a separate command runtime:

- `/plan`
- `/status`
- `/retry`
- `/clear`

Prompt template chips appear only when the thread/input is empty enough for
them to help. They should disappear once the user starts composing.

## Right Companion

The right side is the Quiet Run Companion.

### Collapsed State

Collapsed width should be narrow and stable.

It shows only:

- status icon;
- todo progress, such as `2/5` or a small progress ring;
- attention badge count for pending input, approval, failure, or important
  output;
- expand affordance.

It does not show rotated status text. It does not auto-expand. It may use a
subtle highlight when attention exists.

### Expanded State

Expanded width should be stable and large enough for inspection without turning
the whole application into a console.

Header:

- `Run Companion`;
- current run status badge;
- collapse button.

Tabs:

- Activity;
- Files;
- Approvals;
- Trace.

Activity is the default tab. If the user manually opens Approvals or Trace, the
UI should honor that selection until they switch tabs or the active run changes.

### Activity Tab

Activity provides the everyday execution narrative.

It should show:

- current status;
- current action;
- status reason when available;
- todo progress;
- next useful action;
- lightweight timeline grouped around completed, current, waiting, failed, and
  next items;
- usage summary when available.

It must avoid raw event names as the primary copy.

### Files Tab

Files shows run outputs and workspace impact.

It should prioritize:

1. artifacts and final outputs;
2. files created or modified by the run;
3. other workspace files relevant to the run.

Rows should show file name, type, path, size when available, and preview or
download affordances when allowed. Full host filesystem access is not exposed.

### Approvals Tab

Approvals focuses on actionable approval state.

Pending approvals appear first. They show:

- requested action summary;
- risk/scope;
- redacted payload summary;
- approve and deny actions when the current actor can resolve them.

Resolved approval history is secondary and collapsed by default.

### Trace Tab

Trace is for debugging, audit, and failure diagnosis.

It may include:

- span tree;
- raw event stream;
- tool calls and outcomes;
- capability audit entries;
- model usage events;
- failure diagnostics.

Trace is not the normal comprehension layer and is never the default tab.

## Attention And Auto Behavior

The right companion does not auto-expand for:

- input requests;
- approval requests;
- external approval requests;
- run failures;
- completed outputs.

Instead:

- the center chat gets the inline action card;
- the collapsed right rail gets a badge or highlight;
- the header or goal bar may show state-specific actions;
- the user chooses whether to open the right companion.

This preserves chat-first focus while keeping details one click away.

## Event Projection

Existing backend concepts map directly to UI projections:

- Agent Thread maps to the conversation.
- Agent Run maps to the active execution instance.
- Agent Message maps to transcript entries.
- AgentStreamEvent maps to streaming messages, tool summaries, activity items,
  inline action cards, files, approvals, badges, usage, and trace.
- Workspace and Artifact map to Files tab rows and output summaries.
- Approval and input events map to inline action cards and Approvals tab rows.

Priority rules:

1. User action required: center inline card plus right badge.
2. Execution progress: chat activity summary plus right Activity timeline.
3. Tool visibility: collapsed chat card plus right Trace detail.
4. Result reuse: chat result summary plus right Files detail.
5. Audit/debug: right Trace only unless there is a user-facing failure.

## Responsive Behavior

Desktop:

- left inbox, center chat, and right collapsed rail can coexist;
- right expanded panel uses fixed responsive width;
- center chat maintains readable max line length.

Narrow screens:

- center chat remains primary;
- right companion is hidden behind a drawer or unavailable as a persistent
  column;
- attention appears through inline chat cards;
- composer controls collapse behind the summary chip and icon buttons.

## Stability Rules

- Header height is fixed.
- Composer height grows only to a bounded maximum, then scrolls internally.
- Right collapsed rail width is fixed.
- Right expanded tab list does not wrap.
- Long titles, tool names, file names, and model names truncate.
- Streaming auto-scroll only follows when the user is already at the bottom.
- If the user scrolls up, show a back-to-bottom button instead of forcing
  scroll.
- Cards use stable spacing so status changes do not shift the transcript
  dramatically.

## Security And Capability Boundaries

This UI does not grant real tool execution. It only displays, requests, reviews,
and routes user actions.

All real actions remain behind:

```txt
model / harness
  -> Aithru Tool Bridge
  -> Aithru Capability Router
  -> policy / scope / approval boundary
  -> concrete tool or controlled capability API
  -> event / trace / artifact / redaction
```

The UI must:

- show permission policy in user-readable language;
- preserve approval requirements for risky operations;
- display redacted summaries rather than raw sensitive payloads;
- avoid exposing tokens, credentials, secrets, or unrestricted host paths;
- keep trace and audit inspection available without making it the normal chat
  experience.

## Acceptance Criteria

- The default desktop view shows the center chat as the dominant surface.
- The right companion starts collapsed and does not auto-expand.
- The collapsed rail shows status icon, todo progress, and attention badge only.
- Tool calls appear in the chat as collapsed summary cards.
- Input, approval, failure, and result cards appear inline in the chat.
- Composer defaults to a natural input plus one configuration summary chip.
- Expanding the composer summary reveals Mode, Model, Skill, and Permission.
- Expanded right companion has exactly Activity, Files, Approvals, and Trace
  tabs.
- Trace is not the default tab.
- Sensitive tool inputs and outputs are summarized or redacted.
- No UI behavior implies Agent-owned workflow graph editing or persisted
  workflow definitions.
