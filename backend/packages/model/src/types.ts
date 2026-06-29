import type { AgentRun, AgentMessage } from "@aithru-agent/contracts";

export interface AgentModelToolResult {
  id: string;
  name: string;
  output: unknown;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
    details?: unknown;
  };
}

export interface AgentModelTurnInput {
  run: AgentRun;
  messages: AgentMessage[];
  context: Record<string, unknown>;
  toolResults: AgentModelToolResult[];
}

export type ModelTurnEvent =
  | { type: "text_delta"; delta: string }
  | { type: "reasoning_delta"; delta: string }
  | {
      type: "tool_call";
      id: string;
      name: string;
      input: Record<string, unknown>;
    }
  | {
      type: "usage";
      inputTokens: number;
      outputTokens: number;
      totalTokens?: number;
    }
  | { type: "completed"; content?: string }
  | {
      type: "failed";
      error: { code: string; message: string; retryable?: boolean };
    };

export interface AgentModelAdapter {
  createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent>;
}

export async function collectModelEvents(
  events: AsyncIterable<ModelTurnEvent>,
): Promise<ModelTurnEvent[]> {
  const collected: ModelTurnEvent[] = [];
  for await (const event of events) collected.push(event);
  return collected;
}
