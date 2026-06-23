import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, relativeTime } from "@/lib/utils";

export interface ConversationInboxItem {
  thread: { id: string; title?: string | null };
  latest_run?: { status?: string; created_at?: string } | null;
  needs_attention?: boolean;
  research_degraded?: boolean;
  last_activity_at?: string | null;
}

export function ConversationInbox({
  items,
  activePath,
  locale,
  loading,
  emptyLabel,
}: {
  items: ConversationInboxItem[];
  activePath: string;
  locale: string;
  loading: boolean;
  emptyLabel: string;
}) {
  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-3 px-2 pb-3">
        {loading && (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}
        {items.length > 0 && <ConversationGroup label="Pinned" items={items.slice(0, 1)} activePath={activePath} locale={locale} />}
        {items.length > 1 && <ConversationGroup label="Recent" items={items.slice(1)} activePath={activePath} locale={locale} />}
        {items.length === 0 && !loading && (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">{emptyLabel}</p>
        )}
      </div>
    </ScrollArea>
  );
}

function ConversationGroup({
  label,
  items,
  activePath,
  locale,
}: {
  label: string;
  items: ConversationInboxItem[];
  activePath: string;
  locale: string;
}) {
  return (
    <section>
      <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="space-y-0.5">
        {items.map((item) => (
          <ConversationRow key={item.thread.id} item={item} activePath={activePath} locale={locale} />
        ))}
      </div>
    </section>
  );
}

function ConversationRow({
  item,
  activePath,
  locale,
}: {
  item: ConversationInboxItem;
  activePath: string;
  locale: string;
}) {
  const status = item.latest_run?.status;
  const href = `/threads/${item.thread.id}`;
  return (
    <Link
      to={href}
      className={cn(
        "flex flex-col gap-1 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-secondary",
        activePath === href && "bg-secondary",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-medium">{item.thread.title || item.thread.id}</span>
        {item.needs_attention && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-warning" />}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {status === "completed" && <CheckCircle2 className="h-3 w-3 text-success" />}
        {status === "running" && <Loader2 className="h-3 w-3 animate-spin text-accent" />}
        {status?.startsWith("waiting") && <AlertTriangle className="h-3 w-3 text-warning" />}
        <span className="truncate">{status ?? "idle"}</span>
        <span className="ml-auto shrink-0">{relativeTime(item.last_activity_at ?? item.latest_run?.created_at, locale)}</span>
      </div>
    </Link>
  );
}
