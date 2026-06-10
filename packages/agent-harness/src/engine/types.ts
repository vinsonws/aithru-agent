import type {
  RunId, SkillId, ThreadId, OrgId, UserId, ApprovalId,
} from "@aithru/agent-core";
import type { AgentEventWriter } from "@aithru/agent-stream";
import type { AgentWorkspaceProvider } from "@aithru/agent-workspace";
import type { AithruCapabilityRouter } from "@aithru/agent-tools";
import type { AgentModelPort, AgentModelMessage } from "../model/model-port.js";
import type { AgentSkillResolver } from "../skill/skill-resolver.js";
import type { AgentStreamEvent } from "@aithru/agent-stream";

export type AgentHarnessRunInput = {
  orgId: OrgId;
  actorUserId: UserId;
  goal: string;
  threadId?: ThreadId;
  skillId?: SkillId;
  initialMessages?: AgentModelMessage[];
  scopes?: string[];
};

export type AgentHarnessResumeInput = {
  runId: RunId;
  approval?: {
    approvalId: ApprovalId;
    decision: "approved" | "rejected";
    comment?: string;
  };
};

export type AgentHarnessEnginePorts = {
  eventWriter: AgentEventWriter;
  workspaceProvider: AgentWorkspaceProvider;
  capabilityRouter: AithruCapabilityRouter;
  skillResolver: AgentSkillResolver;
  model: AgentModelPort;
};

export interface AgentHarnessEngine {
  run(input: AgentHarnessRunInput): AsyncIterable<AgentStreamEvent>;
  resume(input: AgentHarnessResumeInput): AsyncIterable<AgentStreamEvent>;
  cancel(runId: string): Promise<void>;
}
