import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Paperclip, Send, ShieldCheck, Square } from "lucide-react";
import { Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { runsApi, skillsApi, modelProfilesApi } from "@/lib/api";
import type { CreateRunRequest } from "@/lib/api";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import { getPromptTemplates } from "./promptTemplates";
import {
  buildComposerHarnessOptions,
  buildComposerScopes,
  type ComposerMode,
  type ComposerPermissionPolicyId,
  PERMISSION_POLICIES,
} from "./composerState";
import { parseSlashCommand } from "./slashCommands";

export { buildComposerHarnessOptions } from "./composerState";

export function ChatComposer({
  threadId,
  activeRunId,
  activeRunGoal,
  onRequestStatus,
  onRunCreated,
  draft: externalDraft,
  onDraftChange: externalDraftChange,
  focusKey,
  onCancelRun,
}: {
  threadId: string | null;
  activeRunId: string | null;
  activeRunGoal?: string | null;
  onRequestStatus?: () => void;
  onRunCreated: (runId: string) => void;
  draft?: string;
  onDraftChange?: (text: string) => void;
  focusKey?: number;
  onCancelRun?: () => void;
}) {
  const { t } = useTranslation(["chat", "common"]);
  const { context } = useHost();
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const [internalGoal, setInternalGoal] = React.useState("");
  const [mode, setMode] = React.useState<ComposerMode>("auto");
  const [templateMode, setTemplateMode] = React.useState<string | null>(null);
  const [skillId, setSkillId] = React.useState<string>("__none__");
  const [profileKey, setProfileKey] = React.useState<string>("__default__");
  const [permissionPolicy, setPermissionPolicy] = React.useState<ComposerPermissionPolicyId>("ask");
  const fileRef = React.useRef<HTMLInputElement>(null);

  const isControlled = externalDraft !== undefined;
  const goal = isControlled ? externalDraft! : internalGoal;
  const setGoal = isControlled
    ? (text: string) => externalDraftChange?.(text)
    : setInternalGoal;

  React.useEffect(() => {
    if (focusKey && focusKey > 0) {
      textareaRef.current?.focus();
    }
  }, [focusKey]);

  React.useEffect(() => {
    if (templateMode) {
      setMode(templateMode as ComposerMode);
      setTemplateMode(null);
    }
  }, [templateMode]);

  const skillsQuery = useQuery({ queryKey: ["skills"], queryFn: skillsApi.list });
  const profilesQuery = useQuery({
    queryKey: ["model-profiles"],
    queryFn: modelProfilesApi.list,
  });

  const createRun = useMutation({
    mutationFn: async (vars: {
      goal: string;
      skillId: string | null;
      profileKey: string | null;
      mode: ComposerMode;
      permissionPolicy: ComposerPermissionPolicyId;
    }) => {
      const harnessOptions = buildComposerHarnessOptions(vars.profileKey, vars.mode);
      const body: CreateRunRequest = {
        goal: vars.goal,
        org_id: context.org?.id ?? "org_1",
        actor_user_id: context.user?.id ?? "user_1",
        scopes: buildComposerScopes(vars.permissionPolicy),
        thread_id: threadId,
        skill_id: vars.skillId,
        harness_options: harnessOptions ?? null,
        wait_for_completion: false,
        persist_goal_message: true,
      };
      const run = await runsApi.create(body);
      return run;
    },
    onSuccess: (run) => onRunCreated(run.id),
  });

  const cancelRun = useMutation({ mutationFn: (id: string) => runsApi.cancel(id) });

  const handleCancel = () => {
    if (onCancelRun) {
      onCancelRun();
    } else if (activeRunId) {
      cancelRun.mutate(activeRunId);
    }
  };

  const handleSend = () => {
    const trimmed = goal.trim();
    if (!trimmed || createRun.isPending) return;

    const command = parseSlashCommand(trimmed, { activeRunGoal });
    if (command.kind === "local") {
      if (command.action === "clear") setGoal("");
      if (command.action === "status") onRequestStatus?.();
      return;
    }
    if (command.kind === "draft") {
      setGoal(command.draft);
      if (command.modeOverride) setMode(command.modeOverride);
      textareaRef.current?.focus();
      return;
    }

    const nextMode = command.modeOverride ?? mode;
    createRun.mutate({
      goal: command.goal,
      skillId: skillId === "__none__" ? null : skillId,
      profileKey,
      mode: nextMode,
      permissionPolicy,
    });
    setGoal("");
    if (command.modeOverride) setMode(command.modeOverride);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTemplateClick = (template: { prompt: string; mode: string }) => {
    setGoal(template.prompt);
    setTemplateMode(template.mode);
    textareaRef.current?.focus();
  };

  const templates = getPromptTemplates();

  return (
    <div className="border-t bg-background px-4 py-3">
      <div className="mx-auto max-w-3xl">
        {!goal.trim() && !activeRunId && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => handleTemplateClick(template)}
                className="rounded-full border bg-card px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {t(template.titleKey, template.fallbackTitle)}
              </button>
            ))}
          </div>
        )}
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <Textarea
            ref={textareaRef}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t("chat:goalPlaceholder")}
            className="min-h-[64px] max-h-40 resize-none rounded-none border-0 bg-transparent px-3 py-3 shadow-none focus-visible:ring-0"
            rows={2}
          />
          {goal.trim().startsWith("/") && (
            <div className="border-t px-3 py-1 text-[11px] text-muted-foreground">
              {t("chat:commandHint")}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 border-t bg-muted/30 px-2 py-2">
            <Select value={mode} onValueChange={(value) => setMode(value as ComposerMode)}>
              <SelectTrigger aria-label={t("chat:composerMode")} className="h-7 w-[104px] border-0 bg-background text-xs shadow-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">{t("chat:modeAuto")}</SelectItem>
                <SelectItem value="plan">{t("chat:modePlan")}</SelectItem>
                <SelectItem value="chat">{t("chat:modeChat")}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={profileKey} onValueChange={setProfileKey}>
              <SelectTrigger aria-label={t("chat:selectModelProfile")} className="h-7 w-[150px] border-0 bg-background text-xs shadow-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">{t("common:default")}</SelectItem>
                {profilesQuery.data?.map((p) => (
                  <SelectItem key={p.key} value={p.key} disabled={!p.enabled}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={skillId} onValueChange={setSkillId}>
              <SelectTrigger aria-label={t("chat:selectSkill")} className="h-7 w-[130px] border-0 bg-background text-xs shadow-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">{t("common:default")}</SelectItem>
                {skillsQuery.data?.map((s) => (
                  <SelectItem key={s.key} value={s.key}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={permissionPolicy}
              onValueChange={(value) =>
                setPermissionPolicy(value as ComposerPermissionPolicyId)
              }
            >
              <SelectTrigger
                aria-label={t("chat:permission.label")}
                className="h-7 w-[122px] border-0 bg-background text-xs shadow-sm"
                title={t("chat:permission.label")}
              >
                <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERMISSION_POLICIES.map((policy) => (
                  <SelectItem key={policy.id} value={policy.id}>
                    {t(policy.labelKey, policy.fallback)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={(e) => {
                e.target.value = "";
              }}
            />
            <Button
              variant="ghost"
              size="icon"
              className="ml-auto h-8 w-8"
              onClick={() => fileRef.current?.click()}
              title={t("chat:attachFile")}
              aria-label={t("chat:attachFile")}
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            {activeRunId && (
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={handleCancel}
                title={t("chat:cancelRun")}
                aria-label={t("chat:cancelRun")}
              >
                <Square className="h-4 w-4" />
              </Button>
            )}
            <Button
              size="icon"
              className="h-8 w-8"
              onClick={handleSend}
              disabled={!goal.trim() || createRun.isPending}
              title={t("chat:sendMessage")}
              aria-label={t("chat:sendMessage")}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
