# Agent Chat Quiet Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Quiet Chat Workbench UI refinement for the center conversation and right run companion.

**Architecture:** Keep the current three-column shell and existing backend contracts. Add small pure view helpers for composer summaries and right companion rail state, then wire those helpers into focused React component changes. Preserve capability boundaries by keeping tool execution, approval resolution, redaction, and trace inspection on existing API/router paths.

**Tech Stack:** React 19, TypeScript, Vite 6, Tailwind, shadcn/Radix primitives, lucide-react, TanStack Query, i18next, Node test runner, esbuild.

---

## File Structure

- Modify `frontend/src/features/chat/composerState.ts`
  - Add pure helper types/functions for the collapsed composer summary chip.
  - Keep mode, model, skill, and permission state independent from React.

- Modify `frontend/tests/chat-composer-options.test.mjs`
  - Add unit coverage for summary labels and permission fallback behavior.

- Modify `frontend/src/features/chat/ChatComposer.tsx`
  - Replace the always-visible Mode/Model/Skill/Permission row with a natural composer plus one summary chip.
  - Expand detailed controls only when the user opens the chip.
  - Keep send, stop, attach, slash command behavior, and run creation unchanged.

- Modify `frontend/src/i18n/resources/en/chat.json`
  - Add English strings for composer summary, context, and expanded controls.

- Modify `frontend/src/i18n/resources/zh/chat.json`
  - Add Chinese strings for the same UI.

- Create `frontend/src/features/inspection/runCompanionView.ts`
  - Add a pure helper for collapsed rail state: status icon tone, progress label, attention count, and tab badges.

- Create `frontend/tests/run-companion-view.test.mjs`
  - Unit test collapsed rail attention and progress projection.

- Modify `frontend/src/features/inspection/RunCompanion.tsx`
  - Use the new rail helper.
  - Remove rotated status text from collapsed state.
  - Show status icon, todo progress, attention badge, and expand affordance only.
  - Keep expanded tabs as Activity, Files, Approvals, Trace.

- Modify `frontend/src/features/chat/ToolCallCard.tsx`
  - Polish collapsed tool summaries so they read as compact inline execution cards.
  - Keep the expanded detail bounded and redaction-friendly.

- Modify `frontend/src/features/chat/ChatPanel.tsx`
  - Keep tool cards inline after messages, but make spacing match the quiet chat posture.
  - Ensure inline request cards remain visible action points.

## Implementation Tasks

### Task 1: Add Composer Summary Projection

**Files:**
- Modify: `frontend/src/features/chat/composerState.ts`
- Modify: `frontend/tests/chat-composer-options.test.mjs`

- [ ] **Step 1: Add failing tests for the collapsed summary helper**

Append these tests to `frontend/tests/chat-composer-options.test.mjs`:

```js
test("buildComposerSummaryParts returns readable defaults", async () => {
  const { buildComposerSummaryParts } = await loadChatComposerOptions();
  assert.deepEqual(
    buildComposerSummaryParts({
      mode: "auto",
      profileKey: "__default__",
      profileName: null,
      skillId: "__none__",
      skillName: null,
      permissionPolicy: "ask",
    }),
    {
      modeLabelKey: "chat:modeAuto",
      modeFallback: "Auto",
      modelLabel: "Default model",
      skillLabel: null,
      permissionLabelKey: "chat:permission.ask",
      permissionFallback: "Ask",
    },
  );
});

test("buildComposerSummaryLabel joins mode, model, skill, and permission", async () => {
  const { buildComposerSummaryLabel } = await loadChatComposerOptions();
  assert.equal(
    buildComposerSummaryLabel({
      modeLabel: "Plan",
      modelLabel: "MiniMax",
      skillLabel: "Research",
      permissionLabel: "Read-only",
    }),
    "Plan / MiniMax / Research / Read-only",
  );
});

test("buildComposerSummaryLabel omits empty skill", async () => {
  const { buildComposerSummaryLabel } = await loadChatComposerOptions();
  assert.equal(
    buildComposerSummaryLabel({
      modeLabel: "Auto",
      modelLabel: "Default model",
      skillLabel: null,
      permissionLabel: "Ask",
    }),
    "Auto / Default model / Ask",
  );
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
cd frontend
node --test tests/chat-composer-options.test.mjs
```

Expected: fails because `buildComposerSummaryParts` and `buildComposerSummaryLabel` are not exported.

- [ ] **Step 3: Implement composer summary helpers**

Add this to `frontend/src/features/chat/composerState.ts` after `PERMISSION_POLICIES`:

```ts
export interface ComposerSummaryInput {
  mode: string | null | undefined;
  profileKey: string | null | undefined;
  profileName: string | null | undefined;
  skillId: string | null | undefined;
  skillName: string | null | undefined;
  permissionPolicy: string | null | undefined;
}

export interface ComposerSummaryParts {
  modeLabelKey: string;
  modeFallback: string;
  modelLabel: string;
  skillLabel: string | null;
  permissionLabelKey: string;
  permissionFallback: string;
}

const MODE_LABELS: Record<ComposerMode, { labelKey: string; fallback: string }> = {
  auto: { labelKey: "chat:modeAuto", fallback: "Auto" },
  plan: { labelKey: "chat:modePlan", fallback: "Plan" },
  chat: { labelKey: "chat:modeChat", fallback: "Chat" },
};

export function buildComposerSummaryParts(input: ComposerSummaryInput): ComposerSummaryParts {
  const mode = normalizeComposerMode(input.mode);
  const permission = getPermissionPolicy(input.permissionPolicy);
  const profileKey = input.profileKey ?? "__default__";
  const skillId = input.skillId ?? "__none__";

  return {
    modeLabelKey: MODE_LABELS[mode].labelKey,
    modeFallback: MODE_LABELS[mode].fallback,
    modelLabel:
      profileKey === "__default__"
        ? "Default model"
        : input.profileName?.trim() || profileKey,
    skillLabel:
      skillId === "__none__"
        ? null
        : input.skillName?.trim() || skillId,
    permissionLabelKey: permission.labelKey,
    permissionFallback: permission.fallback,
  };
}

export function buildComposerSummaryLabel(input: {
  modeLabel: string;
  modelLabel: string;
  skillLabel: string | null;
  permissionLabel: string;
}): string {
  return [
    input.modeLabel,
    input.modelLabel,
    input.skillLabel,
    input.permissionLabel,
  ]
    .filter((part): part is string => Boolean(part))
    .join(" / ");
}
```

- [ ] **Step 4: Run focused tests and verify pass**

Run:

```bash
cd frontend
node --test tests/chat-composer-options.test.mjs
```

Expected: all tests in `chat-composer-options.test.mjs` pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add frontend/src/features/chat/composerState.ts frontend/tests/chat-composer-options.test.mjs
git commit -m "feat: add composer summary projection"
```

### Task 2: Implement Natural Composer With Summary Chip

**Files:**
- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`
- Test: `frontend/tests/chat-composer-options.test.mjs`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/i18n/resources/en/chat.json`, add these keys near the composer strings:

```json
"composerSummary": "Composer settings",
"composerContext": "Context",
"composerSettings": "Settings",
"defaultModel": "Default model",
"defaultSkill": "Default skill",
"expandComposerSettings": "Adjust mode, model, skill, and permission",
"collapseComposerSettings": "Hide composer settings"
```

In `frontend/src/i18n/resources/zh/chat.json`, add matching keys:

```json
"composerSummary": "输入设置",
"composerContext": "上下文",
"composerSettings": "设置",
"defaultModel": "默认模型",
"defaultSkill": "默认技能",
"expandComposerSettings": "调整模式、模型、技能和权限",
"collapseComposerSettings": "隐藏输入设置"
```

Keep JSON commas valid after inserting.

- [ ] **Step 2: Update imports in `ChatComposer.tsx`**

Change the lucide import:

```ts
import { AtSign, ChevronDown, ChevronUp, Paperclip, Send, ShieldCheck, Square } from "lucide-react";
```

Change the composerState import:

```ts
import {
  buildComposerHarnessOptions,
  buildComposerScopes,
  buildComposerSummaryLabel,
  buildComposerSummaryParts,
  type ComposerMode,
  type ComposerPermissionPolicyId,
  PERMISSION_POLICIES,
} from "./composerState";
```

- [ ] **Step 3: Add local expanded settings state and summary values**

Inside `ChatComposer`, near the existing state declarations, add:

```ts
const [settingsOpen, setSettingsOpen] = React.useState(false);
```

After `profilesQuery` and `skillsQuery`, add:

```ts
const selectedProfile = profilesQuery.data?.find((profile) => profile.key === profileKey);
const selectedSkill = skillsQuery.data?.find((skill) => skill.key === skillId);
const summaryParts = buildComposerSummaryParts({
  mode,
  profileKey,
  profileName: selectedProfile?.name ?? null,
  skillId,
  skillName: selectedSkill?.name ?? null,
  permissionPolicy,
});
const summaryLabel = buildComposerSummaryLabel({
  modeLabel: t(summaryParts.modeLabelKey, summaryParts.modeFallback),
  modelLabel:
    profileKey === "__default__"
      ? t("chat:defaultModel", summaryParts.modelLabel)
      : summaryParts.modelLabel,
  skillLabel: summaryParts.skillLabel,
  permissionLabel: t(summaryParts.permissionLabelKey, summaryParts.permissionFallback),
});
```

- [ ] **Step 4: Replace the composer control row**

In `ChatComposer.tsx`, replace the current `<div className="flex flex-wrap items-center gap-2 border-t bg-muted/30 px-2 py-2">...</div>` with:

```tsx
<div className="border-t bg-muted/30 px-2 py-2">
  <div className="flex items-center gap-2">
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-8 min-w-0 max-w-[min(22rem,60vw)] gap-1.5 px-2 text-xs"
      onClick={() => setSettingsOpen((open) => !open)}
      title={settingsOpen ? t("chat:collapseComposerSettings") : t("chat:expandComposerSettings")}
      aria-label={settingsOpen ? t("chat:collapseComposerSettings") : t("chat:expandComposerSettings")}
      aria-expanded={settingsOpen}
    >
      <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{summaryLabel}</span>
      {settingsOpen ? (
        <ChevronUp className="h-3.5 w-3.5 shrink-0" />
      ) : (
        <ChevronDown className="h-3.5 w-3.5 shrink-0" />
      )}
    </Button>
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      title={t("chat:composerContext")}
      aria-label={t("chat:composerContext")}
    >
      <AtSign className="h-4 w-4" />
    </Button>
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
        onClick={handleCancel}
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
  {settingsOpen && (
    <div className="mt-2 grid gap-2 border-t pt-2 sm:grid-cols-2 lg:grid-cols-4">
      <Select value={mode} onValueChange={(value) => setMode(value as ComposerMode)}>
        <SelectTrigger aria-label={t("chat:composerMode")} className="h-8 bg-background text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="auto">{t("chat:modeAuto")}</SelectItem>
          <SelectItem value="plan">{t("chat:modePlan")}</SelectItem>
          <SelectItem value="chat">{t("chat:modeChat")}</SelectItem>
        </SelectContent>
      </Select>
      <Select value={profileKey} onValueChange={setProfileKey}>
        <SelectTrigger aria-label={t("chat:selectModelProfile")} className="h-8 bg-background text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__default__">{t("chat:defaultModel")}</SelectItem>
          {profilesQuery.data?.map((p) => (
            <SelectItem key={p.key} value={p.key} disabled={!p.enabled}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={skillId} onValueChange={setSkillId}>
        <SelectTrigger aria-label={t("chat:selectSkill")} className="h-8 bg-background text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">{t("chat:defaultSkill")}</SelectItem>
          {skillsQuery.data?.map((s) => (
            <SelectItem key={s.key} value={s.key}>
              {s.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={permissionPolicy}
        onValueChange={(value) =>
          setPermissionPolicy(value as ComposerPermissionPolicyId)
        }
      >
        <SelectTrigger
          aria-label={t("chat:permission.label")}
          className="h-8 bg-background text-xs"
          title={t("chat:permission.label")}
        >
          <ShieldCheck className="mr-1 h-3.5 w-3.5" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PERMISSION_POLICIES.map((policy) => (
            <SelectItem key={policy.id} value={policy.id}>
              {t(policy.labelKey, policy.fallback)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )}
</div>
```

- [ ] **Step 5: Remove the duplicate hidden file input**

Delete the old hidden `<input ref={fileRef} type="file" ... />` from the previous control row if it remains after replacement. There must be exactly one file input in `ChatComposer.tsx`.

- [ ] **Step 6: Run focused tests and typecheck**

Run:

```bash
cd frontend
node --test tests/chat-composer-options.test.mjs
npm run typecheck
```

Expected: focused tests pass, TypeScript build check exits 0.

- [ ] **Step 7: Commit Task 2**

```bash
git add frontend/src/features/chat/ChatComposer.tsx frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json
git commit -m "feat: quiet composer controls"
```

### Task 3: Add Right Companion Rail Projection

**Files:**
- Create: `frontend/src/features/inspection/runCompanionView.ts`
- Create: `frontend/tests/run-companion-view.test.mjs`
- Test: `frontend/tests/run-companion-view.test.mjs`

- [ ] **Step 1: Write failing tests for rail projection**

Create `frontend/tests/run-companion-view.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunCompanionView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/inspection/runCompanionView.ts"],
    plugins: [
      {
        name: "run-companion-view-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/features\/chat\/runActivity$/ }, () => ({
            path: "mock-run-activity",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-run-activity$/, namespace: "mock" }, () => ({
            contents: `
              export function buildRunCompanionBadges(state) {
                return state.badges || { activity: 0, files: 0, approvals: 0, trace: 0 };
              }
            `,
            loader: "js",
          }));
        },
      },
    ],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("collapsed rail shows progress and no attention when quiet", async () => {
  const { buildRunCompanionRailView } = await loadRunCompanionView();
  const view = buildRunCompanionRailView({
    runStatus: "running",
    todoProgress: { done: 2, total: 5 },
    streamState: { badges: { activity: 0, files: 0, approvals: 0, trace: 0 } },
  });

  assert.equal(view.status, "running");
  assert.equal(view.statusTone, "live");
  assert.equal(view.progressLabel, "2/5");
  assert.equal(view.attentionCount, 0);
  assert.equal(view.hasAttention, false);
});

test("collapsed rail counts action attention but ignores passive files while running", async () => {
  const { buildRunCompanionRailView } = await loadRunCompanionView();
  const view = buildRunCompanionRailView({
    runStatus: "running",
    todoProgress: null,
    streamState: { badges: { activity: 1, files: 3, approvals: 2, trace: 1 } },
  });

  assert.equal(view.progressLabel, null);
  assert.equal(view.attentionCount, 4);
  assert.equal(view.hasAttention, true);
});

test("completed outputs can contribute attention", async () => {
  const { buildRunCompanionRailView } = await loadRunCompanionView();
  const view = buildRunCompanionRailView({
    runStatus: "completed",
    todoProgress: { done: 3, total: 3 },
    streamState: { badges: { activity: 0, files: 2, approvals: 0, trace: 0 } },
  });

  assert.equal(view.statusTone, "success");
  assert.equal(view.attentionCount, 2);
  assert.equal(view.hasAttention, true);
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
cd frontend
node --test tests/run-companion-view.test.mjs
```

Expected: fails because `runCompanionView.ts` does not exist.

- [ ] **Step 3: Implement the rail helper**

Create `frontend/src/features/inspection/runCompanionView.ts`:

```ts
import { buildRunCompanionBadges } from "@/features/chat/runActivity";
import type { RunStreamState } from "@/features/chat/useRunStream";

export type RunCompanionStatusTone =
  | "muted"
  | "live"
  | "waiting"
  | "success"
  | "danger"
  | "cancelled";

export interface RunCompanionRailView {
  status: string | null;
  statusTone: RunCompanionStatusTone;
  progressLabel: string | null;
  attentionCount: number;
  hasAttention: boolean;
}

export function buildRunCompanionRailView(input: {
  runStatus?: string | null;
  todoProgress?: { done: number; total: number } | null;
  streamState: RunStreamState;
}): RunCompanionRailView {
  const badges = buildRunCompanionBadges(input.streamState);
  const actionAttention = badges.activity + badges.approvals + badges.trace;
  const outputAttention = input.runStatus === "completed" ? badges.files : 0;
  const attentionCount = actionAttention + outputAttention;
  const total = input.todoProgress?.total ?? 0;

  return {
    status: input.runStatus ?? null,
    statusTone: statusTone(input.runStatus),
    progressLabel:
      total > 0 && input.todoProgress
        ? `${input.todoProgress.done}/${input.todoProgress.total}`
        : null,
    attentionCount,
    hasAttention: attentionCount > 0,
  };
}

function statusTone(status?: string | null): RunCompanionStatusTone {
  if (status === "running" || status === "queued") return "live";
  if (
    status === "waiting_input" ||
    status === "waiting_approval" ||
    status === "waiting_external" ||
    status === "paused"
  ) {
    return "waiting";
  }
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "cancelled";
  return "muted";
}
```

- [ ] **Step 4: Run focused tests and verify pass**

Run:

```bash
cd frontend
node --test tests/run-companion-view.test.mjs
```

Expected: all tests in `run-companion-view.test.mjs` pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add frontend/src/features/inspection/runCompanionView.ts frontend/tests/run-companion-view.test.mjs
git commit -m "feat: add quiet companion rail projection"
```

### Task 4: Implement Quiet Right Companion Rail

**Files:**
- Modify: `frontend/src/features/inspection/RunCompanion.tsx`
- Test: `frontend/tests/run-companion-view.test.mjs`

- [ ] **Step 1: Update imports**

In `RunCompanion.tsx`, replace the lucide import with:

```ts
import type * as React from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  FileText,
  GitBranch,
  PanelRightClose,
  PanelRightOpen,
  ShieldCheck,
} from "lucide-react";
```

Add:

```ts
import { cn } from "@/lib/utils";
import { buildRunCompanionRailView } from "./runCompanionView";
```

- [ ] **Step 2: Build rail view**

Inside `RunCompanion`, after `badges`:

```ts
const railView = buildRunCompanionRailView({
  runStatus,
  todoProgress,
  streamState,
});
```

- [ ] **Step 3: Replace collapsed rail JSX**

Replace the current `if (collapsed) { return (...) }` block with:

```tsx
if (collapsed) {
  return (
    <aside
      className={cn(
        "hidden w-12 shrink-0 flex-col items-center gap-3 border-l bg-card py-3 lg:flex",
        railView.hasAttention && "bg-warning/5",
      )}
    >
      <Button variant="ghost" size="icon" onClick={onToggle} title={t("inspection:expand")}>
        <PanelRightOpen className="h-4 w-4" />
      </Button>
      <div
        className={cn(
          "relative flex h-8 w-8 items-center justify-center rounded-full border",
          railToneClass(railView.statusTone),
        )}
        title={railView.status ? t(`common:status.${railView.status}`, { defaultValue: railView.status }) : undefined}
      >
        <RailStatusIcon tone={railView.statusTone} />
        {railView.attentionCount > 0 && (
          <Badge
            variant="secondary"
            className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]"
          >
            {railView.attentionCount > 9 ? "9+" : railView.attentionCount}
          </Badge>
        )}
      </div>
      {railView.progressLabel && (
        <div className="rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          {railView.progressLabel}
        </div>
      )}
    </aside>
  );
}
```

- [ ] **Step 4: Add rail icon helpers**

Append these helper functions below `CompanionTab`:

```tsx
function RailStatusIcon({ tone }: { tone: ReturnType<typeof buildRunCompanionRailView>["statusTone"] }) {
  if (tone === "live") return <Activity className="h-4 w-4" />;
  if (tone === "waiting") return <Clock3 className="h-4 w-4" />;
  if (tone === "success") return <CheckCircle2 className="h-4 w-4" />;
  if (tone === "danger") return <AlertTriangle className="h-4 w-4" />;
  return <Circle className="h-4 w-4" />;
}

function railToneClass(tone: ReturnType<typeof buildRunCompanionRailView>["statusTone"]): string {
  const classes = {
    muted: "border-border text-muted-foreground",
    live: "border-accent/30 bg-accent/10 text-accent",
    waiting: "border-warning/40 bg-warning/10 text-warning",
    success: "border-success/30 bg-success/10 text-success",
    danger: "border-destructive/35 bg-destructive/10 text-destructive",
    cancelled: "border-border bg-muted text-muted-foreground",
  };
  return classes[tone];
}
```

- [ ] **Step 5: Run focused tests and typecheck**

Run:

```bash
cd frontend
node --test tests/run-companion-view.test.mjs
npm run typecheck
```

Expected: focused tests pass, TypeScript build check exits 0.

- [ ] **Step 6: Commit Task 4**

```bash
git add frontend/src/features/inspection/RunCompanion.tsx
git commit -m "feat: quiet companion collapsed rail"
```

### Task 5: Polish Inline Tool Cards For Quiet Chat

**Files:**
- Modify: `frontend/src/features/chat/ToolCallCard.tsx`
- Modify: `frontend/src/features/chat/ChatPanel.tsx`

- [ ] **Step 1: Update collapsed card layout**

In `ToolCallCard.tsx`, change the outer class to keep the card compact:

```tsx
className={cn(
  "rounded-md border bg-muted/25 text-sm shadow-none",
  entry.status === "denied" && "border-destructive/30 bg-destructive/5",
  entry.status === "failed" && "border-destructive/30 bg-destructive/5",
)}
```

Change the button class:

```tsx
className="flex w-full min-w-0 items-center gap-2 px-3 py-1.5 text-left"
```

Change the tool name span:

```tsx
<span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">
  {entry.toolName}
</span>
```

Move `entry.error` into a second line in the collapsed content by adding this after `</button>`:

```tsx
{!open && (entry.outputSummary || entry.inputSummary || entry.error) && (
  <div className="border-t px-3 py-1.5 text-xs text-muted-foreground">
    <span className={cn("line-clamp-1", entry.error && "text-destructive")}>
      {entry.error || entry.outputSummary || entry.inputSummary}
    </span>
  </div>
)}
```

Remove the old inline error span:

```tsx
{entry.error && <span className="ml-auto truncate text-xs text-destructive">{entry.error}</span>}
```

- [ ] **Step 2: Keep expanded details bounded**

In the open detail section, change:

```tsx
<div className="space-y-2 border-t px-3 py-2">
```

to:

```tsx
<div className="max-h-80 space-y-2 overflow-y-auto border-t px-3 py-2">
```

- [ ] **Step 3: Tighten ChatPanel tool group spacing**

In `ChatPanel.tsx`, change:

```tsx
<div className="mx-auto max-w-3xl space-y-2 px-4 py-2">
```

to:

```tsx
<div className="mx-auto max-w-3xl space-y-1.5 px-4 py-1.5">
```

- [ ] **Step 4: Run typecheck**

Run:

```bash
cd frontend
npm run typecheck
```

Expected: TypeScript build check exits 0.

- [ ] **Step 5: Commit Task 5**

```bash
git add frontend/src/features/chat/ToolCallCard.tsx frontend/src/features/chat/ChatPanel.tsx
git commit -m "style: quiet inline tool cards"
```

### Task 6: Verify Quiet Workbench End-To-End

**Files:**
- All frontend files changed in Tasks 1-5.

- [ ] **Step 1: Run frontend unit tests**

Run:

```bash
cd frontend
npm test
```

Expected: all `frontend/tests/*.test.mjs` tests pass.

- [ ] **Step 2: Run frontend typecheck**

Run:

```bash
cd frontend
npm run typecheck
```

Expected: TypeScript build check exits 0.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: Vite build completes and writes `frontend/dist`.

- [ ] **Step 4: Start the local frontend**

Run:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a localhost URL. Keep the server running for visual checks.

- [ ] **Step 5: Browser visual QA**

Open the Vite URL and inspect a thread page with no active run, a running run, a waiting approval/input state, and a completed run if local fixtures make them available.

Check:

- center chat remains visually dominant;
- composer default shows one summary chip, context button, attach, send, and stop only when active;
- expanding the summary chip reveals Mode, Model, Skill, Permission;
- right companion starts collapsed on desktop;
- collapsed rail has no rotated text;
- collapsed rail shows status icon, todo progress, and attention badge;
- approvals/input/failure appear inline in the chat and do not auto-expand the right panel;
- expanded right companion has Activity, Files, Approvals, Trace only;
- tool calls appear as compact collapsed cards in the transcript;
- long model, skill, file, and tool names truncate instead of shifting layout.

- [ ] **Step 6: Stop the local frontend server**

Stop the dev server with `Ctrl-C`.

- [ ] **Step 7: Record verification outcome**

If every command and visual check passes, record the passing commands in the final handoff.
If any check fails, stop implementation and write the exact failing command, browser state,
or visual defect before adding a new focused fix task. Do not make broad polish changes outside
the files listed in this plan.

## Self-Review Checklist

- Spec coverage:
  - Chat-first center surface: Task 5 and visual QA.
  - Tool calls collapsed inline: Task 5.
  - Inline action cards remain central: Task 5 visual QA confirms existing `InlineRequestCard` behavior is preserved.
  - Natural composer plus summary chip: Tasks 1 and 2.
  - Detailed Mode/Model/Skill/Permission controls behind summary chip: Task 2.
  - Right companion collapsed by default and quiet: Tasks 3 and 4.
  - Right expanded tabs remain Activity, Files, Approvals, Trace: Task 4 preserves current tab list, Task 6 verifies.
  - No auto-expand behavior: Task 4 avoids adding auto-open behavior, Task 6 verifies.
  - Redaction/capability boundary preserved: plan does not change API execution paths or raw payload routing.

- Placeholder scan:
  - No implementation task relies on unspecified files or deferred behavior.
  - Each code-changing step includes exact code to add or replace.

- Type consistency:
  - `buildComposerSummaryParts` and `buildComposerSummaryLabel` are defined before component usage.
  - `buildRunCompanionRailView` is defined before component usage.
  - `RunCompanionRailView.statusTone` values match `railToneClass` keys.
