import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { buildRunActivity, type RunActivityItem } from "@/features/chat/runActivity";
import { ClarificationOptions } from "@/features/chat/ClarificationOptions";
import type { RunStreamState } from "@/features/chat/useRunStream";

interface ActivityPanelProps {
  streamState: RunStreamState;
  onClose: () => void;
}

export function ActivityPanel({ streamState, onClose }: ActivityPanelProps) {
  const { t } = useTranslation(["chat", "common"]);
  const activity = buildRunActivity(streamState);

  const handleOptionSelect = (option: string) => {
    console.log("Selected option:", option);
  };

  const hasProgress = activity.progress.total > 0;
  const progressValue = hasProgress
    ? Math.round((activity.progress.done / activity.progress.total) * 100)
    : 0;

  if (activity.items.length === 0 && streamState.status === "idle") {
    return (
      <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
          <span className="flex-1 text-sm font-semibold">{t("chat:tabActivity")}</span>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 text-center text-sm text-muted-foreground">
          {t("chat:noRunActivity")}
        </div>
      </aside>
    );
  }

  return (
    <aside className="hidden shrink-0 flex-1 min-w-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3">
        <span className="flex-1 text-sm font-semibold">{t("chat:tabActivity")}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <section className="rounded-lg border bg-muted/30 p-3">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="font-semibold text-foreground">{activity.narrative.title}</span>
            <span className="text-muted-foreground">
              {t(`common:status.${activity.status}`, { defaultValue: activity.status })}
            </span>
          </div>
          {activity.narrative.detail && (
            <div className="mt-1 text-[11px] text-muted-foreground">{activity.narrative.detail}</div>
          )}
          {activity.narrative.nextAction && activity.narrative.nextAction !== "none" && (
            <div className="mt-1 text-[11px] font-medium text-warning">
              {activity.narrative.nextAction === "reply" && "Reply to continue"}
              {activity.narrative.nextAction === "reviewApproval" && "Review approval"}
              {activity.narrative.nextAction === "inspectTrace" && "View trace for details"}
            </div>
          )}
          {activity.current?.options && activity.current.options.length > 0 && (
            <ClarificationOptions options={activity.current.options} onSelect={handleOptionSelect} />
          )}
          {hasProgress && (
            <>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary" style={{ width: `${progressValue}%` }} />
              </div>
              <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                <span>{activity.current?.title ?? t("chat:thinking")}</span>
                <span>{activity.progress.done}/{activity.progress.total}</span>
              </div>
            </>
          )}
          {activity.usageLabel && (
            <div className="mt-3 text-[11px] text-muted-foreground">{activity.usageLabel}</div>
          )}
        </section>

        {activity.items.length > 0 && (
          <div className="mt-3 space-y-3">
            {activity.items.map((item) => (
              <ActivityRow key={`${item.source}:${item.id}`} item={item} />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function ActivityRow({ item }: { item: RunActivityItem }) {
  const icon = activityIcon(item);
  return (
    <div className="flex gap-2">
      <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">{icon}</div>
      <div
        className={cn(
          "min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm",
          item.status === "current" && "border-primary/30 bg-primary/5",
          item.status === "waiting" && "border-warning/40 bg-warning/5",
          item.status === "failed" && "border-destructive/35 bg-destructive/5",
        )}
      >
        <div className="truncate font-medium">{item.title}</div>
        {item.detail && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.detail}</div>
        )}
      </div>
    </div>
  );
}

function activityIcon(item: RunActivityItem) {
  if (item.status === "completed") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (item.status === "current") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (item.status === "waiting") return <Clock3 className="h-4 w-4 text-warning" />;
  if (item.status === "failed") return <AlertTriangle className="h-4 w-4 text-destructive" />;
  return <Circle className="h-4 w-4 text-muted-foreground" />;
}
