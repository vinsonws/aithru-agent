import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { threadsApi, runsApi } from "@/lib/api";
import { ConversationHeader } from "./ConversationHeader";
import { buildRunHeaderView, getRunMode } from "./runHeaderView";
import { isActiveRunStatus } from "@/features/chat/runStatusCopy";
import { buildRunStreamState, type RunStreamState } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";
import { useTranslation } from "react-i18next";

export function ConversationPage({
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
  rightPanelContent?: React.ReactNode;
  rightRail?: React.ReactNode;
}) {
  const { t } = useTranslation(["chat", "settings"]);
  const qc = useQueryClient();
  const [composerDraft, setComposerDraft] = React.useState("");
  const [composerFocusKey, setComposerFocusKey] = React.useState(0);

  const threadQuery = useQuery({
    queryKey: ["threads", threadId],
    queryFn: () => (threadId ? threadsApi.get(threadId) : Promise.reject(new Error("no thread"))),
    enabled: !!threadId,
  });

  const runsQuery = useQuery({
    queryKey: ["threads", threadId, "runs"],
    queryFn: () => threadsApi.runs(threadId!),
    enabled: !!threadId,
    refetchInterval: (q) => {
      const data = q.state.data as AgentRun[] | undefined;
      const hasActive = data?.some((r) => ["queued", "running"].includes(r.status));
      return hasActive ? 4000 : false;
    },
  });

  const messagesQuery = useQuery({
    queryKey: ["threads", threadId, "messages"],
    queryFn: () => threadsApi.messages(threadId!),
    enabled: !!threadId,
  });

  const runIds = React.useMemo(() => runsQuery.data?.map((run) => run.id) ?? [], [runsQuery.data]);
  const historicalRunStatesQuery = useQuery({
    queryKey: ["threads", threadId, "run-states", runIds.join("|")],
    queryFn: async () => {
      const pairs = await Promise.all(
        runIds.map(async (runId) => {
          try {
            return [runId, buildRunStreamState(await runsApi.events(runId))] as const;
          } catch {
            return null;
          }
        }),
      );
      return Object.fromEntries(pairs.filter((pair): pair is [string, RunStreamState] => pair !== null));
    },
    enabled: !!threadId && runIds.length > 0,
  });

  const activeRun = runsQuery.data?.find((r) => r.id === activeRunId);
  const cancellableRunId =
    activeRun && isActiveRunStatus(activeRun.status) ? activeRunId : null;

  const renameMutation = useMutation({
    mutationFn: (title: string) => threadsApi.update(threadId!, { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["threads"] }),
  });

  const cancelRunMutation = useMutation({
    mutationFn: (id: string) => runsApi.cancel(id),
  });

  const modeLabel = modeLabelForRun(getRunMode(activeRun), t);

  const view = buildRunHeaderView({
    thread: threadQuery.data ?? null,
    activeRun: activeRun ?? null,
    streamStatus: streamState.status,
    streamError: streamState.error,
    threadId: threadId ?? "",
    modeLabel,
  });

  const handlePrefillComposer = (text: string) => {
    setComposerDraft(text);
    setComposerFocusKey((k) => k + 1);
  };

  React.useEffect(() => {
    if (["completed", "failed", "cancelled"].includes(streamState.status)) {
      void qc.invalidateQueries({ queryKey: ["threads", threadId, "messages"] });
      void qc.invalidateQueries({ queryKey: ["threads", threadId, "run-states"] });
    }
  }, [qc, streamState.status, threadId]);

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <ConversationHeader
        view={view}
        tokenUsage={streamState.tokenUsage}
        onRename={(title) => renameMutation.mutate(title)}
      />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <ChatPanel
              state={streamState}
              threadMessages={messagesQuery.data ?? []}
              activeRunId={activeRunId}
              historicalRunStates={historicalRunStatesQuery.data ?? {}}
              onPrefillComposer={handlePrefillComposer}
              onOpenTrace={() => onOpenRightPanel("trace")}
              onPreviewFile={onPreviewFile}
            />
          </div>
          <ChatComposer
            threadId={threadId}
            activeRunId={activeRunId}
            cancellableRunId={cancellableRunId}
            activeRunTaskMsg={activeRun?.task_msg ?? null}
            onRequestStatus={() => onOpenRightPanel("activity")}
            onRunCreated={(id) => {
              onRunIdChange(id);
              qc.invalidateQueries({ queryKey: ["threads", threadId, "runs"] });
              qc.invalidateQueries({ queryKey: ["threads", threadId, "messages"] });
              qc.invalidateQueries({ queryKey: ["threads", threadId, "run-states"] });
              setComposerDraft("");
            }}
            draft={composerDraft}
            onDraftChange={setComposerDraft}
            focusKey={composerFocusKey}
            onCancelRun={() => {
              if (cancellableRunId) cancelRunMutation.mutate(cancellableRunId);
            }}
          />
        </div>
        {rightPanelContent ? (
          <ResizableRightPanel
            width={rightPanelWidth}
            onWidthChange={onRightPanelWidthChange}
            minWidth={240}
            maxWidth={720}
          >
            {rightPanelContent}
          </ResizableRightPanel>
        ) : null}
        {rightRail}
      </div>
    </div>
  );
}

function modeLabelForRun(mode: "auto" | "plan" | "chat", t: (key: string, fallback: string) => string): string {
  if (mode === "plan") return t("chat:modePlan", "Plan");
  if (mode === "chat") return t("chat:modeChat", "Chat");
  return t("chat:modeAuto", "Auto");
}

function ResizableRightPanel({
  width,
  onWidthChange,
  minWidth,
  maxWidth,
  children,
}: {
  width: number;
  onWidthChange: (width: number) => void;
  minWidth: number;
  maxWidth: number;
  children: React.ReactNode;
}) {
  const handleRef = React.useRef<HTMLDivElement>(null);
  const draggingRef = React.useRef(false);
  const startXRef = React.useRef(0);
  const startWidthRef = React.useRef(0);

  React.useEffect(() => {
    const handle = handleRef.current;
    if (!handle) return;

    const onMouseDown = (e: MouseEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      startXRef.current = e.clientX;
      startWidthRef.current = width;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const delta = startXRef.current - e.clientX;
      const next = Math.min(maxWidth, Math.max(minWidth, startWidthRef.current + delta));
      onWidthChange(next);
    };

    const onMouseUp = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    handle.addEventListener("mousedown", onMouseDown);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);

    return () => {
      handle.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [width, onWidthChange, minWidth, maxWidth]);

  return (
    <div className="flex shrink-0" style={{ width }}>
      <div
        ref={handleRef}
        className="group relative w-1 shrink-0 cursor-col-resize bg-border/40 transition-colors hover:bg-primary/30 active:bg-primary/50"
      >
        <div className="absolute inset-y-0 -left-1 -right-1" />
      </div>
      {children}
    </div>
  );
}
