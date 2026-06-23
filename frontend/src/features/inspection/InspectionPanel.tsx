import type { RunStreamState } from "@/features/chat/useRunStream";
import { RunCompanion } from "./RunCompanion";

export function InspectionPanel(props: {
  runId: string | null;
  workspaceId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  runStatus?: string;
  todoProgress?: { done: number; total: number };
  streamState?: RunStreamState;
}) {
  return (
    <RunCompanion
      {...props}
      streamState={
        props.streamState ?? {
          status: "idle",
          messages: [],
          toolCalls: [],
          todos: [],
          inlineRequests: [],
        }
      }
    />
  );
}
