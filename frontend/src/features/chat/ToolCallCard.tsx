import * as React from "react";
import { ChevronDown, ChevronRight, Wrench, ShieldAlert, Check, X, Ban } from "lucide-react";
import { Markdown, CodeBlock } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import type { ToolCallEntry } from "./useRunStream";

function StatusIcon({ status }: { status: ToolCallEntry["status"] }) {
  if (status === "completed") return <Check className="h-3 w-3" />;
  if (status === "failed" || status === "denied") return <X className="h-3 w-3" />;
  return <Wrench className="h-3 w-3" />;
}

function statusTone(status: ToolCallEntry["status"]): string {
  if (status === "completed") return "bg-success/10 text-success";
  if (status === "failed" || status === "denied") return "bg-destructive/10 text-destructive";
  if (status === "started") return "bg-accent/10 text-accent";
  return "bg-muted text-muted-foreground";
}

export function ToolCallCard({ entry }: { entry: ToolCallEntry }) {
  const { t } = useTranslation(["chat", "common"]);
  const [open, setOpen] = React.useState(false);
  const risky = entry.riskLevel === "write" || entry.riskLevel === "dangerous";
  const summary = entry.error || entry.outputSummary || entry.inputSummary;

  return (
    <div
      data-testid="tool-call-row"
      className={cn(
        "text-sm",
        (entry.status === "denied" || entry.status === "failed") && "text-destructive",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full min-w-0 items-center gap-2 rounded-md px-0 py-1 text-left text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t("chat:process.toolLabel")}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium text-foreground">{entry.toolName}</span>
        {summary && !open && (
          <span className={cn("hidden min-w-0 flex-[1.4] truncate text-xs text-muted-foreground sm:block", entry.error && "text-destructive")}>
            {summary}
          </span>
        )}
        <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", statusTone(entry.status))}>
          <StatusIcon status={entry.status} />
          {t(`common:status.${entry.status}`, { defaultValue: entry.status })}
        </span>
        {risky && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning">
            <ShieldAlert className="h-3 w-3" />
            {entry.riskLevel}
          </span>
        )}
      </button>
      {open && (
        <div className="ml-5 max-h-80 space-y-2 overflow-y-auto border-l border-border/70 py-2 pl-3">
          {entry.inputSummary && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">{t("chat:toolCall")} · input</p>
              <CodeBlock language="json">{entry.inputSummary}</CodeBlock>
            </div>
          )}
          {entry.outputSummary && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">{t("chat:process.resultLabel")}</p>
              {entry.outputSummary.trim().startsWith("{") || entry.outputSummary.trim().startsWith("[") ? (
                <CodeBlock language="json" className="bg-muted/60">{entry.outputSummary}</CodeBlock>
              ) : (
                <div className="max-w-none text-foreground">
                  <Markdown variant="chat">{entry.outputSummary}</Markdown>
                </div>
              )}
            </div>
          )}
          {entry.status === "denied" && (
            <p className="flex items-center gap-1 text-xs text-destructive">
              <Ban className="h-3 w-3" />
              {t("chat:toolDenied")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
