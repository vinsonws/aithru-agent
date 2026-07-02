export interface CustomProviderFormValues {
  key: string;
  name: string;
  baseUrl: string;
  apiKey: string;
}

export interface ModelFormValues {
  key: string;
  name: string;
  providerModelId: string;
  contextWindowTokens: string;
  requestJson: string;
  thinking: boolean;
  vision: boolean;
}

export function slugifyModelKey(value: string): string {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "model"
  );
}

export function deepSeekPresetProvider(apiKey: string) {
  return {
    key: "deepseek",
    name: "DeepSeek",
    kind: "openai_compatible" as const,
    enabled: true,
    base_url: "https://api.deepseek.com",
    compat: "deepseek" as const,
    ...(apiKey.trim()
      ? { auth_secret: { write_only_value: apiKey.trim() } }
      : {}),
  };
}

function optionalPositiveInteger(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error("Max context must be a positive integer");
  }
  return parsed;
}

function optionalRequestJson(value: string): Record<string, unknown> | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error("Request parameters must be a valid JSON object");
  }
  if (parsed == null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Request parameters must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

export function buildModelPayload(values: ModelFormValues) {
  const contextWindowTokens = optionalPositiveInteger(values.contextWindowTokens);
  const request = optionalRequestJson(values.requestJson);
  return {
    key: slugifyModelKey(values.key || values.providerModelId),
    name: values.name.trim() || values.providerModelId.trim(),
    provider_model_id: values.providerModelId.trim(),
    enabled: true,
    capabilities: { thinking: values.thinking, vision: values.vision },
    ...(contextWindowTokens ? { context_window_tokens: contextWindowTokens } : {}),
    ...(request ? { request } : {}),
  };
}

export function deepSeekPresetModelValues(): ModelFormValues[] {
  return [
    {
      key: "deepseek-v4-flash",
      name: "DeepSeek V4 Flash",
      providerModelId: "deepseek-v4-flash",
      contextWindowTokens: "",
      requestJson: "",
      thinking: true,
      vision: false,
    },
    {
      key: "deepseek-v4-pro",
      name: "DeepSeek V4 Pro",
      providerModelId: "deepseek-v4-pro",
      contextWindowTokens: "",
      requestJson: "",
      thinking: true,
      vision: false,
    },
  ];
}

export function deepSeekPresetModels() {
  return deepSeekPresetModelValues().map(buildModelPayload);
}

export function buildCustomProviderPayload(values: CustomProviderFormValues) {
  return {
    key: slugifyModelKey(values.key),
    name: values.name.trim() || values.key.trim(),
    kind: "openai_compatible" as const,
    enabled: true,
    base_url: values.baseUrl.trim(),
    compat: null,
    ...(values.apiKey.trim()
      ? { auth_secret: { write_only_value: values.apiKey.trim() } }
      : {}),
  };
}
