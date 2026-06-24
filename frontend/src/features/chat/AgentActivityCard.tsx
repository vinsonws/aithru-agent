import { Activity, AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";
import { buildRunActivity } from "./runActivity";
import type { RunStreamState } from "./useRunStream";
import { useTranslation } from "react-i18next";

export function AgentActivityCard({
  state,
  variant = "status",
}: {
  state: RunStreamState;
  variant?: "status" | "thinking" | "completion";
}) {
  const { t } = useTranslation(["chat"]);
  const activity = buildRunActivity(state);
  if (state.status === "idle") return null;

  const display =
    variant === "thinking"
      ? buildThinkingDisplay(state, t)
      : variant === "completion"
        ? buildCompletionDisplay(state, activity, t)
        : buildStatusDisplay(activity);

  if (!display) return null;

  const Icon =
    variant === "thinking"
      ? Activity
      : display.status === "completed"
      ? CheckCircle2
      : display.status === "failed"
        ? AlertTriangle
        : display.status === "waiting"
          ? Clock3
          : Activity;

  return (
    <div className="mx-auto max-w-3xl px-4 py-2">
      <div
        className="rounded-lg border bg-muted/30 px-3 py-2 text-sm"
        data-testid={
          variant === "thinking"
            ? "agent-thinking-card"
            : variant === "completion"
              ? "agent-completion-card"
              : "agent-activity-card"
        }
      >
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <span className="min-w-0 flex-1 truncate font-medium">{display.title}</span>
          {activity.progress.total > 0 && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {activity.progress.done}/{activity.progress.total}
            </span>
          )}
        </div>
        {display.detail && (
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{display.detail}</div>
        )}
        {activity.usageLabel && (
          <div className="mt-1 text-[10px] text-muted-foreground">{activity.usageLabel}</div>
        )}
      </div>
    </div>
  );
}

type ActivityDisplay = {
  title: string;
  detail?: string;
  status: "completed" | "current" | "waiting" | "failed" | "next";
};

type TFunction = (key: string, options?: Record<string, unknown>) => string;

function buildStatusDisplay(activity: ReturnType<typeof buildRunActivity>): ActivityDisplay | null {
  if (!activity.current) return null;
  return {
    title: activity.narrative.title,
    detail: activity.narrative.detail,
    status: activity.current.status,
  };
}

function buildCompletionDisplay(
  state: RunStreamState,
  activity: ReturnType<typeof buildRunActivity>,
  t: TFunction,
): ActivityDisplay | null {
  if (state.status !== "completed") return null;
  return {
    title: t("chat:runCompleted", { defaultValue: "Run completed" }),
    detail: activity.narrative.detail,
    status: "completed",
  };
}

function buildThinkingDisplay(state: RunStreamState, t: TFunction): ActivityDisplay | null {
  const detailParts = [
    formatThinkingDuration(state, t),
    thinkingDetail(state, t),
  ].filter(Boolean);

  return {
    title:
      state.status === "completed"
        ? t("chat:thinkingCompletedTitle", { defaultValue: "Thought through the request" })
        : t("chat:thinking", { defaultValue: "Thinking" }),
    detail: detailParts.join(" · ") || undefined,
    status: state.status === "completed" ? "completed" : "current",
  };
}

function thinkingDetail(state: RunStreamState, t: TFunction): string {
  const activeTool = state.toolCalls.find((tool) => tool.status === "started" || tool.status === "proposed");
  if (activeTool) {
    return t("chat:thinkingRunningTool", {
      defaultValue: "Using {{tool}}",
      tool: activeTool.toolName,
    });
  }

  const currentTodo = state.todos.find((todo) => ["in_progress", "running", "active"].includes(todo.status));
  if (currentTodo) {
    return t("chat:thinkingCurrentStep", {
      defaultValue: "Working on {{step}}",
      step: currentTodo.title,
    });
  }

  const completedTools = state.toolCalls.filter((tool) => tool.status === "completed");
  if (completedTools.length > 0) {
    return t("chat:thinkingUsedTools", {
      defaultValue: "Used {{count}} tool",
      count: completedTools.length,
      tool: completedTools[completedTools.length - 1]?.toolName,
    });
  }

  if (state.status === "completed") {
    return t("chat:thinkingPrepared", { defaultValue: "Prepared the reply" });
  }

  return t("chat:thinkingPreparing", { defaultValue: "Preparing the reply" });
}

function formatThinkingDuration(state: RunStreamState, t: TFunction): string | null {
  if (!state.modelStartedAt) return null;
  const start = new Date(state.modelStartedAt).getTime();
  const end = new Date(state.modelCompletedAt ?? state.runCompletedAt ?? new Date().toISOString()).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;

  const seconds = Math.max(1, Math.round((end - start) / 1000));
  const duration =
    seconds < 60
      ? t("chat:thinkingDurationSeconds", {
          defaultValue: "{{count}}s",
          count: seconds,
        })
      : t("chat:thinkingDurationMinutes", {
          defaultValue: "{{count}}m",
          count: Math.max(1, Math.round(seconds / 60)),
        });

  return t("chat:thinkingDuration", {
    defaultValue: "Thought for {{duration}}",
    duration,
  });
}
