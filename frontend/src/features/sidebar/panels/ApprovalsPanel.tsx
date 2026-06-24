import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { approvalsApi, type AgentApproval } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";

interface ApprovalsPanelProps {
  runId: string | null;
  onClose: () => void;
}

export function ApprovalsPanel({ runId, onClose }: ApprovalsPanelProps) {
  const { t } = useTranslation(["chat", "common", "approvals"]);
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["approvals", { run_id: runId, status: "pending" }],
    queryFn: () => approvalsApi.list({ run_id: runId ?? undefined, status: "pending" }),
    refetchInterval: 5000,
  });

  const resolveMutation = useMutation({
    mutationFn: (vars: { id: string; decision: "approved" | "rejected" }) =>
      approvalsApi.resolve(vars.id, { decision: vars.decision }),
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
            description={t("approvals:nonePending", "No pending approvals")}
          />
        )}
        {!q.isLoading && !q.isError && pending.map((approval) => (
          <div key={approval.id} className="mb-3 rounded-lg border p-3 text-sm">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-medium">{approval.tool_name ?? "Approval needed"}</span>
            </div>
            {approval.comment && (
              <p className="mb-2 text-xs text-muted-foreground">{approval.comment}</p>
            )}
            {approval.tool_input && (
              <pre className="mb-2 max-h-24 overflow-auto rounded bg-muted p-2 text-[11px]">
                {JSON.stringify(approval.tool_input, null, 2)}
              </pre>
            )}
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs"
                disabled={resolveMutation.isPending}
                onClick={() => resolveMutation.mutate({ id: approval.id, decision: "approved" })}
              >
                {t("approvals:approve")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={resolveMutation.isPending}
                onClick={() => resolveMutation.mutate({ id: approval.id, decision: "rejected" })}
              >
                {t("approvals:reject")}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
