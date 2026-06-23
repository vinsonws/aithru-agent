import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChatPanel } from "@/features/chat/ChatPanel";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { threadsApi } from "@/lib/api";
import { useTranslation } from "react-i18next";
import { ConversationHeader } from "./ConversationHeader";
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

  const renameMutation = useMutation({
    mutationFn: (title: string) => threadsApi.update(threadId!, { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["threads"] }),
  });

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col bg-background">
      <ConversationHeader
        title={threadQuery.data?.title}
        fallbackTitle={t("chat:newConversation")}
        runStatus={runStatus}
        streaming={streaming}
        modelName={activeRun?.harness_options?.model_profile_key ?? activeRun?.harness_options?.model}
        onRename={(title) => renameMutation.mutate(title)}
      />
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
