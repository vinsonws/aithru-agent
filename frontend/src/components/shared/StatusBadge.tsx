import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2,
  CircleDashed,
  Clock,
  Loader2,
  OctagonAlert,
  PauseCircle,
  XCircle,
} from "lucide-react";
import type { AgentRunStatus, AgentTodoStatus, AgentApprovalStatus } from "@/lib/api";
import { useTranslation } from "react-i18next";

type BadgeVariant = "default" | "secondary" | "success" | "warning" | "destructive" | "accent" | "outline";

function statusVariant(status: string): BadgeVariant {
  if (["completed", "done", "approved", "active"].includes(status)) return "success";
  if (["running"].includes(status)) return "accent";
  if (["queued", "pending", "running" /* todo */].includes(status)) {
    return status === "running" ? "accent" : "secondary";
  }
  if (status.startsWith("waiting")) return "warning";
  if (["failed", "cancelled", "blocked", "rejected", "expired"].includes(status))
    return "destructive";
  return "outline";
}

function statusIcon(status: string) {
  if (["completed", "done", "approved"].includes(status)) return <CheckCircle2 className="h-3 w-3" />;
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin" />;
  if (status === "queued") return <CircleDashed className="h-3 w-3" />;
  if (status.startsWith("waiting")) return <Clock className="h-3 w-3" />;
  if (status === "pending") return <Clock className="h-3 w-3" />;
  if (["failed", "blocked", "rejected", "expired"].includes(status))
    return <OctagonAlert className="h-3 w-3" />;
  if (status === "cancelled") return <XCircle className="h-3 w-3" />;
  return null;
}

export function StatusBadge({
  status,
  namespace = "common",
}: {
  status: AgentRunStatus | AgentTodoStatus | AgentApprovalStatus | string;
  namespace?: string;
}) {
  const { t } = useTranslation();
  const label = t(`${namespace}:status.${status}`, { defaultValue: status });
  return (
    <Badge variant={statusVariant(status)}>
      {statusIcon(status)}
      {label}
    </Badge>
  );
}

/** Inline waiting-state indicator used inside the conversation area. */
export function PausedIndicator({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-warning">
      <PauseCircle className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}
