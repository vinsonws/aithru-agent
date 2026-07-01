# File Viewer Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let model/tool output suggest a preferred workspace-file viewer while the frontend keeps final control, fixes HTML persisted previews showing source, and stops draft HTML generation from flickering.

**Architecture:** Backend remains source-file oriented: it serves workspace bytes/content with inferred MIME and exposes optional `preferred_view` hints on capability inputs/outputs. Frontend owns a typed viewer policy that resolves user choice, safety rules, model hint, MIME/extension, and lifecycle into a render mode.

**Tech Stack:** TypeScript, Fastify, existing Agent capability routers, React, TanStack Query, existing Node test harnesses.

## Global Constraints

- Keep Agent as a harness, not a workflow system.
- All real file writes continue through the capability router and existing approval boundary.
- `preferred_view` is advisory only; never let the model name arbitrary React components, iframe sandbox flags, URLs, or executable viewer config.
- Streaming draft HTML must not execute scripts and should default to source rendering to avoid iframe reload flicker.
- Persisted HTML may render in the existing sandboxed iframe when the served content type is `text/html`.
- Do not add a viewer plugin registry, file watchers, new persistence tables, or new dependencies.
- Reuse the existing preferred-view enum from `presentation.present`:
  `html_preview | markdown | json | image | pdf | source_text | download`.

---

## File Structure

```txt
backend/apps/api/src/routes/compat.ts
backend/packages/capabilities/src/production-router.ts
backend/packages/capabilities/src/test-router.ts
backend/tests/integration/api.test.ts
frontend/src/AppShell.tsx
frontend/src/features/inspection/runFilesView.ts
frontend/src/features/sidebar/panels/FilePreviewPanel.tsx
frontend/src/features/sidebar/panels/FileListPanel.tsx
frontend/tests/run-files-view.test.mjs
frontend/tests/file-preview-drafts.test.mjs
docs/superpowers/specs/2026-07-01-file-viewer-policy-design.md
```

---

## Task 1: Serve Workspace File Content With Inferred MIME

**Files:**

- `backend/apps/api/src/routes/compat.ts`
- `backend/tests/integration/api.test.ts`

**Contract:**

- `GET /api/workspaces/:workspace_id/files/:path` returns `media_type` inferred from file path.
- `GET /api/workspaces/:workspace_id/files/:path/content` sets `content-type` inferred from file path.
- Unknown extensions fall back to `text/plain; charset=utf-8`.

**Implementation Steps:**

- [ ] Add failing integration coverage in `backend/tests/integration/api.test.ts`.

```ts
expect(res.headers["content-type"]).toContain("text/html");
```

Add cases for:

```ts
getRuntime().store.writeFile(workspaceId, "/outputs/page.html", "<html>ok</html>");
getRuntime().store.writeFile(workspaceId, "/outputs/data.json", "{\"ok\":true}");
getRuntime().store.writeFile(workspaceId, "/outputs/raw.unknown", "raw");
```

Expected headers:

```txt
text/html
application/json
text/plain
```

- [ ] Add local MIME helpers near the workspace route helpers in `compat.ts`.

```ts
function workspaceMediaTypeForPath(path: string): string {
  const cleanPath = path.split("?")[0]?.toLowerCase() ?? "";
  if (cleanPath.endsWith(".html") || cleanPath.endsWith(".htm")) return "text/html";
  if (cleanPath.endsWith(".md") || cleanPath.endsWith(".markdown")) return "text/markdown";
  if (cleanPath.endsWith(".json")) return "application/json";
  if (cleanPath.endsWith(".css")) return "text/css";
  if (cleanPath.endsWith(".js") || cleanPath.endsWith(".mjs")) return "text/javascript";
  if (cleanPath.endsWith(".csv")) return "text/csv";
  if (cleanPath.endsWith(".svg")) return "image/svg+xml";
  if (cleanPath.endsWith(".png")) return "image/png";
  if (cleanPath.endsWith(".jpg") || cleanPath.endsWith(".jpeg")) return "image/jpeg";
  if (cleanPath.endsWith(".gif")) return "image/gif";
  if (cleanPath.endsWith(".webp")) return "image/webp";
  if (cleanPath.endsWith(".pdf")) return "application/pdf";
  return "text/plain";
}

function workspaceContentTypeForPath(path: string): string {
  const mediaType = workspaceMediaTypeForPath(path);
  if (mediaType.startsWith("text/") || mediaType === "application/json") {
    return `${mediaType}; charset=utf-8`;
  }
  return mediaType;
}
```

- [ ] Use the helpers in both the direct `:path` routes and the wildcard nested-path route.

```ts
return file
  ? { path: file.path, content: file.content, media_type: workspaceMediaTypeForPath(file.path) }
  : notFound(reply, "Workspace file not found");
```

```ts
reply.header("content-type", workspaceContentTypeForPath(file.path));
return file.content;
```

- [ ] Update `workspaceFile(file)` and `workspaceFileWildcardRequest(...)`.

```ts
function workspaceFile(file: any) {
  return {
    workspace_id: file.workspace_id,
    path: file.path,
    size: file.size,
    media_type: workspaceMediaTypeForPath(file.path),
    version: file.version,
    file_version: file.version,
    content_hash: null,
    created_at: file.created_at,
    updated_at: file.updated_at,
  };
}
```

```ts
if (target.action === "content") {
  reply.header("content-type", workspaceContentTypeForPath(file.path));
  return file.content;
}
if (target.action === "read") {
  return { path: file.path, content: file.content, media_type: workspaceMediaTypeForPath(file.path) };
}
```

- [ ] Keep `/download` as `application/octet-stream`.

**Verification:**

```bash
cd backend
npm run test -- --runInBand tests/integration/api.test.ts
```

If the test runner does not support that argument, run:

```bash
cd backend
npm run test
```

---

## Task 2: Expose `preferred_view` on Workspace Write Tools

**Files:**

- `backend/packages/capabilities/src/production-router.ts`
- `backend/packages/capabilities/src/test-router.ts`
- `frontend/src/features/inspection/runFilesView.ts`
- `frontend/tests/run-files-view.test.mjs`

**Contract:**

- `workspace.write_file` accepts optional `preferred_view`.
- The router returns the same valid hint in tool output.
- Draft parsing preserves the hint while the model is streaming a write.
- Invalid or absent values are ignored by the frontend policy.

**Implementation Steps:**

- [ ] Add the same enum to both `workspace.write_file` schemas.

```ts
preferred_view: {
  type: "string",
  enum: ["html_preview", "markdown", "json", "image", "pdf", "source_text", "download"],
},
```

- [ ] Return the advisory hint from router execution when the model supplied it.

```ts
const preferredView = optionalString(input.preferred_view);
return {
  path: file.path,
  version: file.version,
  ...(preferredView ? { preferred_view: preferredView } : {}),
};
```

If `optionalString` is not in scope in `test-router.ts`, add a small local helper there:

```ts
function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}
```

- [ ] Add frontend types and extraction support.

```ts
export type PreferredFileView =
  | "html_preview"
  | "markdown"
  | "json"
  | "image"
  | "pdf"
  | "source_text"
  | "download";
```

Add `preferredView?: PreferredFileView` to `DraftWorkspaceFileInput` and `RunFileView`.

- [ ] Add a normalizer in `runFilesView.ts`.

```ts
const PREFERRED_FILE_VIEWS = new Set<PreferredFileView>([
  "html_preview",
  "markdown",
  "json",
  "image",
  "pdf",
  "source_text",
  "download",
]);

export function normalizePreferredFileView(value: unknown): PreferredFileView | undefined {
  return typeof value === "string" && PREFERRED_FILE_VIEWS.has(value as PreferredFileView)
    ? (value as PreferredFileView)
    : undefined;
}
```

- [ ] Update draft extraction so complete JSON and partial JSON both read `preferred_view`.

```ts
function extractWorkspaceWriteDraft(
  inputText: string,
): { path: string; content: string; preferredView?: PreferredFileView } | null {
  try {
    const parsed = JSON.parse(inputText);
    if (isRecord(parsed) && typeof parsed.path === "string" && typeof parsed.content === "string") {
      return {
        path: parsed.path,
        content: parsed.content,
        preferredView: normalizePreferredFileView(parsed.preferred_view),
      };
    }
  } catch {
    const path = readJsonStringProperty(inputText, "path");
    if (!path) return null;
    return {
      path,
      content: readJsonStringProperty(inputText, "content", { allowUnclosed: true }) ?? "",
      preferredView: normalizePreferredFileView(readJsonStringProperty(inputText, "preferred_view")),
    };
  }

  return null;
}
```

- [ ] Add a `frontend/tests/run-files-view.test.mjs` case proving the hint is preserved.

```js
assert.equal(drafts[0].preferredView, "html_preview");
```

**Verification:**

```bash
node frontend/tests/run-files-view.test.mjs
```

---

## Task 3: Carry Presentation Hints Into File Views

**Files:**

- `frontend/src/AppShell.tsx`
- `frontend/src/features/inspection/runFilesView.ts`
- `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`
- `frontend/src/features/sidebar/panels/FileListPanel.tsx`
- `frontend/tests/run-files-view.test.mjs`

**Contract:**

- `presentation.present` remains the primary way for the model to ask for a final-file viewer.
- File views receive the latest valid `preferred_view` for the same workspace path.
- The inspection helper stays independent of chat stream types.
- Path matching treats `/outputs/a.html` and `outputs/a.html` as the same workspace file.

**Implementation Steps:**

- [ ] Add a hint type and input field in `runFilesView.ts`.

```ts
export interface WorkspaceFilePresentationHint {
  path: string;
  preferredView?: PreferredFileView;
}
```

```ts
export function buildRunFileViews(input: {
  snapshot?: unknown;
  workspaceId?: string | null;
  workspaceFiles?: WorkspaceFileInput[];
  draftWorkspaceFiles?: DraftWorkspaceFileInput[];
  presentationHints?: WorkspaceFilePresentationHint[];
}): RunFileView[] {
```

- [ ] Build a path-normalized hint map, with later stream events winning.

```ts
function preferredViewByWorkspacePath(
  hints: WorkspaceFilePresentationHint[] = [],
): Map<string, PreferredFileView> {
  const result = new Map<string, PreferredFileView>();
  for (const hint of hints) {
    const preferredView = normalizePreferredFileView(hint.preferredView);
    if (!preferredView) continue;
    result.set(normalizeWorkspacePath(hint.path), preferredView);
  }
  return result;
}
```

- [ ] Apply the hint while constructing persisted file views.

```ts
const presentationPreferredViews = preferredViewByWorkspacePath(input.presentationHints);
```

```ts
preferredView: presentationPreferredViews.get(normalizeWorkspacePath(f.path)),
```

- [ ] Apply the draft `preferredView` already parsed from `workspace.write_file` while constructing draft file views.

```ts
preferredView: draft.preferredView,
```

- [ ] Build presentation hints in `AppShell.tsx` without importing chat types into `runFilesView.ts`.

```ts
import {
  buildDraftWorkspaceFiles,
  normalizePreferredFileView,
} from "@/features/inspection/runFilesView";
```

```ts
const workspaceFilePresentationHints = React.useMemo(
  () => (streamState.presentations ?? []).flatMap((presentation) => {
    if (presentation.resource.kind !== "workspace_file" || !presentation.resource.path) return [];
    const preferredView = normalizePreferredFileView(presentation.preferredView);
    return preferredView
      ? [{ path: presentation.resource.path, preferredView }]
      : [];
  }),
  [streamState.presentations],
);
```

- [ ] Pass `presentationHints={workspaceFilePresentationHints}` into both `FilePreviewPanel` and `FileListPanel`.

- [ ] Add `presentationHints?: WorkspaceFilePresentationHint[]` props to both panels and pass them into `buildRunFileViews`.

- [ ] Add a `frontend/tests/run-files-view.test.mjs` case proving persisted files receive presentation hints.

```js
const views = buildRunFileViews({
  workspaceFiles: [{ path: "/outputs/page.html", size: 20, media_type: "text/html" }],
  presentationHints: [{ path: "outputs/page.html", preferredView: "source_text" }],
});
assert.equal(views[0].preferredView, "source_text");
```

**Verification:**

```bash
node frontend/tests/run-files-view.test.mjs
```

---

## Task 4: Add Frontend Viewer Policy

**Files:**

- `frontend/src/features/inspection/runFilesView.ts`
- `frontend/tests/run-files-view.test.mjs`

**Contract:**

- Frontend resolves the actual viewer from lifecycle, file kind, optional user choice, and optional model hint.
- Draft HTML resolves to source text even if the model asks for `html_preview`.
- Persisted HTML can resolve to `html_preview`.
- User safe choices win over model hints.

**Implementation Steps:**

- [ ] Add policy types.

```ts
export type FileLifecycle = "draft" | "persisted";

export interface ResolvedFileViewer {
  view: PreferredFileView;
  reason: "user" | "safety" | "preferred_view" | "file_type" | "fallback";
}
```

- [ ] Add `resolveFileViewer` in `runFilesView.ts`.

```ts
export function resolveFileViewer(input: {
  file: Pick<RunFileView, "previewKind" | "isDraft" | "preferredView">;
  preferredView?: PreferredFileView;
  userView?: PreferredFileView;
}): ResolvedFileViewer {
  const lifecycle: FileLifecycle = input.file.isDraft ? "draft" : "persisted";
  const safeUserView = input.userView && input.userView !== "html_preview" ? input.userView : undefined;
  if (safeUserView) return { view: safeUserView, reason: "user" };

  if (lifecycle === "draft" && input.file.previewKind === "html") {
    return { view: "source_text", reason: "safety" };
  }

  const preferredView = input.preferredView ?? input.file.preferredView;
  if (preferredView && preferredView !== "html_preview") {
    return { view: preferredView, reason: "preferred_view" };
  }
  if (preferredView === "html_preview" && input.file.previewKind === "html") {
    return { view: "html_preview", reason: "preferred_view" };
  }

  if (input.file.previewKind === "html") return { view: "html_preview", reason: "file_type" };
  if (input.file.previewKind === "markdown") return { view: "markdown", reason: "file_type" };
  if (input.file.previewKind === "json") return { view: "json", reason: "file_type" };
  if (input.file.previewKind === "image") return { view: "image", reason: "file_type" };
  if (input.file.previewKind === "pdf") return { view: "pdf", reason: "file_type" };
  return { view: "source_text", reason: "fallback" };
}
```

- [ ] Add tests for:

```js
assert.deepEqual(resolveFileViewer({ file: { previewKind: "html", isDraft: true, preferredView: "html_preview" } }), {
  view: "source_text",
  reason: "safety",
});
assert.deepEqual(resolveFileViewer({ file: { previewKind: "html", isDraft: false } }), {
  view: "html_preview",
  reason: "file_type",
});
assert.deepEqual(resolveFileViewer({
  file: { previewKind: "html", isDraft: false, preferredView: "html_preview" },
  userView: "source_text",
}), {
  view: "source_text",
  reason: "user",
});
```

**Verification:**

```bash
node frontend/tests/run-files-view.test.mjs
```

---

## Task 5: Render Preview Through the Viewer Policy

**Files:**

- `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`
- `frontend/tests/file-preview-drafts.test.mjs`

**Contract:**

- Draft HTML no longer uses `srcDoc`; it renders as source text.
- Persisted HTML uses `src` with the backend `/content` URL and `sandbox="allow-scripts"`.
- Markdown, JSON, image, PDF, code, and text continue using existing renderers.

**Implementation Steps:**

- [ ] Import `resolveFileViewer` and `PreferredFileView`.

```ts
import {
  buildRunFileViews,
  resolveFileViewer,
  type DraftWorkspaceFileInput,
  type PreferredFileView,
  type RunFileView,
  type RunFilePreviewKind,
} from "@/features/inspection/runFilesView";
```

- [ ] Add a resolved view to preview data.

```ts
interface FilePreviewData {
  kind: RunFilePreviewKind;
  viewer: PreferredFileView;
  content?: string;
  mediaType?: string | null;
  dataUrl?: string;
  url?: string;
}
```

- [ ] Resolve viewer in both preview paths.

```ts
function previewFromDraftFile(file: RunFileView): FilePreviewData | null {
  if (file.draftContent === undefined) return null;
  return {
    kind: file.previewKind,
    viewer: resolveFileViewer({ file }).view,
    mediaType: null,
    content: file.draftContent,
  };
}
```

```ts
async function readFilePreview(file: RunFileView, workspaceId: string | null): Promise<FilePreviewData> {
  if (!workspaceId || !file.path) throw new Error("No workspace file is available to preview.");
  const viewer = resolveFileViewer({ file }).view;
  if (viewer === "html_preview" || viewer === "pdf") {
    return {
      kind: file.previewKind,
      viewer,
      mediaType: null,
      url: workspacesApi.contentUrl(workspaceId, file.path),
    };
  }
  if (viewer === "image") {
    const image = await workspacesApi.viewImage(workspaceId, file.path);
    return {
      kind: file.previewKind,
      viewer,
      mediaType: image.media_type,
      dataUrl: `data:${image.media_type};base64,${image.content_base64}`,
    };
  }
  const result = await workspacesApi.readFile(workspaceId, file.path);
  return {
    kind: file.previewKind,
    viewer,
    mediaType: result.media_type,
    content: String(result.content),
  };
}
```

- [ ] Render from `preview.viewer` instead of treating every HTML content preview as an iframe.

```tsx
if (preview.viewer === "html_preview" && preview.url) {
  return (
    <iframe
      title={file.name}
      src={preview.url}
      sandbox="allow-scripts"
      className="h-full min-h-[520px] w-full rounded-md border bg-background"
    />
  );
}

if (preview.viewer === "source_text") {
  return <CodeBlock language={file.language}>{content}</CodeBlock>;
}
```

Keep the existing `Markdown`, JSON formatting, image, PDF, code, and text branches mapped by `preview.viewer`.

- [ ] Update source-level tests:

Remove the assertion that draft HTML uses `srcDoc`. Add assertions that:

```js
assert.match(source, /resolveFileViewer/);
assert.doesNotMatch(source, /srcDoc=/);
assert.match(source, /preview\.viewer === "source_text"/);
assert.match(source, /preview\.viewer === "html_preview"[\s\S]*?sandbox="allow-scripts"/);
```

**Verification:**

```bash
node frontend/tests/file-preview-drafts.test.mjs
```

---

## Task 6: Final Verification

**Commands:**

```bash
cd backend
npm run typecheck
npm run test
npm run check:no-python-backend
npm run examples:file-report
```

```bash
node frontend/tests/run-files-view.test.mjs
node frontend/tests/file-preview-drafts.test.mjs
```

**Manual Check:**

- Start the existing app server normally.
- Open a run that streams an HTML `workspace.write_file`.
- Confirm the draft preview updates as source text without iframe flashing.
- Confirm the completed HTML file opens as a rendered preview instead of raw source.
- Confirm a model-supplied `preferred_view: "source_text"` keeps persisted HTML in source mode once that hint is present on the selected file view.

---

## Self-Review

- Spec coverage: backend MIME, model advisory hint, frontend final policy, draft safety, persisted HTML rendering.
- Boundary check: no workflow semantics, no arbitrary model-selected components, no new privileged execution path.
- Type consistency: one frontend `PreferredFileView` union mirrors existing backend enum strings.
- Minimality check: no database schema, no new dependency, no viewer registry.
