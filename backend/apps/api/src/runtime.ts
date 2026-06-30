import { ProductionCapabilityRouter } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { TERMINAL_RUN_STATUSES } from "@aithru-agent/contracts";
import { ModelTurnLoop, ScriptedHarnessCore } from "@aithru-agent/harness";
import {
  TestModelAdapter,
  createSdkModelAdapter,
  type AgentModelAdapter,
  type AgentModelToolResult,
} from "@aithru-agent/model";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { InMemoryStore, SqliteStore, type AgentApproval, type AgentStore } from "@aithru-agent/persistence";
import { SkillRegistry, SkillResolver, findBuiltinSkillsRoot } from "@aithru-agent/skills";
import { WorkerRunner } from "@aithru-agent/worker";
import { createApprovalResolver, type ScheduleRunExecutionOptions } from "./approval-resolution.js";

export interface AgentRuntime {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  capabilityRouter: ProductionCapabilityRouter;
  harness: ScriptedHarnessCore;
  worker: WorkerRunner;
  skillResolver: SkillResolver;
  scheduleRunExecution: (
    run: AgentRun | string,
    options?: ScheduleRunExecutionOptions,
  ) => Promise<AgentRun | undefined>;
  resolveApproval: (approvalId: string, decision: "approved" | "denied") => Promise<AgentApproval>;
}

let _runtime: AgentRuntime | null = null;

type StoredModelProfile = {
  key: string;
  name?: string;
  provider?: string;
  model?: string;
  enabled?: boolean;
  capabilities?: {
    thinking?: boolean;
    vision?: boolean;
  } | null;
  auth_secret?: {
    has_secret?: boolean;
    secret_ref?: string | null;
  } | null;
  metadata?: {
    base_url?: string;
    baseURL?: string;
    api_kind?: "openai_chat_completions" | "openai_responses" | "anthropic_messages";
    request?: Record<string, unknown>;
    supports_thinking?: boolean;
    supports_reasoning_effort?: boolean;
    when_thinking_enabled?: Record<string, unknown>;
    thinking?: Record<string, unknown>;
    compat?: "deepseek" | "qwen" | "minimax" | "gemini_openai_compatible";
    use_responses_api?: boolean;
  } | null;
};

function modelProfileKey(run: AgentRun): string | null {
  const options = run.harness_options as Record<string, unknown> | null | undefined;
  return typeof options?.model_profile_key === "string" && options.model_profile_key.trim()
    ? options.model_profile_key.trim()
    : null;
}

function defaultTestAdapter(): AgentModelAdapter {
  return new TestModelAdapter([
    (input) => [
      {
        type: "text_delta",
        delta: input.context.purpose === "thread_title"
          ? "Generated Thread Title"
          : `Received: ${input.run.task_msg}`,
      },
      { type: "completed" },
    ],
  ]);
}

function failingAdapter(code: string, message: string): AgentModelAdapter {
  return new TestModelAdapter([
    [
      {
        type: "failed",
        error: { code, message, retryable: false },
      },
    ],
  ]);
}

function storedModelProfile(
  store: AgentStore,
  orgId: string,
  key: string,
): StoredModelProfile | null {
  const profile = store
    .listDocuments("model_profile_entry")
    .map((doc) => doc.payload as StoredModelProfile)
    .find((entry) => entry.key === key && (entry as any).org_id === orgId);
  if (profile) return profile;
  if (key === "default") {
    return {
      key: "default",
      provider: "test",
      model: "test",
      enabled: true,
    };
  }
  return null;
}

function adapterForRun(store: AgentStore, run: AgentRun): AgentModelAdapter {
  const key = modelProfileKey(run);
  if (!key) return defaultTestAdapter();
  const profile = storedModelProfile(store, run.org_id, key);
  if (!profile) {
    return failingAdapter("MODEL_PROFILE_NOT_FOUND", `Model profile not found: ${key}`);
  }
  if (profile.enabled === false) {
    return failingAdapter("MODEL_PROFILE_DISABLED", `Model profile is disabled: ${key}`);
  }
  if (profile.provider === "test" || profile.model === "test") {
    return defaultTestAdapter();
  }

  const secretRef = profile.auth_secret?.secret_ref;
  const apiKey = secretRef ? store.getSecret(secretRef) : undefined;
  if (!apiKey) {
    return failingAdapter("MODEL_PROFILE_SECRET_MISSING", `Model profile has no API key: ${key}`);
  }

  return createSdkModelAdapter({
    provider: profile.provider,
    apiKey,
    model: profile.model ?? key,
    capabilities: profile.capabilities ?? null,
    metadata: profile.metadata ?? null,
  });
}

function createRunScheduler(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  capabilityRouter: ProductionCapabilityRouter;
  skillResolver: SkillResolver;
}) {
  const activeRuns = new Map<string, Promise<AgentRun | undefined>>();

  const failRun = (run: AgentRun, err: unknown): AgentRun | undefined => {
    const current = deps.store.getRun(run.id);
    if (!current || TERMINAL_RUN_STATUSES.has(current.status as any)) return current;
    const message = err instanceof Error ? err.message : "Model run failed";
    const failed = deps.store.updateRun(run.id, {
      status: "failed",
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
      error: { code: "MODEL_RUN_FAILED", message },
    });
    deps.eventWriter.write(run.id, run.thread_id ?? null, EVENT_TYPES.RUN_FAILED, {
      error: failed.error,
    });
    return failed;
  };

  const execute = async (
    runId: string,
    toolResults: AgentModelToolResult[] = [],
  ): Promise<AgentRun | undefined> => {
    const run = deps.store.getRun(runId);
    if (!run) return undefined;
    if (!modelProfileKey(run)) return run;
    if (run.status !== "queued") return run;

    try {
      const loop = new ModelTurnLoop({
        store: deps.store,
        eventWriter: deps.eventWriter,
        capabilityRouter: deps.capabilityRouter,
        modelAdapter: adapterForRun(deps.store, run),
        skillResolver: deps.skillResolver,
      });
      return await loop.execute(run, { toolResults });
    } catch (err) {
      return failRun(run, err);
    }
  };

  return (runOrId: AgentRun | string, options: ScheduleRunExecutionOptions = {}) => {
    const runId = typeof runOrId === "string" ? runOrId : runOrId.id;
    const run = typeof runOrId === "string" ? deps.store.getRun(runOrId) : runOrId;
    if (!run || !modelProfileKey(run)) return Promise.resolve(run);
    if (run.status !== "queued") return Promise.resolve(run);

    const existing = activeRuns.get(runId);
    if (existing) return options.wait ? existing : Promise.resolve(deps.store.getRun(runId));

    const task = execute(runId, options.toolResults ?? []).finally(() => activeRuns.delete(runId));
    activeRuns.set(runId, task);
    return options.wait ? task : Promise.resolve(deps.store.getRun(runId));
  };
}

export async function createRuntime(dbPath?: string): Promise<AgentRuntime> {
  if (_runtime) return _runtime;

  const useSqlite = dbPath || process.env.DB_PATH;
  const store: AgentStore = useSqlite
    ? await SqliteStore.create(useSqlite)
    : new InMemoryStore();

  const eventWriter = new AgentEventWriter(store);
  const skillRegistry = new SkillRegistry();
  const builtinRoot = findBuiltinSkillsRoot();
  if (builtinRoot) skillRegistry.loadBuiltinPackages(builtinRoot);
  const skillResolver = new SkillResolver(skillRegistry, store);
  const capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, skillResolver);
  const harness = new ScriptedHarnessCore({
    store,
    eventWriter,
    capabilityRouter,
  });
  const worker = new WorkerRunner({
    store,
    eventWriter,
    capabilityRouter,
  });
  const scheduleRunExecution = createRunScheduler({
    store,
    eventWriter,
    capabilityRouter,
    skillResolver,
  });
  const resolveApproval = createApprovalResolver({
    store,
    eventWriter,
    capabilityRouter,
    scheduleRunExecution,
  });

  _runtime = {
    store,
    eventWriter,
    capabilityRouter,
    harness,
    worker,
    skillResolver,
    scheduleRunExecution,
    resolveApproval,
  };
  return _runtime;
}

export function getRuntime(): AgentRuntime {
  if (!_runtime)
    throw new Error("Runtime not initialized. Call createRuntime() first.");
  return _runtime;
}

export function resetRuntimeForTests(): void {
  _runtime?.store.close();
  _runtime = null;
}
