# Agent Chat Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize the existing Aithru Agent chat command center into a complete Codex-style agent chat surface with a human conversation inbox, run-aware header, command composer, readable activity narrative, useful files view, message actions, and a guided new-chat state.

**Architecture:** Keep the current three-column shell and add a small typed projection layer between backend contracts and UI components. Projection helpers convert run/thread/events/snapshot data into stable view models; React components render those view models with fixed dimensions and existing API boundaries. No backend workflow semantics or graph editing are introduced.

**Tech Stack:** React, TypeScript, Vite, TanStack Query, lucide-react, existing shadcn-style UI primitives, i18next JSON resources, Node `node:test` plus esbuild fixture tests, and browser verification through the local dev server.

---

## Current Context

The current implementation already has these surfaces:

- `frontend/src/AppShell.tsx` owns the shell, selected run, stream state, and inspection collapse state.
- `frontend/src/features/sidebar/Sidebar.tsx` renders the left rail and passes dashboard items to `ConversationInbox`.
- `frontend/src/features/sidebar/ConversationInbox.tsx` renders a basic pinned/recent list.
- `frontend/src/features/conversation/ConversationPage.tsx` composes the header, chat panel, and composer.
- `frontend/src/features/conversation/ConversationHeader.tsx` renders editable title, status, live marker, and model chip.
- `frontend/src/features/conversation/NewThreadPage.tsx` renders a centered new conversation form.
- `frontend/src/features/chat/ChatComposer.tsx` creates runs, selects mode/model/skill, and cancels active runs.
- `frontend/src/features/chat/ChatPanel.tsx` renders messages, inline requests, tool cards, and the compact activity card.
- `frontend/src/features/chat/runActivity.ts` projects stream state into simple activity summary and companion badges.
- `frontend/src/features/inspection/RunCompanion.tsx` renders Activity, Files, Approvals, and Trace tabs.
- `frontend/src/features/inspection/tabs/WorkspaceTab.tsx` and `ArtifactsTab.tsx` expose lower-level files and artifacts.

Backend contracts already available to the frontend:

- `/api/threads/dashboard` via `threadsApi.dashboard()`, including `summary`, `latest_run`, `needs_attention`, `attention_reasons`, and `action_hints`.
- `/api/threads/{thread_id}/runs` via `threadsApi.runs()`.
- `/api/runs/{run_id}` via `runsApi.get()`.
- `/api/runs/{run_id}/snapshot` via `runsApi.snapshot()`.
- `/api/runs/{run_id}/events` and `/stream` via `runsApi.events()` and `runsApi.stream()`.
- `/api/workspaces/{workspace_id}/files` via `workspacesApi.files()`.
- `/api/artifacts` via `artifactsApi.list()`.
- `/api/runs/{run_id}/operator-actions/follow-up` via `runsApi.operatorFollowUp()`.

This plan is intentionally frontend-first. If a task discovers a missing backend field, keep the UI graceful and record the missing field as follow-up; do not add new backend workflow concepts.

## Target File Structure

New files:

- `frontend/src/features/chat/runStatusCopy.ts`
- `frontend/src/features/chat/messageActions.ts`
- `frontend/src/features/chat/MessageActions.tsx`
- `frontend/src/features/chat/promptTemplates.ts`
- `frontend/src/features/sidebar/conversationInboxView.ts`
- `frontend/src/features/conversation/runHeaderView.ts`
- `frontend/src/features/inspection/runFilesView.ts`
- `frontend/src/features/inspection/tabs/RunFilesTab.tsx`
- `frontend/tests/run-status-copy.test.mjs`
- `frontend/tests/conversation-inbox-view.test.mjs`
- `frontend/tests/run-header-view.test.mjs`
- `frontend/tests/prompt-templates.test.mjs`
- `frontend/tests/message-actions.test.mjs`
- `frontend/tests/run-files-view.test.mjs`

Modified files:

- `frontend/src/AppShell.tsx`
- `frontend/src/features/sidebar/Sidebar.tsx`
- `frontend/src/features/sidebar/ConversationInbox.tsx`
- `frontend/src/features/conversation/ConversationPage.tsx`
- `frontend/src/features/conversation/ConversationHeader.tsx`
- `frontend/src/features/conversation/NewThreadPage.tsx`
- `frontend/src/features/chat/ChatComposer.tsx`
- `frontend/src/features/chat/ChatPanel.tsx`
- `frontend/src/features/chat/AgentActivityCard.tsx`
- `frontend/src/features/chat/runActivity.ts`
- `frontend/src/features/inspection/InspectionPanel.tsx`
- `frontend/src/features/inspection/RunCompanion.tsx`
- `frontend/src/i18n/resources/en/chat.json`
- `frontend/src/i18n/resources/zh/chat.json`
- `frontend/tests/conversation-inbox.test.mjs`
- `frontend/tests/run-activity.test.mjs`
- `frontend/tests/i18n-runtime-sync.test.mjs` if the existing sync test requires fixture changes

## Design Guardrails

- Keep Aithru Agent as an AI harness. Do not add workflow graph editing, workflow schedulers, or persisted AgentPlan-as-workflow semantics.
- Keep real actions behind existing APIs. Frontend actions may call `runsApi.cancel`, `runsApi.operatorFollowUp`, `runsApi.snapshot`, `workspacesApi.files`, and `artifactsApi.list`.
- Do not expose raw secret values. Do not render model API keys or raw metadata that may include secrets.
- Prefer human labels over backend IDs in primary UI. IDs may appear in subdued secondary context only.
- Avoid fake affordances. Do not show pinned groups unless data carries a pin signal. Retry must either call an existing run action or prefill the composer with an explicit retry prompt.
- Keep desktop dimensions stable. Header height, composer frame, companion width, sidebar rows, tabs, and buttons must not resize when content changes.
- Keep narrow screens usable. At mobile widths, side panels remain hidden and the central chat/composer must not overflow horizontally.

## Task 1: Add Run Status Product Copy

This task creates a shared status and run-context projection helper so inbox, header, activity, and message actions use the same product language.

- [ ] Add `frontend/tests/run-status-copy.test.mjs`.

  Test cases:

  - `humanizeRunStatus("idle")` returns fallback `Not started`, tone `muted`, and i18n key `chat:status.notStarted`.
  - `humanizeRunStatus("running")` returns fallback `Running`, tone `live`, and primary action kind `stop`.
  - `humanizeRunStatus("waiting_input")` returns fallback `Awaiting reply` and primary action kind `reply`.
  - `humanizeRunStatus("waiting_approval")` returns fallback `Approval needed` and primary action kind `reviewApproval`.
  - `humanizeRunStatus("failed", { error: "model profile metadata cannot include secret values" })` returns failure category `modelConfiguration` and primary action kind `openModelSettings`.
  - `formatShortRunId("run_123456789")` returns `run_1234`.
  - `formatRunSubline({ runId: "run_123456789", threadId: "thread_abcdef", mode: "Auto" })` includes short run id, short thread id, and mode.

- [ ] Add `frontend/src/features/chat/runStatusCopy.ts`.

  Export these types and functions:

  ```ts
  import type { AgentRunStatus } from "@/lib/api";

  export type ProductStatusTone =
    | "muted"
    | "queued"
    | "live"
    | "waiting"
    | "success"
    | "danger"
    | "cancelled";

  export type ProductActionKind =
    | "stop"
    | "reply"
    | "reviewApproval"
    | "retry"
    | "viewTrace"
    | "openModelSettings"
    | "newFollowUp";

  export type ProductFailureCategory =
    | "modelConfiguration"
    | "approval"
    | "capability"
    | "unknown";

  export interface ProductRunStatusCopy {
    status: AgentRunStatus | "idle";
    labelKey: string;
    fallback: string;
    tone: ProductStatusTone;
    primaryAction?: ProductActionKind;
    failureCategory?: ProductFailureCategory;
  }
  ```

  Implement:

  - `humanizeRunStatus(status?: AgentRunStatus | "idle" | null, options?: { error?: string | null }): ProductRunStatusCopy`
  - `formatShortRunId(id?: string | null): string`
  - `formatRunSubline(input: { runId?: string | null; threadId?: string | null; mode?: string | null }): string`
  - `classifyRunFailure(error?: string | null): ProductFailureCategory`
  - `isTerminalRunStatus(status?: AgentRunStatus | "idle" | null): boolean`
  - `isActiveRunStatus(status?: AgentRunStatus | "idle" | null): boolean`

  Mapping:

  - `idle` -> `Not started`, `muted`
  - `queued` -> `Queued`, `queued`
  - `running` -> `Running`, `live`, `stop`
  - `waiting_input` -> `Awaiting reply`, `waiting`, `reply`
  - `waiting_approval` -> `Approval needed`, `waiting`, `reviewApproval`
  - `waiting_external_approval` -> `External approval`, `waiting`, `reviewApproval`
  - `waiting_external_run` -> `Waiting on external run`, `waiting`
  - `paused` -> `Paused`, `waiting`, `reply`
  - `completed` -> `Completed`, `success`, `newFollowUp`
  - `failed` -> `Failed`, `danger`, `retry` unless failure category is `modelConfiguration`
  - `cancelled` -> `Cancelled`, `cancelled`, `retry`

  Failure classification:

  - Includes `model profile`, `api key`, `metadata cannot include secret`, `base_url`, `provider`, or `model configuration` -> `modelConfiguration`
  - Includes `approval`, `denied`, or `permission` -> `approval`
  - Includes `tool`, `capability`, `workspace`, or `sandbox` -> `capability`
  - Otherwise -> `unknown`

- [ ] Add i18n keys to both `frontend/src/i18n/resources/en/chat.json` and `frontend/src/i18n/resources/zh/chat.json`.

  Required key paths:

  - `status.notStarted`
  - `status.queued`
  - `status.running`
  - `status.awaitingReply`
  - `status.approvalNeeded`
  - `status.externalApproval`
  - `status.waitingExternalRun`
  - `status.paused`
  - `status.completed`
  - `status.failed`
  - `status.cancelled`
  - `actions.stop`
  - `actions.reply`
  - `actions.reviewApproval`
  - `actions.retry`
  - `actions.viewTrace`
  - `actions.openModelSettings`
  - `actions.newFollowUp`

- [ ] Run:

  ```bash
  cd frontend
  npm test -- run-status-copy
  ```

  Expected output includes one passing test file and no assertion failures.

- [ ] Commit:

  ```bash
  git add frontend/src/features/chat/runStatusCopy.ts frontend/tests/run-status-copy.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: add product run status copy"
  ```

## Task 2: Add Conversation Inbox View Projection

This task converts dashboard items into stable row and group view models before touching UI.

- [ ] Add `frontend/tests/conversation-inbox-view.test.mjs`.

  Test cases:

  - Explicit thread title wins over generated fallbacks.
  - Missing title falls back to `summary.latest_message.content_preview`.
  - If no message preview exists, fallback uses latest run goal.
  - If no readable title source exists, fallback is `Untitled conversation`.
  - `needs_attention` items are grouped before normal items.
  - Items with current-day `last_activity_at` are grouped under `today`.
  - Older items are grouped under `earlier`.
  - Search filters by title, status label, subtitle, and action hint label.
  - Raw `thread_` IDs are not used as primary titles when any readable signal exists.

- [ ] Add `frontend/src/features/sidebar/conversationInboxView.ts`.

  Export:

  ```ts
  import type { AgentThreadDashboardItem } from "@/lib/api";
  import type { ProductRunStatusCopy } from "@/features/chat/runStatusCopy";

  export interface ConversationInboxRowView {
    id: string;
    href: string;
    title: string;
    subtitle: string;
    status: ProductRunStatusCopy;
    statusDetail?: string;
    timestamp?: string | null;
    needsAttention: boolean;
    highPriorityActionCount: number;
    actionLabel?: string;
    actionReason?: string;
    activePath: string;
    active: boolean;
  }

  export interface ConversationInboxGroupView {
    id: "pinned" | "attention" | "today" | "earlier";
    labelKey: string;
    fallback: string;
    rows: ConversationInboxRowView[];
  }
  ```

  Implement:

  - `buildConversationInboxGroups(items, options)` where `options` includes `activePath`, `query`, and `now`.
  - `buildConversationInboxRow(item, options)` for unit testing individual row behavior.
  - `getReadableThreadTitle(item)` with the fallback chain from the spec.
  - `getLatestRunStatus(item)` that handles both current loose UI shape and OpenAPI shape:
    - `item.latest_run.status`
    - `item.latest_run.run.status`
    - `item.summary.latest_run.status`
    - fallback `idle`
  - `getLatestRunGoal(item)` from:
    - `item.latest_run.run.goal`
    - `item.latest_run.goal`
    - `item.summary.latest_run.goal`
  - `getInboxSubtitle(item)` from first high-priority action reason, latest message preview, latest run goal, or an empty string.
  - `matchesConversationQuery(row, query)`.

  Grouping rules:

  - Use `attention` for rows where `needsAttention` is true or `highPriorityActionCount > 0`.
  - Use `pinned` only if the item has a boolean `pinned` field set to true. This field is not in the current generated type, so read it through a narrow optional cast.
  - Use `today` when `last_activity_at` is on the same local date as `options.now`.
  - Use `earlier` for the remaining rows.
  - Omit empty groups.

- [ ] Reuse `humanizeRunStatus` from Task 1 for row status.

- [ ] Run:

  ```bash
  cd frontend
  npm test -- conversation-inbox-view
  ```

  Expected output includes all projection tests passing.

- [ ] Commit:

  ```bash
  git add frontend/src/features/sidebar/conversationInboxView.ts frontend/tests/conversation-inbox-view.test.mjs
  git commit -m "feat: add conversation inbox projection"
  ```

## Task 3: Productize Sidebar Conversation Inbox UI

This task replaces the temporary pinned/recent UI with the projection from Task 2.

- [ ] Modify `frontend/src/features/sidebar/ConversationInbox.tsx`.

  Required changes:

  - Accept `query`, `onQueryChange`, and `groups` or build groups internally from `items`.
  - Render a search input at the top of the inbox list.
  - Render projected group labels from `ConversationInboxGroupView`.
  - Render rows with:
    - title line;
    - status phrase and optional action label;
    - subtitle line when available;
    - timestamp;
    - attention marker for attention rows;
    - running spinner for live rows;
    - success, warning, danger, and cancelled icon tones from `status.tone`.
  - Use `href` from the row view.
  - Keep row height stable with `min-h-[68px]` and truncate long text.
  - Use `title` attributes for truncated title and subtitle.

- [ ] Modify `frontend/src/features/sidebar/Sidebar.tsx`.

  Required changes:

  - Add `const [conversationQuery, setConversationQuery] = React.useState("")`.
  - Pass `conversationQuery` and `setConversationQuery` to `ConversationInbox`.
  - Change the expanded title from generic thread copy to `Aithru Agent` or the existing product name if another top-level label already exists in common translations.
  - Keep manager links at the bottom.
  - Keep collapsed sidebar behavior unchanged.

- [ ] Add i18n keys to `en/chat.json` and `zh/chat.json`.

  Required key paths:

  - `inbox.searchPlaceholder`
  - `inbox.groups.pinned`
  - `inbox.groups.attention`
  - `inbox.groups.today`
  - `inbox.groups.earlier`
  - `inbox.untitled`
  - `inbox.noMatches`
  - `inbox.noConversations`

- [ ] Update `frontend/tests/conversation-inbox.test.mjs`.

  Assertions:

  - Search input is rendered.
  - Attention group appears when one row needs attention.
  - Today group appears for current-day rows.
  - Raw `waiting_input` does not appear in rendered HTML; `Awaiting reply` or the localized fallback appears instead.
  - Thread IDs are not rendered as row titles when title/message/goal data exists.

- [ ] Run:

  ```bash
  cd frontend
  npm test -- conversation-inbox
  npm test -- conversation-inbox-view
  ```

  Expected output includes both test files passing.

- [ ] Commit:

  ```bash
  git add frontend/src/features/sidebar/ConversationInbox.tsx frontend/src/features/sidebar/Sidebar.tsx frontend/tests/conversation-inbox.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: productize conversation inbox"
  ```

## Task 4: Productize Run Context Header

This task turns the header into a run-aware control strip with stable actions.

- [ ] Add `frontend/tests/run-header-view.test.mjs`.

  Test cases:

  - Running run exposes `stop`.
  - Waiting input run exposes `reply`.
  - Waiting approval run exposes `reviewApproval`.
  - Failed model-configuration run exposes `openModelSettings` and `viewTrace`.
  - Failed non-configuration run exposes `retry` and `viewTrace`.
  - Completed run exposes `newFollowUp` and `retry`.
  - Subline includes short run id, short thread id, and mode label when present.
  - Model label uses `harness_options.model_profile_key`, then `harness_options.model`, then `Default model`.

- [ ] Add `frontend/src/features/conversation/runHeaderView.ts`.

  Export:

  ```ts
  import type { AgentRun, AgentRunStatus, AgentThread } from "@/lib/api";
  import type { ProductActionKind, ProductRunStatusCopy } from "@/features/chat/runStatusCopy";

  export interface RunHeaderActionView {
    kind: ProductActionKind;
    labelKey: string;
    fallback: string;
    disabled?: boolean;
  }

  export interface RunHeaderView {
    title: string;
    fallbackTitle: string;
    status: ProductRunStatusCopy;
    subline: string;
    modelLabel: string;
    actions: RunHeaderActionView[];
  }
  ```

  Implement:

  - `buildRunHeaderView(input)` where input includes `thread`, `activeRun`, `streamStatus`, `streamError`, `threadId`, and `modeLabel`.
  - Use `humanizeRunStatus` from Task 1.
  - Include at most three visible actions in deterministic order:
    - active stop/reply/review first;
    - failure recovery second;
    - trace third for failed runs;
    - follow-up before retry for completed runs.
  - Return `Default model` fallback when no model is selected.

- [ ] Modify `frontend/src/AppShell.tsx`.

  Required changes:

  - Add inspection tab state:

    ```ts
    const [inspectionTab, setInspectionTab] = useLocalStorage(
      "aithru-agent:inspection-tab",
      "activity",
    );
    ```

  - Pass `inspectionTab` and `setInspectionTab` through `InspectionConnector` into `InspectionPanel`.
  - Pass `onSelectInspectionTab` into `ConversationRoute` and `ConversationPage`.

- [ ] Modify `frontend/src/features/inspection/InspectionPanel.tsx` and `RunCompanion.tsx`.

  Required changes:

  - Accept `activeTab` and `onTabChange`.
  - Change `Tabs` from `defaultValue` to controlled `value` and `onValueChange`.
  - If approvals appear while the selected tab is not set by a user action during the same render cycle, it is acceptable to keep the current tab; do not force tab jumps after this change.

- [ ] Modify `frontend/src/features/conversation/ConversationPage.tsx`.

  Required changes:

  - Add local state for composer draft and focus sequence:

    ```ts
    const [composerDraft, setComposerDraft] = React.useState("");
    const [composerFocusKey, setComposerFocusKey] = React.useState(0);
    ```

  - Move cancel mutation from `ChatComposer` into the page or pass an `onCancelRun` callback down to the composer.
  - Build `headerView` with `buildRunHeaderView`.
  - Handle header actions:
    - `stop`: call `runsApi.cancel(activeRunId)`.
    - `reply`: focus the composer or first inline input by incrementing `composerFocusKey`.
    - `reviewApproval`: call `onSelectInspectionTab("approvals")`.
    - `viewTrace`: call `onSelectInspectionTab("trace")`.
    - `openModelSettings`: call `useManager().open("settings")`.
    - `newFollowUp`: prefill composer with `Follow up on this run: ` and focus it.
    - `retry`: prefill composer with `Retry this task: ${activeRun.goal}` when `activeRun.goal` exists, otherwise `Retry the last task with the same intent.`; focus it.

- [ ] Modify `frontend/src/features/conversation/ConversationHeader.tsx`.

  Required changes:

  - Accept `view: RunHeaderView` or equivalent explicit props.
  - Render title and subline in a fixed-height header.
  - Render human status label instead of raw backend status.
  - Render model chip as a subdued chip.
  - Render action buttons with icons from lucide-react:
    - `Square` for stop
    - `MessageSquare` for reply
    - `ShieldCheck` for review approval
    - `RotateCcw` for retry
    - `GitBranch` for trace
    - `Settings` for model settings
    - `Plus` for follow-up
  - Put lower-priority actions into compact ghost buttons if horizontal space is tight.
  - Do not wrap the header onto a second row on desktop.

- [ ] Modify `frontend/src/features/chat/ChatComposer.tsx`.

  Required changes:

  - Accept `draft`, `onDraftChange`, `focusKey`, and `onCancelRun`.
  - Remove internal `goal` state or keep it only as a fallback when controlled props are not provided.
  - Focus the textarea whenever `focusKey` changes.
  - Keep Enter-to-send behavior unchanged.

- [ ] Run:

  ```bash
  cd frontend
  npm test -- run-header-view
  npm run build
  ```

  Expected output: header projection tests pass and the TypeScript build succeeds.

- [ ] Commit:

  ```bash
  git add frontend/src/AppShell.tsx frontend/src/features/inspection/InspectionPanel.tsx frontend/src/features/inspection/RunCompanion.tsx frontend/src/features/conversation/runHeaderView.ts frontend/src/features/conversation/ConversationPage.tsx frontend/src/features/conversation/ConversationHeader.tsx frontend/src/features/chat/ChatComposer.tsx frontend/tests/run-header-view.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: productize run context header"
  ```

## Task 5: Add Prompt Templates and Command Composer Polish

This task makes the composer and new-chat state feel like an agent command surface.

- [ ] Add `frontend/tests/prompt-templates.test.mjs`.

  Test cases:

  - `getPromptTemplates()` returns stable IDs.
  - Each template has `titleKey`, `fallbackTitle`, `prompt`, and `mode`.
  - Templates cover at least: build or change code, investigate failure, summarize files, plan work, and research question.
  - Applying a template returns its prompt without mutating the template list.

- [ ] Add `frontend/src/features/chat/promptTemplates.ts`.

  Export:

  ```ts
  export type PromptTemplateMode = "auto" | "plan" | "chat";

  export interface PromptTemplate {
    id: "build" | "debug" | "summarize" | "plan" | "research";
    titleKey: string;
    fallbackTitle: string;
    descriptionKey: string;
    fallbackDescription: string;
    prompt: string;
    mode: PromptTemplateMode;
  }
  ```

  Include these prompts:

  - `build`: `Change the current project so that...`
  - `debug`: `Investigate this failure, identify the root cause, and make the smallest safe fix:`
  - `summarize`: `Read the relevant files and summarize what matters for:`
  - `plan`: `Design an implementation plan for:`
  - `research`: `Research this question, cite the evidence you used, and produce a concise answer:`

- [ ] Modify `frontend/src/features/chat/ChatComposer.tsx`.

  Required changes:

  - Rename the visible surface from simple input to command composer through styling, not explanatory text.
  - Add a small template strip above or inside the composer toolbar when the draft is empty.
  - Clicking a template fills the draft and sets mode to the template mode.
  - Keep model and skill selectors compact.
  - Add stable layout constraints:
    - composer outer max width stays `max-w-3xl`;
    - textarea min height stays at least `64px`;
    - toolbar controls do not shift send/cancel buttons.
  - Keep file attachment button present but disabled or no-op if backend upload flow is not wired in this surface. Use a tooltip/title that says `Attach file`.

- [ ] Modify `frontend/src/features/conversation/NewThreadPage.tsx`.

  Required changes:

  - Replace the centered generic empty state with a first-screen new-chat command state.
  - Use template cards from `promptTemplates.ts`.
  - Clicking a template fills the textarea and mode.
  - Keep creating a thread and run through existing `threadsApi.create` and `runsApi.create`.
  - Include model profile and skill selectors only if they can be wired to the create-run body consistently. If they are not wired in this task, leave them out of the new-chat form and keep them in the in-thread composer.
  - Keep the page usable at `390px` width with no horizontal scroll.

- [ ] Add i18n keys to `en/chat.json` and `zh/chat.json`.

  Required key paths:

  - `templates.build.title`
  - `templates.build.description`
  - `templates.debug.title`
  - `templates.debug.description`
  - `templates.summarize.title`
  - `templates.summarize.description`
  - `templates.plan.title`
  - `templates.plan.description`
  - `templates.research.title`
  - `templates.research.description`
  - `newChat.subtitle`
  - `newChat.startButton`

- [ ] Run:

  ```bash
  cd frontend
  npm test -- prompt-templates
  npm run build
  ```

  Expected output: prompt template tests pass and the build succeeds.

- [ ] Commit:

  ```bash
  git add frontend/src/features/chat/promptTemplates.ts frontend/src/features/chat/ChatComposer.tsx frontend/src/features/conversation/NewThreadPage.tsx frontend/tests/prompt-templates.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: add agent prompt templates"
  ```

## Task 6: Enrich Activity Narrative

This task makes execution readable without requiring the user to inspect raw event streams.

- [ ] Extend `frontend/tests/run-activity.test.mjs`.

  Add test cases:

  - Running with no todos returns narrative `Agent is working`.
  - Waiting input returns next action `Reply to continue`.
  - Waiting approval returns next action `Review approval`.
  - Completed with artifacts and file-looking tool outputs increments file badge.
  - Failed tool appears in activity items before passive completed tools.
  - Token usage label still formats as `125 tokens`.

- [ ] Modify `frontend/src/features/chat/runActivity.ts`.

  Extend `RunActivitySummary`:

  ```ts
  export interface RunActivitySummary {
    status: RunStreamState["status"];
    progress: { done: number; total: number };
    current: RunActivityItem | null;
    items: RunActivityItem[];
    usageLabel: string | null;
    narrative: {
      title: string;
      detail?: string;
      nextAction?: "reply" | "reviewApproval" | "inspectTrace" | "none";
    };
    toolCounts: {
      completed: number;
      failed: number;
      running: number;
    };
  }
  ```

  Required behavior:

  - Preserve existing public exports so current tests still pass.
  - Keep todos as the primary timeline when present.
  - Promote inline requests and failed tools above passive completed tools.
  - Add completed tool summary rows only when there are no todos and no inline requests.
  - Use human names for tool status details.
  - Keep `buildRunCompanionBadges` deterministic and based only on stream state.

- [ ] Modify `frontend/src/features/inspection/tabs/ActivityTab.tsx`.

  Required UI:

  - Top narrative block with current status title, detail, and next action.
  - Progress indicator when todos exist.
  - Timeline list with stable row heights and status icons.
  - Empty state remains `No run activity yet`.
  - Do not render raw event type strings as primary labels.

- [ ] Modify `frontend/src/features/chat/AgentActivityCard.tsx`.

  Required UI:

  - Use `summary.narrative.title` and `summary.current`.
  - Show progress when todos exist.
  - Show token usage only as a subdued secondary pill.
  - Keep it compact enough for the central transcript.

- [ ] Add any missing i18n keys used by Activity UI.

- [ ] Run:

  ```bash
  cd frontend
  npm test -- run-activity
  npm run build
  ```

  Expected output: activity tests pass and the build succeeds.

- [ ] Commit:

  ```bash
  git add frontend/src/features/chat/runActivity.ts frontend/src/features/inspection/tabs/ActivityTab.tsx frontend/src/features/chat/AgentActivityCard.tsx frontend/tests/run-activity.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: enrich run activity narrative"
  ```

## Task 7: Productize Files and Artifacts Tab

This task replaces the stacked lower-level workspace/artifact lists with one output-oriented tab.

- [ ] Add `frontend/tests/run-files-view.test.mjs`.

  Test cases:

  - Artifacts are listed before workspace files.
  - Workspace files with the same path as an artifact source are not duplicated when a stable artifact name exists.
  - File type labels are inferred from media type and extension.
  - Empty snapshot returns an empty-state view.
  - Image files receive image type.
  - Markdown, JSON, TypeScript, Python, and plain text receive readable type labels.

- [ ] Add `frontend/src/features/inspection/runFilesView.ts`.

  Export:

  ```ts
  import type { AgentArtifact, AgentWorkspaceFile } from "@/lib/api";
  import type { RunSnapshot } from "@/lib/api/runs";

  export type RunFileKind = "artifact" | "workspace_file";

  export interface RunFileView {
    id: string;
    kind: RunFileKind;
    name: string;
    path?: string;
    typeLabel: string;
    sizeLabel?: string;
    createdAt?: string | null;
    href?: string;
    canDownload: boolean;
    canPreview: boolean;
  }
  ```

  Implement:

  - `buildRunFileViews(input: { snapshot?: RunSnapshot | null; workspaceFiles?: AgentWorkspaceFile[]; artifacts?: AgentArtifact[] }): RunFileView[]`
  - `inferFileTypeLabel(input: { name?: string | null; path?: string | null; mediaType?: string | null; artifactType?: string | null }): string`
  - `formatFileSize(bytes?: number | null): string | undefined`

  Ordering:

  - finalized artifacts first when `finalized` exists;
  - remaining artifacts;
  - workspace files by path.

  Links:

  - artifact content: `/api/artifacts/${artifact.id}/content`
  - workspace file preview should use existing workspace APIs only when the component can call them safely. The view helper can leave `href` undefined for workspace files.

- [ ] Add `frontend/src/features/inspection/tabs/RunFilesTab.tsx`.

  Required behavior:

  - Fetch `runsApi.snapshot(runId)` when `runId` exists.
  - Fetch `workspacesApi.files(workspaceId)` when `workspaceId` exists and snapshot does not include workspace files.
  - Use `buildRunFileViews`.
  - Render one list with sections:
    - `Outputs` for artifacts;
    - `Workspace files` for workspace files.
  - Render refresh button that refetches both queries.
  - Render empty state when no outputs/files exist.
  - Use existing `LoadingState`, `EmptyState`, and `ErrorState`.

- [ ] Modify `frontend/src/features/inspection/RunCompanion.tsx`.

  Required changes:

  - Replace the current `WorkspaceTab` plus `ArtifactsTab` stack inside the `files` tab with `RunFilesTab`.
  - Keep `WorkspaceTab` and `ArtifactsTab` files in the repo for other inspection routes if they are used elsewhere.
  - Use `badges.files` from `buildRunCompanionBadges`.

- [ ] Add i18n keys to `en/chat.json` and `zh/chat.json`.

  Required key paths:

  - `files.outputs`
  - `files.workspaceFiles`
  - `files.emptyTitle`
  - `files.emptyDescription`
  - `files.refresh`
  - `files.preview`
  - `files.download`

- [ ] Run:

  ```bash
  cd frontend
  npm test -- run-files-view
  npm run build
  ```

  Expected output: files projection tests pass and the build succeeds.

- [ ] Commit:

  ```bash
  git add frontend/src/features/inspection/runFilesView.ts frontend/src/features/inspection/tabs/RunFilesTab.tsx frontend/src/features/inspection/RunCompanion.tsx frontend/tests/run-files-view.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: productize run files tab"
  ```

## Task 8: Add Message Actions

This task adds compact per-message actions that support real chat tasks.

- [ ] Add `frontend/tests/message-actions.test.mjs`.

  Test cases:

  - User messages expose `copy` and `editAndRerun`.
  - Assistant messages expose `copy`, `continue`, and `viewTrace`.
  - Empty messages do not expose `copy`.
  - Streaming assistant messages expose no rerun or trace action.
  - `buildEditAndRerunPrompt` returns the original user message content.
  - `buildContinuePrompt` includes a short assistant excerpt and asks the agent to continue.

- [ ] Add `frontend/src/features/chat/messageActions.ts`.

  Export:

  ```ts
  import type { ChatMessage } from "./useRunStream";

  export type MessageActionKind =
    | "copy"
    | "editAndRerun"
    | "continue"
    | "viewTrace";

  export interface MessageActionView {
    kind: MessageActionKind;
    labelKey: string;
    fallback: string;
    disabled?: boolean;
  }
  ```

  Implement:

  - `buildMessageActions(message: ChatMessage): MessageActionView[]`
  - `buildEditAndRerunPrompt(message: ChatMessage): string`
  - `buildContinuePrompt(message: ChatMessage): string`
  - `copyMessageContent(message: ChatMessage): Promise<boolean>` with clipboard API fallback returning `false` when clipboard is unavailable.

- [ ] Add `frontend/src/features/chat/MessageActions.tsx`.

  Required UI:

  - Render as a compact hover/focus action row below each bubble.
  - Use lucide icons:
    - `Copy`
    - `Pencil`
    - `CornerDownRight`
    - `GitBranch`
  - Buttons must have titles and aria labels.
  - Copy action shows a short copied state for the clicked message.

- [ ] Modify `frontend/src/features/chat/ChatPanel.tsx`.

  Required changes:

  - Accept:

    ```ts
    onPrefillComposer?: (text: string) => void;
    onOpenTrace?: () => void;
    ```

  - Pass callbacks into `MessageBubble`.
  - Render `MessageActions` for each message.
  - `editAndRerun` calls `onPrefillComposer(buildEditAndRerunPrompt(message))`.
  - `continue` calls `onPrefillComposer(buildContinuePrompt(message))`.
  - `viewTrace` calls `onOpenTrace`.

- [ ] Modify `frontend/src/features/conversation/ConversationPage.tsx`.

  Required changes:

  - Pass `onPrefillComposer` to `ChatPanel`.
  - `onPrefillComposer` sets the composer draft and increments focus key.
  - Pass `onOpenTrace={() => onSelectInspectionTab("trace")}`.

- [ ] Add i18n keys to `en/chat.json` and `zh/chat.json`.

  Required key paths:

  - `messageActions.copy`
  - `messageActions.copied`
  - `messageActions.editAndRerun`
  - `messageActions.continue`
  - `messageActions.viewTrace`

- [ ] Run:

  ```bash
  cd frontend
  npm test -- message-actions
  npm run build
  ```

  Expected output: message action tests pass and the build succeeds.

- [ ] Commit:

  ```bash
  git add frontend/src/features/chat/messageActions.ts frontend/src/features/chat/MessageActions.tsx frontend/src/features/chat/ChatPanel.tsx frontend/src/features/conversation/ConversationPage.tsx frontend/tests/message-actions.test.mjs frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
  git commit -m "feat: add chat message actions"
  ```

## Task 9: Final Visual Polish, Regression Tests, and Browser QA

This task verifies the full productized chat experience.

- [ ] Run frontend tests:

  ```bash
  cd frontend
  npm test
  ```

  Expected output: all frontend tests pass.

- [ ] Run frontend build:

  ```bash
  cd frontend
  npm run build
  ```

  Expected output: TypeScript build and Vite build succeed. Existing chunk-size warnings are acceptable if no new error appears.

- [ ] Run i18n sync test explicitly if `npm test` output does not make it obvious:

  ```bash
  cd frontend
  npm test -- i18n
  ```

  Expected output: English and Chinese runtime resource keys remain synchronized.

- [ ] Start or reuse the local app:

  ```bash
  AITHRU_AGENT_BACKEND_ADDR=127.0.0.1:18000 \
  AITHRU_AGENT_FRONTEND_PORT=15173 \
  ./scripts/run.sh
  ```

- [ ] Browser QA desktop at `http://127.0.0.1:15173`.

  Verify:

  - left inbox shows search and product groups;
  - row status labels are human-readable;
  - header shows title, subline, status, model chip, and state action;
  - composer templates fill the draft;
  - central transcript message actions are reachable by hover and keyboard focus;
  - right companion tabs can be selected from header/message actions;
  - Files tab renders outputs and workspace files as one productized list;
  - console has no new errors.

- [ ] Browser QA mobile width around `390px`.

  Verify:

  - left sidebar and right companion are hidden;
  - chat panel uses full width;
  - composer does not overflow;
  - template strip wraps without horizontal scroll;
  - message actions do not cover message text.

- [ ] If frontend-only files changed, backend verification is not required by this repo's backend checklist. If any backend file changed during execution, run:

  ```bash
  cd backend
  uv run pytest
  uv run python examples/file_report_agent.py
  ```

  Expected output: backend tests pass and the file report example completes.

- [ ] Final commit if Task 9 introduced additional polish fixes:

  ```bash
  git add frontend
  git commit -m "style: polish productized agent chat"
  ```

## Completion Checklist

- [ ] The chat app remains a hosted Agent Harness UI, not a workflow graph editor.
- [ ] Thread and run labels are human-readable in primary UI.
- [ ] Conversation inbox uses dashboard signals and does not fake pinned rows.
- [ ] Header actions are backed by existing APIs or explicit composer prefills.
- [ ] Composer templates fill drafts and preserve current run creation behavior.
- [ ] Activity narrative explains current work, waits, failures, and progress.
- [ ] Files tab uses existing run snapshot, workspace, and artifact APIs.
- [ ] Message actions support copy, rerun-prefill, continue-prefill, and trace navigation.
- [ ] Narrow screens remain usable without horizontal overflow.
- [ ] `cd frontend && npm test` passes.
- [ ] `cd frontend && npm run build` passes.
