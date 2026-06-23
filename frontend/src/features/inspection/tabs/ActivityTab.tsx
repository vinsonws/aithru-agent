import { AlertTriangle, CheckCircle2, Circle, Clock3, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { buildRunActivity, type RunActivityItem } from "@/features/chat/runActivity";
import type { RunStreamState } from "@/features/chat/useRunStream";

export function ActivityTab({ state }: { state: RunStreamState }) {
  const { t } = useTranslation(["chat", "common"]);
  const activity = buildRunActivity(state);
  const hasProgress = activity.progress.total > 0;
  const progressValue = hasProgress
    ? Math.round((activity.progress.done / activity.progress.total) * 100)
    : 0;

  if (activity.items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-sm text-muted-foreground">
        {t("chat:noRunActivity")}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3">
      <section className="rounded-lg border bg-muted/30 p-3">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-semibold text-foreground">{t("chat:currentRun")}</span>
          <span className="text-muted-foreground">
            {t(`common:status.${activity.status}`, { defaultValue: activity.status })}
          </span>
        </div>
        {hasProgress && (
          <>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${progressValue}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
              <span>{activity.current?.title ?? t("chat:thinking")}</span>
              <span>
                {activity.progress.done}/{activity.progress.total}
              </span>
            </div>
          </>
        )}
        {activity.usageLabel && (
          <div className="mt-3 text-[11px] text-muted-foreground">{activity.usageLabel}</div>
        )}
      </section>

      <div className="mt-3 space-y-3">
        {activity.items.map((item) => (
          <ActivityRow key={`${item.source}:${item.id}`} item={item} />
        ))}
      </div>
    </div>
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
