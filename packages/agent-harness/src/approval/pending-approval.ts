import type {
  RunId,
  ThreadId,
  MessageId,
  TodoId,
  WorkspaceId,
  ToolCallId,
  ApprovalId,
  AgentExternalRunRef,
} from "@aithru/agent-core";
import type { AgentRunContext } from "@aithru/agent-tools";
import type { AgentModelResult } from "../model/model-port.js";

export type PendingApprovalBase = {
  runId: RunId;
  threadId?: ThreadId;
  msgId: MessageId;
  todoId: TodoId;
  workspaceId: WorkspaceId;
  toolCallId: ToolCallId;
  tc: { id: string; name: string; input: unknown };
  runContext: AgentRunContext;
  modelIterator: AsyncIterator<AgentModelResult>;
  toolAllowedNames: Set<string>;
};

export type PendingLocalApproval = PendingApprovalBase & {
  kind: "local_tool";
  approvalId: ApprovalId;
};

export type PendingExternalApproval = PendingApprovalBase & {
  kind: "workflow_capability";
  approvalId: string;
  externalRun: AgentExternalRunRef;
};

export type PendingApproval = PendingLocalApproval | PendingExternalApproval;
