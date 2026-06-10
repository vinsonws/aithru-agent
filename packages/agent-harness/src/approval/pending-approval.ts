import type {
  RunId, ThreadId, MessageId, TodoId, WorkspaceId, ToolCallId, ApprovalId,
} from "@aithru/agent-core";
import type { AgentModelResult } from "../model/model-port.js";
import type { AgentRunContext } from "@aithru/agent-tools";

export type PendingApproval = {
  runId: RunId;
  threadId?: ThreadId;
  msgId: MessageId;
  todoId: TodoId;
  workspaceId: WorkspaceId;
  toolCallId: ToolCallId;
  tc: { name: string; input: unknown };
  runContext: AgentRunContext;
  approvalId: ApprovalId;
  modelIterator: AsyncIterator<AgentModelResult>;
  toolAllowedNames: Set<string>;
};
