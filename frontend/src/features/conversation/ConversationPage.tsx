import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { threadsApi } from "@/lib/api";
import { useTranslation } from "react-i18next";
import type { RunStreamState } from "@/features/chat/useRunStream";
import type { AgentRun } from "@/lib/api";

export function ConversationPage({
  threadId,
  activeRunId,
  onRunIdChange,
  streamState,
  streaming,
}: {
  threadId: string | null;
  activeRunId: string | null;
  onRunIdChange: (id: string | null) => void;
  streamState: RunStreamState;
  streaming: boolean;
}) {
  const { t } = useTranslation(["chat", "common"]);
  const qc = useQueryClient();

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

  // Resolve the active run object for status display.
  const activeRun = runsQuery.data?.find((r) => r.id === activeRunId);
  const runStatus = streamState.status !== "idle" ? streamState.status : activeRun?.status;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      {/* Page-local toolbar (not a global top bar) */}
      <div className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
        <span className="truncate text-sm font-medium">{threadQuery.data?.title ?? t("chat:newConversation")}</span>
        {runStatus && <StatusBadge status={runStatus} />}
        {streaming && (
          <span className="text-xs text-accent">● live</span>
        )}
      </div>

      <div className="min-h-0 flex-1">
        <ChatPanel state={streamState} />
      </div>

      <ChatComposer
        threadId={threadId}
        activeRunId={activeRunId}
        onRunCreated={(id) => {
          onRunIdChange(id);
          qc.invalidateQueries({ queryKey: ["threads", threadId, "runs"] });
        }}
      />
    </div>
  );
}
