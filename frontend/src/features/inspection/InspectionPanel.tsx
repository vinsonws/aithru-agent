import { Group, Panel, Separator } from "react-resizable-panels";
import { PanelRightOpen, PanelRightClose, Activity } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { useTranslation } from "react-i18next";
import type { RunStreamState } from "@/features/chat/useRunStream";
import { RunTab } from "./tabs/RunTab";
import { WorkspaceTab } from "./tabs/WorkspaceTab";
import { ArtifactsTab } from "./tabs/ArtifactsTab";
import { ApprovalsTab } from "./tabs/ApprovalsTab";
import { MemoryTab } from "./tabs/MemoryTab";

export function InspectionPanel({
  runId,
  workspaceId,
  collapsed,
  onToggle,
  runStatus,
  todoProgress,
  streamState: _streamState,
}: {
  runId: string | null;
  workspaceId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  runStatus?: string;
  todoProgress?: { done: number; total: number };
  streamState?: RunStreamState;
}) {
  const { t } = useTranslation("inspection");

  if (collapsed) {
    // Narrow rail: run status + todo progress only.
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center gap-3 border-l bg-card py-3">
        <Button variant="ghost" size="icon" onClick={onToggle} title={t("expand")}>
          <PanelRightOpen className="h-4 w-4" />
        </Button>
        <div className="flex flex-col items-center gap-1">
          <Activity className="h-4 w-4 text-muted-foreground" />
          {runStatus && (
            <div className="rotate-90 whitespace-nowrap text-[10px] text-muted-foreground">
              {t(`status.${runStatus}`, { ns: "common", defaultValue: runStatus })}
            </div>
          )}
        </div>
        {todoProgress && todoProgress.total > 0 && (
          <div className="flex flex-col items-center text-[10px] text-muted-foreground">
            <span className="font-mono">
              {todoProgress.done}/{todoProgress.total}
            </span>
            <div className="mt-1 h-16 w-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="w-full bg-success"
                style={{ height: `${(todoProgress.done / todoProgress.total) * 100}%`, marginTop: "auto" }}
              />
            </div>
          </div>
        )}
      </aside>
    );
  }

  return (
    <Group orientation="horizontal" className="border-l">
      <Panel defaultSize={22} minSize={18} maxSize={42} className="bg-card">
        <div className="flex h-full flex-col">
          <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
            <span className="text-sm font-medium">{t("inspection")}</span>
            {runStatus && <StatusBadge status={runStatus} />}
            <Button variant="ghost" size="icon" className="ml-auto h-7 w-7" onClick={onToggle} title={t("collapse")}>
              <PanelRightClose className="h-4 w-4" />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden p-2">
            <Tabs defaultValue="run" className="flex h-full flex-col">
              <TabsList className="self-start">
                <TabsTrigger value="run">{t("tabRun")}</TabsTrigger>
                <TabsTrigger value="workspace" disabled={!workspaceId}>
                  {t("tabWorkspace")}
                </TabsTrigger>
                <TabsTrigger value="artifacts">{t("tabArtifacts")}</TabsTrigger>
                <TabsTrigger value="approvals">{t("tabApprovals")}</TabsTrigger>
                <TabsTrigger value="memory" disabled={!runId}>
                  {t("tabMemory")}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="run" className="min-h-0 flex-1 overflow-hidden">
                <RunTab runId={runId} />
              </TabsContent>
              <TabsContent value="workspace" className="min-h-0 flex-1 overflow-hidden">
                <WorkspaceTab workspaceId={workspaceId} />
              </TabsContent>
              <TabsContent value="artifacts" className="min-h-0 flex-1 overflow-hidden">
                <ArtifactsTab runId={runId} />
              </TabsContent>
              <TabsContent value="approvals" className="min-h-0 flex-1 overflow-hidden">
                <ApprovalsTab runId={runId} />
              </TabsContent>
              <TabsContent value="memory" className="min-h-0 flex-1 overflow-hidden">
                <MemoryTab runId={runId} />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </Panel>
      <Separator className="w-px bg-border" />
    </Group>
  );
}
