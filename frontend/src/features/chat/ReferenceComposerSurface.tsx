import * as React from "react";
import {
  ArrowUp,
  Check,
  ChevronDown,
  Cpu,
  Eye,
  GraduationCap,
  Lightbulb,
  Paperclip,
  Rocket,
  ShieldCheck,
  Square,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { AgentModelProviderWithModels } from "@/lib/api";
import {
  type ComposerPermissionPolicyId,
  type ComposerReasoningLevel,
  PERMISSION_POLICIES,
  REASONING_LEVELS,
  flattenUsableModels,
  normalizePermissionPolicyId,
  normalizeReasoningLevel,
} from "./composerState";

export interface ComposerSlashSuggestion {
  command: string;
  labelKey: string;
  fallbackLabel: string;
  descriptionKey: string;
  fallbackDescription: string;
}

export interface ReferenceComposerSurfaceProps {
  value: string;
  onChange: (value: string) => void;
  onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  sendDisabled: boolean;
  sendPending?: boolean;
  activeRunId?: string | null;
  onCancelRun?: () => void;
  placeholder: string;
  sendLabel: string;
  cancelLabel: string;
  attachFileLabel: string;
  modelRef: string;
  onModelRefChange: (modelRef: string) => void;
  modelProviders?: AgentModelProviderWithModels[];
  selectModelLabel: string;
  reasoningLevel: ComposerReasoningLevel;
  onReasoningLevelChange: (level: ComposerReasoningLevel) => void;
  permissionPolicy: ComposerPermissionPolicyId;
  onPermissionPolicyChange: (policy: ComposerPermissionPolicyId) => void;
  autoFocus?: boolean;
  rows?: number;
  textareaRef?: React.Ref<HTMLTextAreaElement>;
  textareaMinHeightClassName?: string;
  className?: string;
  slashSuggestions?: ComposerSlashSuggestion[];
  showSlashSuggestions?: boolean;
  onSlashSuggestionSelect?: (command: string) => void;
}

const REASONING_ICONS: Record<ComposerReasoningLevel, React.ElementType> = {
  flash: Zap,
  thinking: Lightbulb,
  pro: GraduationCap,
  ultra: Rocket,
};

const PERMISSION_ICONS: Record<ComposerPermissionPolicyId, React.ElementType> =
  {
    ask: ShieldCheck,
    auto_safe: Zap,
    read_only: Eye,
  };

export function ReferenceComposerSurface({
  value,
  onChange,
  onKeyDown,
  onSend,
  sendDisabled,
  sendPending = false,
  activeRunId,
  onCancelRun,
  placeholder,
  sendLabel,
  cancelLabel,
  attachFileLabel,
  modelRef,
  onModelRefChange,
  modelProviders,
  selectModelLabel,
  reasoningLevel,
  onReasoningLevelChange,
  permissionPolicy,
  onPermissionPolicyChange,
  autoFocus,
  rows = 3,
  textareaRef,
  textareaMinHeightClassName = "min-h-[76px]",
  className,
  slashSuggestions = [],
  showSlashSuggestions = false,
  onSlashSuggestionSelect,
}: ReferenceComposerSurfaceProps) {
  const { t } = useTranslation(["chat", "common"]);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const normalizedPermission = normalizePermissionPolicyId(permissionPolicy);
  const normalizedReasoning = normalizeReasoningLevel(reasoningLevel);
  const selectedPermission =
    PERMISSION_POLICIES.find((policy) => policy.id === normalizedPermission) ??
    PERMISSION_POLICIES[0];
  const selectedReasoning =
    REASONING_LEVELS.find((level) => level.id === normalizedReasoning) ??
    REASONING_LEVELS[2];
  const usableModels = flattenUsableModels(modelProviders);
  const groupedModels = usableModels.reduce<
    Record<string, typeof usableModels>
  >((groups, model) => {
    (groups[model.providerName] ??= []).push(model);
    return groups;
  }, {});
  const selectedModel = usableModels.find((model) => model.ref === modelRef);
  const modelDisplayLabel = selectedModel
    ? selectedModel.modelName
    : t("chat:noModel", "No model");
  const PermissionIcon = PERMISSION_ICONS[normalizedPermission];
  const permissionLabel = t(
    selectedPermission.labelKey,
    selectedPermission.fallback,
  );
  const reasoningLabel = t(
    selectedReasoning.labelKey,
    selectedReasoning.fallback,
  );
  const slashPanelVisible = showSlashSuggestions && slashSuggestions.length > 0;

  return (
    <div className={cn("relative", className)}>
      {slashPanelVisible && (
        <div
          data-testid="slash-suggestions-panel"
          className="absolute bottom-[calc(100%+0.625rem)] left-0 right-0 z-40 max-h-[18rem] overflow-y-auto rounded-[1.25rem] border border-border/80 bg-card/95 p-2 shadow-[0_16px_44px_rgba(15,23,42,0.14)] backdrop-blur"
        >
          {slashSuggestions.map((suggestion, index) => (
            <button
              key={suggestion.command}
              type="button"
              onClick={() => onSlashSuggestionSelect?.(suggestion.command)}
              className={cn(
                "flex w-full min-w-0 items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                index === 0 && "bg-secondary/70",
              )}
            >
              <span className="w-16 shrink-0 font-medium text-foreground">
                {suggestion.command}
              </span>
              <span className="min-w-0 truncate text-muted-foreground">
                <span className="font-medium text-foreground">
                  {t(suggestion.labelKey, suggestion.fallbackLabel)}
                </span>
                <span className="ml-2 text-muted-foreground">
                  {t(suggestion.descriptionKey, suggestion.fallbackDescription)}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
      <div
        data-testid="reference-composer-shell"
        className="overflow-hidden rounded-[1.75rem] border border-border/80 bg-card shadow-[0_2px_8px_rgba(15,23,42,0.05),0_18px_42px_rgba(15,23,42,0.08)] transition-shadow focus-within:shadow-[0_2px_10px_rgba(15,23,42,0.06),0_20px_48px_rgba(15,23,42,0.11)]"
      >
        <Textarea
          ref={textareaRef}
          autoFocus={autoFocus}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className={cn(
            "max-h-36 resize-none rounded-none border-0 bg-transparent px-5 pb-2 pt-4 text-[15px] leading-6 shadow-none placeholder:text-base placeholder:font-semibold placeholder:text-muted-foreground/65 focus-visible:ring-0 sm:text-base",
            textareaMinHeightClassName,
          )}
          rows={rows}
        />
        <div className="flex flex-col gap-2 px-3.5 pb-3 pt-1 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9 rounded-full text-muted-foreground hover:text-foreground"
              onClick={() => fileRef.current?.click()}
              title={attachFileLabel}
              aria-label={attachFileLabel}
            >
              <Paperclip className="h-5 w-5" />
            </Button>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={(event) => {
                event.target.value = "";
              }}
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  data-testid="reference-composer-permission"
                  className={cn(
                    "h-9 min-w-0 rounded-full border px-3 text-sm font-medium shadow-none",
                    normalizedPermission === "auto_safe"
                      ? "border-orange-300/80 bg-orange-50 text-orange-700 hover:bg-orange-100 hover:text-orange-800"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                  aria-label={t("chat:permission.label")}
                  title={t("chat:permission.label")}
                >
                  <PermissionIcon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{permissionLabel}</span>
                  <ChevronDown className="h-4 w-4 shrink-0" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                side="top"
                sideOffset={12}
                className="w-[min(22rem,calc(100vw-2rem))] rounded-2xl p-2"
              >
                <div className="px-2 pb-1 pt-1 text-xs font-semibold text-muted-foreground">
                  {t("chat:permission.label")}
                </div>
                {PERMISSION_POLICIES.map((policy) => {
                  const Icon = PERMISSION_ICONS[policy.id];
                  return (
                    <DropdownMenuItem
                      key={policy.id}
                      onSelect={() => onPermissionPolicyChange(policy.id)}
                      className="items-start gap-3 rounded-xl px-3 py-2.5"
                    >
                      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">
                          {t(policy.labelKey, policy.fallback)}
                        </span>
                        <span className="block text-xs leading-5 text-muted-foreground">
                          {t(policy.descriptionKey, policy.fallbackDescription)}
                        </span>
                      </span>
                      {normalizedPermission === policy.id && (
                        <Check className="mt-0.5 h-4 w-4 shrink-0" />
                      )}
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <div className="flex min-w-0 items-center justify-between gap-2 sm:justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  data-testid="reference-composer-model-reasoning"
                  className="h-10 min-w-0 max-w-[min(22rem,62vw)] rounded-full px-3 text-left text-muted-foreground hover:text-foreground"
                  aria-label={`${selectModelLabel}, ${t("chat:reasoning.label")}`}
                  title={`${selectModelLabel}, ${t("chat:reasoning.label")}`}
                >
                  <Cpu className="h-5 w-5 shrink-0" />
                  <span className="min-w-0 truncate text-sm font-medium text-foreground">
                    {modelDisplayLabel}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {reasoningLabel}
                  </span>
                  <ChevronDown className="h-4 w-4 shrink-0" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                side="top"
                sideOffset={12}
                className="w-[min(25rem,calc(100vw-2rem))] rounded-2xl p-2"
              >
                <div className="px-2 pb-1 pt-1 text-xs font-semibold text-muted-foreground">
                  {t("chat:reasoning.label")}
                </div>
                {REASONING_LEVELS.map((level) => {
                  const Icon = REASONING_ICONS[level.id];
                  return (
                    <DropdownMenuItem
                      key={level.id}
                      onSelect={() => onReasoningLevelChange(level.id)}
                      className="items-start gap-3 rounded-xl px-3 py-2.5"
                    >
                      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">
                          {t(level.labelKey, level.fallback)}
                        </span>
                        <span className="block text-xs leading-5 text-muted-foreground">
                          {t(level.descriptionKey, level.fallbackDescription)}
                        </span>
                      </span>
                      {normalizedReasoning === level.id && (
                        <Check className="mt-0.5 h-4 w-4 shrink-0" />
                      )}
                    </DropdownMenuItem>
                  );
                })}
                <DropdownMenuSeparator />
                <div className="px-2 pb-1 pt-1 text-xs font-semibold text-muted-foreground">
                  {selectModelLabel}
                </div>
                {usableModels.length === 0 ? (
                  <div className="px-3 py-2.5 text-sm text-muted-foreground">
                    {t("chat:noAvailableModels", "No usable models configured")}
                  </div>
                ) : (
                  Object.entries(groupedModels).map(
                    ([providerName, models], groupIndex) => (
                      <React.Fragment key={providerName}>
                        {groupIndex > 0 && <DropdownMenuSeparator />}
                        <div className="px-2 pb-1 pt-2 text-xs font-semibold text-muted-foreground">
                          {providerName}
                        </div>
                        {models.map((model) => (
                          <DropdownMenuItem
                            key={model.ref}
                            onSelect={() => onModelRefChange(model.ref)}
                            className="items-start gap-3 rounded-xl px-3 py-2.5"
                          >
                            <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-medium">
                                {model.modelName}
                              </span>
                              <span className="block truncate text-xs leading-5 text-muted-foreground">
                                {model.ref}
                              </span>
                            </span>
                            {modelRef === model.ref && (
                              <Check className="mt-0.5 h-4 w-4 shrink-0" />
                            )}
                          </DropdownMenuItem>
                        ))}
                      </React.Fragment>
                    ),
                  )
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            {activeRunId ? (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-10 w-10 shrink-0 rounded-full border-border/80 bg-muted/40 text-muted-foreground hover:text-foreground"
                onClick={onCancelRun}
                title={cancelLabel}
                aria-label={cancelLabel}
              >
                <Square className="h-5 w-5" />
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-10 w-10 shrink-0 rounded-full border-border/80 bg-muted/50 text-muted-foreground shadow-none hover:bg-secondary hover:text-foreground"
                onClick={onSend}
                disabled={sendDisabled || sendPending}
                title={sendLabel}
                aria-label={sendLabel}
              >
                <ArrowUp className="h-5 w-5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
