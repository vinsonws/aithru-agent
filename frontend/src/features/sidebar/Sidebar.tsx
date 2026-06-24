import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import {
  Plus,
  Bot,
  ShieldCheck,
  Settings,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import { threadsApi, approvalsApi } from "@/lib/api";
import { useManager, type ManagerKind } from "@/features/manager/ManagerDialogs";
import { ConversationInbox } from "./ConversationInbox";

export function Sidebar({
  collapsed,
  onToggleCollapse,
}: {
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const { t } = useTranslation("common");
  const { context } = useHost();
  const locale = context.locale.language;
  const location = useLocation();
  const manager = useManager();
  const qc = useQueryClient();
  const [conversationQuery, setConversationQuery] = React.useState("");

  const dashboardQuery = useQuery({
    queryKey: ["threads", "dashboard"],
    queryFn: threadsApi.dashboard,
    refetchInterval: 15_000,
  });

  const approvalsQuery = useQuery({
    queryKey: ["approvals", "pending", "count"],
    queryFn: async () => (await approvalsApi.list({ status: "pending" })).length,
    refetchInterval: 15_000,
  });

  const renameThreadMutation = useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      threadsApi.update(threadId, { title }),
    onSuccess: (_thread, variables) => {
      void qc.invalidateQueries({ queryKey: ["threads", "dashboard"] });
      void qc.invalidateQueries({ queryKey: ["threads", variables.threadId] });
    },
  });

  const items = dashboardQuery.data?.items ?? [];

  const open = (kind: ManagerKind) => manager.open(kind);
  const handleRenameThread = (threadId: string, currentTitle: string) => {
    const nextTitle = window.prompt(t("renameThreadPrompt", "Rename conversation"), currentTitle)?.trim();
    if (!nextTitle || nextTitle === currentTitle) return;
    renameThreadMutation.mutate({ threadId, title: nextTitle });
  };

  if (collapsed) {
    return (
      <aside className="hidden w-14 shrink-0 flex-col items-center gap-2 border-r border-border/70 bg-muted/20 py-3 md:flex">
        <Button variant="ghost" size="icon" className="h-9 w-9 rounded-xl" onClick={onToggleCollapse} title={t("expand")}>
          <PanelLeft className="h-4 w-4" />
        </Button>
        <Button asChild variant="secondary" size="icon" className="h-9 w-9 rounded-xl border border-border/60 bg-background shadow-sm" title={t("newThread")}>
          <Link to="/threads/new">
            <Plus className="h-4 w-4" />
          </Link>
        </Button>
        <div className="min-h-0 flex-1" />
        <CollapsedManagerButton
          icon={<ShieldCheck className="h-4 w-4" />}
          label={t("approvals")}
          onClick={() => open("approvals")}
          badge={approvalsQuery.data}
        />
        <CollapsedManagerButton icon={<Settings className="h-4 w-4" />} label={t("settings")} onClick={() => open("settings")} />
      </aside>
    );
  }

  return (
    <aside className="hidden w-72 shrink-0 flex-col border-r border-border/70 bg-muted/20 md:flex">
      <div className="px-3 pb-2 pt-3">
        <div className="flex items-center gap-2">
          <div
            data-testid="sidebar-brand-avatar"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/10 text-accent"
          >
            <Bot className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold tracking-normal text-foreground">Aithru</span>
          <Button variant="ghost" size="icon" className="ml-auto h-8 w-8 rounded-xl text-muted-foreground hover:text-foreground" onClick={onToggleCollapse} title={t("collapse")}>
          <PanelLeftClose className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="px-3 pb-2">
        <Button
          asChild
          variant="secondary"
          className="h-9 w-full justify-start gap-2 rounded-xl border border-border/70 bg-background text-sm font-medium text-foreground shadow-sm hover:bg-secondary"
        >
          <Link to="/threads/new">
            <Plus className="h-4 w-4" />
            {t("newThread")}
          </Link>
        </Button>
      </div>
      <ConversationInbox
        items={items}
        activePath={location.pathname}
        locale={locale}
        loading={dashboardQuery.isLoading}
        emptyLabel={t("empty")}
        query={conversationQuery}
        onQueryChange={setConversationQuery}
        onRenameThread={handleRenameThread}
      />
      <div className="space-y-1 px-2 pb-3 pt-2">
        <ManagerLink
          icon={<ShieldCheck className="h-4 w-4" />}
          label={t("approvals")}
          onClick={() => open("approvals")}
          badge={approvalsQuery.data}
        />
        <ManagerLink icon={<Settings className="h-4 w-4" />} label={t("settings")} onClick={() => open("settings")} />
      </div>
    </aside>
  );
}

function CollapsedManagerButton({
  icon,
  label,
  onClick,
  badge,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  badge?: number;
}) {
  return (
    <Button variant="ghost" size="icon" className="relative h-9 w-9 rounded-xl text-muted-foreground hover:bg-background hover:text-foreground" onClick={onClick} title={label}>
      {icon}
      {badge ? (
        <Badge variant="destructive" className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]">
          {badge > 99 ? "99+" : badge}
        </Badge>
      ) : null}
    </Button>
  );
}

function ManagerLink({
  icon,
  label,
  onClick,
  badge,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  badge?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-9 w-full items-center gap-2 rounded-xl px-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-background hover:text-foreground",
      )}
    >
      <span className="text-muted-foreground">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {badge ? (
        <Badge variant="destructive" className="h-5 min-w-5 justify-center px-1 text-[10px]">
          {badge > 99 ? "99+" : badge}
        </Badge>
      ) : null}
    </button>
  );
}
