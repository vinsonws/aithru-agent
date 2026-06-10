import type { AgentModelPort, AgentModelMessage, AgentModelResult } from "./model-port.js";

export type ScriptStep =
  | { type: "delta"; text: string }
  | { type: "tool"; name: string; input: unknown }
  | { type: "finish" };

export class ScriptedModelPort implements AgentModelPort {
  private cancelled = false;
  private steps: ScriptStep[];

  constructor(steps?: ScriptStep[]) {
    this.steps = steps ?? [
      { type: "delta", text: "I'll process your request step by step.\n\n" },
      { type: "delta", text: "Let me write the results to a file.\n\n" },
      {
        type: "tool",
        name: "workspace.writeFile",
        input: { path: "/reports/result.md", content: "# Analysis Result\n\nTask completed successfully.\n" },
      },
      { type: "delta", text: "\nDone! Written to /reports/result.md.\n" },
      { type: "finish" },
    ];
  }

  async *start(
    _messages: AgentModelMessage[],
    _context: unknown,
  ): AsyncIterable<AgentModelResult> {
    for (const step of this.steps) {
      if (this.cancelled) break;
      await new Promise((r) => setTimeout(r, 10));
      switch (step.type) {
        case "delta":
          yield { delta: step.text, finished: false };
          break;
        case "tool":
          yield {
            toolCalls: [{ id: `tool_${Date.now()}`, name: step.name, input: step.input }],
            finished: false,
          };
          break;
        case "finish":
          yield { finished: true };
          break;
      }
    }
  }

  cancel(): void {
    this.cancelled = true;
  }
}
