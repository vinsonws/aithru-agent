import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Image as ImageIcon, FileCode, RefreshCw } from "lucide-react";
import { workspacesApi } from "@/lib/api";
import type { AgentWorkspaceFile } from "@/lib/api";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

export function WorkspaceTab({ workspaceId }: { workspaceId: string | null }) {
  const { t } = useTranslation("inspection");
  if (!workspaceId) return <EmptyState title={t("noActiveRun")} />;
  const qc = useQueryClient();

  const filesQuery = useQuery({
    queryKey: ["workspaces", workspaceId, "files"],
    queryFn: () => workspacesApi.files(workspaceId),
    refetchInterval: 5000,
  });

  const convertMutation = useMutation({
    mutationFn: (path: string) => workspacesApi.convert(workspaceId, path),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspaces", workspaceId] }),
  });

  if (filesQuery.isLoading) return <LoadingState />;
  if (filesQuery.isError) return <ErrorState error={filesQuery.error} onRetry={() => filesQuery.refetch()} />;

  const files = (filesQuery.data as AgentWorkspaceFile[]) ?? [];

  return (
    <ScrollArea className="h-full">
      <div className="space-y-1 p-1">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase text-muted-foreground">{t("files")} ({files.length})</span>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => filesQuery.refetch()}>
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
        {files.length === 0 ? (
          <EmptyState description={t("upload", { ns: "inspection" })} />
        ) : (
          files.map((f) => {
            const isImage = (f.media_type ?? "").startsWith("image/");
            return (
              <div key={f.path} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary">
                {isImage ? (
                  <ImageIcon className="h-4 w-4 text-accent" />
                ) : (f.media_type ?? "").includes("json") ? (
                  <FileCode className="h-4 w-4 text-primary" />
                ) : (
                  <FileText className="h-4 w-4 text-muted-foreground" />
                )}
                <span className="flex-1 truncate font-mono text-xs">{f.path}</span>
                {f.size != null && (
                  <span className="text-xs text-muted-foreground">{formatBytes(f.size)}</span>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  title={t("convert")}
                  onClick={() => convertMutation.mutate(f.path)}
                >
                  <RefreshCw className="h-3 w-3" />
                </Button>
              </div>
            );
          })
        )}
      </div>
    </ScrollArea>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
