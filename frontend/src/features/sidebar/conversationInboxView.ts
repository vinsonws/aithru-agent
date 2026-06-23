import type { AgentThreadDashboardItem } from "@/lib/api";
import { humanizeRunStatus, type ProductRunStatusCopy } from "@/features/chat/runStatusCopy";

export interface ConversationInboxRowView {
  id: string;
  href: string;
  title: string;
  subtitle: string;
  status: ProductRunStatusCopy;
  statusDetail?: string;
  timestamp?: string | null;
  needsAttention: boolean;
  highPriorityActionCount: number;
  actionLabel?: string;
  actionReason?: string;
  activePath: string;
  active: boolean;
}

export interface ConversationInboxGroupView {
  id: "pinned" | "attention" | "today" | "earlier";
  labelKey: string;
  fallback: string;
  rows: ConversationInboxRowView[];
}

export interface InboxViewOptions {
  activePath: string;
  query?: string;
  now: Date;
}

export function buildConversationInboxGroups(
  items: AgentThreadDashboardItem[],
  options: InboxViewOptions,
): ConversationInboxGroupView[] {
  const rows = items.map((item) => buildConversationInboxRow(item, options));
  const filtered = options.query
    ? rows.filter((row) => matchesConversationQuery(row, options.query!))
    : rows;

  const groups: ConversationInboxGroupView[] = [];

  const attentionRows = filtered.filter((r) => r.needsAttention || r.highPriorityActionCount > 0);
  if (attentionRows.length > 0) {
    groups.push({ id: "attention", labelKey: "chat:inbox.groups.attention", fallback: "Attention", rows: attentionRows });
  }

  const todayRows = filtered.filter(
    (r) => !attentionRows.includes(r) && isSameLocalDate(r.timestamp, options.now),
  );
  if (todayRows.length > 0) {
    groups.push({ id: "today", labelKey: "chat:inbox.groups.today", fallback: "Today", rows: todayRows });
  }

  const earlierRows = filtered.filter((r) => !attentionRows.includes(r) && !todayRows.includes(r));
  if (earlierRows.length > 0) {
    groups.push({ id: "earlier", labelKey: "chat:inbox.groups.earlier", fallback: "Earlier", rows: earlierRows });
  }

  return groups;
}

export function buildConversationInboxRow(
  item: AgentThreadDashboardItem,
  options: InboxViewOptions,
): ConversationInboxRowView {
  const status = getLatestRunStatus(item);
  const statusCopy = humanizeRunStatus(status);
  const subtitle = getInboxSubtitle(item);
  const actionHint = item.action_hints?.[0];
  const title = getReadableThreadTitle(item);

  return {
    id: item.thread.id,
    href: `/threads/${item.thread.id}`,
    title,
    subtitle: subtitle || "",
    status: statusCopy,
    timestamp: item.last_activity_at,
    needsAttention: item.needs_attention || item.high_priority_action_count > 0,
    highPriorityActionCount: item.high_priority_action_count,
    actionLabel: actionHint?.label,
    actionReason: actionHint?.reason ?? undefined,
    activePath: options.activePath,
    active: options.activePath === `/threads/${item.thread.id}`,
  };
}

export function getReadableThreadTitle(item: AgentThreadDashboardItem): string {
  const threadTitle = item.thread.title;
  if (threadTitle) return threadTitle;

  const messagePreview = item.summary?.latest_message?.content_preview;
  if (messagePreview) return messagePreview;

  const runGoal = getLatestRunGoal(item);
  if (runGoal) return runGoal;

  return "Untitled conversation";
}

export function getLatestRunStatus(item: AgentThreadDashboardItem): string {
  const status =
    (item as Record<string, unknown>).latest_run_status as string | undefined ??
    (item.latest_run as Record<string, unknown>)?.status as string | undefined ??
    ((item.latest_run as Record<string, unknown>)?.run as Record<string, unknown>)?.status as string | undefined ??
    item.summary?.latest_run?.status ??
    "idle";
  return status;
}

export function getLatestRunGoal(item: AgentThreadDashboardItem): string | undefined {
  const goal =
    ((item.latest_run as Record<string, unknown>)?.run as Record<string, unknown>)?.goal as string | undefined ??
    (item.latest_run as Record<string, unknown>)?.goal as string | undefined ??
    item.summary?.latest_run?.goal;
  return goal;
}

export function getInboxSubtitle(item: AgentThreadDashboardItem): string | undefined {
  const highPriorityAction = item.action_hints?.find((h) => h.priority === "high");
  if (highPriorityAction?.reason) return highPriorityAction.reason;

  const messagePreview = item.summary?.latest_message?.content_preview;
  if (messagePreview) return messagePreview;

  const runGoal = getLatestRunGoal(item);
  if (runGoal) return runGoal;

  return undefined;
}

export function matchesConversationQuery(row: ConversationInboxRowView, query: string): boolean {
  const lower = query.toLowerCase();
  return (
    row.title.toLowerCase().includes(lower) ||
    row.status.fallback.toLowerCase().includes(lower) ||
    row.subtitle.toLowerCase().includes(lower) ||
    (row.actionLabel ?? "").toLowerCase().includes(lower)
  );
}

function isSameLocalDate(dateStr: string | null | undefined, now: Date): boolean {
  if (!dateStr) return false;
  const date = new Date(dateStr);
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}
