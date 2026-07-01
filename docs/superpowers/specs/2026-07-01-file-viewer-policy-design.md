# File Viewer Policy Design

## Goal

Let model/tool output suggest how a workspace file should be viewed without letting the model directly control UI rendering or bypass safety rules.

The backend continues to provide source files. The frontend owns final viewer selection.

## Non-Goals

- No plugin viewer registry.
- No arbitrary model-supplied component names.
- No model-controlled iframe sandbox settings.
- No filesystem watchers.
- No new dependency.

## Viewer Hint Contract

Tool results, presentation targets, or future file metadata may include:

```ts
type PreferredFileView =
  | "html_preview"
  | "source_text"
  | "markdown"
  | "json"
  | "image"
  | "pdf"
  | "download";
```

This is a hint, not an instruction. Unknown values are ignored.

## Backend Responsibilities

Backend stays boring:

- Store and serve file content.
- Return correct `Content-Type` for `/api/workspaces/:workspace_id/files/:path/content`.
- Preserve optional `preferred_view` metadata when a controlled tool or presentation emits it.

Minimum MIME inference by path is enough:

- `.html`, `.htm` -> `text/html; charset=utf-8`
- `.md`, `.markdown` -> `text/markdown; charset=utf-8`
- `.json` -> `application/json; charset=utf-8`
- `.txt`, `.log`, `.csv` -> text types
- images and PDFs use their standard media types
- fallback -> `text/plain; charset=utf-8`

## Frontend Responsibilities

Frontend owns a single policy function:

```ts
type FileLifecycle = "draft" | "persisted";

function resolveFileViewer(input: {
  file: RunFileView;
  lifecycle: FileLifecycle;
  preferredView?: PreferredFileView | null;
  userView?: PreferredFileView | null;
}): {
  view: PreferredFileView;
  reason: "user" | "safety" | "hint" | "mime" | "fallback";
  sandbox: "none" | "no-scripts" | "allow-scripts";
};
```

Priority:

1. User-selected view, if allowed for that file.
2. Safety rules.
3. Model/tool `preferred_view` hint.
4. MIME or extension inference.
5. `source_text` or `download` fallback.

## Safety Rules

- Streaming draft HTML must not run scripts.
- Streaming draft HTML defaults to `source_text` to avoid iframe reload flicker.
- Persisted HTML may use `html_preview` with the existing sandbox policy.
- Draft image/PDF previews are not attempted from partial text.
- If the hint conflicts with lifecycle or file type, ignore it.

## Current Bug Coverage

This design addresses two observed issues:

- Draft HTML flicker: draft HTML no longer live-renders every streamed delta in an iframe.
- Persisted HTML showing source: `/content` returns `text/html`, so browser iframe preview renders it as HTML.

## Testing

- Backend test for `/content` MIME by extension, especially `.html`.
- Frontend policy tests for:
  - draft `.html` + hint `html_preview` resolves to safe `source_text`;
  - persisted `.html` resolves to `html_preview`;
  - explicit user view wins when safe;
  - unknown hints fall back to MIME inference.

