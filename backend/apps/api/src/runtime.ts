import { ProductionCapabilityRouter, type AgentToolDescriptor } from "@aithru-agent/capabilities";
import type { AgentRun } from "@aithru-agent/contracts";
import { TERMINAL_RUN_STATUSES } from "@aithru-agent/contracts";
import { ControlledWebProvider, McpCatalog, McpProviderAdapter, type McpServerConfig } from "@aithru-agent/external";
import { ModelTurnLoop, ScriptedHarnessCore } from "@aithru-agent/harness";
import { LocalMemoryProvider } from "@aithru-agent/memory";
import {
  TestModelAdapter,
  createSdkModelAdapter,
  type AgentModelAdapter,
  type AgentModelToolResult,
} from "@aithru-agent/model";
import { AgentEventWriter, EVENT_TYPES } from "@aithru-agent/stream";
import { InMemoryStore, SqliteStore, type AgentApproval, type AgentStore } from "@aithru-agent/persistence";
import { SkillRegistry, SkillResolver, findBuiltinSkillsRoot } from "@aithru-agent/skills";
import { SubagentRunner } from "@aithru-agent/subagents";
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
  cancelRun: (runId: string) => AgentRun | undefined;
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

type StoredExternalToolConfig = {
  id?: string;
  org_id?: string;
  key?: string;
  provider_kind?: string;
  enabled?: boolean;
  mcp?: {
    server_key?: string;
    name?: string;
    endpoint?: {
      url?: unknown;
      allowed_hosts?: unknown;
      timeout_ms?: unknown;
      max_response_bytes?: unknown;
      auth_secret?: {
        secret_ref?: unknown;
      } | null;
      headers?: unknown;
    } | null;
    stdio?: {
      command?: unknown;
      args?: unknown;
      timeout_ms?: unknown;
    } | null;
    tools?: unknown;
  } | null;
};

type StoredMcpEndpoint = NonNullable<NonNullable<StoredExternalToolConfig["mcp"]>["endpoint"]>;

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

function createControlledWebProviderFromEnv(): ControlledWebProvider | undefined {
  const allowedHosts = (process.env.AGENT_WEB_ALLOWED_HOSTS ?? process.env.WEB_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  if (!allowedHosts.length) return undefined;

  return new ControlledWebProvider({
    allowedHosts,
    searchEndpoint: process.env.AGENT_WEB_SEARCH_ENDPOINT ?? process.env.WEB_SEARCH_ENDPOINT,
    fetcher: async (url, init) => {
      const fetchImpl = globalThis.fetch;
      if (!fetchImpl) throw new Error("WEB_FETCH_NOT_AVAILABLE");
      const response = await fetchImpl(url, init);
      return {
        status: response.status,
        text: () => response.text(),
      };
    },
  });
}

function createStoreBackedMcpProvider(store: AgentStore) {
  return {
    listAvailableTools(): AgentToolDescriptor[] {
      return createMcpProviderAdapterFromStore(store).listAvailableTools();
    },
    executeTool(toolName: string, input: Record<string, unknown>): Promise<unknown> {
      return createMcpProviderAdapterFromStore(store).executeTool(toolName, input);
    },
  };
}

function createMcpProviderAdapterFromStore(store: AgentStore): McpProviderAdapter {
  const catalog = new McpCatalog();
  for (const doc of store.listDocuments("external_tool_config_entry")) {
    const server = mcpServerFromStoredConfig(store, doc.payload as StoredExternalToolConfig);
    if (server) catalog.register(server);
  }
  return new McpProviderAdapter(catalog);
}

function mcpServerFromStoredConfig(
  store: AgentStore,
  config: StoredExternalToolConfig,
): McpServerConfig | null {
  if (config.provider_kind !== "mcp" || config.enabled === false) return null;
  const mcp = config.mcp;
  if (!mcp) return null;

  const toolDescriptors = Array.isArray(mcp.tools)
    ? mcp.tools.map(mcpToolDescriptorFromConfig).filter((tool): tool is AgentToolDescriptor => Boolean(tool))
    : [];
  if (!toolDescriptors.length) return null;

  const id = stringValue(mcp.server_key) ?? stringValue(config.key) ?? stringValue(config.id);
  if (!id) return null;

  const endpoint = mcp.endpoint;
  const endpointUrl = stringValue(endpoint?.url);
  if (endpointUrl?.startsWith("http://") || endpointUrl?.startsWith("https://")) {
    if (!isAllowedMcpEndpoint(endpointUrl, endpoint?.allowed_hosts)) return null;
    return {
      id,
      transport: "http",
      enabled: true,
      toolDescriptors,
      http: {
        url: endpointUrl,
        headers: mcpEndpointHeaders(store, endpoint),
      },
    };
  }

  const command = stringValue(mcp.stdio?.command);
  if (command) {
    return {
      id,
      transport: "stdio",
      enabled: true,
      toolDescriptors,
      stdio: {
        command,
        args: stringArray(mcp.stdio?.args),
        timeoutMs: positiveInteger(mcp.stdio?.timeout_ms),
      },
    };
  }

  return null;
}

function mcpToolDescriptorFromConfig(value: unknown): AgentToolDescriptor | null {
  if (!isRecord(value)) return null;
  const name = stringValue(value.name);
  if (!name) return null;
  const riskLevel = mcpRiskLevel(value.risk_level);
  return {
    name,
    description: stringValue(value.description) ?? name,
    risk_level: riskLevel,
    requires_approval: mcpRequiresApproval(value, riskLevel),
    required_scopes: stringArray(value.required_scopes, ["mcp:use"]),
    input_schema: isRecord(value.input_schema) ? value.input_schema : {},
  };
}

function mcpRiskLevel(value: unknown): AgentToolDescriptor["risk_level"] {
  if (value === "low" || value === "read") return "low";
  if (value === "medium" || value === "write") return "medium";
  if (value === "high" || value === "dangerous") return "high";
  return "medium";
}

function mcpRequiresApproval(
  value: Record<string, unknown>,
  riskLevel: AgentToolDescriptor["risk_level"],
): boolean {
  if (typeof value.requires_approval === "boolean") return value.requires_approval;
  if (value.approval_policy === "never") return false;
  if (value.approval_policy === "always" || value.approval_policy === "on_risk") return true;
  return riskLevel !== "low";
}

function isAllowedMcpEndpoint(url: string, allowedHosts: unknown): boolean {
  const hosts = stringArray(allowedHosts).map((host) => host.toLowerCase());
  if (!hosts.length) return true;
  try {
    return hosts.includes(new URL(url).hostname.toLowerCase());
  } catch {
    return false;
  }
}

function mcpEndpointHeaders(
  store: AgentStore,
  endpoint: StoredMcpEndpoint | undefined | null,
): Record<string, string> | undefined {
  if (!isRecord(endpoint)) return undefined;
  const headers: Record<string, string> = {};
  if (isRecord(endpoint.headers)) {
    for (const [key, value] of Object.entries(endpoint.headers)) {
      if (typeof value === "string") headers[key] = value;
    }
  }
  const secretRef = isRecord(endpoint.auth_secret) ? stringValue(endpoint.auth_secret.secret_ref) : undefined;
  const secret = secretRef ? store.getSecret(secretRef) : undefined;
  if (secret && !Object.keys(headers).some((key) => key.toLowerCase() === "authorization")) {
    headers.authorization = `Bearer ${secret}`;
  }
  return Object.keys(headers).length ? headers : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function stringArray(value: unknown, fallback: string[] = []): string[] {
  return Array.isArray(value)
    ? value
      .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      .map((item) => item.trim())
    : fallback;
}

function positiveInteger(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) return undefined;
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function createRunScheduler(deps: {
  store: AgentStore;
  eventWriter: AgentEventWriter;
  capabilityRouter: ProductionCapabilityRouter;
  skillResolver: SkillResolver;
}) {
  const activeRuns = new Map<string, { promise: Promise<AgentRun | undefined>; abortController: AbortController }>();

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
    signal?: AbortSignal,
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
      return await loop.execute(run, { toolResults, signal });
    } catch (err) {
      return failRun(run, err);
    }
  };

  const schedule = (runOrId: AgentRun | string, options: ScheduleRunExecutionOptions = {}) => {
    const runId = typeof runOrId === "string" ? runOrId : runOrId.id;
    const run = typeof runOrId === "string" ? deps.store.getRun(runOrId) : runOrId;
    if (!run || !modelProfileKey(run)) return Promise.resolve(run);
    if (run.status !== "queued") return Promise.resolve(run);

    const existing = activeRuns.get(runId);
    if (existing) return options.wait ? existing.promise : Promise.resolve(deps.store.getRun(runId));

    const abortController = new AbortController();
    const task = execute(runId, options.toolResults ?? [], abortController.signal).finally(() => activeRuns.delete(runId));
    activeRuns.set(runId, { promise: task, abortController });
    return options.wait ? task : Promise.resolve(deps.store.getRun(runId));
  };

  const cancel = (runId: string): AgentRun | undefined => {
    const run = deps.store.getRun(runId);
    if (!run) return undefined;
    activeRuns.get(runId)?.abortController.abort();
    if (TERMINAL_RUN_STATUSES.has(run.status as any)) return run;
    const cancelled = deps.store.updateRun(runId, {
      status: "cancelled",
      current_approval_id: null,
      completed_at: new Date().toISOString().replace(/\.\d{3}/, ""),
    });
    if (!deps.store.listEvents(runId).some((event) => event.type === EVENT_TYPES.RUN_CANCELLED)) {
      deps.eventWriter.write(runId, run.thread_id ?? null, EVENT_TYPES.RUN_CANCELLED, { run_id: runId });
    }
    return cancelled;
  };

  return { schedule, cancel };
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
  const webProvider = createControlledWebProviderFromEnv();
  let capabilityRouter!: ProductionCapabilityRouter;
  capabilityRouter = new ProductionCapabilityRouter(store, eventWriter, skillResolver, {
    memoryProvider: new LocalMemoryProvider(),
    mcpProvider: createStoreBackedMcpProvider(store),
    ...(webProvider ? { webProvider } : {}),
    subagentDelegate: (parentRun, spec) =>
      new SubagentRunner(store, eventWriter, capabilityRouter, {
        modelAdapterFactory: (run) => adapterForRun(store, run),
        skillResolver,
      }).delegate(parentRun, spec),
  });
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
  const runScheduler = createRunScheduler({
    store,
    eventWriter,
    capabilityRouter,
    skillResolver,
  });
  const resolveApproval = createApprovalResolver({
    store,
    eventWriter,
    capabilityRouter,
    scheduleRunExecution: runScheduler.schedule,
  });

  _runtime = {
    store,
    eventWriter,
    capabilityRouter,
    harness,
    worker,
    skillResolver,
    scheduleRunExecution: runScheduler.schedule,
    cancelRun: runScheduler.cancel,
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
