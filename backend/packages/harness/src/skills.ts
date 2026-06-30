import type { AgentEventWriter } from "@aithru-agent/stream";
import { EVENT_TYPES, VISIBILITY } from "@aithru-agent/stream";

export type SkillActivationTrigger = "explicit" | "slash" | "model_load";

export function emitSkillActivated(args: {
  eventWriter: AgentEventWriter;
  runId: string;
  threadId: string | null;
  key: string;
  name: string;
  source: string;
  version: string;
  trigger: SkillActivationTrigger;
  allowedTools: string[];
  deniedTools: string[];
}): void {
  args.eventWriter.write(
    args.runId,
    args.threadId,
    EVENT_TYPES.SKILL_ACTIVATED,
    {
      key: args.key,
      name: args.name,
      source: args.source,
      version: args.version,
      trigger: args.trigger,
      policy: {
        allowed_tools: args.allowedTools,
        denied_tools: args.deniedTools,
      },
    },
    { visibility: VISIBILITY.AUDIT, source: { kind: "harness" } },
  );
}
