import type * as React from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  FileText,
  GitBranch,
  PanelRightClose,
  PanelRightOpen,
  ShieldCheck,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { buildRunCompanionBadges } from "@/features/chat/runActivity";
import type { RunStreamState } from "@/features/chat/useRunStream";
import { cn } from "@/lib/utils";
import { buildRunCompanionRailView } from "./runCompanionView";
import { useTranslation } from "react-i18next";
import { ActivityTab } from "./tabs/ActivityTab";
import { RunFilesTab } from "./tabs/RunFilesTab";
import { ApprovalsTab } from "./tabs/ApprovalsTab";
import { RunTab } from "./tabs/RunTab";

export function RunCompanion({
  runId,
  workspaceId,
  collapsed,
  onToggle,
  runStatus,
  todoProgress,
  streamState,
  activeTab,
  onTabChange,
}: {
  runId: string | null;
  workspaceId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  runStatus?: string;
  todoProgress?: { done: number; total: number };
  streamState: RunStreamState;
  activeTab?: string;
  onTabChange?: (tab: string) => void;
}) {
  const { t } = useTranslation(["chat", "inspection", "common"]);
  const badges = buildRunCompanionBadges(streamState);
  const railView = buildRunCompanionRailView({
    runStatus,
    todoProgress,
    streamState,
  });

  const defaultTab = badges.approvals > 0 ? "approvals" : "activity";
  const tabValue = activeTab ?? defaultTab;
  const setTabValue = onTabChange ?? (() => {});

  if (collapsed) {
    return (
      <aside
        className={cn(
          "hidden w-12 shrink-0 flex-col items-center gap-3 border-l bg-card py-3 lg:flex",
          railView.hasAttention && "bg-warning/5",
        )}
      >
        <Button variant="ghost" size="icon" onClick={onToggle} title={t("inspection:expand")}>
          <PanelRightOpen className="h-4 w-4" />
        </Button>
        <div
          className={cn(
            "relative flex h-8 w-8 items-center justify-center rounded-full border",
            railToneClass(railView.statusTone),
          )}
          title={railView.status ? t(`common:status.${railView.status}`, { defaultValue: railView.status }) : undefined}
        >
          <RailStatusIcon tone={railView.statusTone} />
          {railView.attentionCount > 0 && (
            <Badge
              variant="secondary"
              className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]"
            >
              {railView.attentionCount > 9 ? "9+" : railView.attentionCount}
            </Badge>
          )}
        </div>
        {railView.progressLabel && (
          <div className="rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {railView.progressLabel}
          </div>
        )}
      </aside>
    );
  }

  return (
    <aside className="hidden w-[342px] shrink-0 flex-col border-l bg-card lg:flex">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
        <span className="text-sm font-semibold">{t("chat:runCompanion")}</span>
        {runStatus && <StatusBadge status={runStatus} />}
        <Button variant="ghost" size="icon" className="ml-auto h-7 w-7" onClick={onToggle} title={t("inspection:collapse")}>
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>
      <Tabs value={tabValue} onValueChange={setTabValue} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="m-2 grid h-9 grid-cols-4">
          <CompanionTab value="activity" icon={<Activity className="h-3.5 w-3.5" />} label={t("chat:tabActivity")} badge={badges.activity} />
          <CompanionTab value="files" icon={<FileText className="h-3.5 w-3.5" />} label={t("chat:tabFiles")} badge={badges.files} disabled={!workspaceId && badges.files === 0} />
          <CompanionTab value="approvals" icon={<ShieldCheck className="h-3.5 w-3.5" />} label={t("chat:tabApprovals")} badge={badges.approvals} disabled={!runId && badges.approvals === 0} />
          <CompanionTab value="trace" icon={<GitBranch className="h-3.5 w-3.5" />} label={t("chat:tabTrace")} badge={badges.trace} disabled={!runId && badges.trace === 0} />
        </TabsList>
        <TabsContent value="activity" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <ActivityTab state={streamState} />
        </TabsContent>
        <TabsContent value="files" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <RunFilesTab runId={runId} workspaceId={workspaceId} />
        </TabsContent>
        <TabsContent value="approvals" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <ApprovalsTab runId={runId} />
        </TabsContent>
        <TabsContent value="trace" className="mt-0 min-h-0 flex-1 overflow-hidden">
          <RunTab runId={runId} />
        </TabsContent>
      </Tabs>
    </aside>
  );
}

function CompanionTab({
  value,
  icon,
  label,
  badge,
  disabled,
}: {
  value: string;
  icon: React.ReactNode;
  label: string;
  badge: number;
  disabled?: boolean;
}) {
  return (
    <TabsTrigger value={value} disabled={disabled} className="relative gap-1 px-1">
      {icon}
      <span className="sr-only sm:not-sr-only">{label}</span>
      {badge > 0 && (
        <Badge variant="secondary" className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]">
          {badge > 9 ? "9+" : badge}
        </Badge>
      )}
    </TabsTrigger>
  );
}

function RailStatusIcon({ tone }: { tone: ReturnType<typeof buildRunCompanionRailView>["statusTone"] }) {
  if (tone === "live") return <Activity className="h-4 w-4" />;
  if (tone === "waiting") return <Clock3 className="h-4 w-4" />;
  if (tone === "success") return <CheckCircle2 className="h-4 w-4" />;
  if (tone === "danger") return <AlertTriangle className="h-4 w-4" />;
  return <Circle className="h-4 w-4" />;
}

function railToneClass(tone: ReturnType<typeof buildRunCompanionRailView>["statusTone"]): string {
  const classes = {
    muted: "border-border text-muted-foreground",
    live: "border-accent/30 bg-accent/10 text-accent",
    waiting: "border-warning/40 bg-warning/10 text-warning",
    success: "border-success/30 bg-success/10 text-success",
    danger: "border-destructive/35 bg-destructive/10 text-destructive",
    cancelled: "border-border bg-muted text-muted-foreground",
  };
  return classes[tone];
}
