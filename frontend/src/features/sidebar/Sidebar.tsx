import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import {
  Plus,
  MessagesSquare,
  Sparkles,
  ShieldCheck,
  Brain,
  Settings,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useHost } from "@/lib/host/HostProvider";
import { useTranslation } from "react-i18next";
import { threadsApi, approvalsApi } from "@/lib/api";
import { useManager, type ManagerKind } from "@/features/manager/ManagerDialogs";
import { ConversationInbox, type ConversationInboxItem } from "./ConversationInbox";

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

  const items = (dashboardQuery.data?.items ?? []) as ConversationInboxItem[];

  const open = (kind: ManagerKind) => manager.open(kind);

  if (collapsed) {
    return (
      <aside className="hidden w-14 shrink-0 flex-col items-center gap-2 border-r bg-card py-3 md:flex">
        <Button variant="ghost" size="icon" onClick={onToggleCollapse} title={t("expand")}>
          <PanelLeft className="h-4 w-4" />
        </Button>
        <Button asChild variant="ghost" size="icon" title={t("newThread")}>
          <Link to="/threads/new">
            <Plus className="h-4 w-4" />
          </Link>
        </Button>
        <div className="min-h-0 flex-1" />
        <Separator className="my-1" />
        <CollapsedManagerButton icon={<Sparkles className="h-4 w-4" />} label={t("skills")} onClick={() => open("skills")} />
        <CollapsedManagerButton
          icon={<ShieldCheck className="h-4 w-4" />}
          label={t("approvals")}
          onClick={() => open("approvals")}
          badge={approvalsQuery.data}
        />
        <CollapsedManagerButton icon={<Brain className="h-4 w-4" />} label={t("memory")} onClick={() => open("memory")} />
        <CollapsedManagerButton icon={<Settings className="h-4 w-4" />} label={t("settings")} onClick={() => open("settings")} />
      </aside>
    );
  }

  return (
    <aside className="hidden w-72 shrink-0 flex-col border-r bg-card md:flex">
      <div className="flex items-center gap-2 px-3 py-3">
        <MessagesSquare className="h-5 w-5 text-accent" />
        <span className="text-sm font-semibold">{t("threads")}</span>
        <Button variant="ghost" size="icon" className="ml-auto h-7 w-7" onClick={onToggleCollapse} title={t("collapse")}>
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>
      <div className="px-3 pb-2">
        <Button asChild className="w-full justify-start gap-2">
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
      />
      <Separator />
      <div className="space-y-0.5 p-2">
        <ManagerLink icon={<Sparkles className="h-4 w-4" />} label={t("skills")} onClick={() => open("skills")} />
        <ManagerLink
          icon={<ShieldCheck className="h-4 w-4" />}
          label={t("approvals")}
          onClick={() => open("approvals")}
          badge={approvalsQuery.data}
        />
        <ManagerLink icon={<Brain className="h-4 w-4" />} label={t("memory")} onClick={() => open("memory")} />
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
    <Button variant="ghost" size="icon" className="relative" onClick={onClick} title={label}>
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
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-secondary",
      )}
    >
      {icon}
      <span className="flex-1 text-left">{label}</span>
      {badge ? (
        <Badge variant="destructive" className="h-5 min-w-5 justify-center px-1 text-[10px]">
          {badge > 99 ? "99+" : badge}
        </Badge>
      ) : null}
    </button>
  );
}
