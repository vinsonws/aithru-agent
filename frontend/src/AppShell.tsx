import * as React from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/features/sidebar/Sidebar";
import { ConversationPage } from "@/features/conversation/ConversationPage";
import { ManagerDialogs } from "@/features/manager/ManagerDialogs";
import { NewThreadPage } from "@/features/conversation/NewThreadPage";
import { runsApi, threadsApi } from "@/lib/api";
import { useRunStream } from "@/features/chat/useRunStream";
import type { RunStreamState } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";
import { useLocalStorage } from "@/lib/useLocalStorage";
import { resolveActiveRunId, type SelectedRunRef } from "@/features/conversation/activeRunSelection";
import { RightRail } from "@/features/sidebar/RightRail";
import { FilePreviewPanel } from "@/features/sidebar/panels/FilePreviewPanel";
import { FileListPanel } from "@/features/sidebar/panels/FileListPanel";
import { ActivityPanel } from "@/features/sidebar/panels/ActivityPanel";
import { ApprovalsPanel } from "@/features/sidebar/panels/ApprovalsPanel";
import { TracePanel } from "@/features/sidebar/panels/TracePanel";
import { buildRunCompanionBadges } from "@/features/chat/runActivity";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage("aithru-agent:sidebar-collapsed", false);
  const [rightPanel, setRightPanel] = React.useState<string | null>(null);
  const [selectedFile, setSelectedFile] = React.useState<string | null>(null);
  const [selectedRun, setSelectedRun] = React.useState<SelectedRunRef | null>(null);

  return (
    <div className="flex h-full w-full overflow-hidden bg-muted/30">
      <ManagerDialogs>
        <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={() => setSidebarCollapsed((v) => !v)} />
        <div className="flex min-w-0 flex-1">
          <RouteContent
            selectedRun={selectedRun}
            onSelectedRunChange={setSelectedRun}
            rightPanel={rightPanel}
            onRightPanelChange={setRightPanel}
            selectedFile={selectedFile}
            onSelectedFileChange={setSelectedFile}
          />
        </div>
      </ManagerDialogs>
    </div>
  );
}

function RouteContent({
  selectedRun,
  onSelectedRunChange,
  rightPanel,
  onRightPanelChange,
  selectedFile,
  onSelectedFileChange,
}: {
  selectedRun: SelectedRunRef | null;
  onSelectedRunChange: (run: SelectedRunRef | null) => void;
  rightPanel: string | null;
  onRightPanelChange: (panel: string | null) => void;
  selectedFile: string | null;
  onSelectedFileChange: (fileId: string | null) => void;
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
    if (!threadId) {
      onSelectedRunChange(null);
      return;
    }
    if (routeRunId) {
      onSelectedRunChange({ threadId, runId: routeRunId });
    }
  }, [onSelectedRunChange, routeRunId, threadId]);

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

  const activeRunId = React.useMemo(
    () =>
      resolveActiveRunId({
        threadId,
        routeRunId,
        selectedRun,
        runs: runsQuery.data,
      }),
    [routeRunId, runsQuery.data, selectedRun, threadId],
  );

  const { state: streamState } = useRunStream(activeRunId);

  // Fetch run snapshot to determine if output files exist
  const snapshotQuery = useQuery({
    queryKey: ["runs", activeRunId, "snapshot"],
    queryFn: () => runsApi.snapshot(activeRunId!),
    enabled: !!activeRunId,
    refetchInterval: 3000,
  });

  const hasOutputFiles = React.useMemo(() => {
    const snapshot = snapshotQuery.data;
    if (!snapshot) return false;
    const workspaceFiles = (snapshot as Record<string, unknown>).workspace_files as unknown[];
    const artifacts = (snapshot as Record<string, unknown>).artifacts as unknown[];
    return (Array.isArray(workspaceFiles) && workspaceFiles.length > 0) ||
           (Array.isArray(artifacts) && artifacts.length > 0);
  }, [snapshotQuery.data]);

  const badges = buildRunCompanionBadges(streamState);

  const activeRun = runsQuery.data?.find((r: AgentRun) => r.id === activeRunId);
  const workspaceId = (activeRun?.workspace_id as string | undefined) ?? null;

  const handlePreviewFile = (fileId: string) => {
    onSelectedFileChange(fileId);
    onRightPanelChange("preview");
  };

  return (
    <>
      <ConversationRoute
        threadId={threadId}
        activeRunId={activeRunId}
        onRunIdChange={(id) => onSelectedRunChange(id && threadId ? { threadId, runId: id } : null)}
        streamState={streamState}
        onOpenRightPanel={onRightPanelChange}
        onPreviewFile={handlePreviewFile}
      />
      {hasOutputFiles && (
        <>
          <RightRail
            activePanel={rightPanel}
            onPanelChange={onRightPanelChange}
            badges={badges}
          />
          {rightPanel === "preview" && (
            <FilePreviewPanel
              runId={activeRunId}
              workspaceId={workspaceId}
              selectedFileId={selectedFile}
              onSelectFile={handlePreviewFile}
              onClearFile={() => onSelectedFileChange(null)}
              onClose={() => onRightPanelChange(null)}
            />
          )}
          {rightPanel === "files" && (
            <FileListPanel
              runId={activeRunId}
              workspaceId={workspaceId}
              onSelectFile={handlePreviewFile}
              onClose={() => onRightPanelChange(null)}
            />
          )}
          {rightPanel === "activity" && (
            <ActivityPanel streamState={streamState} onClose={() => onRightPanelChange(null)} />
          )}
          {rightPanel === "approvals" && (
            <ApprovalsPanel runId={activeRunId} onClose={() => onRightPanelChange(null)} />
          )}
          {rightPanel === "trace" && (
            <TracePanel runId={activeRunId} onClose={() => onRightPanelChange(null)} />
          )}
        </>
      )}
    </>
  );
}

function ConversationRoute({
  threadId,
  activeRunId,
  onRunIdChange,
  streamState,
  onOpenRightPanel,
  onPreviewFile,
}: {
  threadId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  onOpenRightPanel: (panel: string | null) => void;
  onPreviewFile: (fileId: string) => void;
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
      onOpenRightPanel={onOpenRightPanel}
      onPreviewFile={onPreviewFile}
    />
  );
}
