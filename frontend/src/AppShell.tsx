import * as React from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/features/sidebar/Sidebar";
import { ConversationPage } from "@/features/conversation/ConversationPage";
import { InspectionPanel } from "@/features/inspection/InspectionPanel";
import { ManagerDialogs } from "@/features/manager/ManagerDialogs";
import { NewThreadPage } from "@/features/conversation/NewThreadPage";
import { runsApi, threadsApi } from "@/lib/api";
import { useRunStream } from "@/features/chat/useRunStream";
import type { RunStreamState } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";
import { useLocalStorage } from "@/lib/useLocalStorage";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage("aithru-agent:sidebar-collapsed", false);
  const [inspectionCollapsed, setInspectionCollapsed] = useLocalStorage(
    "aithru-agent:inspection-collapsed",
    true,
  );
  const [inspectionTab, setInspectionTab] = useLocalStorage(
    "aithru-agent:inspection-tab",
    "activity",
  );
  const [runId, setRunId] = React.useState<string | null>(null);

  return (
    <div className="flex h-full w-full overflow-hidden bg-muted/30">
      <ManagerDialogs>
        <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={() => setSidebarCollapsed((v) => !v)} />
      </ManagerDialogs>
      <div className="flex min-w-0 flex-1">
        <RouteContent
          runId={runId}
          onRunIdChange={setRunId}
          inspectionCollapsed={inspectionCollapsed}
          onToggleInspection={() => setInspectionCollapsed((v) => !v)}
          inspectionTab={inspectionTab}
          onSelectInspectionTab={setInspectionTab}
        />
      </div>
    </div>
  );
}

function RouteContent({
  runId,
  onRunIdChange,
  inspectionCollapsed,
  onToggleInspection,
  inspectionTab,
  onSelectInspectionTab,
}: {
  runId: string | null;
  onRunIdChange: (id: string | null) => void;
  inspectionCollapsed: boolean;
  onToggleInspection: () => void;
  inspectionTab: string;
  onSelectInspectionTab: (tab: string) => void;
}) {
  const { pathname: path } = useLocation();
  const segments = React.useMemo(() => path.split("/").filter(Boolean), [path]);
  const threadId =
    segments[0] === "threads" && segments[1] && segments[1] !== "new"
      ? decodeURIComponent(segments[1])
      : null;
  const routeRunId =
    threadId && segments[2] === "runs" && segments[3] ? decodeURIComponent(segments[3]) : null;

  React.useEffect(() => {
    onRunIdChange(routeRunId);
  }, [onRunIdChange, routeRunId]);

  const runsQuery = useQuery({
    queryKey: ["threads", threadId, "runs"],
    queryFn: () => threadsApi.runs(threadId!),
    enabled: !!threadId,
    refetchInterval: (q) => {
      const data = q.state.data as AgentRun[] | undefined;
      const hasActive = data?.some((run) => ["queued", "running"].includes(run.status));
      return hasActive ? 4000 : false;
    },
  });

  const activeRunId = React.useMemo(() => {
    if (runId) return runId;
    const runs = runsQuery.data;
    if (!runs?.length) return null;
    return runs[runs.length - 1].id;
  }, [runId, runsQuery.data]);

  const { state: streamState } = useRunStream(activeRunId);

  return (
    <>
      <ConversationRoute
        threadId={threadId}
        activeRunId={activeRunId}
        onRunIdChange={onRunIdChange}
        streamState={streamState}
        onSelectInspectionTab={onSelectInspectionTab}
      />
      <InspectionConnector
        runId={activeRunId}
        collapsed={inspectionCollapsed}
        onToggle={onToggleInspection}
        streamState={streamState}
        activeTab={inspectionTab}
        onTabChange={onSelectInspectionTab}
      />
    </>
  );
}

function ConversationRoute({
  threadId,
  activeRunId,
  onRunIdChange,
  streamState,
  onSelectInspectionTab,
}: {
  threadId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  onSelectInspectionTab: (tab: string) => void;
}) {
  if (!threadId) {
    return <NewThreadPage />;
  }
  return (
    <ConversationPage
      threadId={threadId}
      activeRunId={activeRunId}
      onRunIdChange={onRunIdChange}
      streamState={streamState}
      onSelectInspectionTab={onSelectInspectionTab}
    />
  );
}

function InspectionConnector({
  runId,
  collapsed,
  onToggle,
  streamState,
  activeTab,
  onTabChange,
}: {
  runId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  streamState: RunStreamState;
  activeTab: string;
  onTabChange: (tab: string) => void;
}) {
  const runQuery = useQuery({
    queryKey: ["runs", runId],
    queryFn: () => runsApi.get(runId!),
    enabled: !!runId,
  });
  const snapshotQuery = useQuery({
    queryKey: ["runs", runId, "snapshot"],
    queryFn: () => runsApi.snapshot(runId!),
    enabled: !!runId,
    refetchInterval: 3000,
  });

  const workspaceId = (runQuery.data?.workspace_id as string | undefined) ?? null;
  const runStatus = runQuery.data?.status;
  const todos = (snapshotQuery.data?.todos as Array<{ status: string }>) ?? [];
  const todoProgress = {
    done: todos.filter((t) => t.status === "done").length,
    total: todos.length,
  };

  return (
    <InspectionPanel
      runId={runId}
      workspaceId={workspaceId}
      collapsed={collapsed}
      onToggle={onToggle}
      runStatus={runStatus}
      todoProgress={todoProgress}
      streamState={streamState}
      activeTab={activeTab}
      onTabChange={onTabChange}
    />
  );
}
