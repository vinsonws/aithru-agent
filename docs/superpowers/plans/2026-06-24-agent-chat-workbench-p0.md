# Agent Chat Workbench P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build P0 of the Agent Chat Workbench: a reliable chat task loop with goal visibility, slash command MVP, permission policy selection, consistent run controls, and shared product state across inbox/header/composer/companion.

**Architecture:** Keep the existing three-column shell and current backend APIs. Add small pure projection helpers for composer state, slash commands, permission scopes, and the run goal bar; React components consume those helpers instead of duplicating state logic. P0 is frontend-first and uses existing `CreateRunRequest.scopes` plus existing `harness_options.instructions`; it does not add workflow semantics or bypass the capability router.

**Tech Stack:** React, TypeScript, Vite, TanStack Query, lucide-react, existing UI primitives, i18next JSON resources, Node `node:test`, esbuild fixture tests, and Vite build verification.

---

## Scope Check

The full design in `docs/superpowers/specs/2026-06-24-agent-chat-workbench-p0-p3-design.md` covers four product phases. This plan implements **P0 only** because P1-P3 introduce separate subsystems: execution timeline, files/diff/artifacts/output review, and capability/multi-task management.

P0 must ship as a complete slice:

- user starts a task from chat;
- user sees goal, mode, model, skill, permission, and run status;
- user can stop, reply, review approval, retry, or open settings from consistent actions;
- slash commands provide local command behavior;
- selected permission policy maps to run scopes without exposing secrets;
- no workflow graph/editor behavior is introduced.

## Current Context

Relevant existing files:

- `frontend/src/features/chat/ChatComposer.tsx`
  - currently owns mode, model profile, skill selection, run creation, stop button, and prompt templates.
  - currently exports `buildComposerHarnessOptions`.
  - currently always sends `scopes: ["*"]`.
- `frontend/src/features/conversation/ConversationPage.tsx`
  - composes `ConversationHeader`, `ChatPanel`, and `ChatComposer`.
  - owns composer draft and focus behavior.
  - maps header actions to cancel, reply focus, trace, settings, follow-up, and retry.
- `frontend/src/features/conversation/ConversationHeader.tsx`
  - renders title, status chip, model chip, and state-specific actions.
- `frontend/src/features/conversation/runHeaderView.ts`
  - builds header view model from thread/run/stream state.
  - already infers mode from `[Aithru mode: ...]` instructions.
- `frontend/src/features/chat/runStatusCopy.ts`
  - maps backend run statuses to product copy and primary actions.
- `frontend/src/features/chat/runActivity.ts`
  - projects stream state into activity narrative and companion badges.
- `frontend/src/features/inspection/RunCompanion.tsx`
  - renders Activity, Files, Approvals, and Trace tabs.
- `frontend/src/i18n/resources/en/chat.json`
- `frontend/src/i18n/resources/zh/chat.json`

Relevant backend/frontend contract facts:

- `CreateRunRequest` has `goal`, `org_id`, `actor_user_id`, `scopes`, `harness_options`, `thread_id`, `selected_skill_keys`, `wait_for_completion`, and `persist_goal_message`.
- `CreateRunRequest` does not currently expose a generic `metadata` field in the generated frontend schema.
- `AgentRun` has `goal`, `scopes`, `selected_skill_keys`, `harness_options`, `status`, `error`, and workspace/run identifiers.
- `AgentRunHarnessOptions` has `model`, `model_profile_key`, `instructions`, model capability/cost/budget fields, research continuation, and operator follow-up options.
- Local tool scopes already include values such as `agent.workspace.read`, `agent.workspace.write`, `agent.todo.write`, `agent.artifact.write`, `agent.input.write`, `agent.research.write`, and memory scopes.

## Target File Structure

Create:

- `frontend/src/features/chat/composerState.ts`
  - pure helpers for mode instructions, permission policy definitions, run scopes, and harness options.
- `frontend/src/features/chat/slashCommands.ts`
  - pure parser for `/plan`, `/status`, `/retry`, and `/clear`.
- `frontend/src/features/conversation/runTaskLoopView.ts`
  - pure projection for the P0 goal bar.
- `frontend/src/features/conversation/RunGoalBar.tsx`
  - visual goal/status/current-step bar between the header and transcript.
- `frontend/tests/composer-state.test.mjs`
- `frontend/tests/slash-commands.test.mjs`
- `frontend/tests/run-task-loop-view.test.mjs`

Modify:

- `frontend/src/features/chat/ChatComposer.tsx`
- `frontend/src/features/conversation/ConversationPage.tsx`
- `frontend/src/features/conversation/ConversationHeader.tsx`
- `frontend/src/features/conversation/runHeaderView.ts`
- `frontend/src/i18n/resources/en/chat.json`
- `frontend/src/i18n/resources/zh/chat.json`
- `frontend/tests/chat-composer-options.test.mjs`
- `frontend/tests/run-header-view.test.mjs`
- `frontend/tests/chat-i18n-usage.test.mjs`

Do not modify backend code for P0 unless implementation discovers the generated frontend API schema is stale. If that happens, regenerate schema through the repo's existing process and keep the backend contract unchanged.

## Design Guardrails

- Do not store API keys, model secrets, base URLs, tokens, or credentials in run metadata, harness options, i18n strings, UI labels, or tests.
- Do not add an Agent workflow graph, workflow editor, drag-and-drop plan nodes, or persisted AgentPlan-as-workflow semantics.
- Do not execute tools directly from the frontend. Permission policy selection only changes the requested run scopes; actual tool authorization remains behind the backend capability router.
- Keep the UI language product-level. Raw IDs may remain in subdued secondary sublines but not as primary titles.
- Keep P0 interactions honest. `/status` should open or focus the Activity view; it should not pretend to query a backend status summary that does not exist yet.
- Use existing i18n namespaces and add every visible string to `chat.json`.

---

## Task 1: Extract Composer State Helpers

**Files:**

- Create: `frontend/src/features/chat/composerState.ts`
- Create: `frontend/tests/composer-state.test.mjs`
- Modify: `frontend/tests/chat-composer-options.test.mjs`

### Purpose

Move mode instructions and permission policy scope mapping into a pure helper so the composer, header, and goal bar can share the same state vocabulary.

### Permission Policy Definitions

P0 policies:

- `ask`: write-capable task policy that grants common Aithru agent scopes while backend approval policy still controls risky actions.
- `auto_safe`: broad policy for local development and trusted runs, represented as `["*"]`.
- `read_only`: read and memory scopes only.

The labels are UI policy labels, not a replacement for backend approval enforcement.

- [ ] **Step 1: Write the failing composer state tests**

Create `frontend/tests/composer-state.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadComposerState() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/composerState.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("auto mode without a model profile omits harness options", async () => {
  const { buildComposerHarnessOptions } = await loadComposerState();
  assert.equal(buildComposerHarnessOptions("__default__", "auto"), undefined);
});

test("plan mode adds instructions and preserves selected model profile", async () => {
  const { buildComposerHarnessOptions } = await loadComposerState();
  const options = buildComposerHarnessOptions("MiniMax-M2.7", "plan");

  assert.equal(options.model_profile_key, "MiniMax-M2.7");
  assert.match(options.instructions, /Aithru mode: plan/);
});

test("chat mode adds chat instructions", async () => {
  const { buildComposerHarnessOptions } = await loadComposerState();
  const options = buildComposerHarnessOptions("__default__", "chat");

  assert.match(options.instructions, /Aithru mode: chat/);
});

test("read only permission policy grants only read-oriented scopes", async () => {
  const { buildComposerScopes } = await loadComposerState();
  assert.deepEqual(buildComposerScopes("read_only"), [
    "agent.workspace.read",
    "agent.memory.read",
  ]);
});

test("ask permission policy grants common task scopes without wildcard", async () => {
  const { buildComposerScopes } = await loadComposerState();
  const scopes = buildComposerScopes("ask");

  assert.ok(scopes.includes("agent.workspace.read"));
  assert.ok(scopes.includes("agent.workspace.write"));
  assert.ok(scopes.includes("agent.todo.write"));
  assert.ok(scopes.includes("agent.artifact.write"));
  assert.ok(scopes.includes("agent.input.write"));
  assert.ok(!scopes.includes("*"));
});

test("auto safe permission policy uses wildcard scope for trusted local runs", async () => {
  const { buildComposerScopes } = await loadComposerState();
  assert.deepEqual(buildComposerScopes("auto_safe"), ["*"]);
});

test("permission policy can be inferred from persisted run scopes", async () => {
  const { inferPermissionPolicyFromScopes } = await loadComposerState();

  assert.equal(inferPermissionPolicyFromScopes(["*"]), "auto_safe");
  assert.equal(
    inferPermissionPolicyFromScopes(["agent.workspace.read", "agent.memory.read"]),
    "read_only",
  );
  assert.equal(
    inferPermissionPolicyFromScopes(["agent.workspace.read", "agent.workspace.write"]),
    "ask",
  );
});

test("unknown permission policy falls back to ask", async () => {
  const { normalizePermissionPolicyId } = await loadComposerState();
  assert.equal(normalizePermissionPolicyId("bad-value"), "ask");
  assert.equal(normalizePermissionPolicyId(null), "ask");
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd frontend
npm test -- composer-state
```

Expected: failure because `frontend/src/features/chat/composerState.ts` does not exist.

- [ ] **Step 3: Implement composer state helpers**

Create `frontend/src/features/chat/composerState.ts`:

```ts
import type { AgentRunHarnessOptions } from "@/lib/api";

export type ComposerMode = "auto" | "plan" | "chat";
export type ComposerPermissionPolicyId = "ask" | "auto_safe" | "read_only";

export interface ComposerPermissionPolicy {
  id: ComposerPermissionPolicyId;
  labelKey: string;
  fallback: string;
  descriptionKey: string;
  fallbackDescription: string;
  scopes: string[];
}

export const MODE_INSTRUCTIONS: Record<ComposerMode, string | null> = {
  auto: null,
  plan: "[Aithru mode: plan]\nWork in planning mode. Produce a clear implementation plan before making changes.",
  chat: "[Aithru mode: chat]\nWork in chat mode. Answer directly and avoid taking tool-driven actions unless the user asks for execution.",
};

export const PERMISSION_POLICIES: ComposerPermissionPolicy[] = [
  {
    id: "ask",
    labelKey: "chat:permission.ask",
    fallback: "Ask",
    descriptionKey: "chat:permission.askDescription",
    fallbackDescription: "Allow common task tools while backend approval policy gates risky actions.",
    scopes: [
      "agent.workspace.read",
      "agent.workspace.write",
      "agent.todo.write",
      "agent.artifact.write",
      "agent.research.write",
      "agent.input.write",
      "agent.memory.read",
    ],
  },
  {
    id: "auto_safe",
    labelKey: "chat:permission.autoSafe",
    fallback: "Auto-safe",
    descriptionKey: "chat:permission.autoSafeDescription",
    fallbackDescription: "Trusted local mode that requests broad capability access.",
    scopes: ["*"],
  },
  {
    id: "read_only",
    labelKey: "chat:permission.readOnly",
    fallback: "Read-only",
    descriptionKey: "chat:permission.readOnlyDescription",
    fallbackDescription: "Inspect workspace and memory without write scopes.",
    scopes: ["agent.workspace.read", "agent.memory.read"],
  },
];

const PERMISSION_POLICY_IDS = new Set(PERMISSION_POLICIES.map((policy) => policy.id));

export function normalizeComposerMode(value: string | null | undefined): ComposerMode {
  return value === "plan" || value === "chat" || value === "auto" ? value : "auto";
}

export function normalizePermissionPolicyId(
  value: string | null | undefined,
): ComposerPermissionPolicyId {
  return PERMISSION_POLICY_IDS.has(value as ComposerPermissionPolicyId)
    ? (value as ComposerPermissionPolicyId)
    : "ask";
}

export function getPermissionPolicy(
  value: string | null | undefined,
): ComposerPermissionPolicy {
  const id = normalizePermissionPolicyId(value);
  return PERMISSION_POLICIES.find((policy) => policy.id === id) ?? PERMISSION_POLICIES[0];
}

export function buildComposerHarnessOptions(
  profileKey: string | null,
  mode: string,
): AgentRunHarnessOptions | undefined {
  const normalizedMode = normalizeComposerMode(mode);
  const harnessOptions: AgentRunHarnessOptions = {};
  if (profileKey && profileKey !== "__default__") {
    harnessOptions.model_profile_key = profileKey;
  }
  const instructions = MODE_INSTRUCTIONS[normalizedMode];
  if (instructions) {
    harnessOptions.instructions = instructions;
  }
  return Object.keys(harnessOptions).length > 0 ? harnessOptions : undefined;
}

export function buildComposerScopes(policyId: string | null | undefined): string[] {
  return [...getPermissionPolicy(policyId).scopes];
}

export function inferPermissionPolicyFromScopes(
  scopes: string[] | null | undefined,
): ComposerPermissionPolicyId {
  const normalized = new Set(scopes ?? []);
  if (normalized.has("*")) return "auto_safe";
  const hasWrite = [...normalized].some((scope) => scope.endsWith(".write"));
  if (hasWrite) return "ask";
  if (normalized.has("agent.workspace.read") || normalized.has("agent.memory.read")) return "read_only";
  return "ask";
}

export function permissionPolicyLabelKey(policyId: string | null | undefined): string {
  return getPermissionPolicy(policyId).labelKey;
}
```

- [ ] **Step 4: Update existing composer options test to import the helper**

Modify `frontend/tests/chat-composer-options.test.mjs` so `loadChatComposerOptions()` loads `src/features/chat/composerState.ts` instead of `src/features/chat/ChatComposer.tsx`.

Replace:

```js
entryPoints: ["src/features/chat/ChatComposer.tsx"],
plugins: [
  {
    name: "chat-composer-options-mocks",
    setup(build) {
      ...
    },
  },
],
```

with:

```js
entryPoints: ["src/features/chat/composerState.ts"],
```

Remove the mock plugin from that test file because `composerState.ts` is a pure helper with no React dependency.

- [ ] **Step 5: Run helper tests**

Run:

```bash
cd frontend
npm test -- composer-state chat-composer-options
```

Expected: both test files pass.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add frontend/src/features/chat/composerState.ts frontend/tests/composer-state.test.mjs frontend/tests/chat-composer-options.test.mjs
git commit -m "feat: add chat composer state helpers"
```

---

## Task 2: Add Slash Command MVP

**Files:**

- Create: `frontend/src/features/chat/slashCommands.ts`
- Create: `frontend/tests/slash-commands.test.mjs`
- Modify: `frontend/src/features/chat/ChatComposer.tsx`

### Purpose

Support `/plan`, `/status`, `/retry`, and `/clear` without introducing a backend command runtime. Commands either transform the current composer state or call a local UI action.

### Command Behavior

- `/plan Fix login` sends `Fix login` with mode override `plan`.
- `/plan` with no body becomes local draft text `Plan the task before making changes.` and mode override `plan`.
- `/status` does not create a run. It asks the page to focus the Activity companion tab.
- `/retry` with an active run goal sets the draft to `Retry this task: <goal>`.
- `/retry` without an active run goal sets the draft to `Retry the last task with the same intent.`
- `/clear` clears the composer and does not create a run.
- Any unknown slash command is treated as normal text so the user can still send it.

- [ ] **Step 1: Write the failing slash command tests**

Create `frontend/tests/slash-commands.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadSlashCommands() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/slashCommands.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

test("/plan with body sends body in plan mode", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/plan Fix login", { activeRunGoal: null }), {
    kind: "send",
    goal: "Fix login",
    modeOverride: "plan",
  });
});

test("/plan without body sets a planning draft", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/plan", { activeRunGoal: null }), {
    kind: "draft",
    draft: "Plan the task before making changes.",
    modeOverride: "plan",
  });
});

test("/status focuses activity instead of creating a run", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/status", { activeRunGoal: "Fix login" }), {
    kind: "local",
    action: "status",
  });
});

test("/retry uses the active run goal when available", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/retry", { activeRunGoal: "Fix login" }), {
    kind: "draft",
    draft: "Retry this task: Fix login",
  });
});

test("/retry without active run goal uses generic retry draft", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/retry", { activeRunGoal: null }), {
    kind: "draft",
    draft: "Retry the last task with the same intent.",
  });
});

test("/clear clears composer locally", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/clear", { activeRunGoal: null }), {
    kind: "local",
    action: "clear",
  });
});

test("unknown slash command is normal text", async () => {
  const { parseSlashCommand } = await loadSlashCommands();
  assert.deepEqual(parseSlashCommand("/unknown do something", { activeRunGoal: null }), {
    kind: "send",
    goal: "/unknown do something",
  });
});
```

- [ ] **Step 2: Run the slash command test and verify it fails**

Run:

```bash
cd frontend
npm test -- slash-commands
```

Expected: failure because `frontend/src/features/chat/slashCommands.ts` does not exist.

- [ ] **Step 3: Implement slash command parser**

Create `frontend/src/features/chat/slashCommands.ts`:

```ts
import type { ComposerMode } from "./composerState";

export type SlashCommandResult =
  | { kind: "send"; goal: string; modeOverride?: ComposerMode }
  | { kind: "draft"; draft: string; modeOverride?: ComposerMode }
  | { kind: "local"; action: "status" | "clear" };

export interface SlashCommandContext {
  activeRunGoal?: string | null;
}

export function parseSlashCommand(
  rawInput: string,
  context: SlashCommandContext,
): SlashCommandResult {
  const input = rawInput.trim();
  if (!input.startsWith("/")) return { kind: "send", goal: input };

  const [commandToken, ...rest] = input.split(/\s+/);
  const command = commandToken.toLowerCase();
  const body = rest.join(" ").trim();

  if (command === "/plan") {
    if (body) return { kind: "send", goal: body, modeOverride: "plan" };
    return {
      kind: "draft",
      draft: "Plan the task before making changes.",
      modeOverride: "plan",
    };
  }

  if (command === "/status") {
    return { kind: "local", action: "status" };
  }

  if (command === "/retry") {
    return {
      kind: "draft",
      draft: context.activeRunGoal
        ? `Retry this task: ${context.activeRunGoal}`
        : "Retry the last task with the same intent.",
    };
  }

  if (command === "/clear") {
    return { kind: "local", action: "clear" };
  }

  return { kind: "send", goal: input };
}
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
cd frontend
npm test -- slash-commands
```

Expected: pass.

- [ ] **Step 5: Wire slash command behavior into ChatComposer**

Modify `frontend/src/features/chat/ChatComposer.tsx`:

Import helpers:

```ts
import {
  buildComposerHarnessOptions,
  buildComposerScopes,
  type ComposerMode,
  type ComposerPermissionPolicyId,
  PERMISSION_POLICIES,
} from "./composerState";
import { parseSlashCommand } from "./slashCommands";
```

Remove the local `MODE_INSTRUCTIONS` constant and local `buildComposerHarnessOptions` export from `ChatComposer.tsx`.

Extend props:

```ts
activeRunGoal?: string | null;
onRequestStatus?: () => void;
```

Replace mode state:

```ts
const [mode, setMode] = React.useState<ComposerMode>("auto");
```

Add permission state:

```ts
const [permissionPolicy, setPermissionPolicy] =
  React.useState<ComposerPermissionPolicyId>("ask");
```

Change create mutation vars:

```ts
mutationFn: async (vars: {
  goal: string;
  skillId: string | null;
  profileKey: string | null;
  mode: ComposerMode;
  permissionPolicy: ComposerPermissionPolicyId;
}) => {
  const harnessOptions = buildComposerHarnessOptions(vars.profileKey, vars.mode);
  const body: CreateRunRequest = {
    goal: vars.goal,
    org_id: context.org?.id ?? "org_1",
    actor_user_id: context.user?.id ?? "user_1",
    scopes: buildComposerScopes(vars.permissionPolicy),
    thread_id: threadId,
    selected_skill_keys: vars.skillId,
    harness_options: harnessOptions ?? null,
    wait_for_completion: false,
    persist_goal_message: true,
  };
  const run = await runsApi.create(body);
  return run;
}
```

Change `handleSend` before mutation:

```ts
const handleSend = () => {
  const trimmed = goal.trim();
  if (!trimmed || createRun.isPending) return;

  const command = parseSlashCommand(trimmed, { activeRunGoal });
  if (command.kind === "local") {
    if (command.action === "clear") setGoal("");
    if (command.action === "status") onRequestStatus?.();
    return;
  }
  if (command.kind === "draft") {
    setGoal(command.draft);
    if (command.modeOverride) setMode(command.modeOverride);
    textareaRef.current?.focus();
    return;
  }

  const nextMode = command.modeOverride ?? mode;
  createRun.mutate({
    goal: command.goal,
    skillId: skillId === "__none__" ? null : skillId,
    profileKey,
    mode: nextMode,
    permissionPolicy,
  });
  setGoal("");
  if (command.modeOverride) setMode(command.modeOverride);
};
```

- [ ] **Step 6: Run composer-related tests**

Run:

```bash
cd frontend
npm test -- slash-commands composer-state chat-composer-options
```

Expected: pass.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add frontend/src/features/chat/slashCommands.ts frontend/tests/slash-commands.test.mjs frontend/src/features/chat/ChatComposer.tsx
git commit -m "feat: add chat slash command MVP"
```

---

## Task 3: Add Permission Policy Control To Composer

**Files:**

- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`
- Modify: `frontend/tests/chat-i18n-usage.test.mjs`

### Purpose

Expose P0 permission policy as a compact composer control. The selection affects only requested run scopes; backend capability router and approval policy remain authoritative.

- [ ] **Step 1: Add i18n keys**

Modify `frontend/src/i18n/resources/en/chat.json`:

```json
{
  "permission": {
    "label": "Permission",
    "ask": "Ask",
    "askDescription": "Allow common task tools while backend approvals gate risky actions.",
    "autoSafe": "Auto-safe",
    "autoSafeDescription": "Trusted local mode that requests broad capability access.",
    "readOnly": "Read-only",
    "readOnlyDescription": "Inspect workspace and memory without write scopes."
  },
  "slashCommands": "Slash commands",
  "commandHint": "/plan, /status, /retry, /clear",
  "goalBar": {
    "goal": "Goal",
    "current": "Current",
    "permission": "Permission",
    "noCurrentStep": "Waiting for activity"
  }
}
```

Merge these keys into the existing JSON object rather than replacing existing keys.

Modify `frontend/src/i18n/resources/zh/chat.json`:

```json
{
  "permission": {
    "label": "权限",
    "ask": "询问",
    "askDescription": "允许常用任务工具，风险动作仍由后端审批拦截。",
    "autoSafe": "自动安全",
    "autoSafeDescription": "受信任的本地模式，请求较宽的能力范围。",
    "readOnly": "只读",
    "readOnlyDescription": "只检查工作区和记忆，不请求写入权限。"
  },
  "slashCommands": "斜杠命令",
  "commandHint": "/plan、/status、/retry、/clear",
  "goalBar": {
    "goal": "目标",
    "current": "当前",
    "permission": "权限",
    "noCurrentStep": "等待活动"
  }
}
```

- [ ] **Step 2: Render permission policy select**

In `frontend/src/features/chat/ChatComposer.tsx`, add `ShieldCheck` import:

```ts
import { Paperclip, Send, ShieldCheck, Square } from "lucide-react";
```

Inside the composer toolbar, after the skill selector, render:

```tsx
<Select
  value={permissionPolicy}
  onValueChange={(value) =>
    setPermissionPolicy(value as ComposerPermissionPolicyId)
  }
>
  <SelectTrigger
    aria-label={t("chat:permission.label")}
    className="h-7 w-[122px] border-0 bg-background text-xs shadow-sm"
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
```

Add a subtle command hint below the textarea and above the toolbar when the composer is not empty:

```tsx
{goal.trim().startsWith("/") && (
  <div className="border-t px-3 py-1 text-[11px] text-muted-foreground">
    {t("chat:commandHint")}
  </div>
)}
```

- [ ] **Step 3: Update i18n static coverage test**

Modify `frontend/tests/chat-i18n-usage.test.mjs` to include these key paths in the test's expected key list:

```js
[
  "permission.label",
  "permission.ask",
  "permission.autoSafe",
  "permission.readOnly",
  "commandHint",
  "goalBar.goal",
  "goalBar.current",
  "goalBar.permission",
  "goalBar.noCurrentStep",
]
```

- [ ] **Step 4: Run i18n and composer tests**

Run:

```bash
cd frontend
npm test -- chat-i18n-usage composer-state slash-commands
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add frontend/src/features/chat/ChatComposer.tsx frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json frontend/tests/chat-i18n-usage.test.mjs
git commit -m "feat: add composer permission policy control"
```

---

## Task 4: Add Run Goal Bar And Task Loop Projection

**Files:**

- Create: `frontend/src/features/conversation/runTaskLoopView.ts`
- Create: `frontend/src/features/conversation/RunGoalBar.tsx`
- Create: `frontend/tests/run-task-loop-view.test.mjs`
- Modify: `frontend/src/features/conversation/ConversationPage.tsx`
- Modify: `frontend/src/features/conversation/runHeaderView.ts`
- Modify: `frontend/tests/run-header-view.test.mjs`

### Purpose

Show the active task goal and current run loop state between the header and transcript. This gives P0 a visible task cockpit without turning the page into an IDE.

- [ ] **Step 1: Write failing task loop projection tests**

Create `frontend/tests/run-task-loop-view.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadRunTaskLoopView() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/conversation/runTaskLoopView.ts"],
    plugins: [
      {
        name: "run-task-loop-view-mocks",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/api$/ }, () => ({
            path: "mock-api",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/runActivity$/ }, () => ({
            path: "mock-run-activity",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\/features\/chat\/composerState$/ }, () => ({
            path: "mock-composer-state",
            namespace: "mock",
          }));
          build.onLoad({ filter: /^mock-api$/, namespace: "mock" }, () => ({
            contents: "export {};",
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-run-activity$/, namespace: "mock" }, () => ({
            contents: `
              export function buildRunActivity(state) {
                return state.activity;
              }
            `,
            loader: "js",
          }));
          build.onLoad({ filter: /^mock-composer-state$/, namespace: "mock" }, () => ({
            contents: `
              export function inferPermissionPolicyFromScopes(scopes) {
                if ((scopes || []).includes("*")) return "auto_safe";
                if ((scopes || []).some((scope) => scope.endsWith(".write"))) return "ask";
                return "read_only";
              }
              export function getPermissionPolicy(id) {
                const map = {
                  ask: { labelKey: "chat:permission.ask", fallback: "Ask" },
                  auto_safe: { labelKey: "chat:permission.autoSafe", fallback: "Auto-safe" },
                  read_only: { labelKey: "chat:permission.readOnly", fallback: "Read-only" },
                };
                return map[id] || map.ask;
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

function makeRun(overrides = {}) {
  return {
    id: "run_1234",
    goal: "Fix login",
    scopes: ["agent.workspace.read", "agent.workspace.write"],
    status: "running",
    harness_options: { model_profile_key: "MiniMax-M2.7" },
    ...overrides,
  };
}

test("returns null when there is no active run", async () => {
  const { buildRunTaskLoopView } = await loadRunTaskLoopView();
  const view = buildRunTaskLoopView({ activeRun: null, streamState: null, modeLabel: "Auto" });
  assert.equal(view, null);
});

test("projects goal, mode, permission, model, and current activity", async () => {
  const { buildRunTaskLoopView } = await loadRunTaskLoopView();
  const view = buildRunTaskLoopView({
    activeRun: makeRun(),
    modeLabel: "Auto",
    streamState: {
      activity: {
        narrative: { title: "Reading files", detail: "auth.ts" },
        progress: { done: 1, total: 3 },
      },
    },
  });

  assert.equal(view.goal, "Fix login");
  assert.equal(view.modeLabel, "Auto");
  assert.equal(view.permission.fallback, "Ask");
  assert.equal(view.modelLabel, "MiniMax-M2.7");
  assert.equal(view.currentTitle, "Reading files");
  assert.equal(view.currentDetail, "auth.ts");
  assert.deepEqual(view.progress, { done: 1, total: 3 });
});

test("uses read only permission label for read scopes", async () => {
  const { buildRunTaskLoopView } = await loadRunTaskLoopView();
  const view = buildRunTaskLoopView({
    activeRun: makeRun({ scopes: ["agent.workspace.read", "agent.memory.read"] }),
    modeLabel: "Plan",
    streamState: { activity: { narrative: { title: "Inspecting" }, progress: { done: 0, total: 0 } } },
  });

  assert.equal(view.permission.fallback, "Read-only");
});
```

- [ ] **Step 2: Run task loop projection test and verify it fails**

Run:

```bash
cd frontend
npm test -- run-task-loop-view
```

Expected: failure because `runTaskLoopView.ts` does not exist.

- [ ] **Step 3: Implement task loop projection**

Create `frontend/src/features/conversation/runTaskLoopView.ts`:

```ts
import type { AgentRun } from "@/lib/api";
import type { RunStreamState } from "@/features/chat/useRunStream";
import { buildRunActivity } from "@/features/chat/runActivity";
import { getPermissionPolicy, inferPermissionPolicyFromScopes } from "@/features/chat/composerState";

export interface RunTaskLoopView {
  goal: string;
  modeLabel: string;
  modelLabel: string;
  permission: {
    id: string;
    labelKey: string;
    fallback: string;
  };
  currentTitle: string;
  currentDetail?: string;
  progress: { done: number; total: number };
}

export function buildRunTaskLoopView(input: {
  activeRun?: AgentRun | null;
  streamState?: RunStreamState | null;
  modeLabel: string;
  defaultModelLabel?: string;
}): RunTaskLoopView | null {
  const { activeRun } = input;
  if (!activeRun) return null;

  const permissionId = inferPermissionPolicyFromScopes(activeRun.scopes);
  const permission = getPermissionPolicy(permissionId);
  const activity = input.streamState ? buildRunActivity(input.streamState) : null;

  return {
    goal: activeRun.goal,
    modeLabel: input.modeLabel,
    modelLabel:
      activeRun.harness_options?.model_profile_key ??
      activeRun.harness_options?.model ??
      input.defaultModelLabel ??
      "Default model",
    permission: {
      id: permission.id,
      labelKey: permission.labelKey,
      fallback: permission.fallback,
    },
    currentTitle: activity?.narrative.title ?? "Waiting for activity",
    currentDetail: activity?.narrative.detail,
    progress: activity?.progress ?? { done: 0, total: 0 },
  };
}
```

- [ ] **Step 4: Implement RunGoalBar component**

Create `frontend/src/features/conversation/RunGoalBar.tsx`:

```tsx
import { Activity, ShieldCheck, Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { RunTaskLoopView } from "./runTaskLoopView";

export function RunGoalBar({ view }: { view: RunTaskLoopView | null }) {
  const { t } = useTranslation("chat");
  if (!view) return null;

  const progressLabel =
    view.progress.total > 0 ? `${view.progress.done}/${view.progress.total}` : null;

  return (
    <div className="border-b bg-muted/20 px-4 py-2">
      <div className="mx-auto flex max-w-4xl items-center gap-2 overflow-hidden text-xs">
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border bg-card px-2.5 py-1.5 shadow-sm">
          <Target className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="shrink-0 font-medium text-muted-foreground">
            {t("goalBar.goal")}
          </span>
          <span className="truncate font-medium">{view.goal}</span>
        </div>
        <div className="hidden min-w-0 flex-[0.8] items-center gap-2 rounded-lg border bg-card px-2.5 py-1.5 shadow-sm md:flex">
          <Activity className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="shrink-0 font-medium text-muted-foreground">
            {t("goalBar.current")}
          </span>
          <span className="truncate">{view.currentTitle}</span>
          {progressLabel && (
            <span className="ml-auto rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {progressLabel}
            </span>
          )}
        </div>
        <div
          className={cn(
            "hidden items-center gap-1 rounded-lg border bg-card px-2.5 py-1.5 shadow-sm lg:flex",
          )}
          title={t(view.permission.labelKey, view.permission.fallback)}
        >
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
          <span>{t(view.permission.labelKey, view.permission.fallback)}</span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire RunGoalBar into ConversationPage**

Modify `frontend/src/features/conversation/ConversationPage.tsx` imports:

```ts
import { RunGoalBar } from "./RunGoalBar";
import { buildRunTaskLoopView } from "./runTaskLoopView";
```

Before `const view = buildRunHeaderView(...)`, add:

```ts
const modeLabel = modeLabelForRun(getRunMode(activeRun), t);
```

Use `modeLabel` in the existing `buildRunHeaderView` call:

```ts
const view = buildRunHeaderView({
  thread: threadQuery.data ?? null,
  activeRun: activeRun ?? null,
  streamStatus: streamState.status,
  streamError: streamState.error,
  threadId: threadId ?? "",
  modeLabel,
  defaultModelLabel: t("settings:defaultModel", "Default model"),
});
```

After `const view = buildRunHeaderView(...)`, add:

```ts
const goalBarView = buildRunTaskLoopView({
  activeRun: activeRun ?? null,
  streamState,
  modeLabel,
  defaultModelLabel: t("settings:defaultModel", "Default model"),
});
```

Render the goal bar directly after `ConversationHeader`:

```tsx
<ConversationHeader
  view={view}
  onRename={(title) => renameMutation.mutate(title)}
  onAction={handleHeaderAction}
/>
<RunGoalBar view={goalBarView} />
```

Pass the active run goal and status handler to composer:

```tsx
<ChatComposer
  threadId={threadId}
  activeRunId={activeRunId}
  activeRunGoal={activeRun?.goal ?? null}
  onRequestStatus={() => onSelectInspectionTab("activity")}
  ...
/>
```

- [ ] **Step 6: Extend run header view to include permission label for future header chips**

Modify `frontend/src/features/conversation/runHeaderView.ts`:

Import:

```ts
import { getPermissionPolicy, inferPermissionPolicyFromScopes } from "@/features/chat/composerState";
```

Extend `RunHeaderView`:

```ts
permissionLabel?: string;
permissionLabelKey?: string;
```

Inside `buildRunHeaderView`, compute:

```ts
const permission = activeRun
  ? getPermissionPolicy(inferPermissionPolicyFromScopes(activeRun.scopes))
  : null;
```

Return:

```ts
permissionLabel: permission?.fallback,
permissionLabelKey: permission?.labelKey,
```

Modify `frontend/src/features/conversation/ConversationHeader.tsx` to render a compact permission chip after model chip:

```tsx
{view.permissionLabel && view.permissionLabelKey && (
  <span className="hidden max-w-28 truncate rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground md:inline">
    {t(view.permissionLabelKey, view.permissionLabel)}
  </span>
)}
```

- [ ] **Step 7: Extend run header tests for permission labels**

Modify `frontend/tests/run-header-view.test.mjs` mock for `@/features/chat/composerState` by adding a resolver and loader:

```js
build.onResolve({ filter: /^@\/features\/chat\/composerState$/ }, () => ({
  path: "mock-composer-state",
  namespace: "mock",
}));
build.onLoad({ filter: /^mock-composer-state$/, namespace: "mock" }, () => ({
  contents: `
    export function inferPermissionPolicyFromScopes(scopes) {
      if ((scopes || []).includes("*")) return "auto_safe";
      if ((scopes || []).some((scope) => scope.endsWith(".write"))) return "ask";
      return "read_only";
    }
    export function getPermissionPolicy(id) {
      const map = {
        ask: { labelKey: "chat:permission.ask", fallback: "Ask" },
        auto_safe: { labelKey: "chat:permission.autoSafe", fallback: "Auto-safe" },
        read_only: { labelKey: "chat:permission.readOnly", fallback: "Read-only" },
      };
      return map[id] || map.ask;
    }
  `,
  loader: "js",
}));
```

Extend `makeRun` to include scopes:

```js
function makeRun(overrides = {}) {
  return {
    id: "run_123456789",
    status: "running",
    goal: "Fix the bug",
    scopes: ["agent.workspace.read", "agent.workspace.write"],
    harness_options: { model_profile_key: "gpt-4", model: "gpt-4" },
    ...overrides,
  };
}
```

Add test:

```js
test("permission label is inferred from run scopes", async () => {
  const { buildRunHeaderView } = await loadRunHeaderView();
  const view = buildRunHeaderView({
    thread: makeThread(),
    activeRun: makeRun({ scopes: ["agent.workspace.read", "agent.memory.read"] }),
    streamStatus: "running",
    threadId: "thread_abcdef",
    modeLabel: "Auto",
  });

  assert.equal(view.permissionLabel, "Read-only");
  assert.equal(view.permissionLabelKey, "chat:permission.readOnly");
});
```

- [ ] **Step 8: Run task loop and header tests**

Run:

```bash
cd frontend
npm test -- run-task-loop-view run-header-view
```

Expected: pass.

- [ ] **Step 9: Commit Task 4**

Run:

```bash
git add frontend/src/features/conversation/runTaskLoopView.ts frontend/src/features/conversation/RunGoalBar.tsx frontend/src/features/conversation/ConversationPage.tsx frontend/src/features/conversation/runHeaderView.ts frontend/src/features/conversation/ConversationHeader.tsx frontend/tests/run-task-loop-view.test.mjs frontend/tests/run-header-view.test.mjs
git commit -m "feat: add run goal bar"
```

---

## Task 5: Polish P0 Task Loop And Verify

**Files:**

- Modify: `frontend/src/features/chat/ChatComposer.tsx`
- Modify: `frontend/src/features/conversation/RunGoalBar.tsx`
- Modify: `frontend/src/i18n/resources/en/chat.json`
- Modify: `frontend/src/i18n/resources/zh/chat.json`
- Modify: `frontend/tests/i18n-runtime-sync.test.mjs` only if the existing sync test requires fixture updates.

### Purpose

Finish P0 as a coherent product slice: stable layout, accessible controls, localized strings, and full frontend verification.

- [ ] **Step 1: Ensure composer controls have stable sizes**

In `frontend/src/features/chat/ChatComposer.tsx`, verify these class names are present:

```tsx
className="h-7 w-[104px] border-0 bg-background text-xs shadow-sm"
className="h-7 w-[150px] border-0 bg-background text-xs shadow-sm"
className="h-7 w-[130px] border-0 bg-background text-xs shadow-sm"
className="h-7 w-[122px] border-0 bg-background text-xs shadow-sm"
```

If any selector wraps awkwardly, reduce only the text label width, not the toolbar height.

- [ ] **Step 2: Ensure RunGoalBar stays single-row on desktop**

In `frontend/src/features/conversation/RunGoalBar.tsx`, verify:

```tsx
<div className="border-b bg-muted/20 px-4 py-2">
  <div className="mx-auto flex max-w-4xl items-center gap-2 overflow-hidden text-xs">
```

Goal text must use `truncate`; current activity must be hidden below `md`; permission must be hidden below `lg`.

- [ ] **Step 3: Add final P0 i18n keys if missing**

Ensure `frontend/src/i18n/resources/en/chat.json` contains:

```json
{
  "permission": {
    "label": "Permission",
    "ask": "Ask",
    "askDescription": "Allow common task tools while backend approvals gate risky actions.",
    "autoSafe": "Auto-safe",
    "autoSafeDescription": "Trusted local mode that requests broad capability access.",
    "readOnly": "Read-only",
    "readOnlyDescription": "Inspect workspace and memory without write scopes."
  },
  "commandHint": "/plan, /status, /retry, /clear",
  "goalBar": {
    "goal": "Goal",
    "current": "Current",
    "permission": "Permission",
    "noCurrentStep": "Waiting for activity"
  }
}
```

Ensure `frontend/src/i18n/resources/zh/chat.json` contains:

```json
{
  "permission": {
    "label": "权限",
    "ask": "询问",
    "askDescription": "允许常用任务工具，风险动作仍由后端审批拦截。",
    "autoSafe": "自动安全",
    "autoSafeDescription": "受信任的本地模式，请求较宽的能力范围。",
    "readOnly": "只读",
    "readOnlyDescription": "只检查工作区和记忆，不请求写入权限。"
  },
  "commandHint": "/plan、/status、/retry、/clear",
  "goalBar": {
    "goal": "目标",
    "current": "当前",
    "permission": "权限",
    "noCurrentStep": "等待活动"
  }
}
```

- [ ] **Step 4: Run targeted P0 tests**

Run:

```bash
cd frontend
npm test -- composer-state slash-commands chat-composer-options run-task-loop-view run-header-view chat-i18n-usage
```

Expected: all targeted P0 tests pass.

- [ ] **Step 5: Run full frontend test suite**

Run:

```bash
cd frontend
npm test
```

Expected: all frontend tests pass.

- [ ] **Step 6: Run frontend typecheck/build**

Run:

```bash
cd frontend
npm run build
```

Expected: build succeeds. Vite chunk-size warnings are acceptable if they already existed before this task.

- [ ] **Step 7: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 8: Commit Task 5**

Run:

```bash
git add frontend/src/features/chat/ChatComposer.tsx frontend/src/features/conversation/RunGoalBar.tsx frontend/src/i18n/resources/en/chat.json frontend/src/i18n/resources/zh/chat.json frontend/tests/i18n-runtime-sync.test.mjs
git commit -m "style: polish chat task loop"
```

If `frontend/tests/i18n-runtime-sync.test.mjs` was not modified, omit it from `git add`.

---

## Final Verification

After all tasks are complete, run:

```bash
cd frontend
npm test
npm run build
cd ..
git diff --check
```

Expected:

- frontend tests pass;
- frontend build succeeds;
- no whitespace errors.

Backend verification is not required for this P0 plan if no backend files were modified. If execution changes backend contracts or generated API schema, also run:

```bash
cd backend
uv run pytest
uv run python examples/file_report_agent.py
```

## Manual QA Checklist

Run the app and verify:

- new chat can start a task with Auto/Plan/Chat mode;
- model and skill selectors still work;
- permission selector offers Ask, Auto-safe, and Read-only;
- Read-only run creation sends read-only scopes;
- Ask run creation sends common task scopes without wildcard;
- Auto-safe run creation sends `["*"]`;
- `/plan Fix login` sends `Fix login` in Plan mode;
- `/plan` without text converts the composer into a planning draft;
- `/status` opens or focuses the Activity companion tab and does not create a run;
- `/retry` fills a retry prompt using the active run goal when available;
- `/clear` clears the composer;
- running run shows Stop;
- waiting input shows Reply;
- waiting approval opens Approvals;
- model configuration failure opens settings;
- goal bar appears for active runs and stays one row on desktop;
- narrow width does not produce horizontal overflow.

## Follow-Up Phase Plans

Create separate implementation plans after P0 is accepted:

- P1 Readable Execution: plan/todo projection, timeline, tool summaries, approval center, error diagnosis.
- P2 Workspace Outputs: files impact, diff review, artifact preview, verification output, result summary.
- P3 Capability And Multi-Task Workbench: capability center, permission policy manager, MCP health, background runs, subagents, automations, global search.
