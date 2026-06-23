# Agent Chat Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Aithru Agent frontend into a Cursor/Codex-style agent chat command center with a conversation inbox, readable chat transcript, compact composer, and Activity-first run companion.

**Architecture:** Keep the existing React/Vite frontend and evolve current surfaces instead of replacing them. Lift run stream state high enough that the center transcript and right companion share one event projection, then split UI responsibilities into focused components.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind CSS, Radix UI primitives, TanStack Query, Node native test runner with esbuild bundling.

---

## Scope Check

This plan implements the frontend chat command center only. It does not change backend workflow semantics, create a workflow graph editor, or add new agent-owned workflow definitions.

## File Structure

Create:

- `frontend/src/features/chat/runActivity.ts`: pure projection helpers that convert `RunStreamState` into right-panel activity rows, progress, tab badges, and summary labels.
- `frontend/src/features/inspection/RunCompanion.tsx`: right-side panel shell replacing the current inspection presentation while preserving existing inspection content as tabs.
- `frontend/src/features/inspection/tabs/ActivityTab.tsx`: Activity-first run companion tab.
- `frontend/src/features/conversation/ConversationHeader.tsx`: focused header for title editing and run/model status.
- `frontend/src/features/chat/AgentActivityCard.tsx`: compact inline activity summary for the transcript.
- `frontend/src/features/sidebar/ConversationInbox.tsx`: conversation-list UI extracted from `Sidebar`.
- `frontend/tests/run-activity.test.mjs`: unit tests for activity projection and tab badges.
- `frontend/tests/conversation-inbox.test.mjs`: render-level test for conversation inbox status grouping.

Modify:

- `frontend/src/AppShell.tsx`: lift `useRunStream` into `RouteContent`, pass stream state to both center chat and right companion.
- `frontend/src/features/conversation/ConversationPage.tsx`: receive stream state as props, use `ConversationHeader`, and keep run creation behavior.
- `frontend/src/features/chat/ChatPanel.tsx`: rename internally toward transcript behavior, add inline `AgentActivityCard`, and keep message rendering stable.
- `frontend/src/features/chat/ChatComposer.tsx`: redesign visible layout so selectors are compact secondary controls.
- `frontend/src/features/inspection/InspectionPanel.tsx`: become a thin compatibility wrapper around `RunCompanion`.
- `frontend/src/features/sidebar/Sidebar.tsx`: delegate expanded body to `ConversationInbox`, keep collapsed rail behavior.
- `frontend/src/i18n/resources/en/chat.json`: add command center copy.
- `frontend/src/i18n/resources/zh/chat.json`: add Chinese command center copy.

Do not modify:

- Backend model/run APIs unless a frontend compile error proves an existing type is missing.
- Workflow-related docs or concepts.

---

### Task 1: Add Run Activity Projection Helpers

**Files:**

- Create: `frontend/src/features/chat/runActivity.ts`
- Create: `frontend/tests/run-activity.test.mjs`
- Read: `frontend/src/features/chat/useRunStream.ts`

- [ ] **Step 1: Write the failing projection tests**

Create `frontend/tests/run-activity.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunActivity() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/runActivity.ts"],
    plugins: [
      {
        name: "run-activity-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/features\/chat\/useRunStream$/ }, () => ({
            path: "mock-use-run-stream",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-use-run-stream$/, namespace: "mock" }, () => ({
            contents: "export {};",
            loader: "js",
          }));
        },
      },
    ],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

function baseState(patch = {}) {
  return {
    status: "running",
    messages: [],
    toolCalls: [],
    todos: [],
    inlineRequests: [],
    ...patch,
  };
}

test("buildRunActivity summarizes todos, current step, and token usage", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const activity = buildRunActivity(
    baseState({
      todos: [
        { id: "todo_1", title: "Inspect frontend", status: "done" },
        { id: "todo_2", title: "Design command center", status: "in_progress" },
        { id: "todo_3", title: "Write implementation plan", status: "pending" },
      ],
      tokenUsage: { input: 100, output: 25, total: 125 },
    }),
  );

  assert.equal(activity.status, "running");
  assert.equal(activity.progress.done, 1);
  assert.equal(activity.progress.total, 3);
  assert.equal(activity.current?.title, "Design command center");
  assert.equal(activity.usageLabel, "125 tokens");
  assert.deepEqual(
    activity.items.map((item) => [item.id, item.status, item.title]),
    [
      ["todo_1", "completed", "Inspect frontend"],
      ["todo_2", "current", "Design command center"],
      ["todo_3", "next", "Write implementation plan"],
    ],
  );
});

test("buildRunActivity promotes waiting input and failed run states", async () => {
  const { buildRunActivity } = await loadRunActivity();
  const waiting = buildRunActivity(
    baseState({
      status: "waiting_input",
      inlineRequests: [
        {
          kind: "input",
          id: "input_1",
          prompt: "What should the agent focus on?",
          runId: "run_1",
        },
      ],
    }),
  );

  assert.equal(waiting.current?.status, "waiting");
  assert.equal(waiting.current?.title, "What should the agent focus on?");

  const failed = buildRunActivity(
    baseState({
      status: "failed",
      error: "model profile metadata cannot include secret values",
    }),
  );

  assert.equal(failed.current?.status, "failed");
  assert.equal(failed.current?.title, "Run failed");
  assert.match(failed.current?.detail ?? "", /metadata cannot include secret values/);
});

test("buildRunCompanionBadges marks approvals, files, and trace attention", async () => {
  const { buildRunCompanionBadges } = await loadRunActivity();
  const badges = buildRunCompanionBadges(
    baseState({
      status: "waiting_approval",
      inlineRequests: [
        {
          kind: "approval",
          id: "approval_1",
          prompt: "Allow filesystem write?",
          approvalId: "approval_1",
          runId: "run_1",
        },
      ],
      toolCalls: [
        {
          id: "tool_1",
          toolName: "workspace.write",
          status: "completed",
          outputSummary: "Updated frontend/src/AppShell.tsx",
        },
        {
          id: "tool_2",
          toolName: "model",
          status: "failed",
          error: "Validation failed",
        },
      ],
    }),
  );

  assert.equal(badges.approvals, 1);
  assert.equal(badges.files, 1);
  assert.equal(badges.trace, 1);
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd frontend
npm test -- run-activity.test.mjs
```

Expected: FAIL with an esbuild error that `src/features/chat/runActivity.ts` cannot be resolved.

- [ ] **Step 3: Implement the projection helper**

Create `frontend/src/features/chat/runActivity.ts`:

```ts
import type { InlineRequest, RunStreamState, TodoEntry, ToolCallEntry } from "./useRunStream";

export type RunActivityItemStatus = "completed" | "current" | "waiting" | "failed" | "next";

export interface RunActivityItem {
  id: string;
  title: string;
  detail?: string;
  status: RunActivityItemStatus;
  source: "todo" | "request" | "tool" | "run";
}

export interface RunActivitySummary {
  status: RunStreamState["status"];
  progress: { done: number; total: number };
  current: RunActivityItem | null;
  items: RunActivityItem[];
  usageLabel: string | null;
}

export interface RunCompanionBadges {
  activity: number;
  files: number;
  approvals: number;
  trace: number;
}

const DONE_STATUSES = new Set(["done", "completed"]);
const ACTIVE_STATUSES = new Set(["in_progress", "running", "active"]);
const WAITING_STATUSES = new Set(["waiting_input", "waiting_approval", "paused"]);
const FILE_TOOL_PATTERNS = [
  "file",
  "workspace",
  "artifact",
  ".ts",
  ".tsx",
  ".py",
  ".md",
  ".json",
  ".txt",
];

export function buildRunActivity(state: RunStreamState): RunActivitySummary {
  const todoItems = state.todos.map(todoToActivityItem);
  const requestItems = state.inlineRequests.map(requestToActivityItem);
  const failedToolItems = state.toolCalls
    .filter((tool) => tool.status === "failed")
    .map(toolToActivityItem);

  const items = [...todoItems, ...requestItems, ...failedToolItems];
  const runItem = runStatusItem(state);
  const current =
    requestItems[0] ??
    failedToolItems[0] ??
    todoItems.find((item) => item.status === "current") ??
    runItem;

  const progressTotal = state.todos.length;
  const progressDone = state.todos.filter((todo) => DONE_STATUSES.has(todo.status)).length;

  return {
    status: state.status,
    progress: { done: progressDone, total: progressTotal },
    current,
    items: items.length > 0 ? items : runItem ? [runItem] : [],
    usageLabel: formatUsage(state.tokenUsage?.total),
  };
}

export function buildRunCompanionBadges(state: RunStreamState): RunCompanionBadges {
  const approvals = state.inlineRequests.filter((request) =>
    request.kind === "approval" || request.kind === "external_approval"
  ).length;
  const files = state.toolCalls.filter(toolLooksFileRelated).length;
  const trace = state.error || state.toolCalls.some((tool) => tool.status === "failed") ? 1 : 0;
  const activity = state.inlineRequests.length + state.toolCalls.filter((tool) => tool.status === "failed").length;

  return { activity, files, approvals, trace };
}

function todoToActivityItem(todo: TodoEntry): RunActivityItem {
  return {
    id: todo.id,
    title: todo.title || "Untitled step",
    status: todoStatus(todo.status),
    source: "todo",
  };
}

function todoStatus(status: string): RunActivityItemStatus {
  if (DONE_STATUSES.has(status)) return "completed";
  if (ACTIVE_STATUSES.has(status)) return "current";
  if (status === "blocked" || status === "failed") return "failed";
  return "next";
}

function requestToActivityItem(request: InlineRequest): RunActivityItem {
  return {
    id: request.id,
    title: request.prompt || request.toolName || "Agent needs attention",
    detail: request.kind === "input" ? "Reply to continue this run." : "Review this action before the run continues.",
    status: "waiting",
    source: "request",
  };
}

function toolToActivityItem(tool: ToolCallEntry): RunActivityItem {
  return {
    id: tool.id,
    title: tool.toolName,
    detail: tool.error || tool.outputSummary || tool.inputSummary,
    status: tool.status === "failed" ? "failed" : tool.status === "completed" ? "completed" : "current",
    source: "tool",
  };
}

function runStatusItem(state: RunStreamState): RunActivityItem | null {
  if (state.status === "idle") return null;
  if (state.status === "failed") {
    return {
      id: "run-failed",
      title: "Run failed",
      detail: state.error,
      status: "failed",
      source: "run",
    };
  }
  if (WAITING_STATUSES.has(state.status)) {
    return {
      id: "run-waiting",
      title: "Waiting for input",
      status: "waiting",
      source: "run",
    };
  }
  if (state.status === "completed") {
    return {
      id: "run-completed",
      title: "Run completed",
      status: "completed",
      source: "run",
    };
  }
  return {
    id: "run-running",
    title: "Agent is working",
    status: "current",
    source: "run",
  };
}

function formatUsage(total: number | undefined): string | null {
  if (total == null) return null;
  return `${total.toLocaleString("en-US")} tokens`;
}

function toolLooksFileRelated(tool: ToolCallEntry): boolean {
  const haystack = [
    tool.toolName,
    tool.inputSummary,
    tool.outputSummary,
    tool.error,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return FILE_TOOL_PATTERNS.some((pattern) => haystack.includes(pattern));
}
```

- [ ] **Step 4: Run projection tests and all frontend tests**

Run:

```bash
cd frontend
npm test -- run-activity.test.mjs
npm test
```

Expected: both commands PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add frontend/src/features/chat/runActivity.ts frontend/tests/run-activity.test.mjs
git commit -m "feat: add run activity projection"
```

---

### Task 2: Lift Active Run Resolution and Stream State to the App Shell

**Files:**

- Modify: `frontend/src/AppShell.tsx`
- Modify: `frontend/src/features/conversation/ConversationPage.tsx`
- Read: `frontend/src/features/chat/useRunStream.ts`

- [ ] **Step 1: Update `ConversationPage` props before changing behavior**

In `frontend/src/features/conversation/ConversationPage.tsx`, change imports and props:

```ts
import type { AgentRun } from "@/lib/api";
import type { RunStreamState } from "@/features/chat/useRunStream";
```

Change the component signature:

```ts
export function ConversationPage({
  threadId,
  runId,
  activeRunId,
  onRunIdChange,
  streamState,
  streaming,
}: {
  threadId: string | null;
  runId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  streaming: boolean;
}) {
```

Remove this line from inside `ConversationPage`:

```ts
const { state, streaming } = useRunStream(activeRunId);
```

Remove the local `activeRunId` `useMemo`; the shell now resolves it so chat and the run companion use the same run.

Replace references:

```ts
const runStatus = streamState.status !== "idle" ? streamState.status : activeRun?.status;
```

Render:

```tsx
<ChatPanel state={streamState} />
```

- [ ] **Step 2: Resolve the active run in `AppShell`**

In `frontend/src/AppShell.tsx`, add:

```ts
import { threadsApi } from "@/lib/api";
import { useRunStream } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";
```

In `RouteContent`, after the route run effect, add the thread run query and active run calculation:

```ts
const runsQuery = useQuery({
  queryKey: ["threads", threadId, "runs"],
  queryFn: () => threadsApi.runs(threadId!),
  enabled: !!threadId,
  refetchInterval: (query) => {
    const data = query.state.data as AgentRun[] | undefined;
    const hasActive = data?.some((run) => ["queued", "running"].includes(run.status));
    return hasActive ? 4000 : false;
  },
});

const activeRunId = React.useMemo(() => {
  if (runId) return runId;
  const runs = runsQuery.data;
  if (!runs?.length) return null;
  return runs[runs.length - 1].id;
}, [runId, runsQuery.data]);

const { state: streamState, streaming } = useRunStream(activeRunId);
```

Pass props:

```tsx
<ConversationRoute
  threadId={threadId}
  runId={runId}
  activeRunId={activeRunId}
  onRunIdChange={onRunIdChange}
  streamState={streamState}
  streaming={streaming}
/>
<InspectionConnector
  runId={activeRunId}
  collapsed={inspectionCollapsed}
  onToggle={onToggleInspection}
  streamState={streamState}
/>
```

Update `ConversationRoute` props and render:

```tsx
function ConversationRoute({
  threadId,
  runId,
  activeRunId,
  onRunIdChange,
  streamState,
  streaming,
}: {
  threadId: string | null;
  runId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  streaming: boolean;
}) {
  if (!threadId) {
    return <NewThreadPage />;
  }
  return (
    <ConversationPage
      threadId={threadId}
      runId={runId}
      activeRunId={activeRunId}
      onRunIdChange={onRunIdChange}
      streamState={streamState}
      streaming={streaming}
    />
  );
}
```

Update `InspectionConnector` props:

```ts
streamState: RunStreamState;
```

Pass it to the panel:

```tsx
<InspectionPanel
  runId={runId}
  workspaceId={workspaceId}
  collapsed={collapsed}
  onToggle={onToggle}
  runStatus={runStatus}
  todoProgress={todoProgress}
  streamState={streamState}
/>
```

- [ ] **Step 3: Make `InspectionPanel` accept the new prop without using it yet**

In `frontend/src/features/inspection/InspectionPanel.tsx`, import:

```ts
import type { RunStreamState } from "@/features/chat/useRunStream";
```

Add prop:

```ts
streamState?: RunStreamState;
```

Do not render it yet. This keeps Task 2 focused on shared state wiring.

- [ ] **Step 4: Run typecheck**

Run:

```bash
cd frontend
npm run typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add frontend/src/AppShell.tsx frontend/src/features/conversation/ConversationPage.tsx frontend/src/features/inspection/InspectionPanel.tsx
git commit -m "refactor: share run stream state across chat layout"
```

---

### Task 3: Build the Activity-First Run Companion

**Files:**

- Create: `frontend/src/features/inspection/RunCompanion.tsx`
- Create: `frontend/src/features/inspection/tabs/ActivityTab.tsx`
- Modify: `frontend/src/features/inspection/InspectionPanel.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`
- Read: `frontend/src/features/inspection/tabs/RunTab.tsx`
- Read: `frontend/src/features/inspection/tabs/WorkspaceTab.tsx`
- Read: `frontend/src/features/inspection/tabs/ArtifactsTab.tsx`
- Read: `frontend/src/features/inspection/tabs/ApprovalsTab.tsx`
- Read: `frontend/src/features/inspection/tabs/MemoryTab.tsx`

- [ ] **Step 1: Add i18n copy for the companion**

Add these keys to `frontend/src/i18n/resources/en/chat.json`:

```json
{
  "runCompanion": "Activity",
  "tabActivity": "Activity",
  "tabFiles": "Files",
  "tabApprovals": "Approvals",
  "tabTrace": "Trace",
  "currentRun": "Current run",
  "noRunActivity": "No run activity yet.",
  "usageRequests": "{{count}} request",
  "usageRequests_plural": "{{count}} requests"
}
```

Add these keys to `frontend/src/i18n/resources/zh/chat.json`:

```json
{
  "runCompanion": "活动",
  "tabActivity": "活动",
  "tabFiles": "文件",
  "tabApprovals": "审批",
  "tabTrace": "轨迹",
  "currentRun": "当前运行",
  "noRunActivity": "暂无运行活动。",
  "usageRequests": "{{count}} 次请求",
  "usageRequests_plural": "{{count}} 次请求"
}
```

Keep valid JSON by inserting the keys before the final closing brace with commas.

- [ ] **Step 2: Create the Activity tab component**

Create `frontend/src/features/inspection/tabs/ActivityTab.tsx`:

```tsx
import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { buildRunActivity, type RunActivityItem } from "@/features/chat/runActivity";
import type { RunStreamState } from "@/features/chat/useRunStream";

export function ActivityTab({ state }: { state: RunStreamState }) {
  const { t } = useTranslation(["chat", "common"]);
  const activity = buildRunActivity(state);
  const hasProgress = activity.progress.total > 0;
  const progressValue = hasProgress
    ? Math.round((activity.progress.done / activity.progress.total) * 100)
    : 0;

  if (activity.items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-sm text-muted-foreground">
        {t("chat:noRunActivity")}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <section className="rounded-lg border bg-muted/30 p-3">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-semibold text-foreground">{t("chat:currentRun")}</span>
          <span className="text-muted-foreground">
            {t(`common:status.${activity.status}`, { defaultValue: activity.status })}
          </span>
        </div>
        {hasProgress && (
          <>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${progressValue}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
              <span>{activity.current?.title ?? t("chat:thinking")}</span>
              <span>
                {activity.progress.done}/{activity.progress.total}
              </span>
            </div>
          </>
        )}
        {activity.usageLabel && (
          <div className="mt-3 text-[11px] text-muted-foreground">{activity.usageLabel}</div>
        )}
      </section>

      <div className="mt-3 space-y-3">
        {activity.items.map((item) => (
          <ActivityRow key={`${item.source}:${item.id}`} item={item} />
        ))}
      </div>
    </div>
  );
}

function ActivityRow({ item }: { item: RunActivityItem }) {
  const icon = activityIcon(item);
  return (
    <div className="flex gap-2">
      <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">{icon}</div>
      <div
        className={cn(
          "min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm",
          item.status === "current" && "border-primary/30 bg-primary/5",
          item.status === "waiting" && "border-warning/40 bg-warning/5",
          item.status === "failed" && "border-destructive/35 bg-destructive/5",
        )}
      >
        <div className="truncate font-medium">{item.title}</div>
        {item.detail && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.detail}</div>
        )}
      </div>
    </div>
  );
}

function activityIcon(item: RunActivityItem) {
  if (item.status === "completed") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (item.status === "current") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (item.status === "waiting") return <Clock3 className="h-4 w-4 text-warning" />;
  if (item.status === "failed") return <AlertTriangle className="h-4 w-4 text-destructive" />;
  return <Circle className="h-4 w-4 text-muted-foreground" />;
}
```

- [ ] **Step 3: Create the run companion shell**

Create `frontend/src/features/inspection/RunCompanion.tsx`:

```tsx
import type * as React from "react";
import { Activity, FileText, GitBranch, PanelRightClose, PanelRightOpen, ShieldCheck } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { buildRunCompanionBadges } from "@/features/chat/runActivity";
import type { RunStreamState } from "@/features/chat/useRunStream";
import { useTranslation } from "react-i18next";
import { ActivityTab } from "./tabs/ActivityTab";
import { WorkspaceTab } from "./tabs/WorkspaceTab";
import { ArtifactsTab } from "./tabs/ArtifactsTab";
import { ApprovalsTab } from "./tabs/ApprovalsTab";
import { RunTab } from "./tabs/RunTab";

export function RunCompanion({
  runId,
  workspaceId,
  collapsed,
  onToggle,
  runStatus,
  todoProgress,
  streamState,
}: {
  runId: string | null;
  workspaceId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  runStatus?: string;
  todoProgress?: { done: number; total: number };
  streamState: RunStreamState;
}) {
  const { t } = useTranslation(["chat", "inspection", "common"]);
  const badges = buildRunCompanionBadges(streamState);

  if (collapsed) {
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center gap-3 border-l bg-card py-3">
        <Button variant="ghost" size="icon" onClick={onToggle} title={t("inspection:expand")}>
          <PanelRightOpen className="h-4 w-4" />
        </Button>
        <Activity className="h-4 w-4 text-muted-foreground" />
        {runStatus && (
          <div className="rotate-90 whitespace-nowrap text-[10px] text-muted-foreground">
            {t(`common:status.${runStatus}`, { defaultValue: runStatus })}
          </div>
        )}
        {todoProgress && todoProgress.total > 0 && (
          <div className="flex flex-col items-center text-[10px] text-muted-foreground">
            <span className="font-mono">
              {todoProgress.done}/{todoProgress.total}
            </span>
          </div>
        )}
      </aside>
    );
  }

  return (
    <aside className="flex w-[342px] shrink-0 flex-col border-l bg-card">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
        <span className="text-sm font-semibold">{t("chat:runCompanion")}</span>
        {runStatus && <StatusBadge status={runStatus} />}
        <Button variant="ghost" size="icon" className="ml-auto h-7 w-7" onClick={onToggle} title={t("inspection:collapse")}>
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>
      <Tabs defaultValue={badges.approvals > 0 ? "approvals" : "activity"} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="m-2 grid h-9 grid-cols-4">
          <CompanionTab value="activity" icon={<Activity className="h-3.5 w-3.5" />} label={t("chat:tabActivity")} badge={badges.activity} />
          <CompanionTab value="files" icon={<FileText className="h-3.5 w-3.5" />} label={t("chat:tabFiles")} badge={badges.files} disabled={!workspaceId && badges.files === 0} />
          <CompanionTab value="approvals" icon={<ShieldCheck className="h-3.5 w-3.5" />} label={t("chat:tabApprovals")} badge={badges.approvals} disabled={!runId && badges.approvals === 0} />
          <CompanionTab value="trace" icon={<GitBranch className="h-3.5 w-3.5" />} label={t("chat:tabTrace")} badge={badges.trace} disabled={!runId && badges.trace === 0} />
        </TabsList>
        <TabsContent value="activity" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <ActivityTab state={streamState} />
        </TabsContent>
        <TabsContent value="files" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <WorkspaceTab workspaceId={workspaceId} />
          <ArtifactsTab runId={runId} />
        </TabsContent>
        <TabsContent value="approvals" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <ApprovalsTab runId={runId} />
        </TabsContent>
        <TabsContent value="trace" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <RunTab runId={runId} />
        </TabsContent>
      </Tabs>
    </aside>
  );
}

function CompanionTab({
  value,
  icon,
  label,
  badge,
  disabled,
}: {
  value: string;
  icon: React.ReactNode;
  label: string;
  badge: number;
  disabled?: boolean;
}) {
  return (
    <TabsTrigger value={value} disabled={disabled} className="relative gap-1 px-1">
      {icon}
      <span className="sr-only sm:not-sr-only">{label}</span>
      {badge > 0 && (
        <Badge variant="secondary" className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]">
          {badge > 9 ? "9+" : badge}
        </Badge>
      )}
    </TabsTrigger>
  );
}
```

- [ ] **Step 4: Replace `InspectionPanel` internals with `RunCompanion`**

In `frontend/src/features/inspection/InspectionPanel.tsx`, replace the component body with a wrapper:

```tsx
import type { RunStreamState } from "@/features/chat/useRunStream";
import { RunCompanion } from "./RunCompanion";

export function InspectionPanel(props: {
  runId: string | null;
  workspaceId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  runStatus?: string;
  todoProgress?: { done: number; total: number };
  streamState?: RunStreamState;
}) {
  return (
    <RunCompanion
      {...props}
      streamState={
        props.streamState ?? {
          status: "idle",
          messages: [],
          toolCalls: [],
          todos: [],
          inlineRequests: [],
        }
      }
    />
  );
}
```

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd frontend
npm run typecheck
npm test
```

Expected: both PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add frontend/src/features/inspection/RunCompanion.tsx frontend/src/features/inspection/InspectionPanel.tsx frontend/src/features/inspection/tabs/ActivityTab.tsx frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
git commit -m "feat: add activity-first run companion"
```

---

### Task 4: Redesign the Chat Header and Transcript

**Files:**

- Create: `frontend/src/features/conversation/ConversationHeader.tsx`
- Create: `frontend/src/features/chat/AgentActivityCard.tsx`
- Modify: `frontend/src/features/conversation/ConversationPage.tsx`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`

- [ ] **Step 1: Extract the conversation header**

Create `frontend/src/features/conversation/ConversationHeader.tsx`:

```tsx
import * as React from "react";
import { Check, Edit3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { AgentRunStatus } from "@/lib/api";

export function ConversationHeader({
  title,
  fallbackTitle,
  runStatus,
  streaming,
  modelName,
  onRename,
}: {
  title?: string | null;
  fallbackTitle: string;
  runStatus?: AgentRunStatus | "idle";
  streaming: boolean;
  modelName?: string | null;
  onRename: (title: string) => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(title ?? "");

  React.useEffect(() => {
    if (!editing) setDraft(title ?? "");
  }, [editing, title]);

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b bg-card/95 px-4">
      {editing ? (
        <form
          className="flex min-w-0 items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const next = draft.trim();
            if (next) onRename(next);
            setEditing(false);
          }}
        >
          <Input autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} className="h-8 w-72 max-w-[50vw]" />
          <Button type="submit" size="icon" variant="ghost" className="h-8 w-8" aria-label="Save title">
            <Check className="h-4 w-4" />
          </Button>
        </form>
      ) : (
        <button
          type="button"
          className="flex min-w-0 items-center gap-1.5 text-sm font-semibold hover:text-primary"
          onClick={() => {
            setDraft(title ?? "");
            setEditing(true);
          }}
        >
          <span className="truncate">{title || fallbackTitle}</span>
          <Edit3 className="h-3.5 w-3.5 shrink-0 opacity-50" />
        </button>
      )}
      {runStatus && runStatus !== "idle" && <StatusBadge status={runStatus} />}
      {streaming && <span className="text-xs text-accent">● live</span>}
      {modelName && (
        <span className="ml-auto hidden max-w-48 truncate rounded-full bg-secondary px-2 py-1 text-xs text-muted-foreground sm:inline">
          {modelName}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add inline activity card**

Create `frontend/src/features/chat/AgentActivityCard.tsx`:

```tsx
import { Activity, AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";
import { buildRunActivity } from "./runActivity";
import type { RunStreamState } from "./useRunStream";

export function AgentActivityCard({ state }: { state: RunStreamState }) {
  const activity = buildRunActivity(state);
  if (!activity.current || state.status === "idle") return null;

  const Icon =
    activity.current.status === "completed"
      ? CheckCircle2
      : activity.current.status === "failed"
        ? AlertTriangle
        : activity.current.status === "waiting"
          ? Clock3
          : Activity;

  return (
    <div className="mx-auto max-w-3xl px-4 py-2">
      <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <span className="min-w-0 flex-1 truncate font-medium">{activity.current.title}</span>
          {activity.progress.total > 0 && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {activity.progress.done}/{activity.progress.total}
            </span>
          )}
        </div>
        {activity.current.detail && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{activity.current.detail}</div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Use `ConversationHeader` in `ConversationPage`**

In `frontend/src/features/conversation/ConversationPage.tsx`, remove local header JSX and import:

```ts
import { ConversationHeader } from "./ConversationHeader";
```

Render:

```tsx
<ConversationHeader
  title={threadQuery.data?.title}
  fallbackTitle={t("chat:newConversation")}
  runStatus={runStatus}
  streaming={streaming}
  modelName={activeRun?.harness_options?.model_profile_key ?? activeRun?.harness_options?.model}
  onRename={(title) => renameMutation.mutate(title)}
/>
```

Keep `renameMutation` and remove the now-unused `editingTitle` and `titleDraft` state.

- [ ] **Step 4: Add inline activity card to `ChatPanel`**

In `frontend/src/features/chat/ChatPanel.tsx`, import:

```ts
import { AgentActivityCard } from "./AgentActivityCard";
```

Render it after messages and before raw tool calls:

```tsx
{state.messages.length > 0 && <AgentActivityCard state={state} />}
```

Keep `ToolCallCard` rendering after the inline summary. It remains the more detailed view.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd frontend
npm run typecheck
npm test
```

Expected: both PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add frontend/src/features/conversation/ConversationHeader.tsx frontend/src/features/conversation/ConversationPage.tsx frontend/src/features/chat/AgentActivityCard.tsx frontend/src/features/chat/ChatPanel.tsx
git commit -m "feat: refine chat transcript and header"
```

---

### Task 5: Redesign the Composer as a Chat Input

**Files:**

- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`

- [ ] **Step 1: Add composer copy**

Add these keys to `frontend/src/i18n/resources/en/chat.json`:

```json
{
  "modeAuto": "Auto",
  "modePlan": "Plan",
  "modeChat": "Chat",
  "composerMode": "Mode",
  "sendMessage": "Send message"
}
```

Add these keys to `frontend/src/i18n/resources/zh/chat.json`:

```json
{
  "modeAuto": "自动",
  "modePlan": "计划",
  "modeChat": "聊天",
  "composerMode": "模式",
  "sendMessage": "发送消息"
}
```

- [ ] **Step 2: Add local mode state and compact controls**

In `frontend/src/features/chat/ChatComposer.tsx`, add mode state near existing state:

```ts
const [mode, setMode] = React.useState<string>("auto");
```

Replace the current `return` contents with this structure:

```tsx
return (
  <div className="border-t bg-background px-4 py-3">
    <div className="mx-auto max-w-3xl">
      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <Textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t("chat:goalPlaceholder")}
          className="min-h-[64px] max-h-40 resize-none rounded-none border-0 bg-transparent px-3 py-3 shadow-none focus-visible:ring-0"
          rows={2}
        />
        <div className="flex flex-wrap items-center gap-2 border-t bg-muted/30 px-2 py-2">
          <Select value={mode} onValueChange={setMode}>
            <SelectTrigger aria-label={t("chat:composerMode")} className="h-7 w-[104px] border-0 bg-background text-xs shadow-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">{t("chat:modeAuto")}</SelectItem>
              <SelectItem value="plan">{t("chat:modePlan")}</SelectItem>
              <SelectItem value="chat">{t("chat:modeChat")}</SelectItem>
            </SelectContent>
          </Select>
          <Select value={profileKey} onValueChange={setProfileKey}>
            <SelectTrigger aria-label={t("chat:selectModelProfile")} className="h-7 w-[150px] border-0 bg-background text-xs shadow-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__default__">{t("common:default")}</SelectItem>
              {profilesQuery.data?.map((p) => (
                <SelectItem key={p.key} value={p.key} disabled={!p.enabled}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={skillId} onValueChange={setSkillId}>
            <SelectTrigger aria-label={t("chat:selectSkill")} className="h-7 w-[130px] border-0 bg-background text-xs shadow-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">{t("common:default")}</SelectItem>
              {skillsQuery.data?.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              e.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto h-8 w-8"
            onClick={() => fileRef.current?.click()}
            title={t("chat:attachFile")}
            aria-label={t("chat:attachFile")}
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          {activeRunId && (
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => cancelRun.mutate(activeRunId)}
              title={t("chat:cancelRun")}
              aria-label={t("chat:cancelRun")}
            >
              <Square className="h-4 w-4" />
            </Button>
          )}
          <Button
            size="icon"
            className="h-8 w-8"
            onClick={handleSend}
            disabled={!goal.trim() || createRun.isPending}
            title={t("chat:sendMessage")}
            aria-label={t("chat:sendMessage")}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  </div>
);
```

Remove the old top row that used `Label` for Skill and Model profile. Remove the `Label` import.

- [ ] **Step 3: Confirm run creation still sends selected profile and skill**

No behavior change is needed in `handleSend` or `createRun`. Verify this block remains:

```ts
createRun.mutate({
  goal: trimmed,
  skillId: skillId === "__none__" ? null : skillId,
  profileKey,
});
```

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend
npm run typecheck
npm test
```

Expected: both PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add frontend/src/features/chat/ChatComposer.tsx frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
git commit -m "feat: redesign chat composer controls"
```

---

### Task 6: Turn the Sidebar Into a Conversation Inbox

**Files:**

- Create: `frontend/src/features/sidebar/ConversationInbox.tsx`
- Create: `frontend/tests/conversation-inbox.test.mjs`
- Modify: `frontend/src/features/sidebar/Sidebar.tsx`
- Modify: `frontend/src/i18n/resources/en/common.json`
- Modify: `frontend/src/i18n/resources/zh/common.json`

- [ ] **Step 1: Create a render test for inbox content**

Create `frontend/tests/conversation-inbox.test.mjs`:

```js
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { test } from "node:test";
import esbuild from "esbuild";

async function renderInbox() {
  const resolveDir = new URL("..", import.meta.url).pathname;
  const fixture = `
    import React from "react";
    import { renderToStaticMarkup } from "react-dom/server";
    import { ConversationInbox } from "./src/features/sidebar/ConversationInbox";
    const items = [
      {
        thread: { id: "thread_1", title: "Chat app redesign" },
        latest_run: { status: "running", created_at: "2026-06-23T00:00:00.000Z" },
        needs_attention: false,
        last_activity_at: "2026-06-23T00:00:00.000Z",
      },
      {
        thread: { id: "thread_2", title: "Meeting reminder" },
        latest_run: { status: "waiting_input", created_at: "2026-06-23T00:00:00.000Z" },
        needs_attention: true,
        last_activity_at: "2026-06-23T00:00:00.000Z",
      },
    ];
    export default renderToStaticMarkup(
      React.createElement(ConversationInbox, {
        items,
        activePath: "/threads/thread_1",
        locale: "en-US",
        loading: false,
        emptyLabel: "No conversations",
      }),
    );
  `;

  const result = await esbuild.build({
    absWorkingDir: resolveDir,
    bundle: true,
    format: "cjs",
    platform: "node",
    write: false,
    stdin: {
      contents: fixture,
      resolveDir,
      sourcefile: "conversation-inbox-fixture.tsx",
      loader: "tsx",
    },
    plugins: [
      {
        name: "conversation-inbox-test-mocks",
        setup(build) {
          build.onResolve({ filter: /^react-router-dom$/ }, () => ({
            path: "mock-router",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/components\/ui\/scroll-area$/ }, () => ({
            path: "mock-scroll-area",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: new URL(\`../src/\${args.path.slice(2)}\`, import.meta.url).pathname,
          }));
          build.onLoad({ filter: /^mock-router$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function Link(props) { return React.createElement("a", { href: props.to, className: props.className }, props.children); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-scroll-area$/, namespace: "mock" }, () => ({
            contents: `
              import React from "react";
              export function ScrollArea(props) { return React.createElement("div", props); }
            `,
            loader: "js",
            resolveDir,
          }));
          build.onLoad({ filter: /^mock-utils$/, namespace: "mock" }, () => ({
            contents: `
              export function cn(...classes) { return classes.filter(Boolean).join(" "); }
              export function relativeTime() { return "now"; }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  const tmp = await mkdtemp(join(tmpdir(), "aithru-conversation-inbox-"));
  const outFile = join(tmp, "conversation-inbox.cjs");
  await writeFile(outFile, result.outputFiles[0].text, "utf8");
  try {
    const require = createRequire(import.meta.url);
    return require(outFile).default;
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}

test("conversation inbox renders active conversation and attention state", async () => {
  const html = await renderInbox();

  assert.match(html, /Chat app redesign/);
  assert.match(html, /Meeting reminder/);
  assert.match(html, /running/);
  assert.match(html, /waiting_input/);
});
```

- [ ] **Step 2: Run the inbox test and verify it fails**

Run:

```bash
cd frontend
npm test -- conversation-inbox.test.mjs
```

Expected: FAIL with an esbuild error that `ConversationInbox` cannot be resolved.

- [ ] **Step 3: Implement `ConversationInbox`**

Create `frontend/src/features/sidebar/ConversationInbox.tsx`:

```tsx
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, relativeTime } from "@/lib/utils";

export interface ConversationInboxItem {
  thread: { id: string; title?: string | null };
  latest_run?: { status?: string; created_at?: string } | null;
  needs_attention?: boolean;
  research_degraded?: boolean;
  last_activity_at?: string | null;
}

export function ConversationInbox({
  items,
  activePath,
  locale,
  loading,
  emptyLabel,
}: {
  items: ConversationInboxItem[];
  activePath: string;
  locale: string;
  loading: boolean;
  emptyLabel: string;
}) {
  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-3 px-2 pb-3">
        {loading && (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}
        {items.length > 0 && <ConversationGroup label="Pinned" items={items.slice(0, 1)} activePath={activePath} locale={locale} />}
        {items.length > 1 && <ConversationGroup label="Recent" items={items.slice(1)} activePath={activePath} locale={locale} />}
        {items.length === 0 && !loading && (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">{emptyLabel}</p>
        )}
      </div>
    </ScrollArea>
  );
}

function ConversationGroup({
  label,
  items,
  activePath,
  locale,
}: {
  label: string;
  items: ConversationInboxItem[];
  activePath: string;
  locale: string;
}) {
  return (
    <section>
      <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="space-y-0.5">
        {items.map((item) => (
          <ConversationRow key={item.thread.id} item={item} activePath={activePath} locale={locale} />
        ))}
      </div>
    </section>
  );
}

function ConversationRow({
  item,
  activePath,
  locale,
}: {
  item: ConversationInboxItem;
  activePath: string;
  locale: string;
}) {
  const status = item.latest_run?.status;
  const href = `/threads/${item.thread.id}`;
  return (
    <Link
      to={href}
      className={cn(
        "flex flex-col gap-1 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-secondary",
        activePath === href && "bg-secondary",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-medium">{item.thread.title || item.thread.id}</span>
        {item.needs_attention && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-warning" />}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {status === "completed" && <CheckCircle2 className="h-3 w-3 text-success" />}
        {status === "running" && <Loader2 className="h-3 w-3 animate-spin text-accent" />}
        {status?.startsWith("waiting") && <AlertTriangle className="h-3 w-3 text-warning" />}
        <span className="truncate">{status ?? "idle"}</span>
        <span className="ml-auto shrink-0">{relativeTime(item.last_activity_at ?? item.latest_run?.created_at, locale)}</span>
      </div>
    </Link>
  );
}
```

- [ ] **Step 4: Use `ConversationInbox` in `Sidebar`**

In `frontend/src/features/sidebar/Sidebar.tsx`, import:

```ts
import { ConversationInbox, type ConversationInboxItem } from "./ConversationInbox";
```

Remove direct `ScrollArea`, `CheckCircle2`, `AlertTriangle`, and `Loader2` usage from the expanded conversation list if unused after the replacement.

Replace the expanded `<ScrollArea>` block with:

```tsx
<ConversationInbox
  items={items as ConversationInboxItem[]}
  activePath={location.pathname}
  locale={locale}
  loading={dashboardQuery.isLoading}
  emptyLabel={t("empty")}
/>
```

- [ ] **Step 5: Run tests and typecheck**

Run:

```bash
cd frontend
npm test -- conversation-inbox.test.mjs
npm test
npm run typecheck
```

Expected: all PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```bash
git add frontend/src/features/sidebar/ConversationInbox.tsx frontend/src/features/sidebar/Sidebar.tsx frontend/tests/conversation-inbox.test.mjs frontend/src/i18n/resources/en/common.json frontend/src/i18n/resources/zh/common.json
git commit -m "feat: add conversation inbox sidebar"
```

---

### Task 7: Responsive Layout, Visual Polish, and Browser Verification

**Files:**

- Modify: `frontend/src/AppShell.tsx`
- Modify: `frontend/src/features/conversation/ConversationPage.tsx`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`
- Modify: `frontend/src/features/inspection/RunCompanion.tsx`
- Modify: `frontend/src/index.css` only if a reusable layout utility is needed.

- [ ] **Step 1: Stabilize three-column layout sizing**

In `frontend/src/AppShell.tsx`, keep the outer layout fixed and prevent center overflow:

```tsx
return (
  <div className="flex h-full w-full overflow-hidden bg-muted/30">
    <ManagerDialogs>
      <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={() => setSidebarCollapsed((v) => !v)} />
    </ManagerDialogs>
    <div className="flex min-w-0 flex-1">
      <RouteContent
        runId={runId}
        onRunIdChange={setRunId}
        inspectionCollapsed={inspectionCollapsed}
        onToggleInspection={() => setInspectionCollapsed((v) => !v)}
      />
    </div>
  </div>
);
```

In `frontend/src/features/conversation/ConversationPage.tsx`, ensure the center panel is min-width safe:

```tsx
return (
  <div className="flex h-full min-w-0 flex-1 flex-col bg-background">
    <ConversationHeader
      title={threadQuery.data?.title}
      fallbackTitle={t("chat:newConversation")}
      runStatus={runStatus}
      streaming={streaming}
      modelName={activeRun?.harness_options?.model_profile_key ?? activeRun?.harness_options?.model}
      onRename={(title) => renameMutation.mutate(title)}
    />
    <div className="min-h-0 flex-1">
      <ChatPanel state={streamState} />
    </div>
    <ChatComposer
      threadId={threadId}
      activeRunId={activeRunId}
      onRunCreated={(id) => {
        onRunIdChange(id);
        qc.invalidateQueries({ queryKey: ["threads", threadId, "runs"] });
      }}
    />
  </div>
);
```

- [ ] **Step 2: Make the right companion responsive**

In `frontend/src/features/inspection/RunCompanion.tsx`, change the expanded aside class:

```tsx
<aside className="hidden w-[342px] shrink-0 flex-col border-l bg-card lg:flex">
```

Keep the collapsed rail visible on desktop:

```tsx
<aside className="hidden w-12 shrink-0 flex-col items-center gap-3 border-l bg-card py-3 lg:flex">
```

This makes the center chat primary on narrow screens. A bottom sheet can be added later when the repo already has a drawer primitive.

- [ ] **Step 3: Improve message width and text overflow**

In `frontend/src/features/chat/ChatPanel.tsx`, update message container classes:

```tsx
<div className={cn("max-w-[min(80%,42rem)] space-y-2", isUser && "items-end")}>
```

Keep message bubble text:

```tsx
<p className="whitespace-pre-wrap break-words">{message.content}</p>
```

Keep markdown wrapped in a parent with `min-w-0`:

```tsx
<div className="relative min-w-0">
  <Markdown variant="chat">{message.content}</Markdown>
  {message.streaming && (
    <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-accent align-text-bottom" />
  )}
</div>
```

- [ ] **Step 4: Run full frontend checks**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected: both PASS.

- [ ] **Step 5: Start or reuse the dev server**

If the user's server at `http://127.0.0.1:15173` is still running through `./scripts/run.sh`, do not start a second server. Use the existing URL.

If it is not running, start the frontend dev server:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 15173
```

Expected: Vite reports a local URL on port `15173`. If the port is occupied, use `15174`.

- [ ] **Step 6: Browser-verify key states**

Open the app in the in-app browser and check:

```txt
Desktop:
- left inbox visible;
- center chat readable;
- right Activity companion visible;
- composer controls do not dominate input;
- no text overlaps.

Collapsed left rail:
- icon rail remains usable;
- attention badge remains visible.

Collapsed right companion:
- center chat expands;
- run status remains discoverable.

Narrow viewport:
- center chat remains primary;
- hidden companion does not create horizontal scroll.

Run states:
- running;
- waiting input;
- approval needed when available;
- failed;
- completed.
```

- [ ] **Step 7: Commit Task 7**

Run:

```bash
git add frontend/src/AppShell.tsx frontend/src/features/conversation/ConversationPage.tsx frontend/src/features/chat/ChatPanel.tsx frontend/src/features/inspection/RunCompanion.tsx frontend/src/index.css
git commit -m "style: polish agent chat command center layout"
```

---

## Final Verification

Run:

```bash
cd frontend
npm test
npm run build
cd ../backend
uv run pytest
uv run python examples/file_report_agent.py
```

Expected:

- frontend tests pass;
- frontend build passes;
- backend tests pass;
- file report example completes.

Browser verification must confirm the implemented UI matches the approved command center design:

- three-column desktop layout;
- conversation inbox left side;
- chat transcript as the center focus;
- Activity-first run companion on the right;
- compact composer with Mode, Model, Skill, attachment, stop, and send controls;
- Files, Approvals, and Trace available as right-panel tabs;
- no duplicate waiting input cards;
- no layout resizing from long messages or status labels.

## Self-Review Notes

Spec coverage:

- Three-column Command Center: Tasks 2, 3, 4, 6, and 7.
- Conversation inbox: Task 6.
- Center transcript and composer: Tasks 4 and 5.
- Activity-first run companion: Tasks 1 and 3.
- Files, Approvals, Trace tabs: Task 3.
- Responsive collapse behavior: Task 7.
- Existing backend concepts and no workflow editor: preserved by frontend-only tasks.

Placeholder scan:

- This plan contains no unresolved placeholder markers or deferred implementation notes.

Type consistency:

- `RunStreamState`, `InlineRequest`, `TodoEntry`, and `ToolCallEntry` are imported from `useRunStream`.
- `buildRunActivity` and `buildRunCompanionBadges` are created in Task 1 and consumed in Tasks 3 and 4.
- `RunCompanion` receives the same run identifiers and workspace identifiers as `InspectionPanel`.
