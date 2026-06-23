import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import { threadsApi, runsApi } from "@/lib/api";
import * as React from "react";
import { getPromptTemplates } from "@/features/chat/promptTemplates";

export function NewThreadPage() {
  const { t } = useTranslation(["chat", "common"]);
  const { context } = useHost();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [goal, setGoal] = React.useState("");

  const createMutation = useMutation({
    mutationFn: async (goalText: string) => {
      const thread = await threadsApi.create({
        org_id: context.org?.id ?? "org_1",
        owner_user_id: context.user?.id ?? "user_1",
      });
      const run = await runsApi.create({
        goal: goalText,
        org_id: context.org?.id ?? "org_1",
        actor_user_id: context.user?.id ?? "user_1",
        scopes: ["*"],
        thread_id: thread.id,
        wait_for_completion: false,
        persist_goal_message: true,
      });
      return { thread, run };
    },
    onSuccess: ({ thread, run }) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      navigate(`/threads/${thread.id}/runs/${run.id}`);
    },
  });

  const templates = getPromptTemplates();

  return (
    <div className="flex h-full flex-1 flex-col overflow-y-auto p-6">
      <div className="mx-auto w-full max-w-2xl space-y-6">
        <div className="space-y-2 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-accent/15 text-accent">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold">What should Aithru work on?</h1>
          <p className="text-sm text-muted-foreground">
            {t("chat:newChat.subtitle", "Describe a task or choose a template below")}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {templates.map((template) => (
            <button
              key={template.id}
              type="button"
              onClick={() => setGoal(template.prompt)}
              className="flex flex-col gap-1 rounded-lg border bg-card p-3 text-left text-sm transition-colors hover:bg-secondary"
            >
              <span className="font-medium">{template.fallbackTitle}</span>
              <span className="text-xs text-muted-foreground">{template.fallbackDescription}</span>
            </button>
          ))}
        </div>
        <Textarea
          autoFocus
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder={t("chat:goalPlaceholder")}
          className="min-h-[120px]"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              if (goal.trim()) createMutation.mutate(goal.trim());
            }
          }}
        />
        <div className="flex justify-end gap-2">
          <Button
            onClick={() => goal.trim() && createMutation.mutate(goal.trim())}
            disabled={!goal.trim() || createMutation.isPending}
          >
            {t("chat:newChat.startButton", "Start")}
          </Button>
        </div>
      </div>
    </div>
  );
}
