import { Activity, AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";
import { buildRunActivity } from "./runActivity";
import type { RunStreamState } from "./useRunStream";

export function AgentActivityCard({ state }: { state: RunStreamState }) {
  const activity = buildRunActivity(state);
  if (!activity.current || state.status === "idle") return null;

  const Icon =
    activity.current.status === "completed"
      ? CheckCircle2
      : activity.current.status === "failed"
        ? AlertTriangle
        : activity.current.status === "waiting"
          ? Clock3
          : Activity;

  return (
    <div className="mx-auto max-w-3xl px-4 py-2">
      <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <span className="min-w-0 flex-1 truncate font-medium">{activity.current.title}</span>
          {activity.progress.total > 0 && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {activity.progress.done}/{activity.progress.total}
            </span>
          )}
        </div>
        {activity.current.detail && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{activity.current.detail}</div>
        )}
      </div>
    </div>
  );
}
