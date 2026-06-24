import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChevronRight,
  Download,
  MoreHorizontal,
  Pencil,
  Loader2,
  Search,
  Share2,
  MessageSquareOff,
  Trash2,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { buildConversationInboxGroups, compactConversationTime } from "./conversationInboxView";
import type { ConversationInboxGroupView } from "./conversationInboxView";
import type { AgentThreadDashboardItem } from "@/lib/api";
import { useTranslation } from "react-i18next";

export interface ConversationInboxProps {
  items: AgentThreadDashboardItem[];
  activePath: string;
  locale: string;
  loading: boolean;
  emptyLabel: string;
  query?: string;
  onQueryChange?: (query: string) => void;
  onRenameThread?: (threadId: string, currentTitle: string) => void;
}

export function ConversationInbox({
  items,
  activePath,
  loading,
  emptyLabel,
  query: externalQuery,
  onQueryChange,
  onRenameThread,
}: ConversationInboxProps) {
  const { t } = useTranslation("chat");
  const [internalQuery, setInternalQuery] = useState("");
  const query = externalQuery ?? internalQuery;
  const handleQueryChange = onQueryChange ?? setInternalQuery;

  const groups = useMemo(
    () => buildConversationInboxGroups(items, { activePath, query, now: new Date() }),
    [items, activePath, query],
  );

  const hasMatches = groups.some((g) => g.rows.length > 0);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t("chat:inbox.searchPlaceholder", "Search conversations...")}
            className="h-9 rounded-xl border-border/70 bg-background pl-8 text-xs shadow-sm"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
          />
        </div>
      </div>
      <ScrollArea
        className="min-h-0 min-w-0 flex-1"
        viewportClassName="[&>div]:!block [&>div]:!min-w-0 [&>div]:!w-full"
      >
        <div className="min-w-0 space-y-3 pb-3 pl-2 pr-4">
          {loading && (
            <div className="flex justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {!loading && groups.map((group) => (
            <InboxGroupSection
              key={group.id}
              group={group}
              onRenameThread={onRenameThread}
            />
          ))}
          {!loading && !hasMatches && (
            <div className="flex flex-col items-center gap-2 px-2 py-8 text-center">
              <MessageSquareOff className="h-6 w-6 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">
                {query ? t("chat:inbox.noMatches", "No matching conversations") : emptyLabel}
              </p>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function InboxGroupSection({
  group,
  onRenameThread,
}: {
  group: ConversationInboxGroupView;
  onRenameThread?: (threadId: string, currentTitle: string) => void;
}) {
  const { t } = useTranslation("chat");
  if (group.rows.length === 0) return null;

  return (
    <section className="min-w-0">
      <div className="flex items-center px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span>{t(group.labelKey, group.fallback)}</span>
        {group.id === "attention" && (
          <span className="ml-auto rounded-full bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">
            {group.rows.length}
          </span>
        )}
      </div>
      <div className="min-w-0 space-y-0.5">
        {group.rows.map((row) => (
          <div
            key={row.id}
            data-testid="conversation-row"
            data-active={row.active ? "true" : "false"}
            data-attention={row.needsAttention || row.highPriorityActionCount > 0 ? "true" : "false"}
            className={cn(
              "group/thread relative flex h-9 w-full max-w-full min-w-0 items-center overflow-hidden rounded-lg border border-transparent text-sm transition-colors hover:border-border/70 hover:bg-secondary/70 hover:text-foreground focus-within:border-border/70 focus-within:bg-secondary/70 focus-within:text-foreground",
              row.active && "border-border/80 bg-secondary text-foreground shadow-sm ring-1 ring-primary/25 hover:bg-secondary",
            )}
            title={`${row.title} — ${t(row.status.labelKey, row.status.fallback)}${row.subtitle ? ` — ${row.subtitle}` : ""}`}
          >
            <Link
              to={row.href}
              className="flex h-full min-w-0 flex-1 items-center gap-2 px-2.5 pr-1 focus-visible:outline-none"
            >
              <StatusDot tone={row.status.tone} label={t(row.status.labelKey, row.status.fallback)} />
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium leading-5 text-foreground">
                {row.title}
              </span>
              <span className="ml-auto max-w-20 shrink-0 truncate text-right text-[11px] leading-4 text-muted-foreground">
                {compactConversationTime(row.timestamp)}
              </span>
            </Link>
            <ThreadRowMenu
              rowId={row.id}
              title={row.title}
              onRenameThread={onRenameThread}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function ThreadRowMenu({
  rowId,
  title,
  onRenameThread,
}: {
  rowId: string;
  title: string;
  onRenameThread?: (threadId: string, currentTitle: string) => void;
}) {
  const { t } = useTranslation("chat");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-testid="conversation-row-menu-trigger"
          className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-background hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 group-hover/thread:opacity-100 data-[state=open]:opacity-100"
          aria-label={t("chat:inbox.actions.open", "Open conversation menu")}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={6} className="w-44 rounded-xl p-1.5 shadow-lg">
        <DropdownMenuItem
          className="gap-2 rounded-lg px-2.5 py-2 text-sm"
          onSelect={() => onRenameThread?.(rowId, title)}
          disabled={!onRenameThread}
        >
          <Pencil className="h-4 w-4 text-muted-foreground" />
          {t("chat:inbox.actions.rename", "Rename")}
        </DropdownMenuItem>
        <DropdownMenuItem disabled className="gap-2 rounded-lg px-2.5 py-2 text-sm">
          <Share2 className="h-4 w-4 text-muted-foreground" />
          {t("chat:inbox.actions.share", "Share")}
        </DropdownMenuItem>
        <DropdownMenuItem disabled className="gap-2 rounded-lg px-2.5 py-2 text-sm">
          <Download className="h-4 w-4 text-muted-foreground" />
          <span className="flex-1">{t("chat:inbox.actions.export", "Export")}</span>
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled className="gap-2 rounded-lg px-2.5 py-2 text-sm text-destructive">
          <Trash2 className="h-4 w-4" />
          {t("chat:inbox.actions.delete", "Delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function StatusDot({ tone, label }: { tone: string; label: string }) {
  return (
    <span
      data-testid="conversation-status-dot"
      title={label}
      aria-label={label}
      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDotClassName(tone))}
    />
  );
}

function statusDotClassName(tone: string): string {
  switch (tone) {
    case "live":
      return "bg-accent";
    case "success":
      return "bg-success";
    case "danger":
      return "bg-destructive";
    case "cancelled":
      return "bg-muted-foreground/60";
    case "waiting":
    case "queued":
      return "bg-warning";
    case "muted":
    default:
      return "bg-muted-foreground/60";
  }
}
