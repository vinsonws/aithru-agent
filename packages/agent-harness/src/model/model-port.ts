export type AgentModelMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type AgentModelToolCall = {
  id: string;
  name: string;
  input: unknown;
};

export type AgentModelResult = {
  delta?: string;
  toolCalls?: AgentModelToolCall[];
  finished: boolean;
};

export interface AgentModelPort {
  start(messages: AgentModelMessage[], context: unknown): AsyncIterable<AgentModelResult>;
  cancel(): void;
}
