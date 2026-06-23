import * as React from "react";
import { Check, Edit3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { AgentRunStatus } from "@/lib/api";

export function ConversationHeader({
  title,
  fallbackTitle,
  runStatus,
  streaming,
  modelName,
  onRename,
}: {
  title?: string | null;
  fallbackTitle: string;
  runStatus?: AgentRunStatus | "idle";
  streaming: boolean;
  modelName?: string | null;
  onRename: (title: string) => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(title ?? "");

  React.useEffect(() => {
    if (!editing) setDraft(title ?? "");
  }, [editing, title]);

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b bg-card/95 px-4">
      {editing ? (
        <form
          className="flex min-w-0 items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const next = draft.trim();
            if (next) onRename(next);
            setEditing(false);
          }}
        >
          <Input autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} className="h-8 w-72 max-w-[50vw]" />
          <Button type="submit" size="icon" variant="ghost" className="h-8 w-8" aria-label="Save title">
            <Check className="h-4 w-4" />
          </Button>
        </form>
      ) : (
        <button
          type="button"
          className="flex min-w-0 items-center gap-1.5 text-sm font-semibold hover:text-primary"
          onClick={() => {
            setDraft(title ?? "");
            setEditing(true);
          }}
        >
          <span className="truncate">{title || fallbackTitle}</span>
          <Edit3 className="h-3.5 w-3.5 shrink-0 opacity-50" />
        </button>
      )}
      {runStatus && runStatus !== "idle" && <StatusBadge status={runStatus} />}
      {streaming && <span className="text-xs text-accent">● live</span>}
      {modelName && (
        <span className="ml-auto hidden max-w-48 truncate rounded-full bg-secondary px-2 py-1 text-xs text-muted-foreground sm:inline">
          {modelName}
        </span>
      )}
    </div>
  );
}
