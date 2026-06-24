# Right Sidebar Rail + Panel Redesign

Date: 2026-06-24

## Goal

Redesign the right sidebar (`InspectionPanel` / `RunCompanion`) from a
tab-based companion panel into a rail-driven panel system where:

- The primary surface is **output preview** (files, artifacts).
- Execution process information (Activity, Approvals, Trace) moves into
  individual panels triggered from a persistent rail.
- When no run or no output files exist, the right sidebar is completely hidden.

This design also introduces **file cards** in the chat stream so that produced
files are visible inline in conversation history.

## Current State

The right sidebar is `RunCompanion`, a 342px panel with two modes:

| Mode | Width | Content |
|---|---|---|
| Collapsed | 48px rail | Status dot + optional todo progress badge |
| Expanded | 342px | Tabs: Activity, Files, Approvals, Trace |

Problems identified:

1. **Layout**: Tab-only switching; all four tabs live at the same level but
   represent different conceptual categories (Files = output, the other three =
   execution process). No direct way to jump to a specific panel.
2. **Visual**: The tab bar is visually dense and not modern; the collapsed rail
   shows very little information.
3. **Missing**: No dedicated first-class preview surface. The Files tab has
   preview capability but it's buried behind tabs.

## Target Architecture

### Three States

The right sidebar has three mutually exclusive states:

| State | Trigger | Appearance |
|---|---|---|
| **Hidden** | No active run OR no output files | Right sidebar completely absent; center chat fills the full width |
| **Rail** | Output files exist, no panel open | 48px narrow strip with vertically stacked icon buttons |
| **Panel open** | Icon button clicked | Rail stays visible (48px), panel slides out to its right (~340px) |

### Rail Icons (top to bottom)

```
┌──────────────┐
│  📄 Preview   │  ← opens preview panel (current file content)
│  📁 Files     │  ← opens file list panel
│  ─────────── │  ← separator
│  📊 Activity  │  ← opens execution activity panel
│  🛡️ Approvals │  ← opens approval panel (with pending-count badge)
│  🔀 Trace     │  ← opens trace / run detail panel
└──────────────┘
```

- Each icon can display a numeric badge (e.g., pending approval count).
- The currently active icon is highlighted / filled.
- Clicking the already-active icon closes the panel (back to pure rail).
- Each open panel has a close button in its header.
- The current expand/collapse toggle button is **removed**.

### Panel Specifications

#### 📄 Preview Panel

```
┌────────────────────────────────┐
│ ← Back    report.md       ⬇    │  ← top bar: back btn + filename + download
├────────────────────────────────┤
│                                │
│     Full preview content        │  ← Markdown / code / image / PDF
│                                │
│                                │
├────────────────────────────────┤
│ Markdown · 12 KB               │  ← bottom info bar
└────────────────────────────────┘
```

- When no file is selected, shows the **file list** (same as 📁 panel).
- When a file is selected, transitions to full-preview with a ← Back button
  to return to the list.
- Supported preview types: Markdown, syntax-highlighted code, formatted JSON,
  images, PDF (iframe).
- Real-time updates as the run produces new files.

#### 📁 Files Panel

```
┌────────────────────────────────┐
│ Outputs (3)              🔄     │
├────────────────────────────────┤
│ 📄 report.md     Markdown      │
│ 🖼 chart.png        Image       │
│ 📊 data.json         JSON       │
│ ─────────────────────────────  │
│ Workspace files (2)            │
│ 📜 script.py       Python       │
│ 📝 notes.txt         Text       │
└────────────────────────────────┘
```

- Grouped sections: "Outputs" (artifacts) and "Workspace files".
- Each row: type icon + filename + type label + size.
- Clicking a row opens that file in the preview panel.
- Download link for downloadable files.
- Refresh button to re-fetch file list.

#### 📊 Activity Panel

```
┌────────────────────────────────┐
│ Activity                       │
├────────────────────────────────┤
│ ● Reasoning                    │
│   "Analyzing the codebase…"    │
│                                │
│ 🔧 Tool call                    │
│   read_file app.tsx             │
│                                │
│ ● Reasoning                    │
│   "I can see the structure…"   │
│                                │
│ ⏸ Waiting for approval         │
│   File write approval needed   │
└────────────────────────────────┘
```

- Streams run events in real time.
- Reverse chronological order (newest at top).
- Event types: reasoning segments, tool calls, approval requests,
  inline input requests, subagent spawns.
- Reuses existing `runActivity` event classification and rendering.

#### 🛡️ Approvals Panel

```
┌────────────────────────────────┐
│ Approvals (2)                  │
├────────────────────────────────┤
│ ⚠ File write                   │
│   path: config.json            │
│   risk: medium                 │
│   [Approve]  [Reject]          │
│ ─────────────────────────────  │
│ ⚠ Shell command                │
│   npm install                  │
│   risk: high                   │
│   [Approve]  [Reject]          │
└────────────────────────────────┘
```

- Lists all pending approval requests for the current run.
- Each item shows: operation type, detail (path, command), risk level.
- Approve / Reject action buttons.
- Handled approvals are collapsed or removed.
- Badge on rail icon reflects the pending count.

#### 🔀 Trace Panel

```
┌────────────────────────────────┐
│ Trace                          │
├────────────────────────────────┤
│ Run #3    completed    1.2s    │
│ task: analyze code structure   │
│ todos: 3/3                     │
├────────────────────────────────┤
│ Span tree / timeline           │
│  ├─ read_file    120ms        │
│  ├─ model_call   340ms        │
│  └─ write_file   80ms         │
└────────────────────────────────┘
```

- Current run metadata: status, duration, task message, todo progress.
- Span call tree or timeline visualization.
- Reuses existing run detail data from `runsApi.snapshot()`.

### File Cards in Chat

When the agent produces files, they appear as inline cards within the chat
message stream:

```
┌─────────────────────────────────────┐
│ 📄 report.md              Markdown  │
│ "A comprehensive analysis report…"  │
│                            [Preview] │
└─────────────────────────────────────┘
```

- Card shows: file type icon, filename, type label, content snippet.
- "Preview" button opens the file in the right preview panel (same as clicking
  a file from the 📁 files panel).
- Cards are rendered as part of the chat timeline, not as separate UI.

## Dependencies

- Reuses existing `RunCompanion` / `RunFilesTab` preview logic (`runFilesView.ts`,
  `RunFilesTab.tsx`, `readFilePreview`).
- Reuses existing `runActivity` event classification for Activity panel.
- Reuses existing `runsApi.snapshot()` for Trace panel.
- Reuses existing `approvalsApi` for Approvals panel.

## Existing Code Impact

### Components to Modify

| File | Change |
|---|---|
| `AppShell.tsx` | Replace `InspectionPanel` / `RunCompanion` with new rail+panel system; remove `inspectionCollapsed` state |
| `InspectionPanel.tsx` | Rewrite entirely or remove; replaced by new side panel system |
| `RunCompanion.tsx` | Rewrite entirely or remove; rail + individual panels replace it |

### Components to Add

| File | Purpose |
|---|---|
| `features/sidebar/RightRail.tsx` | Rail component with icon buttons and badge support |
| `features/sidebar/panels/PreviewPanel.tsx` | File preview with back-to-list navigation |
| `features/sidebar/panels/FilesPanel.tsx` | File list with groups |
| `features/sidebar/panels/ActivityPanel.tsx` | Real-time execution activity stream |
| `features/sidebar/panels/ApprovalsPanel.tsx` | Pending approvals with action buttons |
| `features/sidebar/panels/TracePanel.tsx` | Run detail + span timeline |
| `features/chat/FileCard.tsx` | Inline file card component for chat stream |

### Components to Keep (refactor)

| File | Change |
|---|---|
| `runFilesView.ts` | Keep logic, may extract from `features/inspection` to shared location |
| `runCompanionView.ts` | Keep `buildRunCompanionRailView` logic, move to shared location |
| `runActivity.ts` | Keep event classification, reused by ActivityPanel |

### State Changes

- Remove `inspectionCollapsed` and `inspectionTab` from localStorage keys.
- Replace with `rightPanelActive` (which panel is open) and `rightPanelFile` (selected file for preview).
- Panel open/close is session-only; no localStorage persistence for active panel.

### Tests to Update

| File | Change |
|---|---|
| `tests/run-companion-view.test.mjs` | Update to test new view functions |
| `tests/run-activity.test.mjs` | Verify ActivityPanel uses same activity data |
| `tests/run-files-view.test.mjs` | Verify file views work in new panel context |
| `tests/app-shell-actions.test.mjs` | Update for new right sidebar state |
| `tests/app-shell-defaults.test.mjs` | Update for removed inspection collapse |
| `tests/chat-conversation-flow.test.mjs` | Add file card rendering tests |

## Non-Goals

- No changes to the left sidebar (Sidebar / ConversationInbox).
- No changes to the center chat panel layout.
- No drag-and-drop file reordering.
- No file system tree view; flat grouped list is sufficient.

## Verification

```bash
cd frontend
npm run typecheck
npm test
```

Manual verification:

- Start a run that produces files → rail appears when files exist.
- Click Preview icon → panel opens with file list.
- Click a file → full-preview with back button.
- Click Approvals icon → approval list with badge.
- Click active icon again → panel closes.
- No run → right sidebar hidden.
- File cards appear in chat when agent produces artifacts.
