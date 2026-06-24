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
