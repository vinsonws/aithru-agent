import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { approvalsApi } from "@/lib/api";
import type { AgentApproval } from "@/lib/api";
import { useHost } from "@/lib/host/HostProvider";
import { relativeTime } from "@/lib/utils";
import { useTranslation } from "react-i18next";

/** Pending approvals queue — used inside the Approvals manager dialog. */
export function ApprovalsContent() {
  const { context } = useHost();
  const { t } = useTranslation("approvals");
  const qc = useQueryClient();
  const [comments, setComments] = React.useState<Record<string, string>>({});

  const q = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => approvalsApi.list({ status: "pending" }),
    refetchInterval: 8000,
  });

  const resolveMutation = useMutation({
    mutationFn: (vars: { id: string; decision: "approved" | "rejected"; comment?: string }) =>
      approvalsApi.resolve(vars.id, { decision: vars.decision, comment: vars.comment }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const rows = (q.data as AgentApproval[]) ?? [];

  if (rows.length === 0) return <EmptyState description={t("noApprovals")} />;

  return (
    <DataTable
      data={rows}
      columns={[
        {
          accessorKey: "tool_name",
          header: t("tool"),
          cell: ({ row }) => <span className="font-mono text-xs">{row.original.tool_name ?? "—"}</span>,
        },
        {
          accessorKey: "run_id",
          header: t("run"),
          cell: ({ row }) => <span className="font-mono text-xs">{row.original.run_id}</span>,
        },
        { accessorKey: "risk_level", header: t("riskLevel") },
        {
          accessorKey: "created_at",
          header: "",
          cell: ({ row }) => (
            <span className="text-xs text-muted-foreground">
              {relativeTime(row.original.created_at, context.locale.language)}
            </span>
          ),
        },
        {
          id: "status",
          header: "",
          cell: ({ row }) => <StatusBadge status={row.original.status} />,
        },
        {
          id: "actions",
          header: t("decision"),
          cell: ({ row }) => (
            <div className="flex items-center gap-2">
              <Input
                placeholder={t("commentPlaceholder")}
                className="h-7 w-32 text-xs"
                value={comments[row.original.id] ?? ""}
                onChange={(e) =>
                  setComments((c) => ({ ...c, [row.original.id]: e.target.value }))
                }
              />
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7 text-success"
                title={t("approve")}
                onClick={() =>
                  resolveMutation.mutate({
                    id: row.original.id,
                    decision: "approved",
                    comment: comments[row.original.id],
                  })
                }
              >
                <Check className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="icon"
                variant="outline"
                className="h-7 w-7 text-destructive"
                title={t("reject")}
                onClick={() =>
                  resolveMutation.mutate({
                    id: row.original.id,
                    decision: "rejected",
                    comment: comments[row.original.id],
                  })
                }
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ),
        },
      ]}
    />
  );
}
