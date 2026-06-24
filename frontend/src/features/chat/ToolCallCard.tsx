import * as React from "react";
import { ChevronDown, ChevronRight, Wrench, ShieldAlert, Check, X, Ban } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Markdown, CodeBlock } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import type { ToolCallEntry } from "./useRunStream";

const statusVariant: Record<
  ToolCallEntry["status"],
  "secondary" | "accent" | "success" | "destructive" | "outline"
> = {
  proposed: "secondary",
  started: "accent",
  completed: "success",
  failed: "destructive",
  denied: "destructive",
};

function StatusIcon({ status }: { status: ToolCallEntry["status"] }) {
  if (status === "completed") return <Check className="h-3 w-3" />;
  if (status === "failed" || status === "denied") return <X className="h-3 w-3" />;
  return <Wrench className="h-3 w-3" />;
}

export function ToolCallCard({ entry }: { entry: ToolCallEntry }) {
  const { t } = useTranslation(["chat", "common"]);
  const [open, setOpen] = React.useState(false);
  const risky = entry.riskLevel === "write" || entry.riskLevel === "dangerous";

  return (
    <div
      className={cn(
        "rounded-md border bg-muted/25 text-sm shadow-none",
        entry.status === "denied" && "border-destructive/30 bg-destructive/5",
        entry.status === "failed" && "border-destructive/30 bg-destructive/5",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full min-w-0 items-center gap-2 px-3 py-1.5 text-left"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium">{entry.toolName}</span>
        <Badge variant={statusVariant[entry.status]}>
          <StatusIcon status={entry.status} />
          {t(`common:status.${entry.status}`, { defaultValue: entry.status })}
        </Badge>
        {risky && (
          <Badge variant="warning">
            <ShieldAlert className="h-3 w-3" />
            {entry.riskLevel}
          </Badge>
        )}
      </button>
      {!open && (entry.outputSummary || entry.inputSummary || entry.error) && (
        <div className="border-t px-3 py-1.5 text-xs text-muted-foreground">
          <span className={cn("line-clamp-1", entry.error && "text-destructive")}>
            {entry.error || entry.outputSummary || entry.inputSummary}
          </span>
        </div>
      )}
      {open && (
        <div className="max-h-80 space-y-2 overflow-y-auto border-t px-3 py-2">
          {entry.inputSummary && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">{t("chat:toolCall")} · input</p>
              <CodeBlock language="json">{entry.inputSummary}</CodeBlock>
            </div>
          )}
          {entry.outputSummary && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">result</p>
              {entry.outputSummary.trim().startsWith("{") || entry.outputSummary.trim().startsWith("[") ? (
                <CodeBlock language="json">{entry.outputSummary}</CodeBlock>
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
