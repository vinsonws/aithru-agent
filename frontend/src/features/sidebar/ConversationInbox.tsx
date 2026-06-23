import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Clock,
  Ban,
  CircleDot,
  Search,
  MessageSquareOff,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, relativeTime } from "@/lib/utils";
import { buildConversationInboxGroups } from "./conversationInboxView";
import type { ConversationInboxGroupView } from "./conversationInboxView";
import type { AgentThreadDashboardItem } from "@/lib/api";

export interface ConversationInboxProps {
  items: AgentThreadDashboardItem[];
  activePath: string;
  locale: string;
  loading: boolean;
  emptyLabel: string;
  query?: string;
  onQueryChange?: (query: string) => void;
}

export function ConversationInbox({
  items,
  activePath,
  locale,
  loading,
  emptyLabel,
  query: externalQuery,
  onQueryChange,
}: ConversationInboxProps) {
  const [internalQuery, setInternalQuery] = useState("");
  const query = externalQuery ?? internalQuery;
  const handleQueryChange = onQueryChange ?? setInternalQuery;

  const groups = useMemo(
    () => buildConversationInboxGroups(items, { activePath, query, now: new Date() }),
    [items, activePath, query],
  );

  const hasMatches = groups.some((g) => g.rows.length > 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search conversations..."
            className="h-8 pl-7 text-xs"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
          />
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2 px-2 pb-3">
          {loading && (
            <div className="flex justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {!loading && groups.map((group) => (
            <InboxGroupSection key={group.id} group={group} locale={locale} />
          ))}
          {!loading && !hasMatches && (
            <div className="flex flex-col items-center gap-2 px-2 py-8 text-center">
              <MessageSquareOff className="h-6 w-6 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">
                {query ? "No matching conversations" : emptyLabel}
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
  locale,
}: {
  group: ConversationInboxGroupView;
  locale: string;
}) {
  if (group.rows.length === 0) return null;

  return (
    <section>
      <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {group.fallback}
      </div>
      <div className="space-y-0.5">
        {group.rows.map((row) => (
          <Link
            key={row.id}
            to={row.href}
            className={cn(
              "flex min-h-[68px] flex-col gap-1 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-secondary",
              row.active && "bg-secondary",
            )}
            title={`${row.title}${row.subtitle ? ` — ${row.subtitle}` : ""}`}
          >
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-medium">
                {row.title}
              </span>
              {row.needsAttention && (
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-warning" />
              )}
              {row.highPriorityActionCount > 0 && !row.needsAttention && (
                <CircleDot className="h-3 w-3 shrink-0 text-warning" />
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <StatusIcon tone={row.status.tone} />
              <span className="truncate">{row.status.fallback}</span>
              {row.statusDetail && (
                <span className="hidden truncate text-[10px] lg:inline">
                  · {row.statusDetail}
                </span>
              )}
              {row.actionLabel && (
                <span className="truncate text-[10px] text-warning">
                  · {row.actionLabel}
                </span>
              )}
              <span className="ml-auto shrink-0">
                {relativeTime(row.timestamp, locale)}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function StatusIcon({ tone }: { tone: string }) {
  switch (tone) {
    case "live":
      return <Loader2 className="h-3 w-3 animate-spin text-accent" />;
    case "success":
      return <CheckCircle2 className="h-3 w-3 text-success" />;
    case "danger":
      return <AlertTriangle className="h-3 w-3 text-destructive" />;
    case "cancelled":
      return <Ban className="h-3 w-3 text-muted-foreground" />;
    case "waiting":
    case "queued":
      return <Clock className="h-3 w-3 text-warning" />;
    case "muted":
    default:
      return <Clock className="h-3 w-3 text-muted-foreground" />;
  }
}
