import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, FileCode, Image, RefreshCcw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { runsApi, workspacesApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import {
  buildRunFileViews,
  type DraftWorkspaceFileInput,
  type RunFileView,
} from "@/features/inspection/runFilesView";

interface FileListPanelProps {
  runId: string | null;
  workspaceId: string | null;
  draftWorkspaceFiles?: DraftWorkspaceFileInput[];
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

export function FileListPanel({
  runId,
  workspaceId,
  draftWorkspaceFiles = [],
  onSelectFile,
  onClose,
}: FileListPanelProps) {
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

  const isLoading = snapshotQuery.isLoading || workspaceQuery.isLoading;
  const error = snapshotQuery.error || workspaceQuery.error;

  const snapshot = snapshotQuery.data;
  const workspaceFiles = (snapshot?.workspace_files as Array<{ path: string; size?: number; media_type?: string | null }> | undefined) ?? workspaceQuery.data ?? [];

  const views = buildRunFileViews({
    snapshot,
    workspaceId,
    workspaceFiles: workspaceFiles as Array<{ path: string; size?: number; media_type?: string | null }>,
    draftWorkspaceFiles,
  });

  const handleRefresh = () => {
    snapshotQuery.refetch();
    workspaceQuery.refetch();
  };

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={handleRefresh} />;

  const outputs = views.filter((v) => v.kind === "output_file");
  const modifiedFiles = views.filter((v) => v.kind === "modified_file");

  return (
    <PanelShell title={t("chat:tabFiles", "Files")} onClose={onClose}>
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
          {modifiedFiles.length > 0 && (
            <section>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t("chat:files.modified", "Modified")}
              </div>
              <div className="space-y-1">
                {modifiedFiles.map((file) => (
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
    <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
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
