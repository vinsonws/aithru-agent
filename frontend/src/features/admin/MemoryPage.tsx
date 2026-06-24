import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X, Trash2 } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { memoryApi } from "@/lib/api";
import type { AgentMemoryEntry, AgentMemoryCandidate } from "@/lib/api";
import { useHost } from "@/lib/host/HostProvider";
import { relativeTime } from "@/lib/utils";
import { useTranslation } from "react-i18next";

/** Memory manager content (entries + candidates) — used inside the Memory dialog. */
export function MemoryContent() {
  const { t } = useTranslation("memory");
  return (
    <Tabs defaultValue="entries">
      <TabsList>
        <TabsTrigger value="entries">{t("entries")}</TabsTrigger>
        <TabsTrigger value="candidates">{t("candidates")}</TabsTrigger>
      </TabsList>
      <TabsContent value="entries">
        <EntriesTable />
      </TabsContent>
      <TabsContent value="candidates">
        <CandidatesTable />
      </TabsContent>
    </Tabs>
  );
}

function EntriesTable() {
  const { context } = useHost();
  const { t } = useTranslation("memory");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["memory"], queryFn: () => memoryApi.list() });
  const forgetMutation = useMutation({
    mutationFn: (id: string) => memoryApi.forget(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memory"] }),
  });
  const [toForget, setToForget] = React.useState<string | null>(null);

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const rows = (q.data as AgentMemoryEntry[]) ?? [];
  return (
    <>
      <DataTable
        data={rows}
        columns={[
          { accessorKey: "scope", header: t("scope") },
          { accessorKey: "key", header: t("key"), cell: ({ row }) => <span className="font-mono text-xs">{row.original.key}</span> },
          { accessorKey: "value", header: t("value"), cell: ({ row }) => <span className="line-clamp-1 text-xs text-muted-foreground">{row.original.value}</span> },
          { accessorKey: "source", header: t("source") },
          {
            accessorKey: "created_at",
            header: "",
            cell: ({ row }) => <span className="text-xs text-muted-foreground">{relativeTime(row.original.created_at, context.locale.language)}</span>,
          },
          {
            id: "actions",
            header: "",
            cell: ({ row }) => (
              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setToForget(row.original.id)}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            ),
          },
        ]}
        empty={t("noMemory")}
      />
      <ConfirmDialog
        open={!!toForget}
        onOpenChange={(o) => !o && setToForget(null)}
        title={t("forget")}
        destructive
        confirmLabel={t("forget")}
        onConfirm={() => toForget && forgetMutation.mutate(toForget)}
      />
    </>
  );
}

function CandidatesTable() {
  const { context } = useHost();
  const { t } = useTranslation("memory");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["memory-candidates"], queryFn: () => memoryApi.candidates() });
  const approveMutation = useMutation({
    mutationFn: (id: string) => memoryApi.approveCandidate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memory-candidates"] });
      qc.invalidateQueries({ queryKey: ["memory"] });
    },
  });
  const rejectMutation = useMutation({
    mutationFn: (id: string) => memoryApi.rejectCandidate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memory-candidates"] }),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const rows = (q.data as AgentMemoryCandidate[]) ?? [];
  return (
    <DataTable
      data={rows}
      columns={[
        { accessorKey: "scope", header: t("scope") },
        { accessorKey: "key", header: t("key"), cell: ({ row }) => <span className="font-mono text-xs">{row.original.key}</span> },
        { accessorKey: "value", header: t("value"), cell: ({ row }) => <span className="line-clamp-1 text-xs text-muted-foreground">{row.original.value}</span> },
        { accessorKey: "source", header: t("source") },
        {
          accessorKey: "created_at",
          header: "",
          cell: ({ row }) => <span className="text-xs text-muted-foreground">{relativeTime(row.original.created_at, context.locale.language)}</span>,
        },
        {
          id: "actions",
          header: "",
          cell: ({ row }) => (
            <div className="flex gap-1">
              <Button size="icon" variant="outline" className="h-7 w-7 text-success" onClick={() => approveMutation.mutate(row.original.id)}>
                <Check className="h-3.5 w-3.5" />
              </Button>
              <Button size="icon" variant="outline" className="h-7 w-7 text-destructive" onClick={() => rejectMutation.mutate(row.original.id)}>
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ),
        },
      ]}
      empty={t("noCandidates")}
    />
  );
}
