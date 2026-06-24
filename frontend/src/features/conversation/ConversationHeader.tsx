import * as React from "react";
import {
  Check,
  Edit3,
  Square,
  MessageSquare,
  ShieldCheck,
  RotateCcw,
  GitBranch,
  Settings,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { RunHeaderView } from "./runHeaderView";
import { useTranslation } from "react-i18next";

const ACTION_ICONS: Record<string, React.ReactNode> = {
  stop: <Square className="h-3.5 w-3.5" />,
  reply: <MessageSquare className="h-3.5 w-3.5" />,
  reviewApproval: <ShieldCheck className="h-3.5 w-3.5" />,
  retry: <RotateCcw className="h-3.5 w-3.5" />,
  viewTrace: <GitBranch className="h-3.5 w-3.5" />,
  openModelSettings: <Settings className="h-3.5 w-3.5" />,
};

export function ConversationHeader({
  view,
  onRename,
  onAction,
}: {
  view: RunHeaderView;
  onRename: (title: string) => void;
  onAction: (kind: string) => void;
}) {
  const { t } = useTranslation(["chat"]);
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(view.title);

  React.useEffect(() => {
    if (!editing) setDraft(view.title);
  }, [editing, view.title]);

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
          <Input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="h-8 w-72 max-w-[50vw]"
          />
          <Button type="submit" size="icon" variant="ghost" className="h-8 w-8" aria-label={t("saveTitle", "Save title")}>
            <Check className="h-4 w-4" />
          </Button>
        </form>
      ) : (
        <div className="flex min-w-0 items-center gap-1.5">
          <button
            type="button"
            className="flex items-center gap-1.5 text-sm font-semibold hover:text-primary"
            onClick={() => {
              setDraft(view.title);
              setEditing(true);
            }}
          >
            <span className="truncate">{view.title || view.fallbackTitle}</span>
            <Edit3 className="h-3.5 w-3.5 shrink-0 opacity-50" />
          </button>
        </div>
      )}
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        <StatusChip tone={view.status.tone} label={t(view.status.labelKey, view.status.fallback)} />
        {view.actions.map((action) => {
          const actionLabel = t(action.labelKey, action.fallback);
          return (
            <Button
              key={action.kind}
              variant={action.kind === "stop" ? "destructive" : "ghost"}
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() => onAction(action.kind)}
              title={actionLabel}
              aria-label={actionLabel}
            >
              {ACTION_ICONS[action.kind]}
              <span className="hidden sm:inline">{actionLabel}</span>
            </Button>
          );
        })}
      </div>
    </div>
  );
}

function StatusChip({ tone, label }: { tone: string; label: string }) {
  const colors: Record<string, string> = {
    muted: "bg-muted text-muted-foreground",
    queued: "bg-muted text-muted-foreground",
    live: "bg-accent/10 text-accent",
    waiting: "bg-warning/10 text-warning",
    success: "bg-success/10 text-success",
    danger: "bg-destructive/10 text-destructive",
    cancelled: "bg-muted text-muted-foreground",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        colors[tone] ?? colors.muted,
      )}
    >
      {label}
    </span>
  );
}
