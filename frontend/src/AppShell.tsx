import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/features/sidebar/Sidebar";
import { ConversationPage } from "@/features/conversation/ConversationPage";
import { ManagerDialogs } from "@/features/manager/ManagerDialogs";
import { NewThreadPage } from "@/features/conversation/NewThreadPage";
import { threadsApi } from "@/lib/api";
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
import { buildDraftWorkspaceFiles } from "@/features/inspection/runFilesView";

const DEFAULT_RIGHT_PANEL_WIDTH = 340;
const MIN_RIGHT_PANEL_WIDTH = 240;
const MAX_RIGHT_PANEL_WIDTH = 720;

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage("aithru-agent:sidebar-collapsed", false);
  const [rightPanel, setRightPanel] = React.useState<string | null>(null);
  const [rightPanelWidth, setRightPanelWidth] = useLocalStorage("aithru-agent:right-panel-width", DEFAULT_RIGHT_PANEL_WIDTH);
  const clampedRightPanelWidth = clampRightPanelWidth(rightPanelWidth);
  const handleRightPanelWidthChange = React.useCallback(
    (width: number) => setRightPanelWidth(clampRightPanelWidth(width)),
    [setRightPanelWidth],
  );
  const [openFileIds, setOpenFileIds] = React.useState<string[]>([]);
  const [activeFileId, setActiveFileId] = React.useState<string | null>(null);
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
            rightPanelWidth={clampedRightPanelWidth}
            onRightPanelWidthChange={handleRightPanelWidthChange}
            openFileIds={openFileIds}
            onOpenFileIdsChange={setOpenFileIds}
            activeFileId={activeFileId}
            onActiveFileIdChange={setActiveFileId}
          />
        </div>
      </ManagerDialogs>
    </div>
  );
}

function clampRightPanelWidth(width: number): number {
  return Math.min(MAX_RIGHT_PANEL_WIDTH, Math.max(MIN_RIGHT_PANEL_WIDTH, width));
}

function RouteContent({
  selectedRun,
  onSelectedRunChange,
  rightPanel,
  onRightPanelChange,
  rightPanelWidth,
  onRightPanelWidthChange,
  openFileIds,
  onOpenFileIdsChange,
  activeFileId,
  onActiveFileIdChange,
}: {
  selectedRun: SelectedRunRef | null;
  onSelectedRunChange: (run: SelectedRunRef | null) => void;
  rightPanel: string | null;
  onRightPanelChange: (panel: string | null) => void;
  rightPanelWidth: number;
  onRightPanelWidthChange: (width: number) => void;
  openFileIds: string[];
  onOpenFileIdsChange: (ids: string[]) => void;
  activeFileId: string | null;
  onActiveFileIdChange: (id: string | null) => void;
}) {
  const { pathname: path } = useLocation();
  const navigate = useNavigate();
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
  const draftWorkspaceFiles = React.useMemo(
    () => buildDraftWorkspaceFiles(streamState.toolInputDrafts ?? []),
    [streamState.toolInputDrafts],
  );
  const openedDraftFileIdsRef = React.useRef<Set<string>>(new Set());

  const badges = buildRunCompanionBadges(streamState);

  const activeRun = runsQuery.data?.find((r: AgentRun) => r.id === activeRunId);
  const workspaceId = (activeRun?.workspace_id as string | undefined) ?? null;

  const handlePreviewFile = React.useCallback((fileId: string) => {
    onOpenFileIdsChange(
      openFileIds.includes(fileId) ? openFileIds : [...openFileIds, fileId],
    );
    onActiveFileIdChange(fileId);
    onRightPanelChange("preview");
  }, [onActiveFileIdChange, onOpenFileIdsChange, onRightPanelChange, openFileIds]);

  React.useEffect(() => {
    const draft = draftWorkspaceFiles.find(
      (file) => file.content.length > 0 && !openedDraftFileIdsRef.current.has(file.id),
    );
    if (!draft) return;
    openedDraftFileIdsRef.current.add(draft.id);
    handlePreviewFile(draft.id);
  }, [draftWorkspaceFiles, handlePreviewFile]);

  const rightPanelContent = activeRunId && rightPanel ? (
    <>
      {rightPanel === "preview" && (
        <FilePreviewPanel
          runId={activeRunId}
          workspaceId={workspaceId}
          draftWorkspaceFiles={draftWorkspaceFiles}
          openFileIds={openFileIds}
          activeFileId={activeFileId}
          onSelectFile={handlePreviewFile}
          onActiveFileChange={onActiveFileIdChange}
          onCloseFile={(fileId) => {
            const next = openFileIds.filter((id) => id !== fileId);
            onOpenFileIdsChange(next);
            if (activeFileId === fileId) {
              onActiveFileIdChange(next.length > 0 ? next[next.length - 1] : null);
            }
          }}
          onClose={() => onRightPanelChange(null)}
        />
      )}
      {rightPanel === "files" && (
        <FileListPanel
          runId={activeRunId}
          workspaceId={workspaceId}
          draftWorkspaceFiles={draftWorkspaceFiles}
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
  ) : null;

  const rightRail = activeRunId ? (
    <RightRail
      activePanel={rightPanel}
      onPanelChange={onRightPanelChange}
      badges={badges}
    />
  ) : null;

  return (
    <ConversationRoute
      threadId={threadId}
      activeRunId={activeRunId}
      onRunIdChange={(id) => {
        onSelectedRunChange(id && threadId ? { threadId, runId: id } : null);
        if (id && threadId && routeRunId) {
          navigate(`/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(id)}`);
        }
      }}
      streamState={streamState}
      onOpenRightPanel={onRightPanelChange}
      onPreviewFile={handlePreviewFile}
      rightPanelWidth={rightPanelWidth}
      onRightPanelWidthChange={onRightPanelWidthChange}
      rightPanelContent={rightPanelContent}
      rightRail={rightRail}
    />
  );
}

function ConversationRoute({
  threadId,
  activeRunId,
  onRunIdChange,
  streamState,
  onOpenRightPanel,
  onPreviewFile,
  rightPanelWidth,
  onRightPanelWidthChange,
  rightPanelContent,
  rightRail,
}: {
  threadId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  onOpenRightPanel: (panel: string | null) => void;
  onPreviewFile: (fileId: string) => void;
  rightPanelWidth: number;
  onRightPanelWidthChange: (width: number) => void;
  rightPanelContent: React.ReactNode;
  rightRail: React.ReactNode;
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
      rightPanelWidth={rightPanelWidth}
      onRightPanelWidthChange={onRightPanelWidthChange}
      rightPanelContent={rightPanelContent}
      rightRail={rightRail}
    />
  );
}
