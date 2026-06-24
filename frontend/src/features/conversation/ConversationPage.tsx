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
import { useManager } from "@/features/manager/ManagerDialogs";
import { useTranslation } from "react-i18next";

export function ConversationPage({
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
  const { t } = useTranslation(["chat", "settings"]);
  const manager = useManager();
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

  const handleHeaderAction = (kind: string) => {
    switch (kind) {
      case "stop":
        if (activeRunId) cancelRunMutation.mutate(activeRunId);
        break;
      case "reply":
        setComposerFocusKey((k) => k + 1);
        break;
      case "reviewApproval":
        onOpenRightPanel("approvals");
        break;
      case "viewTrace":
        onOpenRightPanel("trace");
        break;
      case "openModelSettings":
        manager.open("settings");
        break;
      case "newFollowUp":
        setComposerDraft(t("chat:followUpPrompt", "Follow up on this run: "));
        setComposerFocusKey((k) => k + 1);
        break;
      case "retry":
        if (activeRun?.task_msg) {
          setComposerDraft(t("chat:retryPromptWithTaskMsg", "Retry this task: {{task}}", { task: activeRun.task_msg }));
        } else {
          setComposerDraft(t("chat:retryPrompt", "Retry the last task with the same intent."));
        }
        setComposerFocusKey((k) => k + 1);
        break;
    }
  };

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
    <div className="flex h-full min-w-0 flex-1 flex-col bg-background">
      <ConversationHeader
        view={view}
        onRename={(title) => renameMutation.mutate(title)}
        onAction={handleHeaderAction}
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
      </div>
    </div>
  );
}

function modeLabelForRun(mode: "auto" | "plan" | "chat", t: (key: string, fallback: string) => string): string {
  if (mode === "plan") return t("chat:modePlan", "Plan");
  if (mode === "chat") return t("chat:modeChat", "Chat");
  return t("chat:modeAuto", "Auto");
}
