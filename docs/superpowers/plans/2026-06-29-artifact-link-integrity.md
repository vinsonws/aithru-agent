# Artifact Link Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop assistant replies from presenting unusable model-invented artifact URLs, and make existing `https://aithru.ai/artifact/{org_id}/{artifact_id}` links resolve to the current platform artifact preview when the artifact is known to the thread.

**Architecture:** Use two defensive layers. Backend prompt guidance tells the model that artifacts are platform resources rendered as cards and that it must not invent public artifact URLs. Frontend rendering keeps the immutable transcript intact, but resolves known Aithru artifact links at display and copy time using artifact display cards from the current thread/run state.

**Tech Stack:** Python, FastAPI, Pydantic AI instruction assembly, React, TypeScript, `react-markdown`, Vite, `node:test`, esbuild, pytest.

## Global Constraints

- Preserve the Aithru capability boundary: models may propose tool calls, but real artifact access must continue through `/api/artifacts/*` routes.
- Do not introduce Agent workflow graph, WorkflowSpec, scheduler, or plan-as-workflow behavior.
- Keep Pydantic AI details inside `backend/src/aithru_agent/harness` and `backend/src/aithru_agent/agent`; do not make Pydantic AI types public API contracts.
- Do not mutate historical assistant message content in storage; the stored transcript remains the audit record.
- Only rewrite links that match the Aithru artifact pattern and point to an artifact id already present in this thread/run display-card state.
- Unknown or external links must remain unchanged.
- Backend verification for meaningful changes: `cd backend && uv run pytest`.
- Frontend verification for UI changes: `cd frontend && npm test`, `npm run typecheck`, and `npm run build`.

---

## File Structure

- Modify `backend/src/aithru_agent/agent/instructions.py`
  - Add a dedicated artifact-link guidance block to the model-facing system instructions.
  - Responsibility: reduce future model-invented artifact URLs.
- Modify `backend/tests/unit/agent/test_instructions.py`
  - Cover the new guidance and update exact instruction string expectations.
- Create `frontend/src/features/chat/artifactLinks.ts`
  - Pure TypeScript helpers for collecting known artifact ids, resolving model-invented Aithru artifact URLs, and rewriting Markdown link destinations for copy text.
  - Responsibility: no React, no DOM, no API calls.
- Modify `frontend/src/components/Markdown.tsx`
  - Add an optional link resolver hook for Markdown anchors.
  - Responsibility: generic Markdown link rewriting without artifact-specific knowledge.
- Modify `frontend/src/features/chat/ChatPanel.tsx`
  - Build the artifact link resolver from active and historical run display cards.
  - Pass the resolver into assistant message Markdown rendering.
  - Use the same resolver when copying assistant message content.
- Create `frontend/tests/artifact-links.test.mjs`
  - Unit tests for the pure resolver and Markdown-link rewrite helper.
- Create `frontend/tests/markdown-links.test.mjs`
  - Server-render test proving `Markdown` applies the resolver to anchor hrefs.

---

### Task 1: Backend Artifact Link Guidance

**Files:**
- Modify: `backend/src/aithru_agent/agent/instructions.py`
- Modify: `backend/tests/unit/agent/test_instructions.py`

**Interfaces:**
- Consumes: `InstructionBuilder.build(deps: PydanticAgentDeps) -> str`
- Produces: A new system prompt section named `## Artifact Link Guidance`

- [ ] **Step 1: Write the failing test for the new guidance**

Add this test to `backend/tests/unit/agent/test_instructions.py`:

```python
@pytest.mark.asyncio
async def test_instruction_builder_warns_model_not_to_invent_artifact_links() -> None:
    deps = await build_deps(store=InMemoryAgentStore())

    instructions = await InstructionBuilder("Base instructions.").build(deps)

    assert "## Artifact Link Guidance" in instructions
    assert "Do not invent public artifact URLs" in instructions
    assert "https://aithru.ai/artifact/" in instructions
    assert "artifact cards or the Files panel" in instructions
```

- [ ] **Step 2: Run the failing backend test**

Run:

```bash
cd backend
uv run pytest tests/unit/agent/test_instructions.py::test_instruction_builder_warns_model_not_to_invent_artifact_links -q
```

Expected: fail because the guidance block is not present.

- [ ] **Step 3: Add the guidance block to instruction assembly**

In `backend/src/aithru_agent/agent/instructions.py`, add this constant near `_CLARIFICATION_GUIDANCE`:

```python
_ARTIFACT_LINK_GUIDANCE = """## Artifact Link Guidance

Artifacts are platform resources rendered by Aithru as artifact cards or in the Files panel.
Do not invent public artifact URLs such as https://aithru.ai/artifact/{org_id}/{artifact_id}.
When an artifact is created, refer to it by name and artifact id only, and let the UI-provided artifact card handle preview and download actions.
If you need to mention where the user can open an artifact, say it is available in the artifact cards or the Files panel."""
```

Then append it immediately after clarification guidance:

```python
        # Add clarification guidance
        sections.append(_CLARIFICATION_GUIDANCE)

        # Add artifact presentation guidance
        sections.append(_ARTIFACT_LINK_GUIDANCE)
```

- [ ] **Step 4: Update exact-string instruction tests**

Two existing tests assert the full instruction string:

- `test_instruction_builder_combines_base_and_skill_instructions`
- `test_instruction_builder_adds_run_harness_instructions`

Update their expected values so `_ARTIFACT_LINK_GUIDANCE` appears after `_CLARIFICATION_GUIDANCE` and before run/skill instructions. The final order must be:

```text
Base instructions.

## When to Ask for Clarification
...

## Artifact Link Guidance
...

Skill instructions:
...
```

and:

```text
Base instructions.

## When to Ask for Clarification
...

## Artifact Link Guidance
...

Run instructions:
...
```

- [ ] **Step 5: Verify backend instruction tests**

Run:

```bash
cd backend
uv run pytest tests/unit/agent/test_instructions.py -q
```

Expected: all tests in `test_instructions.py` pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/aithru_agent/agent/instructions.py backend/tests/unit/agent/test_instructions.py
git commit -m "fix: discourage invented artifact links"
```

---

### Task 2: Frontend Artifact Link Resolver

**Files:**
- Create: `frontend/src/features/chat/artifactLinks.ts`
- Create: `frontend/tests/artifact-links.test.mjs`

**Interfaces:**
- Consumes: `RunStreamState` and `PresentationEntry` from `frontend/src/features/chat/useRunStream.ts`
- Produces:
  - `artifactContentHref(artifactId: string): string`
  - `artifactIdsFromRunStates(states: RunStreamState[]): Set<string>`
  - `resolveKnownArtifactHref(href: string, artifactIds: ReadonlySet<string>): string`
  - `buildArtifactLinkResolver(states: RunStreamState[]): (href: string) => string`
  - `rewriteKnownArtifactMarkdownLinks(markdown: string, resolveHref: (href: string) => string): string`

- [ ] **Step 1: Write the failing resolver tests**

Create `frontend/tests/artifact-links.test.mjs`:

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";
import esbuild from "esbuild";

async function loadArtifactLinks() {
  const result = await esbuild.build({
    absWorkingDir: new URL("..", import.meta.url).pathname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
    entryPoints: ["src/features/chat/artifactLinks.ts"],
  });

  return import(`data:text/javascript,${encodeURIComponent(result.outputFiles[0].text)}`);
}

function stateWithArtifactCard(id) {
  return {
    status: "completed",
    messages: [],
    toolCalls: [],
    reasoningSegments: [],
    assistantOutputSegments: [],
    todos: [],
    inlineRequests: [],
    displayCards: [
      {
        id: `card_${id}`,
        type: "artifact",
        status: "ready",
        title: "Starlight Wishes",
        surface: "conversation",
        resource: { kind: "artifact", id },
        actions: [{ kind: "preview", label: "Preview" }],
      },
    ],
  };
}

test("resolveKnownArtifactHref rewrites known Aithru artifact public links to local content routes", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();
  const known = new Set(["artifact_1"]);

  assert.equal(
    resolveKnownArtifactHref("https://aithru.ai/artifact/org_1/artifact_1", known),
    "/api/artifacts/artifact_1/content",
  );
});

test("resolveKnownArtifactHref leaves unknown Aithru artifact links unchanged", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();
  const known = new Set(["artifact_1"]);

  assert.equal(
    resolveKnownArtifactHref("https://aithru.ai/artifact/org_1/artifact_missing", known),
    "https://aithru.ai/artifact/org_1/artifact_missing",
  );
});

test("resolveKnownArtifactHref leaves unrelated external links unchanged", async () => {
  const { resolveKnownArtifactHref } = await loadArtifactLinks();

  assert.equal(
    resolveKnownArtifactHref("https://example.com/artifact/org_1/artifact_1", new Set(["artifact_1"])),
    "https://example.com/artifact/org_1/artifact_1",
  );
});

test("buildArtifactLinkResolver collects artifact ids from active run display cards", async () => {
  const { buildArtifactLinkResolver } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactCard("artifact_1")]);

  assert.equal(
    resolveHref("https://aithru.ai/artifact/org_1/artifact_1"),
    "/api/artifacts/artifact_1/content",
  );
});

test("rewriteKnownArtifactMarkdownLinks rewrites copied Markdown destinations", async () => {
  const { buildArtifactLinkResolver, rewriteKnownArtifactMarkdownLinks } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactCard("artifact_1")]);

  assert.equal(
    rewriteKnownArtifactMarkdownLinks(
      "[Starlight Wishes](https://aithru.ai/artifact/org_1/artifact_1)",
      resolveHref,
    ),
    "[Starlight Wishes](/api/artifacts/artifact_1/content)",
  );
});
```

- [ ] **Step 2: Run the failing frontend resolver tests**

Run:

```bash
cd frontend
node --test tests/artifact-links.test.mjs
```

Expected: fail because `artifactLinks.ts` does not exist.

- [ ] **Step 3: Implement the resolver utility**

Create `frontend/src/features/chat/artifactLinks.ts`:

```typescript
import type { DisplayCardEntry, RunStreamState } from "./useRunStream";

const AITHRU_ARTIFACT_URL_RE = /^https:\/\/aithru\.ai\/artifact\/([^/?#]+)\/([^/?#]+)([?#].*)?$/i;
const MARKDOWN_LINK_DESTINATION_RE = /(\]\()([^)]+)(\))/g;

export function artifactContentHref(artifactId: string): string {
  return `/api/artifacts/${encodeURIComponent(artifactId)}/content`;
}

export function artifactIdsFromRunStates(states: RunStreamState[]): Set<string> {
  const ids = new Set<string>();
  for (const state of states) {
    for (const card of state.displayCards ?? []) {
      const artifactId = artifactIdFromDisplayCard(card);
      if (artifactId) ids.add(artifactId);
    }
  }
  return ids;
}

export function resolveKnownArtifactHref(
  href: string,
  artifactIds: ReadonlySet<string>,
): string {
  const match = AITHRU_ARTIFACT_URL_RE.exec(href.trim());
  if (!match) return href;

  const artifactId = decodeURIComponent(match[2]);
  if (!artifactIds.has(artifactId)) return href;

  return artifactContentHref(artifactId);
}

export function buildArtifactLinkResolver(states: RunStreamState[]): (href: string) => string {
  const artifactIds = artifactIdsFromRunStates(states);
  return (href: string) => resolveKnownArtifactHref(href, artifactIds);
}

export function rewriteKnownArtifactMarkdownLinks(
  markdown: string,
  resolveHref: (href: string) => string,
): string {
  return markdown.replace(MARKDOWN_LINK_DESTINATION_RE, (full, open, href, close) => {
    const resolved = resolveHref(href.trim());
    return resolved === href.trim() ? full : `${open}${resolved}${close}`;
  });
}

function artifactIdFromDisplayCard(card: DisplayCardEntry): string | null {
  if (card.resource?.kind !== "artifact") return null;
  const id = card.resource.id?.trim();
  return id || null;
}
```

- [ ] **Step 4: Verify resolver tests pass**

Run:

```bash
cd frontend
node --test tests/artifact-links.test.mjs
```

Expected: all resolver tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/chat/artifactLinks.ts frontend/tests/artifact-links.test.mjs
git commit -m "fix: resolve known artifact links in chat"
```

---

### Task 3: Markdown Link Resolver Hook

**Files:**
- Modify: `frontend/src/components/Markdown.tsx`
- Create: `frontend/tests/markdown-links.test.mjs`

**Interfaces:**
- Consumes: `resolveLinkHref?: (href: string) => string`
- Produces: Markdown anchor tags whose `href` may be rewritten by the caller

- [ ] **Step 1: Write the failing Markdown render test**

Create `frontend/tests/markdown-links.test.mjs`:

```javascript
import assert from "node:assert/strict";
import path from "node:path";
import { test } from "node:test";
import esbuild from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

async function loadMarkdown() {
  const root = new URL("..", import.meta.url).pathname;
  const result = await esbuild.build({
    absWorkingDir: root,
    bundle: true,
    format: "esm",
    jsx: "automatic",
    platform: "node",
    write: false,
    entryPoints: ["src/components/Markdown.tsx"],
    plugins: [
      {
        name: "mock-runtime-imports",
        setup(build) {
          build.onResolve({ filter: /^@\/lib\/utils$/ }, () => ({
            path: "mock-utils",
            namespace: "mock",
          }));
          build.onResolve({ filter: /^@\// }, (args) => ({
            path: path.join(root, "src", args.path.slice(2)),
          }));
          build.onLoad({ filter: /^mock-utils$/, namespace: "mock" }, () => ({
            contents: `
              export function cn(...values) {
                return values.filter(Boolean).join(" ");
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

test("Markdown applies resolveLinkHref to anchor hrefs", async () => {
  const { Markdown } = await loadMarkdown();
  const html = renderToStaticMarkup(
    React.createElement(
      Markdown,
      {
        resolveLinkHref: (href) =>
          href === "https://aithru.ai/artifact/org_1/artifact_1"
            ? "/api/artifacts/artifact_1/content"
            : href,
      },
      "[Starlight Wishes](https://aithru.ai/artifact/org_1/artifact_1)",
    ),
  );

  assert.match(html, /href="\/api\/artifacts\/artifact_1\/content"/);
  assert.doesNotMatch(html, /href="https:\/\/aithru\.ai\/artifact\/org_1\/artifact_1"/);
});
```

- [ ] **Step 2: Run the failing Markdown render test**

Run:

```bash
cd frontend
node --test tests/markdown-links.test.mjs
```

Expected: fail because `MarkdownProps` does not accept or apply `resolveLinkHref`.

- [ ] **Step 3: Implement optional anchor rewriting in Markdown**

Modify `frontend/src/components/Markdown.tsx`:

```typescript
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
```

Extend props:

```typescript
export interface MarkdownProps {
  children: string;
  className?: string;
  /** Render with chat-friendly spacing (tighter, no huge headings). */
  variant?: "default" | "chat";
  resolveLinkHref?: (href: string) => string;
}
```

Apply components in the render function:

```typescript
export function Markdown({
  children,
  className,
  variant = "default",
  resolveLinkHref,
}: MarkdownProps) {
  const components: Components | undefined = resolveLinkHref
    ? {
        a({ href, children, ...props }) {
          const resolvedHref = href ? resolveLinkHref(href) : undefined;
          const external = Boolean(resolvedHref && /^https?:\/\//i.test(resolvedHref));
          return (
            <a
              {...props}
              href={resolvedHref}
              target={external ? "_blank" : undefined}
              rel={external ? "noreferrer" : undefined}
            >
              {children}
            </a>
          );
        },
      }
    : undefined;

  return (
    <div className={cn(/* existing className list stays unchanged */)}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
```

Keep the existing className list exactly as-is inside `cn(...)`.

- [ ] **Step 4: Verify Markdown test passes**

Run:

```bash
cd frontend
node --test tests/markdown-links.test.mjs
```

Expected: test passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Markdown.tsx frontend/tests/markdown-links.test.mjs
git commit -m "fix: allow chat markdown link rewriting"
```

---

### Task 4: ChatPanel Integration And Copy Behavior

**Files:**
- Modify: `frontend/src/features/chat/ChatPanel.tsx`
- Modify: `frontend/tests/artifact-links.test.mjs`

**Interfaces:**
- Consumes:
  - `buildArtifactLinkResolver(states: RunStreamState[]): (href: string) => string`
  - `rewriteKnownArtifactMarkdownLinks(markdown: string, resolveHref: (href: string) => string): string`
- Produces:
  - Assistant Markdown links are rewritten for known artifact ids during rendering.
  - Copying an assistant message rewrites known artifact Markdown links to local content URLs.

- [ ] **Step 1: Add copy rewrite coverage**

Extend `frontend/tests/artifact-links.test.mjs` with a multi-link copy case:

```javascript
test("rewriteKnownArtifactMarkdownLinks only rewrites known Aithru artifact links", async () => {
  const { buildArtifactLinkResolver, rewriteKnownArtifactMarkdownLinks } = await loadArtifactLinks();
  const resolveHref = buildArtifactLinkResolver([stateWithArtifactCard("artifact_1")]);

  assert.equal(
    rewriteKnownArtifactMarkdownLinks(
      [
        "[Known](https://aithru.ai/artifact/org_1/artifact_1)",
        "[Unknown](https://aithru.ai/artifact/org_1/artifact_2)",
        "[External](https://example.com/a)",
      ].join(" "),
      resolveHref,
    ),
    [
      "[Known](/api/artifacts/artifact_1/content)",
      "[Unknown](https://aithru.ai/artifact/org_1/artifact_2)",
      "[External](https://example.com/a)",
    ].join(" "),
  );
});
```

- [ ] **Step 2: Run the current resolver tests**

Run:

```bash
cd frontend
node --test tests/artifact-links.test.mjs
```

Expected: pass after Task 2; this test confirms the copy helper is ready before wiring it into the UI.

- [ ] **Step 3: Wire resolver into ChatPanel**

Modify imports in `frontend/src/features/chat/ChatPanel.tsx`:

```typescript
import {
  buildArtifactLinkResolver,
  rewriteKnownArtifactMarkdownLinks,
} from "./artifactLinks";
```

Extend `MessageBubble` props:

```typescript
function MessageBubble({
  message,
  locale,
  onPrefillComposer,
  onOpenTrace,
  resolveLinkHref,
}: {
  message: ChatMessage;
  locale: string;
  onPrefillComposer?: (text: string) => void;
  onOpenTrace?: () => void;
  resolveLinkHref?: (href: string) => string;
}) {
```

Use the resolver for copying:

```typescript
  const copyContent = resolveLinkHref
    ? rewriteKnownArtifactMarkdownLinks(message.content, resolveLinkHref)
    : message.content;

  const handleMessageAction = (kind: string, _messageId: string) => {
    if (kind === "copy") {
      navigator.clipboard.writeText(copyContent).catch(() => {});
    } else if (kind === "editAndRerun") {
      onPrefillComposer?.(buildEditAndRerunPrompt(message));
    } else if (kind === "viewTrace") {
      onOpenTrace?.();
    }
  };
```

Pass the resolver into Markdown:

```tsx
<Markdown variant="chat" resolveLinkHref={resolveLinkHref}>
  {message.content}
</Markdown>
```

Build one resolver in `ChatPanel`:

```typescript
  const artifactLinkResolver = React.useMemo(
    () => buildArtifactLinkResolver([state, ...Object.values(historicalRunStates)]),
    [state, historicalRunStates],
  );
```

Pass it into `MessageBubble`:

```tsx
<MessageBubble
  key={item.id}
  message={item.message}
  locale={locale}
  onPrefillComposer={onPrefillComposer}
  onOpenTrace={onOpenTrace}
  resolveLinkHref={artifactLinkResolver}
/>
```

- [ ] **Step 4: Run targeted frontend tests**

Run:

```bash
cd frontend
node --test tests/artifact-links.test.mjs tests/markdown-links.test.mjs
npm run typecheck
```

Expected: targeted tests pass and TypeScript typecheck succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/chat/ChatPanel.tsx frontend/tests/artifact-links.test.mjs
git commit -m "fix: rewrite artifact links in chat messages"
```

---

### Task 5: Manual Verification On The Reproduction Thread

**Files:**
- No source changes

**Interfaces:**
- Consumes: local app at `http://localhost:15173/threads/thread_45`
- Produces: confirmation that the old stored reply now opens a local artifact preview route

- [ ] **Step 1: Start or confirm local services**

Use the existing project run script if the app is not already running:

```bash
./scripts/run.sh
```

If the services are already running on `localhost:15173`, keep them running and do not restart unnecessarily.

- [ ] **Step 2: Open the reproduction thread**

Open:

```text
http://localhost:15173/threads/thread_45
```

- [ ] **Step 3: Inspect the Starlight Wishes link**

Use browser DOM inspection or devtools to confirm the visible Markdown link now has:

```text
href="/api/artifacts/artifact_1/content"
```

Expected: the link no longer points at:

```text
https://aithru.ai/artifact/org_1/artifact_1
```

- [ ] **Step 4: Click the link**

Expected: the browser opens the HTML artifact from:

```text
http://localhost:15173/api/artifacts/artifact_1/content
```

The response should be `200 OK` and render the `Starlight Wishes` HTML content.

- [ ] **Step 5: Verify the artifact card still works**

On the same thread, verify:

- The artifact card still shows `Starlight Wishes`.
- The card `Preview` action still opens the right rail preview.
- The card `Download` link still targets `/api/artifacts/artifact_1/download`.

- [ ] **Step 6: Verify copy behavior**

Use the assistant message `Copy` action and paste into a scratch text field. Expected copied Markdown contains:

```markdown
[Starlight Wishes](/api/artifacts/artifact_1/content)
```

The copied text should not contain:

```text
https://aithru.ai/artifact/org_1/artifact_1
```

---

### Task 6: Full Verification

**Files:**
- No source changes

**Interfaces:**
- Consumes: all changes from Tasks 1-5
- Produces: final confidence that backend, frontend, and example workflows still pass

- [ ] **Step 1: Run frontend tests**

```bash
cd frontend
npm test
```

Expected: all frontend tests pass.

- [ ] **Step 2: Run frontend typecheck**

```bash
cd frontend
npm run typecheck
```

Expected: TypeScript completes without errors.

- [ ] **Step 3: Run frontend build**

```bash
cd frontend
npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 4: Run backend tests**

```bash
cd backend
uv run pytest
```

Expected: backend test suite passes.

- [ ] **Step 5: Run the backend file report example**

```bash
cd backend
uv run python examples/file_report_agent.py
```

Expected: example completes without errors.

- [ ] **Step 6: Commit final verification note if needed**

If no additional code changed during verification, do not create an empty commit. If verification required small fixes, commit only those fixes:

```bash
git add <changed-files>
git commit -m "test: verify artifact link handling"
```

---

## Self-Review

**Spec coverage:** This plan covers the observed root cause in `thread_45`: model output invented `https://aithru.ai/artifact/org_1/artifact_1`; platform artifact APIs actually expose `/api/artifacts/artifact_1/content` and `/api/artifacts/artifact_1/download`. Task 1 reduces future generation. Tasks 2-4 fix existing rendered and copied messages without mutating stored transcript. Task 5 verifies the exact reproduction.

**Placeholder scan:** No unresolved placeholder values are required. All paths, commands, function names, and expected link values are explicit.

**Type consistency:** `buildArtifactLinkResolver` returns `(href: string) => string`; `Markdown` consumes `resolveLinkHref?: (href: string) => string`; `ChatPanel` passes the same resolver to display and copy helpers.

**Boundary check:** The fix does not create a public artifact service and does not expose unrestricted artifact access. It only maps known current-thread artifact ids to existing `/api/artifacts/{id}/content` preview routes.
