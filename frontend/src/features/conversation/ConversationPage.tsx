import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { threadsApi, runsApi } from "@/lib/api";
import { ConversationHeader } from "./ConversationHeader";
import { buildRunHeaderView } from "./runHeaderView";
import type { RunStreamState } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";

export function ConversationPage({
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

  const activeRun = runsQuery.data?.find((r) => r.id === activeRunId);

  const renameMutation = useMutation({
    mutationFn: (title: string) => threadsApi.update(threadId!, { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["threads"] }),
  });

  const cancelRunMutation = useMutation({
    mutationFn: (id: string) => runsApi.cancel(id),
  });

  const view = buildRunHeaderView({
    thread: threadQuery.data ?? null,
    activeRun: activeRun ?? null,
    streamStatus: streamState.status,
    streamError: streamState.error,
    threadId: threadId ?? "",
    modeLabel: "Auto",
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
        onSelectInspectionTab("approvals");
        break;
      case "viewTrace":
        onSelectInspectionTab("trace");
        break;
      case "openModelSettings":
        window.dispatchEvent(new CustomEvent("aithru:open-settings"));
        break;
      case "newFollowUp":
        setComposerDraft("Follow up on this run: ");
        setComposerFocusKey((k) => k + 1);
        break;
      case "retry":
        if (activeRun?.goal) {
          setComposerDraft(`Retry this task: ${activeRun.goal}`);
        } else {
          setComposerDraft("Retry the last task with the same intent.");
        }
        setComposerFocusKey((k) => k + 1);
        break;
    }
  };

  const handlePrefillComposer = (text: string) => {
    setComposerDraft(text);
    setComposerFocusKey((k) => k + 1);
  };

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-background">
      <ConversationHeader
        view={view}
        onRename={(title) => renameMutation.mutate(title)}
        onAction={handleHeaderAction}
      />
      <div className="min-h-0 flex-1">
        <ChatPanel
          state={streamState}
          {...({ onPrefillComposer: handlePrefillComposer, onOpenTrace: () => onSelectInspectionTab("trace") } as any)}
        />
      </div>
      <ChatComposer
        threadId={threadId}
        activeRunId={activeRunId}
        onRunCreated={(id) => {
          onRunIdChange(id);
          qc.invalidateQueries({ queryKey: ["threads", threadId, "runs"] });
          setComposerDraft("");
        }}
        draft={composerDraft}
        onDraftChange={setComposerDraft}
        focusKey={composerFocusKey}
        onCancelRun={() => cancelRunMutation.mutate(activeRunId!)}
      />
    </div>
  );
}
