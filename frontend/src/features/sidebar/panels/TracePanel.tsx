import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ListTree, GitBranch, Gauge, ShieldCheck, X } from "lucide-react";
import { runsApi, type AgentTraceSpan, type AgentTodo, type AgentRunUsageSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/states";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface TracePanelProps {
  runId: string | null;
  onClose: () => void;
}

export function TracePanel({ runId, onClose }: TracePanelProps) {
  const { t } = useTranslation("inspection");

  if (!runId) {
    return (
      <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
          <span className="flex-1 text-sm font-semibold">{t("trace")}</span>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <EmptyState title={t("noActiveRun")} />
        </div>
      </aside>
    );
  }

  return (
    <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">{t("trace")}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3 space-y-4">
        <RunMetaSection runId={runId} />
        <Separator />
        <TodosSection runId={runId} />
        <Separator />
        <TraceSection runId={runId} />
        <Separator />
        <UsageSection runId={runId} />
        <Separator />
        <SubagentsSection runId={runId} />
        <Separator />
        <AuditSection runId={runId} />
      </div>
    </aside>
  );
}

function RunMetaSection({ runId }: { runId: string }) {
  const q = useQuery({
    queryKey: ["runs", runId],
    queryFn: () => runsApi.get(runId),
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const run = q.data;
  return (
    <section>
      <div className="flex items-center gap-2">
        <StatusBadge status={run?.status ?? "unknown"} />
        <span className="text-sm font-medium">{run?.task_msg ?? `Run ${runId.slice(0, 8)}`}</span>
      </div>
      <div className="mt-1 flex gap-4 text-[11px] text-muted-foreground">
        {run?.status && <span>{run.status}</span>}
        {run?.started_at && <span>{new Date(run.started_at).toLocaleTimeString()}</span>}
      </div>
    </section>
  );
}

function TodosSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({
    queryKey: ["runs", runId, "snapshot", "todos"],
    queryFn: async () => (await runsApi.snapshot(runId)).todos ?? [],
    refetchInterval: 3000,
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const todos = (q.data as AgentTodo[]) ?? [];
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <ListTree className="h-3.5 w-3.5" />
        {t("todos")}
      </h4>
      {todos.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("noTodos")}</p>
      ) : (
        <ul className="space-y-1">
          {todos.map((todo) => (
            <li key={todo.id} className="flex items-center gap-2 text-sm">
              <StatusBadge status={todo.status} />
              <span className={cn("flex-1 truncate", todo.status === "done" && "text-muted-foreground line-through")}>
                {todo.title}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const spanKindColor: Record<string, string> = {
  model: "text-accent", tool: "text-primary", sandbox: "text-warning",
  workspace: "text-primary", artifact: "text-success", run: "text-muted-foreground",
  message: "text-muted-foreground", todo: "text-muted-foreground",
};

function TraceSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({
    queryKey: ["runs", runId, "trace"],
    queryFn: () => runsApi.trace(runId),
    refetchInterval: 3000,
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const spans = (q.data as AgentTraceSpan[]) ?? [];
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <GitBranch className="h-3.5 w-3.5" />
        {t("trace")}
      </h4>
      {spans.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("noTrace")}</p>
      ) : (
        <ul className="space-y-0.5 text-xs">
          {spans.map((s) => (
            <li key={s.id} className="flex items-center gap-2 font-mono">
              <span className={cn("w-16 shrink-0 font-sans font-medium", spanKindColor[s.kind] ?? "text-muted-foreground")}>
                {s.kind}
              </span>
              <span className="flex-1 truncate">{s.name}</span>
              {s.status === "failed" && <span className="text-destructive">✕</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function UsageSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({ queryKey: ["runs", runId, "usage"], queryFn: () => runsApi.usage(runId) });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const u = q.data as AgentRunUsageSummary | undefined;
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <Gauge className="h-3.5 w-3.5" />
        {t("usage")}
      </h4>
      <dl className="grid grid-cols-2 gap-1 text-xs">
        <dt className="text-muted-foreground">Input</dt>
        <dd className="text-right font-mono">{u?.own_input_tokens ?? 0}</dd>
        <dt className="text-muted-foreground">Output</dt>
        <dd className="text-right font-mono">{u?.own_output_tokens ?? 0}</dd>
        <dt className="text-muted-foreground">Total</dt>
        <dd className="text-right font-mono">{u?.own_total_tokens ?? 0}</dd>
        <dt className="text-muted-foreground">Requests</dt>
        <dd className="text-right font-mono">{u?.own_requests ?? 0}</dd>
      </dl>
    </section>
  );
}

function SubagentsSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const q = useQuery({ queryKey: ["runs", runId, "tree"], queryFn: () => runsApi.tree(runId) });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} />;
  const tree = (q.data ?? {}) as Record<string, unknown>;
  const children = (Array.isArray((tree as Record<string, unknown>).children)
    ? (tree as Record<string, unknown>).children
    : (tree as Record<string, unknown>).nodes) as Array<Record<string, unknown>> | undefined;
  const childList = children ?? [];
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
        <GitBranch className="h-3.5 w-3.5" />
        {t("runTree")} / {t("subagents")}
      </h4>
      {childList.length === 0 ? (
        <p className="text-xs text-muted-foreground">—</p>
      ) : (
        <ul className="space-y-1 text-xs">
          {childList.map((c, i) => (
            <li key={String(c.id ?? i)} className="flex items-center gap-2">
              {typeof c.status === "string" && <StatusBadge status={c.status} />}
              <span className="truncate text-muted-foreground">{String(c.task_msg ?? c.id ?? "")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AuditSection({ runId }: { runId: string }) {
  const { t } = useTranslation("inspection");
  const [open, setOpen] = React.useState(false);
  const q = useQuery({
    queryKey: ["runs", runId, "capability-audit"],
    queryFn: () => runsApi.capabilityAudit(runId),
    enabled: open,
  });
  return (
    <section>
      <button
        className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <ShieldCheck className="h-3.5 w-3.5" />
        {t("capabilityAudit")}
      </button>
      {open && q.data ? (
        <pre className="max-h-48 overflow-auto rounded bg-muted p-2 text-[10px]">
          {JSON.stringify(q.data, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}
