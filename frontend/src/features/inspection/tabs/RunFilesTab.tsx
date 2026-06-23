import { useQuery } from "@tanstack/react-query";
import { FileText, FileCode, Image, RefreshCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { runsApi, workspacesApi, artifactsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { buildRunFileViews, type RunFileView } from "@/features/inspection/runFilesView";

const TYPE_ICONS: Record<string, React.ReactNode> = {
  Image: <Image className="h-4 w-4" />,
  Markdown: <FileText className="h-4 w-4" />,
  JSON: <FileCode className="h-4 w-4" />,
  TypeScript: <FileCode className="h-4 w-4" />,
  JavaScript: <FileCode className="h-4 w-4" />,
  Python: <FileCode className="h-4 w-4" />,
};

export function RunFilesTab({
  runId,
  workspaceId,
}: {
  runId: string | null;
  workspaceId: string | null;
}) {
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
    artifacts: artifacts as Array<{ id: string; name: string; type?: string; media_type?: string | null; created_at?: string; finalized?: unknown }>,
  });

  const handleRefresh = () => {
    snapshotQuery.refetch();
    workspaceQuery.refetch();
    artifactsQuery.refetch();
  };

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={handleRefresh} />;

  if (views.length === 0) {
    return (
      <div className="p-3">
        <EmptyState
          title={t("chat:files.emptyTitle", "No files")}
          description={t("chat:files.emptyDescription", "No outputs or files from this run yet.")}
        />
      </div>
    );
  }

  const outputs = views.filter((v) => v.kind === "artifact");
  const wsFiles = views.filter((v) => v.kind === "workspace_file");

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{views.length} items</span>
        <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={handleRefresh}>
          <RefreshCcw className="h-3 w-3" />
          {t("chat:files.refresh", "Refresh")}
        </Button>
      </div>
      {outputs.length > 0 && (
        <section className="mb-3">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t("chat:files.outputs", "Outputs")}
          </div>
          <div className="space-y-1">
            {outputs.map((file) => (
              <FileRow key={file.id} file={file} />
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
              <FileRow key={file.id} file={file} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function FileRow({ file }: { file: RunFileView }) {
  const icon = TYPE_ICONS[file.typeLabel] ?? <FileText className="h-4 w-4" />;

  return (
    <div className="flex items-center gap-2 rounded-md border bg-card px-2.5 py-2 text-sm">
      <span className="shrink-0 text-muted-foreground">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{file.name}</div>
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{file.typeLabel}</span>
          {file.path && <span className="truncate">{file.path}</span>}
          {file.sizeLabel && <span>{file.sizeLabel}</span>}
        </div>
      </div>
      <div className="flex shrink-0 gap-0.5">
        {file.canDownload && file.href && (
          <a
            href={file.href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-7 items-center rounded px-2 text-xs text-muted-foreground hover:bg-secondary"
            title="Download"
          >
            Download
          </a>
        )}
      </div>
    </div>
  );
}
