import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";
import { runsApi } from "@/lib/api";
import type { AgentMemoryRecall } from "@/lib/api";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useTranslation } from "react-i18next";

export function MemoryTab({ runId }: { runId: string | null }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({
    queryKey: ["runs", runId, "memory-recall"],
    queryFn: () => runsApi.memoryRecall(runId!),
    enabled: !!runId,
  });

  if (!runId) return <EmptyState title={t("noActiveRun")} />;
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const recall = q.data as AgentMemoryRecall | undefined;
  const items = recall?.items ?? [];

  return (
    <ScrollArea className="h-full">
      <div className="space-y-2 p-1">
        {items.length === 0 ? (
          <EmptyState icon={<Brain className="h-8 w-8 opacity-60" />} />
        ) : (
          items.map((item: Record<string, unknown>, i: number) => (
            <div key={(item.id as string) ?? i} className="rounded-md border p-2 text-xs">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-medium">{String(item.key ?? "")}</span>
                {(item.scope as string) && (
                  <span className="text-muted-foreground">{String(item.scope)}</span>
                )}
              </div>
              <p className="text-muted-foreground">{String(item.value ?? "")}</p>
            </div>
          ))
        )}
      </div>
    </ScrollArea>
  );
}
