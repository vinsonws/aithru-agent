import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import { threadsApi, runsApi, modelProfilesApi } from "@/lib/api";
import { getPromptTemplates } from "@/features/chat/promptTemplates";
import {
  ReferenceComposerSurface,
} from "@/features/chat/ReferenceComposerSurface";
import {
  buildComposerHarnessOptions,
  buildComposerScopes,
  composerModeForReasoningLevel,
  reasoningLevelForComposerMode,
  type ComposerPermissionPolicyId,
  type ComposerReasoningLevel,
} from "@/features/chat/composerState";
import { parseSlashCommand } from "@/features/chat/slashCommands";
import { SLASH_SUGGESTIONS } from "@/features/chat/composerSuggestions";

export function NewThreadPage() {
  const { t } = useTranslation(["chat", "common"]);
  const { context } = useHost();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const [taskMsg, setTaskMsg] = React.useState("");
  const [reasoningLevel, setReasoningLevel] =
    React.useState<ComposerReasoningLevel>("pro");
  const [profileKey, setProfileKey] = React.useState<string>("");
  const [permissionPolicy, setPermissionPolicy] =
    React.useState<ComposerPermissionPolicyId>("ask");

  const profilesQuery = useQuery({
    queryKey: ["model-profiles"],
    queryFn: modelProfilesApi.list,
  });

  React.useEffect(() => {
    const profiles = profilesQuery.data;
    if (!profiles || profiles.length === 0) {
      setProfileKey("");
      return;
    }
    if (profileKey && profiles.some((p) => p.key === profileKey && p.enabled)) {
      return;
    }
    const firstEnabled = profiles.find((p) => p.enabled);
    setProfileKey(firstEnabled?.key ?? "");
  }, [profilesQuery.data, profileKey]);

  const createMutation = useMutation({
    mutationFn: async (vars: {
      taskMsgText: string;
      profileKey: string | null;
      reasoningLevel: ComposerReasoningLevel;
      permissionPolicy: ComposerPermissionPolicyId;
    }) => {
      const mode = composerModeForReasoningLevel(vars.reasoningLevel);
      const harnessOptions = buildComposerHarnessOptions(
        vars.profileKey,
        mode,
        vars.reasoningLevel,
      );
      const thread = await threadsApi.create({
        org_id: context.org?.id ?? "org_1",
        owner_user_id: context.user?.id ?? "user_1",
      });
      const run = await runsApi.create({
        task_msg: vars.taskMsgText,
        org_id: context.org?.id ?? "org_1",
        actor_user_id: context.user?.id ?? "user_1",
        scopes: buildComposerScopes(vars.permissionPolicy),
        thread_id: thread.id,
        skill_id: null,
        harness_options: harnessOptions ?? null,
        wait_for_completion: false,
        persist_task_msg_message: true,
      });
      return { thread, run };
    },
    onSuccess: ({ thread, run }) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      navigate(`/threads/${thread.id}/runs/${run.id}`);
    },
  });

  const handleSend = () => {
    const trimmed = taskMsg.trim();
    if (!trimmed || createMutation.isPending) return;

    const command = parseSlashCommand(trimmed, {});
    if (command.kind === "local") {
      if (command.action === "clear") setTaskMsg("");
      return;
    }
    if (command.kind === "draft") {
      setTaskMsg(command.draft);
      if (command.modeOverride) {
        setReasoningLevel(reasoningLevelForComposerMode(command.modeOverride));
      }
      textareaRef.current?.focus();
      return;
    }

    const nextReasoning = command.modeOverride
      ? reasoningLevelForComposerMode(command.modeOverride)
      : reasoningLevel;
    createMutation.mutate({
      taskMsgText: command.taskMsg,
      profileKey,
      reasoningLevel: nextReasoning,
      permissionPolicy,
    });
    setTaskMsg("");
    if (command.modeOverride) setReasoningLevel(nextReasoning);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleTemplateClick = (template: { prompt: string; mode: string }) => {
    setTaskMsg(template.prompt);
    setReasoningLevel(reasoningLevelForComposerMode(template.mode));
    textareaRef.current?.focus();
  };

  const handleSlashSuggestionSelect = (command: string) => {
    setTaskMsg(`${command} `);
    textareaRef.current?.focus();
  };

  const templates = getPromptTemplates();

  return (
    <div className="flex h-full flex-1 overflow-x-hidden overflow-y-auto bg-background px-4 py-8 sm:p-8">
      <div className="mx-auto flex min-h-full w-full max-w-[46rem] min-w-0 flex-col justify-center gap-6 py-8">
        <div className="space-y-2 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-accent/15 text-accent">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-3xl font-semibold tracking-normal text-foreground">
            {t("chat:newChat.title", "What should Aithru work on?")}
          </h1>
          <p className="mx-auto max-w-2xl text-base font-medium leading-7 text-muted-foreground">
            {t("chat:newChat.subtitle", "Describe a task or choose a template below")}
          </p>
        </div>
        <ReferenceComposerSurface
          value={taskMsg}
          onChange={setTaskMsg}
          onKeyDown={handleKeyDown}
          onSend={handleSend}
          sendDisabled={!taskMsg.trim() || !profileKey}
          sendPending={createMutation.isPending}
          placeholder={t("chat:taskMsgPlaceholder")}
          sendLabel={t("chat:newChat.startButton", "Start")}
          cancelLabel={t("chat:cancelRun")}
          attachFileLabel={t("chat:attachFile")}
          profileKey={profileKey}
          onProfileKeyChange={setProfileKey}
          modelProfiles={profilesQuery.data}
          selectModelLabel={t("chat:selectModelProfile")}
          reasoningLevel={reasoningLevel}
          onReasoningLevelChange={setReasoningLevel}
          permissionPolicy={permissionPolicy}
          onPermissionPolicyChange={setPermissionPolicy}
          autoFocus
          textareaRef={textareaRef}
          slashSuggestions={SLASH_SUGGESTIONS}
          showSlashSuggestions={taskMsg.trim().startsWith("/")}
          onSlashSuggestionSelect={handleSlashSuggestionSelect}
        />
        <div className="flex flex-wrap justify-center gap-2">
          {templates.map((template) => {
            const templateTitle = t(template.titleKey, template.fallbackTitle);
            const templateDescription = t(template.descriptionKey, template.fallbackDescription);
            return (
              <button
                key={template.id}
                type="button"
                data-testid="template-stamp"
                onClick={() => handleTemplateClick(template)}
                className="rounded-full border border-border/80 bg-card/90 px-3.5 py-1.5 text-sm font-medium text-muted-foreground shadow-sm transition-colors hover:bg-secondary hover:text-foreground"
                title={templateDescription}
                aria-label={`${templateTitle}: ${templateDescription}`}
              >
                {templateTitle}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
