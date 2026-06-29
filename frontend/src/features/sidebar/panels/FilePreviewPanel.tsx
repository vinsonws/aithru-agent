
import { useQuery } from "@tanstack/react-query";
import { Download, X, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { runsApi, workspacesApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Markdown, CodeBlock } from "@/components/Markdown";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import {
  buildRunFileViews,
  type RunFileView,
  type RunFilePreviewKind,
} from "@/features/inspection/runFilesView";

interface FilePreviewPanelProps {
  runId: string | null;
  workspaceId: string | null;
  openFileIds: string[];
  activeFileId: string | null;
  onSelectFile: (fileId: string) => void;
  onActiveFileChange: (fileId: string | null) => void;
  onCloseFile: (fileId: string) => void;
  onClose: () => void;
}

export function FilePreviewPanel({
  runId,
  workspaceId,
  openFileIds,
  activeFileId,

  onActiveFileChange,
  onCloseFile,
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

  const snapshot = snapshotQuery.data;
  const workspaceFiles = (snapshot?.workspace_files as Array<{ path: string; size?: number; media_type?: string | null }> | undefined) ?? workspaceQuery.data ?? [];

  const views = buildRunFileViews({
    snapshot,
    workspaceId,
    workspaceFiles: workspaceFiles as Array<{ path: string; size?: number; media_type?: string | null }>,
  });

  const openFiles = views.filter((v) => openFileIds.includes(v.id));
  const activeFile = views.find((v) => v.id === activeFileId) ?? null;

  const previewQuery = useQuery({
    queryKey: ["outputs", "preview", workspaceId, activeFile?.id, activeFile?.previewKind],
    queryFn: () => readFilePreview(activeFile!, workspaceId),
    enabled: !!activeFile && activeFile.canPreview,
  });

  // Empty state: no files selected
  if (openFileIds.length === 0 || !activeFile) {
    return (
      <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
          <span className="flex-1 text-sm font-semibold">{t("chat:tabPreview", "Preview")}</span>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <EmptyState
            icon={<EyeOff className="h-10 w-10 text-muted-foreground/50" />}
            title={t("chat:preview.emptyTitle", "No file selected")}
            description={t("chat:preview.emptyDescription", "Select a file from Files to preview its contents.")}
          />
        </div>
      </aside>
    );
  }

  return (
    <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
      {/* Tab bar */}
      <div className="flex h-10 shrink-0 items-center border-b bg-muted/30 px-1">
        <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
          {openFiles.map((file) => (
            <div
              key={file.id}
              className={`flex items-center gap-1.5 rounded-t-md px-2.5 py-1.5 text-xs font-medium whitespace-nowrap transition-colors cursor-pointer ${
                file.id === activeFileId
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              }`}
              onClick={() => onActiveFileChange(file.id)}
              role="tab"
              aria-selected={file.id === activeFileId}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onActiveFileChange(file.id);
                }
              }}
            >
              <span className="max-w-[120px] truncate">{file.name}</span>
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseFile(file.id);
                }}
                className="ml-0.5 rounded p-0.5 hover:bg-muted cursor-pointer"
                title={t("chat:preview.closeTab", "Close")}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    e.stopPropagation();
                    onCloseFile(file.id);
                  }
                }}
              >
                <X className="h-3 w-3" />
              </span>
            </div>
          ))}
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* File info bar */}
      <div className="flex h-9 shrink-0 items-center gap-2 border-b px-3">
        <span className="truncate text-xs font-medium text-foreground">{activeFile.name}</span>
        <span className="shrink-0 text-[11px] text-muted-foreground">{activeFile.typeLabel}</span>
        {activeFile.sizeLabel && (
          <span className="shrink-0 text-[11px] text-muted-foreground">{activeFile.sizeLabel}</span>
        )}
        {activeFile.canDownload && activeFile.href && (
          <a
            href={activeFile.href}
            target="_blank"
            rel="noreferrer"
            className="ml-auto inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <Download className="h-3.5 w-3.5" />
            <span className="sr-only">{t("chat:files.download", "Download")}</span>
          </a>
        )}
      </div>

      {/* Preview content */}
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {previewQuery.isLoading && <LoadingState />}
        {previewQuery.error && (
          <ErrorState error={previewQuery.error} onRetry={() => previewQuery.refetch()} />
        )}
        {!previewQuery.isLoading && !previewQuery.error && previewQuery.data && (
          <PreviewBody file={activeFile} preview={previewQuery.data} />
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

// ---- Preview helpers ----

interface FilePreviewData {
  kind: RunFilePreviewKind;
  content?: string;
  mediaType?: string | null;
  dataUrl?: string;
  url?: string;
}

async function readFilePreview(file: RunFileView, workspaceId: string | null): Promise<FilePreviewData> {
  if (!workspaceId || !file.path) throw new Error("No workspace file is available to preview.");
  if (file.previewKind === "html" || file.previewKind === "pdf") {
    return {
      kind: file.previewKind,
      mediaType: null,
      url: workspacesApi.contentUrl(workspaceId, file.path),
    };
  }
  if (file.previewKind === "image") {
    const image = await workspacesApi.viewImage(workspaceId, file.path);
    return { kind: "image", mediaType: image.media_type, dataUrl: `data:${image.media_type};base64,${image.content_base64}` };
  }
  const result = await workspacesApi.readFile(workspaceId, file.path);
  return { kind: file.previewKind, mediaType: result.media_type, content: String(result.content) };
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
  if (preview.kind === "html" && preview.url) {
    return (
      <iframe
        title={file.name}
        src={preview.url}
        sandbox="allow-scripts"
        className="h-full min-h-[520px] w-full rounded-md border bg-background"
      />
    );
  }
  const content = preview.content ?? "";
  if (preview.kind === "html") {
    return <CodeBlock language="html">{content}</CodeBlock>;
  }
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
