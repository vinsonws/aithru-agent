# Agent Chat Productization Design

Date: 2026-06-23

## Goal

Productize the existing Aithru Agent Chat Command Center so it feels like a complete
Codex-style agent chat application rather than a functional harness shell.

This is a second-layer design on top of the existing three-column Command Center:

1. Conversation inbox on the left.
2. Chat transcript and command composer in the center.
3. Activity-first run companion on the right.

The layout direction is already chosen. This spec refines the visible product experience
across seven areas:

1. Conversation inbox.
2. Run context header.
3. Command composer.
4. Activity narrative.
5. Files and artifacts.
6. Message actions.
7. New chat empty state.

This work keeps Aithru Agent as an AI harness. It does not introduce workflow graph
editing, persisted workflow definitions, workflow scheduling, or agent-owned workflow
semantics.

## Selected Approach

Use the Codex-polished Command Center approach.

The app should stay calm and chat-first. It should not become an IDE command console or
an artifact-first workbench. Power features such as slash commands, file context, trace
inspection, and output review should exist as natural secondary surfaces around the chat.

## Product Principles

- Human language over backend labels: avoid showing raw `thread_13`, `idle`, or opaque
  event names as primary UI.
- Chat remains central: all productization should make the central conversation more
  useful, not bury it under debugging panels.
- Execution is readable: the user should understand what the agent is doing, what it
  changed, what it needs, and what it produced.
- Power on demand: advanced details such as trace events, raw tool payloads, and low-level
  file metadata remain accessible but not dominant.
- Stable dimensions: headers, composer, sidebar rows, tabs, cards, and controls should
  not resize unpredictably as content changes.
- Actionable failure states: failed runs should always offer the next useful action.

## Scope

In scope:

- frontend-only UI and projection improvements;
- humanized status labels;
- richer run activity projection;
- improved files/artifacts presentation using existing workspace/artifact APIs;
- message-level actions that are local or use existing run APIs;
- prompt-template empty state that pre-fills the composer;
- responsive behavior that keeps the chat usable on narrow screens.

Out of scope:

- backend workflow semantics;
- workflow graph editor;
- new workflow scheduler;
- drag-and-drop plan nodes;
- persisted AgentPlan-as-workflow definitions;
- unrestricted model tool execution;
- full mobile drawer implementation if the current UI library does not already provide the
  required drawer primitive.

## Current State

The current implementation already has:

- three-column desktop shell;
- `ConversationInbox`;
- `ConversationHeader`;
- `ChatComposer`;
- `AgentActivityCard`;
- `RunCompanion`;
- `ActivityTab`;
- `Files`, `Approvals`, and `Trace` tabs;
- responsive hiding of side panels on narrow screens.

Current rough edges:

- conversation rows still expose raw titles or fallback IDs too often;
- statuses still show backend labels such as `idle`;
- composer has compact selectors but not yet a command feeling;
- Activity is correct but too sparse for real agent work;
- Files tab reuses lower-level workspace/artifact surfaces instead of a productized output
  view;
- messages have no action affordances;
- new chat empty state does not yet guide the user into common agent tasks.

## Layer 1: Conversation Inbox

The left sidebar should feel like a conversation inbox, not a thread table.

### Layout

Top area:

- Aithru Agent identity.
- New chat button.
- Search conversations input.

Groups:

- Pinned.
- Today.
- Earlier.

Rows:

- generated or fallback title;
- human-readable status phrase;
- brief latest outcome or attention summary;
- relative timestamp;
- status marker.

### Title Rules

Use the first available value:

1. Explicit thread title.
2. Generated title from backend.
3. Latest user message summary.
4. `Untitled conversation`.

Do not show raw thread IDs as primary row titles unless no other signal exists in developer
or debug-only contexts.

### Status Copy

Map backend states to product language:

- `idle`: `Not started`;
- `queued`: `Queued`;
- `running`: `Running`;
- `waiting_input`: `Awaiting reply`;
- `waiting_approval`: `Approval needed`;
- `completed`: `Completed`;
- `failed`: `Failed`;
- `cancelled`: `Cancelled`.

When useful, append outcome context:

- `Completed · returned OK`;
- `Completed · 4 files changed`;
- `Approval needed · filesystem write`;
- `Failed · model configuration`.

### Search

Search filters locally over visible dashboard items by:

- title;
- latest status phrase;
- latest message or summary when available.

If backend search becomes available later, this UI can switch from local filtering to
server-backed filtering without changing the visual model.

## Layer 2: Run Context Header

The header should answer: what task is this, what run is active, what model is selected,
and what can I do next?

### Header Content

Left:

- editable thread title;
- subline with `Run <id> · Thread <id> · Mode`.

Right:

- status chip;
- model profile chip;
- state-specific action button.

### State-Specific Actions

Running:

- Stop.

Failed:

- Retry;
- View trace;
- Open model settings when the failure appears configuration-related.

Completed:

- New follow-up;
- Retry;
- Export or copy run summary when available.

Waiting input:

- Reply focus action that moves focus to the inline request or composer.

Waiting approval:

- Review approval action that opens the Approvals tab.

### Dimensions

Header height is fixed. Long titles truncate. Chips do not wrap into a second row on
desktop; lower-priority controls collapse into an overflow menu if needed.

## Layer 3: Command Composer

The composer should feel like the user's command surface for the agent.

### Default Surface

Visible controls:

- multiline input;
- mode segmented control: Auto, Plan, Chat;
- model chip;
- skill chip;
- `@ context` button;
- `/ commands` affordance;
- attach file button;
- stop button when a run is active;
- send button.

The input remains visually dominant. Mode, model, and skill controls stay compact.

### Placeholder

Use:

```txt
Ask Aithru to inspect, edit, plan, or explain...
```

Chinese:

```txt
让 Aithru 检查、修改、规划或解释...
```

### Slash Commands

The first implementation can support lightweight command templates without a full command
palette.

Commands:

- `/plan`: prefix the composer with planning language;
- `/fix`: prefix with debugging/fix language;
- `/explain`: prefix with explanation language;
- `/search`: prefix with research/search language.

Selecting a command inserts or transforms composer text. It does not need a backend API
change.

### Context Mentions

The `@ context` control opens a small menu with:

- workspace files when available;
- recent artifacts when available;
- current run;
- current thread.

If workspace files are unavailable, show a clear empty state instead of a disabled-looking
dead control.

### Attachment Preview

After selecting a local file, show a compact pending attachment chip. If upload is not yet
implemented end-to-end, label it as local context pending and avoid pretending it was
uploaded.

## Layer 4: Activity Narrative

The Activity tab is the everyday explanation of what the agent is doing.

### Summary Card

Show:

- run status;
- elapsed time when available;
- progress count when todos/steps exist;
- token usage;
- current step or final outcome.

### Timeline

Rows are grouped by status:

- Completed;
- Current;
- Waiting;
- Failed;
- Next.

Each row has:

- icon;
- title in human language;
- optional detail;
- optional source badge such as Tool, Model, File, Approval.

### Tool Summaries

Tool calls should be summarized in product language:

- `Read frontend/src/features/chat/ChatComposer.tsx`;
- `Updated model profile metadata`;
- `Created artifact report.md`;
- `Search failed: network timeout`.

Raw payloads stay in Trace.

### Waiting and Approval States

Waiting input:

- amber card;
- prompt text;
- Reply action.

Approval needed:

- amber card;
- requested action;
- risk/scope;
- Approve and Deny actions if the existing approval API supports it.

Failure:

- red card;
- short reason;
- View trace;
- Retry;
- Open relevant settings when detectable.

## Layer 5: Files and Artifacts

The Files tab should answer: what did the agent touch or produce?

### Tab Structure

Sections:

- Changed files;
- Read files;
- Artifacts.

### File Rows

Each row shows:

- filename;
- path;
- status: Modified, Created, Deleted, Read;
- optional one-line reason or source;
- actions: Open, Diff, Copy path.

If diff data is unavailable, show Open and Copy path only. Do not show disabled controls
without explaining why.

### Artifact Cards

Each artifact card shows:

- title;
- type;
- path or id;
- created time when available;
- actions: Open, Download, Copy path.

### Badges

The Files tab gets a badge when:

- changed files exist;
- artifacts exist;
- file-related tool calls completed.

## Layer 6: Message Actions

Messages should have useful actions without cluttering the transcript.

### Assistant Message Actions

Shown on hover and keyboard focus:

- Copy;
- Retry from here;
- Continue;
- View details.

### User Message Actions

Shown on hover and keyboard focus:

- Copy;
- Edit and rerun.

### Failure Message Actions

Failure cards show actions persistently:

- View trace;
- Retry;
- Open model settings when configuration-related;
- Copy error.

### Accessibility

Actions must be reachable by keyboard. Icon-only actions require accessible labels and
tooltips.

## Layer 7: New Chat Empty State

The new chat page should invite real tasks rather than showing a blank space.

### Layout

Center area:

- heading: `What should Aithru work on?`;
- short subtext;
- prompt template grid;
- composer below or integrated with templates.

### Prompt Templates

Templates:

- Inspect a file;
- Fix a bug;
- Plan an implementation;
- Configure a model;
- Search or research.

Each template fills the composer with editable text.

Examples:

- `Read @workspace/... and summarize the important points.`
- `Find why this run failed and propose a fix.`
- `Design and plan a UI improvement for ...`
- `Add a new model profile for ...`
- `Search for ... and summarize with sources.`

### Empty State Rules

Do not add marketing copy. The empty state is a working surface, not a landing page.

## Data Projection

Add or refine pure projection helpers rather than embedding business rules directly in
components.

Recommended helpers:

- `conversationInboxView.ts`: title, grouping, status copy, attention summaries.
- `runHeaderView.ts`: header chips and available actions.
- `runActivity.ts`: timeline and current step projection.
- `runFilesView.ts`: file/artifact grouping from workspace, artifact, and tool-call data.
- `messageActions.ts`: available actions per message/run state.
- `promptTemplates.ts`: template definitions and composer fill behavior.

These helpers should be testable without rendering React.

## Component Boundaries

Existing components stay, but get clearer responsibilities.

- `ConversationInbox`: list UI, search input, groups, row rendering.
- `ConversationHeader`: title, context chips, state-specific actions.
- `ChatPanel`: transcript layout and scroll behavior.
- `ChatMessage`: message bubble and message actions.
- `AgentActivityCard`: compact inline current activity summary.
- `ChatComposer`: command input, mode/model/skill/context controls.
- `RunCompanion`: right panel shell and tab badges.
- `ActivityTab`: run narrative.
- `RunFilesTab`: productized files/artifacts surface.
- `ApprovalsTab`: actionable approval review.
- `RunTab` or `TraceTab`: raw event/span debugging.
- `NewThreadPage`: prompt-template empty state.

Avoid turning `ChatPanel`, `ChatComposer`, or `RunCompanion` into large multipurpose
components. Move projection and formatting into helpers.

## Interaction Flow

New chat:

1. User chooses a template or types freely.
2. Composer updates with the selected prompt.
3. User chooses mode/model/skill if needed.
4. User sends.
5. Thread appears in inbox with `Queued` or `Running`.
6. Activity tab shows the run narrative.

Running run:

1. Header shows Running and Stop.
2. Transcript streams assistant text.
3. Inline activity summarizes current work.
4. Activity tab shows detailed progress.
5. Files tab badge appears when outputs exist.

Failure:

1. Transcript shows compact failure card.
2. Header shows Failed and Retry.
3. Activity tab shows failed step and reason.
4. Trace tab badge appears.

Completed run:

1. Header shows Completed and follow-up/retry actions.
2. Activity summary shows final outcome and usage.
3. Files tab shows changed files and artifacts.

## Responsive Behavior

Desktop:

- left inbox visible at `md` and above;
- right companion visible at `lg` and above;
- center chat always primary.

Narrow screens:

- side panels hide;
- chat and composer remain full width;
- inline activity cards carry the most important state;
- future drawer/bottom-sheet side panels can be added when a drawer primitive is adopted.

## Error Handling

Configuration errors:

- show concise failure reason;
- offer Open model settings when the error mentions model profile, API key, base URL, or
  provider.

Tool errors:

- show tool name and short failure reason;
- keep raw input/output in Trace.

File/artifact errors:

- show which output failed;
- show retry or copy diagnostic action where useful.

## Testing

Unit tests:

- status copy projection;
- inbox title fallback;
- inbox grouping;
- command template fill behavior;
- run header action projection;
- activity timeline grouping;
- file/artifact grouping;
- message action availability.

Render tests:

- inbox renders human titles/statuses;
- composer renders command controls and template-filled text;
- Activity tab renders waiting, failed, running, and completed states;
- Files tab renders changed files and artifacts;
- empty state template click fills composer.

Browser QA:

- desktop command center;
- narrow screen chat usability;
- new chat empty state;
- running run;
- waiting input;
- failed run;
- completed run with files/artifacts;
- message hover/focus actions.

## Implementation Notes

Prefer incremental commits by layer. The implementation should not require backend changes
unless an existing frontend type does not expose data already returned by the API.

If a design element depends on backend data that is not yet available, implement the
projection so it gracefully shows the best available state and hides unsupported actions.

## Acceptance Criteria

- No primary UI shows raw `idle` or raw thread IDs when a better label exists.
- New chat page offers task templates and fills the composer.
- Composer feels command-oriented and keeps input as the visual priority.
- Header exposes current run/model/status and useful actions.
- Activity tab narrates work in human language.
- Files tab shows outputs as product cards/rows.
- Messages expose copy/retry/continue/detail actions.
- Narrow screens keep chat usable without horizontal scrolling.
- Existing frontend tests and build pass.
- Backend tests remain unaffected.
