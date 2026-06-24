import type { AgentModelProfileEntry } from "@/lib/api";

export type ModelProfileProvider = "test" | "openai" | "anthropic" | "custom";

export interface ModelProfileFormValues {
  key: string;
  name: string;
  provider: ModelProfileProvider;
  model: string;
  apiKey: string;
  baseUrl: string;
  vision: boolean;
  thinking: boolean;
  maxTotalTokens: string;
  maxRunCostUsd: string;
}

export function emptyModelProfileFormValues(): ModelProfileFormValues {
  return {
    key: "",
    name: "",
    provider: "openai",
    model: "",
    apiKey: "",
    baseUrl: "",
    vision: false,
    thinking: false,
    maxTotalTokens: "",
    maxRunCostUsd: "",
  };
}

export function buildModelProfileCreatePayload(
  values: ModelProfileFormValues,
): Record<string, unknown> {
  const provider = values.provider;
  const normalizedModel = normalizeModelName(provider, values.model);
  const payload: Record<string, unknown> = {
    key: values.key.trim() || inferProfileKey(provider, values.model),
    name: values.name.trim() || inferProfileName(values.model),
    provider,
    model: normalizedModel,
    enabled: true,
    capabilities: {
      vision: values.vision,
      thinking: values.thinking,
    },
    cost_policy: {},
    selection_policy: {
      required_scopes: [],
    },
  };

  const maxRunCostUsd = parseOptionalNumber(values.maxRunCostUsd);
  if (maxRunCostUsd !== undefined) {
    (payload.cost_policy as Record<string, unknown>).max_run_cost_usd = maxRunCostUsd;
  }

  const maxTotalTokens = parseOptionalInteger(values.maxTotalTokens);
  if (maxTotalTokens !== undefined) {
    (payload.selection_policy as Record<string, unknown>).max_total_tokens = maxTotalTokens;
  }

  const apiKey = values.apiKey.trim();
  if (apiKey) {
    payload.auth_secret = { write_only_value: apiKey };
  }

  const baseUrl = values.baseUrl.trim();
  if (baseUrl) {
    payload.metadata = { base_url: baseUrl };
  }

  return payload;
}

export function modelProfileFormValuesFromProfile(
  profile: AgentModelProfileEntry,
): ModelProfileFormValues {
  return {
    key: profile.key,
    name: profile.name,
    provider: profile.provider as ModelProfileProvider,
    model: profile.model,
    apiKey: "",
    baseUrl: metadataBaseUrl(profile.metadata),
    vision: profile.capabilities?.vision ?? false,
    thinking: profile.capabilities?.thinking ?? false,
    maxTotalTokens: formatOptionalNumber(profile.selection_policy?.max_total_tokens),
    maxRunCostUsd: formatOptionalNumber(profile.cost_policy?.max_run_cost_usd),
  };
}

export function buildModelProfileUpdatePayload(
  values: ModelProfileFormValues,
  originalProfile: AgentModelProfileEntry,
): Record<string, unknown> {
  const provider = values.provider;
  const normalizedModel = normalizeModelName(provider, values.model);
  const payload: Record<string, unknown> = {
    name: values.name.trim() || inferProfileName(values.model),
    provider,
    model: normalizedModel,
    capabilities: {
      vision: values.vision,
      thinking: values.thinking,
    },
    cost_policy: buildUpdatedCostPolicy(values, originalProfile),
    selection_policy: buildUpdatedSelectionPolicy(values, originalProfile),
    metadata: buildUpdatedMetadata(values, originalProfile),
  };

  const apiKey = values.apiKey.trim();
  if (apiKey) {
    payload.auth_secret = { write_only_value: apiKey };
  }

  return payload;
}

export function inferProfileKey(provider: ModelProfileProvider, rawModel: string): string {
  const model = stripKnownProviderPrefix(rawModel.trim()) || provider;
  return `${provider}-${slugify(model)}`;
}

export function inferProfileName(rawModel: string): string {
  const model = stripKnownProviderPrefix(rawModel.trim());
  return model ? humanizeModelName(model) : "New model";
}

function normalizeModelName(provider: ModelProfileProvider, rawModel: string): string {
  const model = rawModel.trim();
  if (
    !model ||
    hasKnownProviderPrefix(model)
  ) {
    return model;
  }
  return `${provider}:${model}`;
}

function stripKnownProviderPrefix(value: string): string {
  for (const prefix of ["test:", "openai:", "anthropic:", "custom:"]) {
    if (value.startsWith(prefix)) return value.slice(prefix.length);
  }
  return value;
}

function hasKnownProviderPrefix(value: string): boolean {
  return (
    value.startsWith("test:") ||
    value.startsWith("openai:") ||
    value.startsWith("anthropic:") ||
    value.startsWith("custom:")
  );
}

function slugify(value: string): string {
  const slug = stripKnownProviderPrefix(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
  return slug || "model";
}

function humanizeModelName(value: string): string {
  return stripKnownProviderPrefix(value)
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function parseOptionalNumber(raw: string): number | undefined {
  const value = raw.trim();
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseOptionalInteger(raw: string): number | undefined {
  const value = raw.trim();
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function buildUpdatedCostPolicy(
  values: ModelProfileFormValues,
  originalProfile: AgentModelProfileEntry,
): Record<string, unknown> {
  const costPolicy = { ...(originalProfile.cost_policy ?? {}) } as Record<string, unknown>;
  if (!values.maxRunCostUsd.trim()) {
    costPolicy.max_run_cost_usd = null;
    return costPolicy;
  }

  const maxRunCostUsd = parseOptionalNumber(values.maxRunCostUsd);
  if (maxRunCostUsd !== undefined) {
    costPolicy.max_run_cost_usd = maxRunCostUsd;
  }
  return costPolicy;
}

function buildUpdatedSelectionPolicy(
  values: ModelProfileFormValues,
  originalProfile: AgentModelProfileEntry,
): Record<string, unknown> {
  const selectionPolicy = { ...(originalProfile.selection_policy ?? {}) } as Record<
    string,
    unknown
  >;
  if (!values.maxTotalTokens.trim()) {
    selectionPolicy.max_total_tokens = null;
    return selectionPolicy;
  }

  const maxTotalTokens = parseOptionalInteger(values.maxTotalTokens);
  if (maxTotalTokens !== undefined) {
    selectionPolicy.max_total_tokens = maxTotalTokens;
  }
  return selectionPolicy;
}

function buildUpdatedMetadata(
  values: ModelProfileFormValues,
  originalProfile: AgentModelProfileEntry,
): Record<string, unknown> | null {
  const metadata = { ...(originalProfile.metadata ?? {}) } as Record<string, unknown>;
  const baseUrl = values.baseUrl.trim();
  if (baseUrl) {
    metadata.base_url = baseUrl;
  } else {
    delete metadata.base_url;
  }
  return Object.keys(metadata).length ? metadata : null;
}

function metadataBaseUrl(metadata: AgentModelProfileEntry["metadata"]): string {
  const baseUrl = metadata?.base_url;
  return typeof baseUrl === "string" ? baseUrl : "";
}

function formatOptionalNumber(value: number | null | undefined): string {
  return value == null ? "" : String(value);
}
