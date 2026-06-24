# Right Sidebar Rail + Panel Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tab-based `RunCompanion`/`InspectionPanel` with a rail-driven panel system where the right sidebar is an output-first preview surface with execution info in individual slide-out panels, triggered from icon buttons on a persistent 48px rail.

**Architecture:** The right sidebar becomes three-state: hidden (no output files), rail-only (48px icon strip), panel-open (rail + 340px panel). Five icon-triggered panels replace the four current tabs. File cards are added to the chat timeline. A new `RightRail` component orchestrates the rail; each panel is a standalone component reusing existing data-fetching and view logic.

**Tech Stack:** React 19, TypeScript, Tailwind CSS 3, shadcn/ui, lucide-react, TanStack Query, react-i18next. No new dependencies.

## Global Constraints

- No changes to left sidebar (`Sidebar` / `ConversationInbox`).
- No changes to center chat panel layout (only add FileCard within existing timeline).
- No drag-and-drop, file tree, or workflow-graph features.
- All real tool execution stays behind the Aithru capability boundary (frontend only displays).
- Follow existing naming: camelCase for functions, PascalCase for components, `@/` path aliases.
- Reuse existing view logic (`runFilesView.ts`, `runActivity.ts`, `runCompanionView.ts`) rather than rewriting.
- Tests use `node:test` + `esbuild` pattern; test files end in `.test.mjs`.
- Verification: `cd frontend && npm run typecheck && npm test`.

---

## File Map

### Create

| File | Responsibility |
|---|---|
| `frontend/src/features/sidebar/RightRail.tsx` | 48px rail with 5 icon buttons + badge support |
| `frontend/src/features/sidebar/panels/FileListPanel.tsx` | Grouped file list (artifacts + workspace files), click-to-preview |
| `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx` | File list + full-preview with back-to-list; the primary output surface |
| `frontend/src/features/sidebar/panels/ActivityPanel.tsx` | Real-time execution activity stream |
| `frontend/src/features/sidebar/panels/ApprovalsPanel.tsx` | Pending approvals with approve/reject actions |
| `frontend/src/features/sidebar/panels/TracePanel.tsx` | Run detail + span timeline + todos + usage |
| `frontend/src/features/chat/FileCard.tsx` | Inline file card rendered inside the chat message timeline |

### Modify

| File | Change |
|---|---|
| `frontend/src/AppShell.tsx` | Replace `InspectionPanel` + `RunCompanion` with new rail + panel system; remove `inspectionCollapsed`/`inspectionTab` state; add `rightPanel`/`selectedFile` state |
| `frontend/src/features/chat/ChatPanel.tsx` | Add `FileCard` rendering into the chat timeline for artifact/produced-file events |

### Remove (after integration)

| File | Reason |
|---|---|
| `frontend/src/features/inspection/InspectionPanel.tsx` | Replaced by new panel system |
| `frontend/src/features/inspection/RunCompanion.tsx` | Replaced by `RightRail` + individual panels |
| `frontend/src/features/inspection/tabs/RunFilesTab.tsx` | Replaced by `FileListPanel` + `FilePreviewPanel` |
| `frontend/src/features/inspection/tabs/ActivityTab.tsx` | Replaced by `ActivityPanel` |
| `frontend/src/features/inspection/tabs/ApprovalsTab.tsx` | Replaced by `ApprovalsPanel` |
| `frontend/src/features/inspection/tabs/RunTab.tsx` | Replaced by `TracePanel` |

### Keep (shared logic, unchanged)

| File | Used by |
|---|---|
| `frontend/src/features/inspection/runFilesView.ts` | `FileListPanel`, `FilePreviewPanel`, `FileCard` |
| `frontend/src/features/inspection/runCompanionView.ts` | `RightRail` (badge logic) |
| `frontend/src/features/chat/runActivity.ts` | `ActivityPanel` |

### Tests to update

| File | Change |
|---|---|
| `frontend/tests/app-shell-actions.test.mjs` | Update for new `rightPanel`/`selectedFile` state; remove `inspectionCollapsed` |
| `frontend/tests/app-shell-defaults.test.mjs` | Update default state expectations |
| `frontend/tests/run-companion-view.test.mjs` | Update for new rail view expectations |
| `frontend/tests/chat-conversation-flow.test.mjs` | Add `FileCard` rendering assertions |

---

## Shared Interfaces (defined here, used across tasks)

```typescript
// RightRail.tsx
interface RightRailProps {
  activePanel: string | null;
  onPanelChange: (panel: string | null) => void;
  badges: { approvals: number };
}

// FileListPanel.tsx
interface FileListPanelProps {
  runId: string | null;
  workspaceId: string | null;
  onSelectFile: (fileId: string) => void;
  onClose: () => void;
}

// FilePreviewPanel.tsx
interface FilePreviewPanelProps {
  runId: string | null;
  workspaceId: string | null;
  selectedFileId: string | null;
  onSelectFile: (fileId: string) => void;
  onClearFile: () => void;
  onClose: () => void;
}

// ActivityPanel.tsx
interface ActivityPanelProps {
  streamState: RunStreamState;
  onClose: () => void;
}

// ApprovalsPanel.tsx
interface ApprovalsPanelProps {
  runId: string | null;
  onClose: () => void;
}

// TracePanel.tsx
interface TracePanelProps {
  runId: string | null;
  onClose: () => void;
}

// FileCard.tsx
interface FileCardProps {
  file: RunFileView;
  onPreview: () => void;
}
```

---

### Task 1: RightRail Component

**Files:**
- Create: `frontend/src/features/sidebar/RightRail.tsx`
- Test: `frontend/tests/right-rail.test.mjs`

**Interfaces:**
- Consumes: None (standalone component)
- Produces: `<RightRail activePanel onPanelChange badges />`

**Description:** A 48px-wide vertical strip with 5 icon buttons. Active panel icon is highlighted. Clicking the active icon deactivates (closes panel). Badge on approvals icon.

- [ ] **Step 1: Create RightRail.tsx**

```tsx
import * as React from "react";
import { Activity, FileText, GitBranch, Image, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const PANELS = [
  { id: "preview", icon: Image, label: "Preview" },
  { id: "files", icon: FileText, label: "Files" },
  { id: null, icon: null, label: null }, // separator
  { id: "activity", icon: Activity, label: "Activity" },
  { id: "approvals", icon: ShieldCheck, label: "Approvals" },
  { id: "trace", icon: GitBranch, label: "Trace" },
] as const;

interface RightRailProps {
  activePanel: string | null;
  onPanelChange: (panel: string | null) => void;
  badges: { approvals: number };
}

export function RightRail({ activePanel, onPanelChange, badges }: RightRailProps) {
  return (
    <aside className="hidden w-12 shrink-0 flex-col items-center gap-1 border-l border-border/70 bg-background py-3 lg:flex">
      {PANELS.map((item) => {
        if (item.id === null) {
          return <div key="sep" className="my-2 w-6 border-t border-border/50" />;
        }
        const isActive = activePanel === item.id;
        const hasBadge = item.id === "approvals" && badges.approvals > 0;
        const Icon = item.icon!;

        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onPanelChange(isActive ? null : item.id)}
            title={item.label}
            className={cn(
              "relative flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
              isActive && "bg-secondary text-foreground ring-1 ring-primary/25",
            )}
          >
            <Icon className="h-4 w-4" />
            {hasBadge && (
              <Badge
                variant="destructive"
                className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]"
              >
                {badges.approvals > 9 ? "9+" : badges.approvals}
              </Badge>
            )}
          </button>
        );
      })}
    </aside>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sidebar/RightRail.tsx
git commit -m "feat: add RightRail component with 5 panel icon buttons"
```

---

### Task 2: FileListPanel Component

**Files:**
- Create: `frontend/src/features/sidebar/panels/FileListPanel.tsx`

**Interfaces:**
- Consumes: `RunFileView`, `buildRunFileViews` from `@/features/inspection/runFilesView`; `runsApi`, `workspacesApi`, `artifactsApi` from `@/lib/api`
- Produces: `<FileListPanel runId workspaceId onSelectFile onClose />`

**Description:** Panel showing grouped file list (Outputs / Workspace files). Each row is clickable and calls `onSelectFile`. Has a header with close button and refresh. Reuses the file row rendering pattern from the current `RunFilesTab`.

- [ ] **Step 1: Create FileListPanel.tsx**

```tsx
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, FileCode, Image, RefreshCcw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { runsApi, workspacesApi, artifactsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { buildRunFileViews, type RunFileView } from "@/features/inspection/runFilesView";

interface FileListPanelProps {
  runId: string | null;
  workspaceId: string | null;
  onSelectFile: (fileId: string) => void;
  onClose: () => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  Image: <Image className="h-4 w-4" />,
  Markdown: <FileText className="h-4 w-4" />,
  JSON: <FileCode className="h-4 w-4" />,
  TypeScript: <FileCode className="h-4 w-4" />,
  JavaScript: <FileCode className="h-4 w-4" />,
  Python: <FileCode className="h-4 w-4" />,
};

export function FileListPanel({ runId, workspaceId, onSelectFile, onClose }: FileListPanelProps) {
  const { t } = useTranslation(["chat", "common"]);

  const snapshotQuery = useQuery({
    queryKey: ["runs", runId, "snapshot", "files"],
    queryFn: () => runsApi.snapshot(runId!),
    enabled: !!runId,
  });

  const workspaceQuery = useQuery({
    queryKey: ["workspaces", workspaceId, "files"],
    queryFn: () => workspacesApi.files(workspaceId!),
    enabled: !!workspaceId && !snapshotQuery.data?.workspace_files,
  });

  const artifactsQuery = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => artifactsApi.list({ run_id: runId! }),
    enabled: !!runId,
  });

  const isLoading = snapshotQuery.isLoading || workspaceQuery.isLoading || artifactsQuery.isLoading;
  const error = snapshotQuery.error || workspaceQuery.error || artifactsQuery.error;

  const snapshot = snapshotQuery.data;
  const workspaceFiles = (snapshot?.workspace_files as Array<{ path: string; size?: number; media_type?: string | null }> | undefined) ?? workspaceQuery.data ?? [];
  const artifactsData = artifactsQuery.data;
  const artifacts = Array.isArray(artifactsData)
    ? artifactsData
    : (artifactsData as { items?: unknown[] } | undefined)?.items ?? [];

  const views = buildRunFileViews({
    snapshot,
    workspaceFiles: workspaceFiles as Array<{ path: string; size?: number; media_type?: string | null }>,
    artifacts: artifacts as Array<{
      id: string; name: string; type?: string; media_type?: string | null;
      created_at?: string; finalized_at?: string | null; finalized?: unknown;
      uri?: string | null; metadata?: Record<string, unknown> | null;
    }>,
  });

  const handleRefresh = () => {
    snapshotQuery.refetch();
    workspaceQuery.refetch();
    artifactsQuery.refetch();
  };

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={handleRefresh} />;

  const outputs = views.filter((v) => v.kind === "artifact");
  const wsFiles = views.filter((v) => v.kind === "workspace_file");

  return (
    <PanelShell title={t("chat:tabOutputs", "Outputs")} onClose={onClose}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          {t("chat:files.itemCount", "{{count}} items", { count: views.length })}
        </span>
        <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={handleRefresh}>
          <RefreshCcw className="h-3 w-3" />
          {t("chat:files.refresh", "Refresh")}
        </Button>
      </div>
      {views.length === 0 ? (
        <EmptyState
          title={t("chat:files.emptyTitle", "No files")}
          description={t("chat:files.emptyDescription", "No outputs or files from this run yet.")}
        />
      ) : (
        <div className="space-y-3">
          {outputs.length > 0 && (
            <section>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t("chat:files.outputs", "Outputs")}
              </div>
              <div className="space-y-1">
                {outputs.map((file) => (
                  <FileRow key={file.id} file={file} onSelect={() => onSelectFile(file.id)} />
                ))}
              </div>
            </section>
          )}
          {wsFiles.length > 0 && (
            <section>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t("chat:files.workspaceFiles", "Workspace files")}
              </div>
              <div className="space-y-1">
                {wsFiles.map((file) => (
                  <FileRow key={file.id} file={file} onSelect={() => onSelectFile(file.id)} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </PanelShell>
  );
}

function FileRow({ file, onSelect }: { file: RunFileView; onSelect: () => void }) {
  const { t } = useTranslation("chat");
  const icon = TYPE_ICONS[file.typeLabel] ?? <FileText className="h-4 w-4" />;

  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-left text-sm transition-colors hover:bg-secondary/70"
    >
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{file.name}</div>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{file.typeLabel}</span>
          {file.sizeLabel && <span>{file.sizeLabel}</span>}
        </div>
      </div>
      {file.canDownload && file.href && (
        <a
          href={file.href}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-secondary"
          title={t("chat:files.download", "Download")}
          onClick={(e) => e.stopPropagation()}
        >
          <Download className="h-3.5 w-3.5" />
        </a>
      )}
    </button>
  );
}

function PanelShell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">{title}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {children}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sidebar/panels/FileListPanel.tsx
git commit -m "feat: add FileListPanel with grouped file list"
```

---

### Task 3: FilePreviewPanel Component

**Files:**
- Create: `frontend/src/features/sidebar/panels/FilePreviewPanel.tsx`

**Interfaces:**
- Consumes: `RunFileView` from `@/features/inspection/runFilesView`; `runsApi`, `workspacesApi`, `artifactsApi` from `@/lib/api`; `Markdown`, `CodeBlock` from `@/components/Markdown`
- Produces: `<FilePreviewPanel runId workspaceId selectedFileId onSelectFile onClearFile onClose />`

**Description:** When `selectedFileId` is null, renders the file list (same layout as `FileListPanel`). When a file is selected, renders full-preview with a ← Back button. Reuses the preview logic from `RunFilesTab` (`readFilePreview`, `FilePreview`, `PreviewBody`).

- [ ] **Step 1: Create FilePreviewPanel.tsx**

```tsx
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { runsApi, workspacesApi, artifactsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Markdown, CodeBlock } from "@/components/Markdown";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import {
  buildRunFileViews,
  type RunFileView,
  type RunFilePreviewKind,
} from "@/features/inspection/runFilesView";
import {
  FileText,
  FileCode,
  Image,
  RefreshCcw,
  Download as DownloadIcon,
} from "lucide-react";

interface FilePreviewPanelProps {
  runId: string | null;
  workspaceId: string | null;
  selectedFileId: string | null;
  onSelectFile: (fileId: string) => void;
  onClearFile: () => void;
  onClose: () => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  Image: <Image className="h-4 w-4" />,
  Markdown: <FileText className="h-4 w-4" />,
  JSON: <FileCode className="h-4 w-4" />,
  TypeScript: <FileCode className="h-4 w-4" />,
  JavaScript: <FileCode className="h-4 w-4" />,
  Python: <FileCode className="h-4 w-4" />,
};

export function FilePreviewPanel({
  runId,
  workspaceId,
  selectedFileId,
  onSelectFile,
  onClearFile,
  onClose,
}: FilePreviewPanelProps) {
  const { t } = useTranslation(["chat", "common"]);

  const snapshotQuery = useQuery({
    queryKey: ["runs", runId, "snapshot", "files"],
    queryFn: () => runsApi.snapshot(runId!),
    enabled: !!runId,
  });

  const workspaceQuery = useQuery({
    queryKey: ["workspaces", workspaceId, "files"],
    queryFn: () => workspacesApi.files(workspaceId!),
    enabled: !!workspaceId && !snapshotQuery.data?.workspace_files,
  });

  const artifactsQuery = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => artifactsApi.list({ run_id: runId! }),
    enabled: !!runId,
  });

  const isLoading = snapshotQuery.isLoading || workspaceQuery.isLoading || artifactsQuery.isLoading;
  const error = snapshotQuery.error || workspaceQuery.error || artifactsQuery.error;

  const snapshot = snapshotQuery.data;
  const workspaceFiles = (snapshot?.workspace_files as Array<{ path: string; size?: number; media_type?: string | null }> | undefined) ?? workspaceQuery.data ?? [];
  const artifactsData = artifactsQuery.data;
  const artifacts = Array.isArray(artifactsData)
    ? artifactsData
    : (artifactsData as { items?: unknown[] } | undefined)?.items ?? [];

  const views = buildRunFileViews({
    snapshot,
    workspaceFiles: workspaceFiles as Array<{ path: string; size?: number; media_type?: string | null }>,
    artifacts: artifacts as Array<{
      id: string; name: string; type?: string; media_type?: string | null;
      created_at?: string; finalized_at?: string | null; finalized?: unknown;
      uri?: string | null; metadata?: Record<string, unknown> | null;
    }>,
  });

  const selectedFile = views.find((v) => v.id === selectedFileId) ?? null;

  const previewQuery = useQuery({
    queryKey: ["outputs", "preview", workspaceId, selectedFile?.id, selectedFile?.previewKind],
    queryFn: () => readFilePreview(selectedFile!, workspaceId),
    enabled: !!selectedFile && selectedFile.canPreview,
  });

  const handleRefresh = () => {
    snapshotQuery.refetch();
    workspaceQuery.refetch();
    artifactsQuery.refetch();
    previewQuery.refetch();
  };

  // Show file list when no file is selected
  if (!selectedFile) {
    if (isLoading) return <LoadingState />;
    if (error) return <ErrorState error={error} onRetry={handleRefresh} />;

    const outputs = views.filter((v) => v.kind === "artifact");
    const wsFiles = views.filter((v) => v.kind === "workspace_file");

    return (
      <PanelShell title={t("chat:tabOutputs", "Outputs")} onClose={onClose}>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">
            {t("chat:files.itemCount", "{{count}} items", { count: views.length })}
          </span>
          <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={handleRefresh}>
            <RefreshCcw className="h-3 w-3" />
            {t("chat:files.refresh", "Refresh")}
          </Button>
        </div>
        {views.length === 0 ? (
          <EmptyState
            title={t("chat:files.emptyTitle", "No files")}
            description={t("chat:files.emptyDescription", "No outputs or files from this run yet.")}
          />
        ) : (
          <div className="space-y-3">
            {outputs.length > 0 && (
              <section>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {t("chat:files.outputs", "Outputs")}
                </div>
                <div className="space-y-1">
                  {outputs.map((file) => (
                    <FileRow key={file.id} file={file} onSelect={() => onSelectFile(file.id)} />
                  ))}
                </div>
              </section>
            )}
            {wsFiles.length > 0 && (
              <section>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {t("chat:files.workspaceFiles", "Workspace files")}
                </div>
                <div className="space-y-1">
                  {wsFiles.map((file) => (
                    <FileRow key={file.id} file={file} onSelect={() => onSelectFile(file.id)} />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </PanelShell>
    );
  }

  // Full preview view
  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-2">
        <Button variant="ghost" size="sm" className="h-8 gap-1 px-2 text-xs" onClick={onClearFile}>
          <ArrowLeft className="h-3.5 w-3.5" />
          {t("chat:files.backToOutputs", "Outputs")}
        </Button>
        <span className="flex-1 truncate text-sm font-semibold">{selectedFile.name}</span>
        {selectedFile.canDownload && selectedFile.href && (
          <a
            href={selectedFile.href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
            title={t("chat:files.download", "Download")}
          >
            <Download className="h-3.5 w-3.5" />
            <span className="sr-only">{t("chat:files.download", "Download")}</span>
          </a>
        )}
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="border-b px-3 py-2">
        <div className="truncate text-sm font-semibold">{selectedFile.name}</div>
        <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
          <span>{selectedFile.typeLabel}</span>
          {selectedFile.path && <span className="truncate">{selectedFile.path}</span>}
          {selectedFile.sizeLabel && <span>{selectedFile.sizeLabel}</span>}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {previewQuery.isLoading && <LoadingState />}
        {previewQuery.error && (
          <ErrorState error={previewQuery.error} onRetry={() => previewQuery.refetch()} />
        )}
        {!previewQuery.isLoading && !previewQuery.error && previewQuery.data && (
          <PreviewBody file={selectedFile} preview={previewQuery.data} />
        )}
        {!previewQuery.isLoading && !previewQuery.error && !previewQuery.data && (
          <EmptyState
            title={t("chat:files.previewUnavailable", "Preview unavailable")}
            description={t("chat:files.previewUnavailableDescription", "Download this file to open it locally.")}
          />
        )}
      </div>
    </aside>
  );
}

function FileRow({ file, onSelect }: { file: RunFileView; onSelect: () => void }) {
  const { t } = useTranslation("chat");
  const icon = TYPE_ICONS[file.typeLabel] ?? <FileText className="h-4 w-4" />;

  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-left text-sm transition-colors hover:bg-secondary/70"
    >
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{file.name}</div>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{file.typeLabel}</span>
          {file.sizeLabel && <span>{file.sizeLabel}</span>}
        </div>
      </div>
      {file.canDownload && file.href && (
        <a
          href={file.href}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-secondary"
          title={t("chat:files.download", "Download")}
          onClick={(e) => e.stopPropagation()}
        >
          <DownloadIcon className="h-3.5 w-3.5" />
        </a>
      )}
    </button>
  );
}

// ---- Reused preview helpers from RunFilesTab ----

interface FilePreviewData {
  kind: RunFilePreviewKind;
  content?: string;
  mediaType?: string | null;
  dataUrl?: string;
  url?: string;
}

async function readFilePreview(file: RunFileView, workspaceId: string | null): Promise<FilePreviewData> {
  if (file.kind === "artifact" && file.artifactId) {
    const response = await artifactsApi.content(file.artifactId);
    const mediaType = response.headers.get("content-type");
    if (file.previewKind === "image") {
      return { kind: file.previewKind, mediaType, dataUrl: await blobToDataUrl(await response.blob()) };
    }
    return { kind: file.previewKind, mediaType, content: await response.text(), url: file.previewHref };
  }
  if (!workspaceId || !file.path) throw new Error("No workspace file is available to preview.");
  if (file.previewKind === "image") {
    const image = await workspacesApi.viewImage(workspaceId, file.path);
    return { kind: "image", mediaType: image.media_type, dataUrl: `data:${image.media_type};base64,${image.content_base64}` };
  }
  const result = await workspacesApi.readFile(workspaceId, file.path);
  return { kind: file.previewKind, mediaType: result.media_type, content: result.content };
}

function PreviewBody({ file, preview }: { file: RunFileView; preview: FilePreviewData }) {
  const { t } = useTranslation("chat");

  if (preview.kind === "image" && preview.dataUrl) {
    return (
      <div className="flex min-h-full items-start justify-center">
        <img src={preview.dataUrl} alt={file.name} className="max-h-full max-w-full rounded-md border bg-background object-contain" />
      </div>
    );
  }
  if (preview.kind === "pdf" && preview.url) {
    return <iframe title={file.name} src={preview.url} className="h-full min-h-[520px] w-full rounded-md border bg-background" />;
  }
  const content = preview.content ?? "";
  if (preview.kind === "markdown") {
    return <Markdown variant="chat">{content}</Markdown>;
  }
  if (preview.kind === "json") {
    return <CodeBlock language="json">{formatJsonContent(content)}</CodeBlock>;
  }
  if (preview.kind === "code" || preview.kind === "text") {
    return <CodeBlock language={file.language}>{content}</CodeBlock>;
  }
  return (
    <EmptyState
      title={t("chat:files.previewUnavailable", "Preview unavailable")}
      description={t("chat:files.previewUnavailableDescription", "Download this file to open it locally.")}
    />
  );
}

function formatJsonContent(content: string): string {
  try { return JSON.stringify(JSON.parse(content), null, 2); } catch { return content; }
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function PanelShell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">{title}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {children}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sidebar/panels/FilePreviewPanel.tsx
git commit -m "feat: add FilePreviewPanel with file list and full preview"
```

---

### Task 4: ActivityPanel Component

**Files:**
- Create: `frontend/src/features/sidebar/panels/ActivityPanel.tsx`

**Interfaces:**
- Consumes: `RunStreamState` from `@/features/chat/useRunStream`; `buildRunActivity`, `RunActivityItem` from `@/features/chat/runActivity`; `ClarificationOptions` from `@/features/chat/ClarificationOptions`
- Produces: `<ActivityPanel streamState onClose />`

**Description:** Reuses `buildRunActivity` from `runActivity.ts` and rendering patterns from `ActivityTab.tsx`. Shows a summary card + activity item list. Has close button in header.

- [ ] **Step 1: Create ActivityPanel.tsx**

```tsx
import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { buildRunActivity, type RunActivityItem } from "@/features/chat/runActivity";
import { ClarificationOptions } from "@/features/chat/ClarificationOptions";
import type { RunStreamState } from "@/features/chat/useRunStream";

interface ActivityPanelProps {
  streamState: RunStreamState;
  onClose: () => void;
}

export function ActivityPanel({ streamState, onClose }: ActivityPanelProps) {
  const { t } = useTranslation(["chat", "common"]);
  const activity = buildRunActivity(streamState);

  const handleOptionSelect = (option: string) => {
    console.log("Selected option:", option);
  };

  const hasProgress = activity.progress.total > 0;
  const progressValue = hasProgress
    ? Math.round((activity.progress.done / activity.progress.total) * 100)
    : 0;

  if (activity.items.length === 0 && streamState.status === "idle") {
    return (
      <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
          <span className="flex-1 text-sm font-semibold">{t("chat:tabActivity")}</span>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 text-center text-sm text-muted-foreground">
          {t("chat:noRunActivity")}
        </div>
      </aside>
    );
  }

  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">{t("chat:tabActivity")}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <section className="rounded-lg border bg-muted/30 p-3">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-semibold text-foreground">{activity.narrative.title}</span>
            <span className="text-muted-foreground">
              {t(`common:status.${activity.status}`, { defaultValue: activity.status })}
            </span>
          </div>
          {activity.narrative.detail && (
            <div className="mt-1 text-[11px] text-muted-foreground">{activity.narrative.detail}</div>
          )}
          {activity.narrative.nextAction && activity.narrative.nextAction !== "none" && (
            <div className="mt-1 text-[11px] font-medium text-warning">
              {activity.narrative.nextAction === "reply" && "Reply to continue"}
              {activity.narrative.nextAction === "reviewApproval" && "Review approval"}
              {activity.narrative.nextAction === "inspectTrace" && "View trace for details"}
            </div>
          )}
          {activity.current?.options && activity.current.options.length > 0 && (
            <ClarificationOptions options={activity.current.options} onSelect={handleOptionSelect} />
          )}
          {hasProgress && (
            <>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary" style={{ width: `${progressValue}%` }} />
              </div>
              <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                <span>{activity.current?.title ?? t("chat:thinking")}</span>
                <span>{activity.progress.done}/{activity.progress.total}</span>
              </div>
            </>
          )}
          {activity.usageLabel && (
            <div className="mt-3 text-[11px] text-muted-foreground">{activity.usageLabel}</div>
          )}
        </section>

        {activity.items.length > 0 && (
          <div className="mt-3 space-y-3">
            {activity.items.map((item) => (
              <ActivityRow key={`${item.source}:${item.id}`} item={item} />
            ))}
          </div>
        )}
      </div>
    </aside>
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

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sidebar/panels/ActivityPanel.tsx
git commit -m "feat: add ActivityPanel with real-time execution activity stream"
```

---

### Task 5: ApprovalsPanel Component

**Files:**
- Create: `frontend/src/features/sidebar/panels/ApprovalsPanel.tsx`

**Interfaces:**
- Consumes: `approvalsApi`, `AgentApproval` from `@/lib/api`; `StatusBadge` from `@/components/shared/StatusBadge`
- Produces: `<ApprovalsPanel runId onClose />`

**Description:** Lists pending approvals with approve/reject buttons. Reuses the data fetching pattern from `ApprovalsTab.tsx` and adds action controls.

- [ ] **Step 1: Create ApprovalsPanel.tsx**

```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { approvalsApi, type AgentApproval } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";

interface ApprovalsPanelProps {
  runId: string | null;
  onClose: () => void;
}

const RISK_COLORS: Record<string, string> = {
  low: "bg-success/10 text-success border-success/20",
  medium: "bg-warning/10 text-warning border-warning/20",
  high: "bg-destructive/10 text-destructive border-destructive/20",
  critical: "bg-destructive/20 text-destructive border-destructive/30",
};

export function ApprovalsPanel({ runId, onClose }: ApprovalsPanelProps) {
  const { t } = useTranslation(["chat", "common"]);
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["approvals", { run_id: runId, status: "pending" }],
    queryFn: () => approvalsApi.list({ run_id: runId ?? undefined, status: "pending" }),
    refetchInterval: 5000,
  });

  const approveMutation = useMutation({
    mutationFn: (approvalId: string) => approvalsApi.approve(approvalId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (approvalId: string) => approvalsApi.reject(approvalId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });

  const items = (q.data as AgentApproval[]) ?? [];
  const pending = items.filter((a) => a.status === "pending");

  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">
          {t("chat:tabApprovals")}
          {pending.length > 0 && (
            <span className="ml-1.5 text-xs text-muted-foreground">({pending.length})</span>
          )}
        </span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {q.isLoading && <LoadingState />}
        {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {!q.isLoading && !q.isError && pending.length === 0 && (
          <EmptyState
            icon={<ShieldCheck className="h-8 w-8 text-muted-foreground" />}
            description={t("chat:approvals.nonePending", "No pending approvals")}
          />
        )}
        {!q.isLoading && !q.isError && pending.map((approval) => (
          <div key={approval.id} className="mb-3 rounded-lg border p-3 text-sm">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-medium">{approval.tool_name ?? approval.action ?? "Approval needed"}</span>
              {approval.risk_level && (
                <Badge
                  variant="outline"
                  className={RISK_COLORS[approval.risk_level] ?? RISK_COLORS.medium}
                >
                  {approval.risk_level}
                </Badge>
              )}
            </div>
            {approval.comment && (
              <p className="mb-2 text-xs text-muted-foreground">{approval.comment}</p>
            )}
            {approval.detail && (
              <pre className="mb-2 max-h-24 overflow-auto rounded bg-muted p-2 text-[11px]">
                {JSON.stringify(approval.detail, null, 2)}
              </pre>
            )}
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs"
                disabled={approveMutation.isPending}
                onClick={() => approveMutation.mutate(approval.id)}
              >
                {t("common:approve", "Approve")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={rejectMutation.isPending}
                onClick={() => rejectMutation.mutate(approval.id)}
              >
                {t("common:reject", "Reject")}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sidebar/panels/ApprovalsPanel.tsx
git commit -m "feat: add ApprovalsPanel with approve/reject actions"
```

---

### Task 6: TracePanel Component

**Files:**
- Create: `frontend/src/features/sidebar/panels/TracePanel.tsx`

**Interfaces:**
- Consumes: `runsApi` from `@/lib/api`; `StatusBadge` from `@/components/shared/StatusBadge`
- Produces: `<TracePanel runId onClose />`

**Description:** Shows run metadata (status, duration, task, todos), span tree/timeline, token usage, and subagents. Reuses data-fetching patterns from `RunTab.tsx` but as a flat panel with close button.

- [ ] **Step 1: Create TracePanel.tsx**

```tsx
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ListTree, GitBranch, Gauge, ShieldCheck, X } from "lucide-react";
import { runsApi, type AgentTraceSpan, type AgentTodo, type AgentRunUsageSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface TracePanelProps {
  runId: string | null;
  onClose: () => void;
}

export function TracePanel({ runId, onClose }: TracePanelProps) {
  const { t } = useTranslation("inspection");

  if (!runId) {
    return (
      <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
          <span className="flex-1 text-sm font-semibold">{t("trace")}</span>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <EmptyState title={t("noActiveRun")} />
        </div>
      </aside>
    );
  }

  return (
    <aside className="hidden w-[340px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">{t("trace")}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3 space-y-4">
        <RunMetaSection runId={runId} />
        <Separator />
        <TodosSection runId={runId} />
        <Separator />
        <TraceSection runId={runId} />
        <Separator />
        <UsageSection runId={runId} />
        <Separator />
        <SubagentsSection runId={runId} />
        <Separator />
        <AuditSection runId={runId} />
      </div>
    </aside>
  );
}

function RunMetaSection({ runId }: { runId: string }) {
  const q = useQuery({
    queryKey: ["runs", runId],
    queryFn: () => runsApi.get(runId),
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const run = q.data;
  return (
    <section>
      <div className="flex items-center gap-2">
        <StatusBadge status={run?.status ?? "unknown"} />
        <span className="text-sm font-medium">{run?.task_msg ?? `Run ${runId.slice(0, 8)}`}</span>
      </div>
      <div className="mt-1 flex gap-4 text-[11px] text-muted-foreground">
        {run?.status && <span>{run.status}</span>}
        {run?.started_at && <span>{new Date(run.started_at).toLocaleTimeString()}</span>}
      </div>
    </section>
  );
}

function TodosSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({
    queryKey: ["runs", runId, "snapshot", "todos"],
    queryFn: async () => (await runsApi.snapshot(runId)).todos ?? [],
    refetchInterval: 3000,
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const todos = (q.data as AgentTodo[]) ?? [];
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <ListTree className="h-3.5 w-3.5" />
        {t("todos")}
      </h4>
      {todos.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("noTodos")}</p>
      ) : (
        <ul className="space-y-1">
          {todos.map((todo) => (
            <li key={todo.id} className="flex items-center gap-2 text-sm">
              <StatusBadge status={todo.status} />
              <span className={cn("flex-1 truncate", todo.status === "done" && "text-muted-foreground line-through")}>
                {todo.title}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const spanKindColor: Record<string, string> = {
  model: "text-accent", tool: "text-primary", sandbox: "text-warning",
  workspace: "text-primary", artifact: "text-success", run: "text-muted-foreground",
  message: "text-muted-foreground", todo: "text-muted-foreground",
};

function TraceSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({
    queryKey: ["runs", runId, "trace"],
    queryFn: () => runsApi.trace(runId),
    refetchInterval: 3000,
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const spans = (q.data as AgentTraceSpan[]) ?? [];
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <GitBranch className="h-3.5 w-3.5" />
        {t("trace")}
      </h4>
      {spans.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("noTrace")}</p>
      ) : (
        <ul className="space-y-0.5 text-xs">
          {spans.map((s) => (
            <li key={s.id} className="flex items-center gap-2 font-mono">
              <span className={cn("w-16 shrink-0 font-sans font-medium", spanKindColor[s.kind] ?? "text-muted-foreground")}>
                {s.kind}
              </span>
              <span className="flex-1 truncate">{s.name}</span>
              {s.status === "failed" && <span className="text-destructive">✕</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function UsageSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({ queryKey: ["runs", runId, "usage"], queryFn: () => runsApi.usage(runId) });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const u = q.data as AgentRunUsageSummary | undefined;
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <Gauge className="h-3.5 w-3.5" />
        {t("usage")}
      </h4>
      <dl className="grid grid-cols-2 gap-1 text-xs">
        <dt className="text-muted-foreground">Input</dt>
        <dd className="text-right font-mono">{u?.own_input_tokens ?? 0}</dd>
        <dt className="text-muted-foreground">Output</dt>
        <dd className="text-right font-mono">{u?.own_output_tokens ?? 0}</dd>
        <dt className="text-muted-foreground">Total</dt>
        <dd className="text-right font-mono">{u?.own_total_tokens ?? 0}</dd>
        <dt className="text-muted-foreground">Requests</dt>
        <dd className="text-right font-mono">{u?.own_requests ?? 0}</dd>
      </dl>
    </section>
  );
}

function SubagentsSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({ queryKey: ["runs", runId, "tree"], queryFn: () => runsApi.tree(runId) });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const tree = (q.data ?? {}) as Record<string, unknown>;
  const children = (Array.isArray((tree as Record<string, unknown>).children)
    ? (tree as Record<string, unknown>).children
    : (tree as Record<string, unknown>).nodes) as Array<Record<string, unknown>> | undefined;
  const childList = children ?? [];
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <GitBranch className="h-3.5 w-3.5" />
        {t("runTree")} / {t("subagents")}
      </h4>
      {childList.length === 0 ? (
        <p className="text-xs text-muted-foreground">—</p>
      ) : (
        <ul className="space-y-1 text-xs">
          {childList.map((c, i) => (
            <li key={String(c.id ?? i)} className="flex items-center gap-2">
              {typeof c.status === "string" && <StatusBadge status={c.status} />}
              <span className="truncate text-muted-foreground">{String(c.task_msg ?? c.id ?? "")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AuditSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const [open, setOpen] = React.useState(false);
  const q = useQuery({
    queryKey: ["runs", runId, "capability-audit"],
    queryFn: () => runsApi.capabilityAudit(runId),
    enabled: open,
  });
  return (
    <section>
      <button
        className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <ShieldCheck className="h-3.5 w-3.5" />
        {t("capabilityAudit")}
      </button>
      {open && q.data ? (
        <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-[10px]">
          {JSON.stringify(q.data, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/sidebar/panels/TracePanel.tsx
git commit -m "feat: add TracePanel with run metadata, spans, todos, and usage"
```

---

### Task 7: FileCard Component (Chat Timeline)

**Files:**
- Create: `frontend/src/features/chat/FileCard.tsx`
- Modify: `frontend/src/features/chat/ChatPanel.tsx` (add FileCard rendering)

**Interfaces:**
- Consumes: `RunFileView` from `@/features/inspection/runFilesView`
- Produces: `<FileCard file onPreview />`

**Description:** Inline file card shown in the chat message timeline when the agent produces files. Card shows file type icon, filename, type label, content snippet. Preview button opens the file in the right preview panel.

- [ ] **Step 1: Create FileCard.tsx**

```tsx
import { FileText, FileCode, Image, Eye } from "lucide-react";
import type { RunFileView } from "@/features/inspection/runFilesView";
import { useTranslation } from "react-i18next";

interface FileCardProps {
  file: RunFileView;
  onPreview: () => void;
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  Image: <Image className="h-4 w-4" />,
  Markdown: <FileText className="h-4 w-4" />,
  JSON: <FileCode className="h-4 w-4" />,
  TypeScript: <FileCode className="h-4 w-4" />,
  JavaScript: <FileCode className="h-4 w-4" />,
  Python: <FileCode className="h-4 w-4" />,
};

export function FileCard({ file, onPreview }: FileCardProps) {
  const { t } = useTranslation("chat");
  const icon = TYPE_ICONS[file.typeLabel] ?? <FileText className="h-4 w-4" />;

  return (
    <div className="my-2 rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="shrink-0 text-muted-foreground">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{file.name}</div>
          <div className="text-[11px] text-muted-foreground">{file.typeLabel}</div>
        </div>
        {file.canPreview && (
          <button
            type="button"
            onClick={onPreview}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary/10"
            title={t("chat:files.preview", "Preview")}
          >
            <Eye className="h-3.5 w-3.5" />
            {t("chat:files.preview", "Preview")}
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/chat/FileCard.tsx
git commit -m "feat: add FileCard component for inline chat file display"
```

---

### Task 8: AppShell Integration

**Files:**
- Modify: `frontend/src/AppShell.tsx`

**Interfaces:**
- Consumes: All panel components from Tasks 1-6; `RightRail` from Task 1
- Produces: Integrated `AppShell` with rail-driven right sidebar

**Description:** Replace the `InspectionPanel` / `RunCompanion` in `AppShell` with the new rail + panel system. Introduce `rightPanel` and `selectedFile` state. Determine visibility (hidden/rail/panel) based on whether output files exist. Remove `inspectionCollapsed` and `inspectionTab` localStorage state.

- [ ] **Step 1: Determine the visibility logic and modify AppShell.tsx**

The key change: determine when the right sidebar shows. The rail should appear when the run has output files (workspace files or artifacts). We'll need to check the run snapshot for file data, or use a simpler heuristic: show the rail whenever there's an active run that has progressed past `queued` status.

Read the current `AppShell.tsx` and replace the `RouteContent` / `InspectionConnector` section with the new rail system. The new state variables replace `inspectionCollapsed` and `inspectionTab`:

```tsx
// Replace these state lines in AppShell:
// const [inspectionCollapsed, setInspectionCollapsed] = useLocalStorage(...)
// const [inspectionTab, setInspectionTab] = useLocalStorage(...)

// With:
const [rightPanel, setRightPanel] = React.useState<string | null>(null);
const [selectedFile, setSelectedFile] = React.useState<string | null>(null);
```

Replace the `InspectionConnector` component and the `inspectionPanel` prop drilling with a `RightSidebar` component that renders conditionally.

The full modified `AppShell.tsx` should:

1. Import new components: `RightRail`, `FilePreviewPanel`, `FileListPanel`, `ActivityPanel`, `ApprovalsPanel`, `TracePanel`
2. Remove `InspectionPanel` import
3. Remove `useLocalStorage` for `inspectionCollapsed` and `inspectionTab`
4. Add `rightPanel` and `selectedFile` state (session-only, no localStorage)
5. Compute `hasOutputFiles` from the runs snapshot data
6. Render right sidebar conditionally: hidden if no outputs, rail if outputs exist but no panel open, rail + panel if panel open
7. Pass `onPreview` callback to `ChatPanel` for `FileCard` click handling

Since this is the integration task that ties everything together, here's the full modified `AppShell.tsx`:

```tsx
import * as React from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/features/sidebar/Sidebar";
import { ConversationPage } from "@/features/conversation/ConversationPage";
import { ManagerDialogs } from "@/features/manager/ManagerDialogs";
import { NewThreadPage } from "@/features/conversation/NewThreadPage";
import { runsApi, threadsApi } from "@/lib/api";
import { useRunStream } from "@/features/chat/useRunStream";
import type { RunStreamState } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";
import { useLocalStorage } from "@/lib/useLocalStorage";
import { resolveActiveRunId, type SelectedRunRef } from "@/features/conversation/activeRunSelection";
import { RightRail } from "@/features/sidebar/RightRail";
import { FilePreviewPanel } from "@/features/sidebar/panels/FilePreviewPanel";
import { FileListPanel } from "@/features/sidebar/panels/FileListPanel";
import { ActivityPanel } from "@/features/sidebar/panels/ActivityPanel";
import { ApprovalsPanel } from "@/features/sidebar/panels/ApprovalsPanel";
import { TracePanel } from "@/features/sidebar/panels/TracePanel";
import { buildRunCompanionBadges } from "@/features/chat/runActivity";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage("aithru-agent:sidebar-collapsed", false);
  const [rightPanel, setRightPanel] = React.useState<string | null>(null);
  const [selectedFile, setSelectedFile] = React.useState<string | null>(null);
  const [selectedRun, setSelectedRun] = React.useState<SelectedRunRef | null>(null);

  return (
    <div className="flex h-full w-full overflow-hidden bg-muted/30">
      <ManagerDialogs>
        <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={() => setSidebarCollapsed((v) => !v)} />
        <div className="flex min-w-0 flex-1">
          <RouteContent
            selectedRun={selectedRun}
            onSelectedRunChange={setSelectedRun}
            rightPanel={rightPanel}
            onRightPanelChange={setRightPanel}
            selectedFile={selectedFile}
            onSelectedFileChange={setSelectedFile}
          />
        </div>
      </ManagerDialogs>
    </div>
  );
}

function RouteContent({
  selectedRun,
  onSelectedRunChange,
  rightPanel,
  onRightPanelChange,
  selectedFile,
  onSelectedFileChange,
}: {
  selectedRun: SelectedRunRef | null;
  onSelectedRunChange: (run: SelectedRunRef | null) => void;
  rightPanel: string | null;
  onRightPanelChange: (panel: string | null) => void;
  selectedFile: string | null;
  onSelectedFileChange: (fileId: string | null) => void;
}) {
  const { pathname: path } = useLocation();
  const segments = React.useMemo(() => path.split("/").filter(Boolean), [path]);
  const threadId =
    segments[0] === "threads" && segments[1] && segments[1] !== "new"
      ? decodeURIComponent(segments[1])
      : null;
  const routeRunId =
    threadId && segments[2] === "runs" && segments[3] ? decodeURIComponent(segments[3]) : null;

  React.useEffect(() => {
    if (!threadId) {
      onSelectedRunChange(null);
      return;
    }
    if (routeRunId) {
      onSelectedRunChange({ threadId, runId: routeRunId });
    }
  }, [onSelectedRunChange, routeRunId, threadId]);

  const runsQuery = useQuery({
    queryKey: ["threads", threadId, "runs"],
    queryFn: () => threadsApi.runs(threadId!),
    enabled: !!threadId,
    refetchInterval: (q) => {
      const data = q.state.data as AgentRun[] | undefined;
      const hasActive = data?.some((run) => ["queued", "running"].includes(run.status));
      return hasActive ? 4000 : false;
    },
  });

  const activeRunId = React.useMemo(
    () =>
      resolveActiveRunId({
        threadId,
        routeRunId,
        selectedRun,
        runs: runsQuery.data,
      }),
    [routeRunId, runsQuery.data, selectedRun, threadId],
  );

  const { state: streamState } = useRunStream(activeRunId);

  // Fetch run snapshot to determine if output files exist
  const snapshotQuery = useQuery({
    queryKey: ["runs", activeRunId, "snapshot"],
    queryFn: () => runsApi.snapshot(activeRunId!),
    enabled: !!activeRunId,
    refetchInterval: 3000,
  });

  const hasOutputFiles = React.useMemo(() => {
    const snapshot = snapshotQuery.data;
    if (!snapshot) return false;
    const workspaceFiles = (snapshot as Record<string, unknown>).workspace_files as unknown[];
    const artifacts = (snapshot as Record<string, unknown>).artifacts as unknown[];
    return (Array.isArray(workspaceFiles) && workspaceFiles.length > 0) ||
           (Array.isArray(artifacts) && artifacts.length > 0);
  }, [snapshotQuery.data]);

  const badges = buildRunCompanionBadges(streamState);

  const activeRun = runsQuery.data?.find((r: AgentRun) => r.id === activeRunId);
  const workspaceId = (activeRun?.workspace_id as string | undefined) ?? null;

  const handlePreviewFile = (fileId: string) => {
    onSelectedFileChange(fileId);
    onRightPanelChange("preview");
  };

  return (
    <>
      <ConversationRoute
        threadId={threadId}
        activeRunId={activeRunId}
        onRunIdChange={(id) => onSelectedRunChange(id && threadId ? { threadId, runId: id } : null)}
        streamState={streamState}
        onPreviewFile={handlePreviewFile}
      />
      {hasOutputFiles && (
        <>
          <RightRail
            activePanel={rightPanel}
            onPanelChange={onRightPanelChange}
            badges={badges}
          />
          {rightPanel === "preview" && (
            <FilePreviewPanel
              runId={activeRunId}
              workspaceId={workspaceId}
              selectedFileId={selectedFile}
              onSelectFile={handlePreviewFile}
              onClearFile={() => onSelectedFileChange(null)}
              onClose={() => onRightPanelChange(null)}
            />
          )}
          {rightPanel === "files" && (
            <FileListPanel
              runId={activeRunId}
              workspaceId={workspaceId}
              onSelectFile={handlePreviewFile}
              onClose={() => onRightPanelChange(null)}
            />
          )}
          {rightPanel === "activity" && (
            <ActivityPanel streamState={streamState} onClose={() => onRightPanelChange(null)} />
          )}
          {rightPanel === "approvals" && (
            <ApprovalsPanel runId={activeRunId} onClose={() => onRightPanelChange(null)} />
          )}
          {rightPanel === "trace" && (
            <TracePanel runId={activeRunId} onClose={() => onRightPanelChange(null)} />
          )}
        </>
      )}
    </>
  );
}

function ConversationRoute({
  threadId,
  activeRunId,
  onRunIdChange,
  streamState,
  onPreviewFile,
}: {
  threadId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  onPreviewFile: (fileId: string) => void;
}) {
  if (!threadId) {
    return <NewThreadPage />;
  }
  return (
    <ConversationPage
      threadId={threadId}
      activeRunId={activeRunId}
      onRunIdChange={onRunIdChange}
      streamState={streamState}
      onPreviewFile={onPreviewFile}
    />
  );
}
```

- [ ] **Step 2: Update ConversationHeader to remove inspection toggle**

In `ConversationHeader.tsx`:
- Remove `inspectionCollapsed` and `onToggleInspection` from the props interface
- Remove the `inspectionLabel` variable and the toggle button (lines 45-47, 109-124)
- Remove unused imports: `PanelRightClose`, `PanelRightOpen`

- [ ] **Step 3: Update ConversationPage to use new props**

In `ConversationPage.tsx`:
- Remove props: `onSelectInspectionTab`, `inspectionPanel`, `inspectionCollapsed`, `onToggleInspection`
- Add props: `onOpenRightPanel: (panel: string) => void`, `onPreviewFile: (fileId: string) => void`
- Update `handleHeaderAction`: `reviewApproval` → `onOpenRightPanel("approvals")`, `viewTrace` → `onOpenRightPanel("trace")`
- Update `ChatComposer.onRequestStatus`: `onSelectInspectionTab("activity")` → `onOpenRightPanel("activity")`
- Pass `onPreviewFile` prop to `ChatPanel`
- Remove `inspectionPanel` from JSX (line 190)
- Remove `inspectionCollapsed` and `onToggleInspection` from `ConversationHeader` props
- Remove `ChatComposer.onRequestStatus` if it was removed, or update its callback

- [ ] **Step 4: Update ChatPanel to accept and pass onPreviewFile**

In `ChatPanel.tsx`:
- Add `onPreviewFile?: (fileId: string) => void` to props
- The prop is forwarded so that `FileCard` components rendered in the chat timeline can trigger preview

File card rendering integration: for this initial pass, wire the `onPreviewFile` callback through. The full file-card-in-timeline rendering (detecting file-producing tool calls and emitting `FileCard` components) is done in Task 7 - the cards are inserted into the `ChatTimelineItem` stream in `ChatPanel`.

- [ ] **Step 5: Run typecheck**

```bash
cd frontend && npm run typecheck
```

Expected: no type errors. May need to fix prop drilling through `ConversationPage` and `ChatPanel`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/AppShell.tsx
git commit -m "feat: integrate RightRail and panel system into AppShell"
```

---

### Task 9: Remove Deprecated Files and Update Existing Tests

**Files:**
- Remove: `frontend/src/features/inspection/InspectionPanel.tsx`
- Remove: `frontend/src/features/inspection/RunCompanion.tsx`
- Remove: `frontend/src/features/inspection/tabs/RunFilesTab.tsx`
- Remove: `frontend/src/features/inspection/tabs/ActivityTab.tsx`
- Remove: `frontend/src/features/inspection/tabs/ApprovalsTab.tsx`
- Remove: `frontend/src/features/inspection/tabs/RunTab.tsx`
- Modify: `frontend/tests/app-shell-actions.test.mjs`
- Modify: `frontend/tests/app-shell-defaults.test.mjs`
- Modify: `frontend/tests/run-companion-view.test.mjs`
- Modify: `frontend/tests/chat-conversation-flow.test.mjs`

**Description:** Remove the old components. Update existing tests to match the new state shape (`rightPanel`/`selectedFile` instead of `inspectionCollapsed`/`inspectionTab`). Keep shared logic files (`runFilesView.ts`, `runCompanionView.ts`, `runActivity.ts`).

- [ ] **Step 1: Remove old component files**

```bash
rm frontend/src/features/inspection/InspectionPanel.tsx
rm frontend/src/features/inspection/RunCompanion.tsx
rm frontend/src/features/inspection/tabs/RunFilesTab.tsx
rm frontend/src/features/inspection/tabs/ActivityTab.tsx
rm frontend/src/features/inspection/tabs/ApprovalsTab.tsx
rm frontend/src/features/inspection/tabs/RunTab.tsx
```

- [ ] **Step 2: Update test: app-shell-defaults.test.mjs**

Update the test to no longer expect `inspectionCollapsed` default. The test should verify the new defaults for `rightPanel` (null) and `selectedFile` (null).

- [ ] **Step 3: Update test: app-shell-actions.test.mjs**

Update to test `rightPanel` toggling behavior instead of `inspectionCollapsed`. The test should verify:
- Setting `rightPanel` to "preview" opens the panel
- Setting `rightPanel` to null closes the panel
- Clicking the same icon twice toggles the panel off

- [ ] **Step 4: Update test: run-companion-view.test.mjs**

The `buildRunCompanionRailView` function is kept; ensure its tests still pass. Update any test references from `inspection` to new panel paths.

- [ ] **Step 5: Update test: chat-conversation-flow.test.mjs**

Add assertions for `FileCard` rendering in the chat timeline when artifacts are present.

- [ ] **Step 6: Run all tests**

```bash
cd frontend && npm test
```

Expected: all tests pass.

- [ ] **Step 7: Run full verification**

```bash
cd backend && uv run pytest
cd ../frontend && npm run typecheck && npm test
```

- [ ] **Step 8: Commit**

```bash
git add -u frontend/
git commit -m "chore: remove deprecated inspection components, update tests"
```

---

### Task 10: Final Verification and Cleanup

**Files:**
- (No new files; verify and clean up any remaining references)

**Description:** Run the full test suite and example to confirm nothing is broken. Remove any remaining dead imports or references.

- [ ] **Step 1: Full typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 2: Full test suite**

```bash
cd frontend && npm test
```

- [ ] **Step 3: Verify backend example still works**

```bash
cd ../backend && uv run python examples/file_report_agent.py
```

- [ ] **Step 4: Run backend tests**

```bash
cd ../backend && uv run pytest
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final verification and cleanup for right sidebar redesign"
```
