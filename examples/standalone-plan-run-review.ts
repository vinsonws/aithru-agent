import type { AgentEvent, AgentHost } from "@aithru/agent-core";
import { AgentRuntime } from "@aithru/agent-runtime";
import { ScriptedModelAdapter } from "@aithru/model-test";

const events: AgentEvent[] = [];

const host: AgentHost = {
  emit(event) {
    events.push(event);
  },
  async callTool(request) {
    return {
      id: request.id,
      toolName: request.toolName,
      output: {
        path: request.arguments,
        content: "# Demo README\n\nAithru Agent demo repository.",
      },
    };
  },
  async listTools() {
    return [
      {
        name: "repo.read",
        description: "Read a repository file.",
        riskLevel: "read",
      },
    ];
  },
};

const model = new ScriptedModelAdapter({
  events(input) {
    if (input.mode === "plan") {
      return [
        {
          type: "structured.output",
          value: {
            steps: [
              {
                id: "step_read_readme",
                title: "Read README",
                objective: "Read the repository README.",
                allowedTools: ["repo.read"],
              },
            ],
          },
        },
      ];
    }

    if (input.mode === "execute") {
      return [
        {
          type: "tool_call.proposed",
          toolCall: {
            id: "tool_read_readme",
            toolName: "repo.read",
            arguments: { path: "README.md" },
            reason: "Need repository context.",
            riskLevel: "read",
          },
        },
        {
          type: "final",
          output: {
            summary: "README was read successfully.",
          },
        },
      ];
    }

    if (input.mode === "review") {
      return [
        {
          type: "structured.output",
          value: {
            status: "passed",
            summary: "The task completed successfully.",
          },
        },
      ];
    }

    return [{ type: "final", output: {} }];
  },
});

const runtime = new AgentRuntime();

for await (const event of runtime.run("plan-run-review", {
  task: {
    id: "task_plan_run_review_demo",
    goal: "Read the README and summarize it.",
  },
  model,
  host,
  options: {
    maxSteps: 4,
    review: true,
  },
})) {
  console.log(event.type);
}

console.log(JSON.stringify(events.at(-1), null, 2));
