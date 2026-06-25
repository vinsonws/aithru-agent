import * as React from "react";
import {
  Check,
  Coins,
  Edit3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { RunHeaderView } from "./runHeaderView";
import { buildTokenUsageDisplay, type TokenUsageCounters } from "./tokenUsageStat";
import { useTranslation } from "react-i18next";

export function ConversationHeader({
  view,
  tokenUsage,
  onRename,
}: {
  view: RunHeaderView;
  tokenUsage?: TokenUsageCounters | null;
  onRename: (title: string) => void;
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
        <TokenUsageStat usage={tokenUsage} />
        <StatusChip tone={view.status.tone} label={t(view.status.labelKey, view.status.fallback)} />
      </div>
    </div>
  );
}

function TokenUsageStat({ usage }: { usage?: TokenUsageCounters | null }) {
  const { t } = useTranslation(["chat"]);
  const display = React.useMemo(() => buildTokenUsageDisplay(usage), [usage]);
  const [open, setOpen] = React.useState(false);
  const tooltipId = React.useId();
  const showDetail = React.useCallback(() => setOpen(true), []);
  const hideDetail = React.useCallback(() => setOpen(false), []);

  if (!display) return null;

  const label = t("chat:usageSummaryAria", {
    value: display.summary,
    defaultValue: "Token usage: {{value}}",
  });

  return (
    <div
      className="group relative hidden sm:block"
      onMouseEnter={showDetail}
      onMouseLeave={hideDetail}
      onMouseOver={showDetail}
      onPointerEnter={showDetail}
      onPointerLeave={hideDetail}
      onFocus={showDetail}
      onBlur={hideDetail}
    >
      <button
        type="button"
        className="inline-flex h-8 items-center gap-1.5 rounded-md px-1.5 text-sm font-medium tabular-nums text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-describedby={open ? tooltipId : undefined}
        aria-label={label}
        onPointerDown={(event) => {
          event.preventDefault();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") hideDetail();
        }}
      >
        <Coins className="h-4 w-4" />
        <span>{display.summary}</span>
      </button>
      <div
        id={tooltipId}
        role="tooltip"
        className={cn(
          "pointer-events-none invisible absolute right-0 top-full z-50 mt-2 w-52 rounded-xl bg-[#070c11] p-0 text-slate-50 opacity-0 shadow-xl ring-1 ring-white/10 transition-opacity duration-100 group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100",
          open && "visible opacity-100",
        )}
      >
        <div className="px-4 py-3">
          <div className="text-sm font-semibold">{t("chat:usageTooltipTitle")}</div>
          <dl className="mt-2 space-y-1.5 text-sm">
            <TokenUsageRow label={t("chat:usageInput")} value={display.input} />
            <TokenUsageRow label={t("chat:usageOutput")} value={display.output} />
          </dl>
          <div className="my-2 h-px bg-white/20" />
          <dl className="text-sm">
            <TokenUsageRow label={t("chat:usageTotal")} value={display.total} />
          </dl>
        </div>
      </div>
    </div>
  );
}

function TokenUsageRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-5">
      <dt className="font-medium text-slate-100">{label}</dt>
      <dd className="font-mono font-semibold tabular-nums text-slate-50">{value}</dd>
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
