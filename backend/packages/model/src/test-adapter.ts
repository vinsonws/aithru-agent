import type {
  AgentModelAdapter,
  AgentModelTurnInput,
  ModelTurnEvent,
} from "./types.js";

export type TestModelTurn =
  | ModelTurnEvent[]
  | ((input: AgentModelTurnInput) => ModelTurnEvent[]);

export class TestModelAdapter implements AgentModelAdapter {
  private turnIndex = 0;

  constructor(private turns: TestModelTurn[]) {}

  async *createTurn(input: AgentModelTurnInput): AsyncIterable<ModelTurnEvent> {
    const turn = this.turns[Math.min(this.turnIndex, this.turns.length - 1)];
    this.turnIndex += 1;
    const events = typeof turn === "function" ? turn(input) : turn;
    for (const event of events) yield event;
  }
}
