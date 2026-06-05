import type {
  AgentModelAdapter,
  AgentModelEvent,
  AgentModelInput,
} from "@aithru/agent-core";

export type ScriptedModelAdapterOptions = {
  name?: string;
  events: AgentModelEvent[] | ((input: AgentModelInput) => AgentModelEvent[]);
};

export class ScriptedModelAdapter implements AgentModelAdapter {
  readonly name: string;

  private readonly events: ScriptedModelAdapterOptions["events"];

  constructor(options: ScriptedModelAdapterOptions) {
    this.name = options.name ?? "scripted-test-model";
    this.events = options.events;
  }

  async *generate(input: AgentModelInput): AsyncIterable<AgentModelEvent> {
    const events = typeof this.events === "function" ? this.events(input) : this.events;

    for (const event of events) {
      yield event;
    }
  }
}

export function createStaticFinalModel(output: unknown, name = "static-final-model") {
  return new ScriptedModelAdapter({
    name,
    events: [{ type: "final", output }],
  });
}

export function createStaticStructuredModel(
  value: unknown,
  name = "static-structured-model",
) {
  return new ScriptedModelAdapter({
    name,
    events: [{ type: "structured.output", value }],
  });
}
