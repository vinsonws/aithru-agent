import { useQuery } from "@tanstack/react-query";
import { FileBox, Download } from "lucide-react";
import { artifactsApi } from "@/lib/api";
import type { AgentArtifact } from "@/lib/api";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useHost } from "@/lib/host/HostProvider";
import { relativeTime } from "@/lib/utils";

export function ArtifactsTab({ runId }: { runId: string | null }) {
  const { context } = useHost();
  const q = useQuery({
    queryKey: ["artifacts", { run_id: runId }],
    queryFn: () => artifactsApi.list(runId ? { run_id: runId } : undefined),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const data = q.data;
  const items: AgentArtifact[] = Array.isArray(data) ? data : (data?.items ?? []);

  return (
    <ScrollArea className="h-full">
      <div className="space-y-1 p-1">
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          items.map((a) => (
            <a
              key={a.id}
              href={`/api/artifacts/${a.id}/content`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary"
            >
              <FileBox className="h-4 w-4 text-success" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{a.name ?? a.id}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {a.type} · {relativeTime(a.created_at, context.locale.language)}
                </p>
              </div>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {a.type}
              </Badge>
              <Download className="h-3.5 w-3.5 text-muted-foreground" />
            </a>
          ))
        )}
      </div>
    </ScrollArea>
  );
}
