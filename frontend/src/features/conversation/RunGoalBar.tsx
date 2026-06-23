import { Activity, ShieldCheck, Target } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { RunTaskLoopView } from "./runTaskLoopView";

export function RunGoalBar({ view }: { view: RunTaskLoopView | null }) {
  const { t } = useTranslation("chat");
  if (!view) return null;

  const progressLabel =
    view.progress.total > 0 ? `${view.progress.done}/${view.progress.total}` : null;

  return (
    <div className="border-b bg-muted/20 px-4 py-2">
      <div className="mx-auto flex max-w-4xl items-center gap-2 overflow-hidden text-xs">
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border bg-card px-2.5 py-1.5 shadow-sm">
          <Target className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="shrink-0 font-medium text-muted-foreground">
            {t("goalBar.goal")}
          </span>
          <span className="truncate font-medium">{view.goal}</span>
        </div>
        <div className="hidden min-w-0 flex-[0.8] items-center gap-2 rounded-lg border bg-card px-2.5 py-1.5 shadow-sm md:flex">
          <Activity className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="shrink-0 font-medium text-muted-foreground">
            {t("goalBar.current")}
          </span>
          <span className="truncate">{view.currentTitle}</span>
          {progressLabel && (
            <span className="ml-auto rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {progressLabel}
            </span>
          )}
        </div>
        <div
          className={cn(
            "hidden items-center gap-1 rounded-lg border bg-card px-2.5 py-1.5 shadow-sm lg:flex",
          )}
          title={t(view.permission.labelKey, view.permission.fallback)}
        >
          <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
          <span>{t(view.permission.labelKey, view.permission.fallback)}</span>
        </div>
      </div>
    </div>
  );
}
