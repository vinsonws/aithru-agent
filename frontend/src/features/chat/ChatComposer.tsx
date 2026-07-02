import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { runsApi, modelProvidersApi } from "@/lib/api";
import type { CreateRunRequest } from "@/lib/api";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import { getPromptTemplates } from "./promptTemplates";
import {
  buildComposerHarnessOptions,
  buildComposerScopes,
  composerModeForReasoningLevel,
  normalizeReasoningLevel,
  reasoningLevelForComposerMode,
  selectUsableModelRef,
  type ComposerPermissionPolicyId,
  type ComposerReasoningLevel,
} from "./composerState";
import { parseSlashCommand } from "./slashCommands";
import { ReferenceComposerSurface } from "./ReferenceComposerSurface";
import { SLASH_SUGGESTIONS } from "./composerSuggestions";

export { buildComposerHarnessOptions } from "./composerState";

export function ChatComposer({
  threadId,
  activeRunId,
  cancellableRunId,
  activeRunTaskMsg,
  onRequestStatus,
  onRunCreated,
  draft: externalDraft,
  onDraftChange: externalDraftChange,
  focusKey,
  onCancelRun,
  initialReasoningLevel,
}: {
  threadId: string | null;
  activeRunId: string | null;
  cancellableRunId?: string | null;
  activeRunTaskMsg?: string | null;
  onRequestStatus?: () => void;
  onRunCreated: (runId: string) => void;
  draft?: string;
  onDraftChange?: (text: string) => void;
  focusKey?: number;
  onCancelRun?: () => void;
  initialReasoningLevel?: ComposerReasoningLevel | null;
}) {
  const { t } = useTranslation(["chat", "common"]);
  const { context } = useHost();
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const [internalTaskMsg, setInternalTaskMsg] = React.useState("");
  const [reasoningLevel, setReasoningLevel] =
    React.useState<ComposerReasoningLevel>("pro");
  const [modelRef, setModelRef] = React.useState<string>("");
  const [permissionPolicy, setPermissionPolicy] =
    React.useState<ComposerPermissionPolicyId>("ask");

  const isControlled = externalDraft !== undefined;
  const taskMsg = isControlled ? externalDraft! : internalTaskMsg;
  const setTaskMsg = isControlled
    ? (text: string) => externalDraftChange?.(text)
    : setInternalTaskMsg;
  const cancelTargetRunId =
    cancellableRunId === undefined ? activeRunId : cancellableRunId;

  React.useEffect(() => {
    if (focusKey && focusKey > 0) {
      textareaRef.current?.focus();
    }
  }, [focusKey]);

  React.useEffect(() => {
    if (initialReasoningLevel)
      setReasoningLevel(normalizeReasoningLevel(initialReasoningLevel));
  }, [initialReasoningLevel]);

  const providersQuery = useQuery({
    queryKey: ["model-providers"],
    queryFn: modelProvidersApi.list,
  });

  React.useEffect(() => {
    setModelRef(selectUsableModelRef(providersQuery.data, modelRef));
  }, [providersQuery.data, modelRef]);

  const createRun = useMutation({
    mutationFn: async (vars: {
      taskMsg: string;
      selectedSkillKeys: string[];
      model_ref: string | null;
      reasoningLevel: ComposerReasoningLevel;
      permissionPolicy: ComposerPermissionPolicyId;
    }) => {
      const mode = composerModeForReasoningLevel(vars.reasoningLevel);
      const harnessOptions = buildComposerHarnessOptions(
        vars.model_ref,
        mode,
        vars.reasoningLevel,
      );
      const body: CreateRunRequest = {
        task_msg: vars.taskMsg,
        org_id: context.org?.id ?? "org_1",
        actor_user_id: context.user?.id ?? "user_1",
        scopes: buildComposerScopes(vars.permissionPolicy),
        thread_id: threadId,
        selected_skill_keys: vars.selectedSkillKeys,
        harness_options: harnessOptions ?? null,
        wait_for_completion: false,
        persist_task_msg_message: true,
      };
      const run = await runsApi.create(body);
      return run;
    },
    onSuccess: (run) => onRunCreated(run.id),
  });

  const cancelRun = useMutation({
    mutationFn: (id: string) => runsApi.cancel(id),
  });

  const handleCancel = () => {
    if (onCancelRun) {
      onCancelRun();
    } else if (cancelTargetRunId) {
      cancelRun.mutate(cancelTargetRunId);
    }
  };

  const handleSend = () => {
    const trimmed = taskMsg.trim();
    if (!trimmed || !modelRef || createRun.isPending) return;

    const command = parseSlashCommand(trimmed, { activeRunTaskMsg });
    if (command.kind === "local") {
      if (command.action === "clear") setTaskMsg("");
      if (command.action === "status") onRequestStatus?.();
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
    createRun.mutate({
      taskMsg: command.taskMsg,
      selectedSkillKeys: command.selectedSkillKeys ?? [],
      model_ref: modelRef,
      reasoningLevel: nextReasoning,
      permissionPolicy,
    });
    setTaskMsg("");
    if (command.modeOverride) setReasoningLevel(nextReasoning);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
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
    <div className="bg-background px-4 pb-3 pt-2">
      <div className="mx-auto max-w-[46rem]">
        <ReferenceComposerSurface
          value={taskMsg}
          onChange={setTaskMsg}
          onKeyDown={onKeyDown}
          onSend={handleSend}
          sendDisabled={!taskMsg.trim() || !modelRef}
          sendPending={createRun.isPending}
          activeRunId={cancelTargetRunId}
          onCancelRun={handleCancel}
          placeholder={t("chat:taskMsgPlaceholder")}
          sendLabel={t("chat:sendMessage")}
          cancelLabel={t("chat:cancelRun")}
          attachFileLabel={t("chat:attachFile")}
          modelRef={modelRef}
          onModelRefChange={setModelRef}
          modelProviders={providersQuery.data}
          selectModelLabel={t("chat:selectModelProfile")}
          reasoningLevel={reasoningLevel}
          onReasoningLevelChange={setReasoningLevel}
          permissionPolicy={permissionPolicy}
          onPermissionPolicyChange={setPermissionPolicy}
          textareaRef={textareaRef}
          slashSuggestions={SLASH_SUGGESTIONS}
          showSlashSuggestions={taskMsg.trim().startsWith("/")}
          onSlashSuggestionSelect={handleSlashSuggestionSelect}
        />
        {!taskMsg.trim() && !activeRunId && (
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                data-testid="template-stamp"
                onClick={() => handleTemplateClick(template)}
                className="rounded-full border border-border/80 bg-card/90 px-3 py-1.5 text-sm text-muted-foreground shadow-sm transition-colors hover:bg-secondary hover:text-foreground"
              >
                {t(template.titleKey, template.fallbackTitle)}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
