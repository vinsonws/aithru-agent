import type {
  AgentHost,
  AgentResearchFinding,
  AgentResearchReport,
  AgentResearchSource,
} from "@aithru/agent-core";
import { ScriptedModelAdapter } from "@aithru/agent-model-test";
import { AgentRuntime } from "@aithru/agent-runtime";

const source: AgentResearchSource = {
  id: "source_runtime_readme",
  title: "Runtime boundary note",
  uri: "memory://runtime-boundary",
  content:
    "Aithru Agent owns intelligent execution inside bounded tasks or nodes.",
};

const finding: AgentResearchFinding = {
  id: "finding_runtime_boundary",
  claim:
    "Deep Research V0 can stay inside the Agent runtime while tool execution remains host-owned.",
  sourceIds: [source.id],
  confidence: 0.91,
};

const report: AgentResearchReport = {
  title: "Deep Research V0 Boundary Report",
  summary:
    "Deep Research V0 completed with deterministic local evidence and no external network calls.",
  findings: [finding],
  sources: [source],
  limitations: [
    "The example uses a fake local source and scripted model events.",
  ],
};

const host: AgentHost = {
  emit(event) {
    console.log(event.type);
  },
  async callTool(request) {
    if (request.toolName !== "local.readSource") {
      return {
        id: request.id,
        toolName: request.toolName,
        error: {
          code: "unknown_tool",
          message: `Unknown local tool: ${request.toolName}`,
        },
      };
    }

    return {
      id: request.id,
      toolName: request.toolName,
      output: source,
      metadata: {
        deterministic: true,
      },
    };
  },
  async listTools() {
    return [
      {
        name: "local.readSource",
        description: "Read a deterministic in-memory source.",
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
            id: "plan_deep_research_demo",
            taskId: input.task.id,
            steps: [
              {
                id: "step_collect_runtime_boundary",
                title: "Collect runtime boundary source",
                objective:
                  "Read one deterministic local source through AgentHost.callTool.",
                allowedTools: ["local.readSource"],
              },
            ],
          },
        },
      ];
    }

    if (input.mode === "execute" && input.step) {
      return [
        {
          type: "tool_call.proposed",
          toolCall: {
            id: "tool_read_runtime_boundary",
            toolName: "local.readSource",
            arguments: { id: source.id },
            reason: "Need a local source for bounded research.",
            stepId: input.step.id,
            riskLevel: "read",
          },
        },
        {
          type: "final",
          output: {
            summary: "Collected one deterministic local source.",
            findings: [finding],
            sources: [source],
          },
        },
      ];
    }

    if (input.mode === "execute") {
      return [
        {
          type: "structured.output",
          value: report,
        },
      ];
    }

    if (input.mode === "review") {
      return [
        {
          type: "structured.output",
          value: {
            status: "passed",
            summary:
              "The report is grounded in the deterministic local source.",
          },
        },
      ];
    }

    return [];
  },
});

const runtime = new AgentRuntime();
const output = await runtime.runTask("deep-research", {
  task: {
    id: "task_deep_research_demo",
    goal: "Research whether Deep Research V0 can stay within the Aithru Agent boundary.",
  },
  model,
  host,
  options: {
    maxSteps: 1,
    maxSources: 1,
    review: true,
  },
});

console.log(output.summary);
console.log(
  JSON.stringify(
    output.artifacts.find((artifact) => artifact.type === "report"),
    null,
    2,
  ),
);
