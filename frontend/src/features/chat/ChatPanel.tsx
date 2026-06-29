import * as React from "react";
import { AlertTriangle, ArrowDown, ChevronDown, ChevronRight } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { cn, relativeTime } from "@/lib/utils";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import type { ChatMessage, RunStreamState } from "./useRunStream";
import type { AgentMessage } from "@/lib/api";
import { PresentationItem } from "./PresentationItem";
import { presentationEffectKey, previewTargetForPresentationEffect } from "./presentationEffects";
import { ToolCallCard } from "./ToolCallCard";
import { InlineRequestCard } from "./InlineRequestCard";
import {
  buildWorkspaceLinkResolver,
  copyMessageContentWithWorkspaceLinks,
} from "./messageLinks";
import { buildChatTimeline } from "./chatTimeline";
import type { ChatTimelineItem } from "./chatTimeline";
import { buildMessageActions, buildEditAndRerunPrompt } from "./messageActions";
import { MessageActions } from "./MessageActionsComponent";

type AssistantProcessItem = Extract<ChatTimelineItem, { kind: "assistantProcess" }>;
type Translate = (key: string, options?: Record<string, unknown>) => string;

const CHAT_RAIL_CLASSNAME = "mx-auto w-full max-w-[46rem] px-4 sm:px-6";
const ASSISTANT_GUIDE_CLASSNAME = "border-l border-border/70 pl-4";
const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);

function LoadingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function MessageBubble({
  message,
  locale,
  onPrefillComposer,
  onOpenTrace,
  resolveLinkHref,
  showFooter = true,
  footerMessage,
}: {
  message: ChatMessage;
  locale: string;
  onPrefillComposer?: (text: string) => void;
  onOpenTrace?: () => void;
  resolveLinkHref?: (href: string) => string;
  showFooter?: boolean;
  footerMessage?: ChatMessage;
}) {
  const isUser = message.role === "user";
  const footerSource = footerMessage ?? message;
  const actions = showFooter ? buildMessageActions(footerSource) : [];

  const copyContent = copyMessageContentWithWorkspaceLinks(footerSource, resolveLinkHref);

  const handleMessageAction = (kind: string, _messageId: string) => {
    if (kind === "copy") {
      navigator.clipboard.writeText(copyContent).catch(() => {});
    } else if (kind === "editAndRerun") {
      onPrefillComposer?.(buildEditAndRerunPrompt(footerSource));
    } else if (kind === "viewTrace") {
      onOpenTrace?.();
    }
  };

  if (!isUser && !message.content && !message.streaming) return null;

  return (
    <div className={cn("group py-3", isUser && "flex justify-end")}>
      <div
        className={cn(
          "min-w-0 space-y-1.5",
          isUser ? "max-w-[78%] sm:max-w-[34rem]" : `w-full ${ASSISTANT_GUIDE_CLASSNAME}`,
        )}
      >
        {isUser ? (
          <div className="rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-6 text-primary-foreground shadow-sm">
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        ) : message.content ? (
          <div className="relative min-w-0 text-foreground">
            <Markdown variant="chat" resolveLinkHref={resolveLinkHref}>{message.content}</Markdown>
          </div>
        ) : (
          <LoadingDots />
        )}
        {showFooter && (
          <div className={cn("flex items-center gap-2", isUser ? "justify-end" : "justify-start")}>
            {footerSource.createdAt && (
              <p className={cn("text-xs text-muted-foreground", isUser && "text-right")}>
                {relativeTime(footerSource.createdAt, locale)}
              </p>
            )}
            {actions.length > 0 && (
              <MessageActions
                actions={actions}
                messageId={footerSource.id}
                onAction={handleMessageAction}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function AssistantProcess({
  item,
}: {
  item: AssistantProcessItem;
}) {
  const { t } = useTranslation(["chat"]);
  const autoOpen = shouldAutoOpenAssistantProcess(item);
  const [manualOpen, setManualOpen] = React.useState<boolean | null>(null);
  const open = manualOpen ?? autoOpen;
  const hasDetails = item.steps.length > 0;
  const hasThinkingContent = item.steps.some(
    (step) => step.kind === "reasoning" && step.content.trim().length > 0,
  );
  const toolCount = item.steps.filter((step) => step.kind === "tool").length;
  const summary = buildProcessSummary(item.state, {
    hasThinkingContent,
    toolCount,
    startedAt: item.startedAt,
    completedAt: item.completedAt,
    t,
  });

  React.useEffect(() => {
    setManualOpen(null);
  }, [item.id]);

  return (
    <div className="py-2">
      <div className={ASSISTANT_GUIDE_CLASSNAME}>
        <button
          type="button"
          onClick={() => hasDetails && setManualOpen((value) => !(value ?? autoOpen))}
          className={cn(
            "flex min-h-7 items-center gap-1.5 rounded-md text-sm text-muted-foreground",
            hasDetails && "hover:text-foreground",
          )}
          aria-expanded={hasDetails ? open : undefined}
          disabled={!hasDetails}
          data-testid="assistant-process-toggle"
        >
          {hasDetails ? (
            open ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )
          ) : (
            <span className="h-3.5 w-3.5" />
          )}
          <span>{summary}</span>
          {!hasDetails &&
            (item.state.status === "running" || item.state.status === "queued") && (
              <LoadingDots />
            )}
        </button>

        {open && hasDetails && (
          <div className="mt-2 space-y-2 border-l border-border/60 pl-3">
            {item.steps.map((step) => {
              if (step.kind === "tool") {
                return <ToolCallCard key={step.id} entry={step.tool} />;
              }
              return (
                <div key={step.id} className="py-1 text-sm text-muted-foreground">
                  {step.content.trim() ? (
                    <Markdown variant="chat">{step.content}</Markdown>
                  ) : (
                    <LoadingDots />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function shouldAutoOpenAssistantProcess(item: AssistantProcessItem): boolean {
  const hasReasoningContent = item.state.reasoningSegments.some(
    (segment) => segment.content.trim().length > 0,
  );
  const hasAssistantOutput = item.state.messages.some(
    (message) => message.role === "assistant" && message.content.trim().length > 0,
  );
  return hasReasoningContent && !isTerminalState(item.state) && !hasAssistantOutput;
}

function isTerminalState(state: RunStreamState): boolean {
  return TERMINAL_RUN_STATUSES.has(state.status);
}

function RunCompletionFooter({
  state,
  onOpenTrace,
}: {
  state: RunStreamState;
  onOpenTrace?: () => void;
}) {
  const { t } = useTranslation(["chat"]);
  const parts = [t("chat:process.completedLabel")];
  const completedTools = state.toolCalls.filter((tool) => tool.status === "completed").length;

  if (completedTools > 0) {
    parts.push(
      t("chat:process.toolsUsed", {
        count: completedTools,
        defaultValue: "{{count}} tools",
      }),
    );
  }
  if (state.tokenUsage?.total != null) {
    parts.push(
      t("chat:process.tokens", {
        value: state.tokenUsage.total.toLocaleString(),
        defaultValue: "{{value}} tokens",
      }),
    );
  }

  return (
    <div className="pb-5 pt-1">
      <div
        className={cn(
          "flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground",
          ASSISTANT_GUIDE_CLASSNAME,
        )}
      >
        <span>{parts.join(" · ")}</span>
        {onOpenTrace && (
          <button
            type="button"
            onClick={onOpenTrace}
            className="rounded-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            {t("chat:messageActions.viewTrace")}
          </button>
        )}
      </div>
    </div>
  );
}

function buildProcessSummary(
  state: RunStreamState,
  {
    hasThinkingContent,
    toolCount,
    startedAt,
    completedAt,
    t,
  }: {
    hasThinkingContent: boolean;
    toolCount: number;
    startedAt?: string;
    completedAt?: string;
    t: Translate;
  },
): string {
  const parts: string[] = [];
  const duration = processDurationLabel(
    {
      startedAt: startedAt ?? state.modelStartedAt,
      completedAt: completedAt ?? (startedAt ? undefined : state.modelCompletedAt ?? state.runCompletedAt),
    },
    t,
  );
  if (duration) {
    parts.push(
      hasThinkingContent
        ? t("chat:process.thoughtFor", { duration })
        : t("chat:process.processedFor", { duration }),
    );
  } else {
    parts.push(t("chat:thinking"));
  }
  if (toolCount > 0) {
    parts.push(
      t("chat:process.usedTools", {
        count: toolCount,
      }),
    );
  }
  return parts.join(" · ");
}

function processDurationLabel(
  {
    startedAt,
    completedAt,
  }: {
    startedAt?: string;
    completedAt?: string;
  },
  t: Translate,
): string | null {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt ?? new Date().toISOString()).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;

  const seconds = Math.max(1, Math.round((end - start) / 1000));
  if (seconds < 60) {
    return t("chat:thinkingDurationSeconds", {
      defaultValue: "{{count}}s",
      count: seconds,
    });
  }

  return t("chat:thinkingDurationMinutes", {
    defaultValue: "{{count}}m",
    count: Math.max(1, Math.round(seconds / 60)),
  });
}

export function ChatPanel({
  state,
  threadMessages = [],
  activeRunId = null,
  historicalRunStates = {},
  onPrefillComposer,
  onOpenTrace,
  onPreviewFile,
}: {
  state: RunStreamState;
  threadMessages?: AgentMessage[];
  activeRunId?: string | null;
  historicalRunStates?: Record<string, RunStreamState>;
  onPrefillComposer?: (text: string) => void;
  onOpenTrace?: () => void;
  onPreviewFile?: (fileId: string) => void;
}) {
  const { context } = useHost();
  const { t } = useTranslation(["chat", "common"]);
  const locale = context.locale.language;
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = React.useState(true);
  const timeline = React.useMemo(
    () => buildChatTimeline(state, threadMessages, activeRunId, historicalRunStates),
    [state, threadMessages, activeRunId, historicalRunStates],
  );

  const onScroll = React.useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAtBottom(distance < 80);
  }, []);

  React.useEffect(() => {
    if (atBottom && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [timeline, atBottom]);

  const workspaceLinkResolver = React.useMemo(
    () => buildWorkspaceLinkResolver(),
    [],
  );
  const appliedPresentationEffectsRef = React.useRef<Set<string>>(new Set());

  React.useEffect(() => {
    if (!onPreviewFile) return;
    for (const presentation of state.presentations ?? []) {
      const previewTarget = previewTargetForPresentationEffect(presentation);
      if (!previewTarget) continue;
      const effectKey = presentationEffectKey(presentation);
      if (appliedPresentationEffectsRef.current.has(effectKey)) continue;
      appliedPresentationEffectsRef.current.add(effectKey);
      onPreviewFile(previewTarget);
    }
  }, [onPreviewFile, state.presentations]);

  const running = state.status === "running" || state.status === "queued";
  const failed = state.status === "failed";
  const hasProcessItem = timeline.some((item) => item.kind === "assistantProcess");

  return (
    <div className="relative flex h-full flex-col">
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        <div className={cn(CHAT_RAIL_CLASSNAME, "py-5")}>
          {timeline.length === 0 && !running && (
            <div className="py-20 text-center text-sm text-muted-foreground">
              {t("chat:emptyThread")}
            </div>
          )}

          {timeline.map((item) => {
            if (item.kind === "message") {
              return (
                <MessageBubble
                  key={item.id}
                  message={item.message}
                  locale={locale}
                  onPrefillComposer={onPrefillComposer}
                  onOpenTrace={onOpenTrace}
                  resolveLinkHref={workspaceLinkResolver}
                  showFooter={item.showFooter ?? true}
                  footerMessage={item.footerMessage}
                />
              );
            }
            if (item.kind === "assistantProcess") {
              return <AssistantProcess key={item.id} item={item} />;
            }
            if (item.kind === "presentation") {
              return (
                <div key={item.id} className={ASSISTANT_GUIDE_CLASSNAME}>
                  <PresentationItem presentation={item.presentation} onPreviewFile={onPreviewFile} />
                </div>
              );
            }
            if (item.kind === "inlineRequest") {
              return (
                <div key={item.id} className="py-2">
                  <div className={ASSISTANT_GUIDE_CLASSNAME}>
                    <InlineRequestCard request={item.request} />
                  </div>
                </div>
              );
            }
            return <RunCompletionFooter key={item.id} state={state} onOpenTrace={onOpenTrace} />;
          })}

          {running && !hasProcessItem && state.messages.at(-1)?.role === "user" && (
            <div className="py-3">
              <LoadingDots />
            </div>
          )}

          {failed && state.error && (
            <div className="flex items-center gap-2 py-3 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" />
              {t("chat:runFailed")}: {state.error}
            </div>
          )}
        </div>
      </div>

      {/* Back-to-bottom control */}
      <div className="pointer-events-none absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-2">
        {!atBottom && (
          <button
            type="button"
            onClick={() => {
              if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
            }}
            className="pointer-events-auto flex h-8 w-8 items-center justify-center rounded-full bg-background shadow ring-1 ring-border"
            aria-label={t("chat:scrollToBottom")}
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
