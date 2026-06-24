import * as React from "react";
import { Bot, User, AlertTriangle, ArrowDown } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { cn, relativeTime } from "@/lib/utils";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import type { ChatMessage, RunStreamState } from "./useRunStream";
import { ToolCallCard } from "./ToolCallCard";
import { InlineRequestCard } from "./InlineRequestCard";
import { AgentActivityCard } from "./AgentActivityCard";
import { buildMessageActions, buildEditAndRerunPrompt, buildContinuePrompt } from "./messageActions";
import { MessageActions } from "./MessageActionsComponent";

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
}: {
  message: ChatMessage;
  locale: string;
  onPrefillComposer?: (text: string) => void;
  onOpenTrace?: () => void;
}) {
  const isUser = message.role === "user";
  const actions = buildMessageActions(message);

  const handleMessageAction = (kind: string, _messageId: string) => {
    if (kind === "copy") {
      navigator.clipboard.writeText(message.content).catch(() => {});
    } else if (kind === "editAndRerun") {
      onPrefillComposer?.(buildEditAndRerunPrompt(message));
    } else if (kind === "continue") {
      onPrefillComposer?.(buildContinuePrompt(message));
    } else if (kind === "viewTrace") {
      onOpenTrace?.();
    }
  };

  return (
    <div className={cn("group flex gap-3 px-4 py-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-secondary text-secondary-foreground" : "bg-accent/15 text-accent",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className={cn("max-w-[min(80%,42rem)] space-y-2", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-lg px-3 py-2 text-sm",
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-card border border-border text-foreground",
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : message.content ? (
            <div className="relative min-w-0">
              <Markdown variant="chat">{message.content}</Markdown>
              {message.streaming && (
                <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-accent align-text-bottom" />
              )}
            </div>
          ) : message.streaming ? (
            <LoadingDots />
          ) : null}
        </div>
        <div className="flex items-center justify-between gap-2">
          {message.createdAt && (
            <p className={cn("text-xs text-muted-foreground", isUser && "text-right")}>
              {relativeTime(message.createdAt, locale)}
            </p>
          )}
          {actions.length > 0 && (
            <MessageActions
              actions={actions}
              messageId={message.id}
              onAction={handleMessageAction}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export function ChatPanel({
  state,
  onPrefillComposer,
  onOpenTrace,
}: {
  state: RunStreamState;
  onPrefillComposer?: (text: string) => void;
  onOpenTrace?: () => void;
}) {
  const { context } = useHost();
  const { t } = useTranslation(["chat", "common"]);
  const locale = context.locale.language;
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = React.useState(true);

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
  }, [state.messages, state.toolCalls, atBottom]);

  const running = state.status === "running" || state.status === "queued";
  const failed = state.status === "failed";

  return (
    <div className="relative flex h-full flex-col">
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl py-4">
          {state.messages.length === 0 && state.toolCalls.length === 0 && !running && (
            <div className="py-20 text-center text-sm text-muted-foreground">
              {t("chat:emptyThread")}
            </div>
          )}

          {state.messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              locale={locale}
              onPrefillComposer={onPrefillComposer}
              onOpenTrace={onOpenTrace}
            />
          ))}

          {state.messages.length > 0 && <AgentActivityCard state={state} />}

          {/* Tool calls rendered inline, grouped after the latest assistant message. */}
          {state.toolCalls.length > 0 && (
            <div className="mx-auto max-w-3xl space-y-1.5 px-4 py-1.5">
              {state.toolCalls.map((tc) => (
                <ToolCallCard key={tc.id} entry={tc} />
              ))}
            </div>
          )}

          {/* Inline requests (input / approval) */}
          {state.inlineRequests.map((req) => (
            <div key={req.id} className="mx-auto max-w-3xl px-4 py-2">
              <InlineRequestCard request={req} />
            </div>
          ))}

          {running && state.messages.at(-1)?.role === "user" && (
            <div className="flex gap-3 px-4 py-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/15 text-accent">
                <Bot className="h-4 w-4" />
              </div>
              <LoadingDots />
            </div>
          )}

          {failed && state.error && (
            <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-3 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" />
              {t("chat:runFailed")}: {state.error}
            </div>
          )}
        </div>
      </div>

      {/* Floating token usage + back-to-bottom */}
      <div className="pointer-events-none absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-2">
        {state.tokenUsage?.total != null && (
          <div className="pointer-events-auto rounded-full bg-background/80 px-2 py-1 text-xs text-muted-foreground shadow backdrop-blur">
            {t("chat:tokenUsage")}: <span className="font-mono">{state.tokenUsage.total}</span>
          </div>
        )}
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
