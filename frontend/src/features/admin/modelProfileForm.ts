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

export function buildModelPayload(values: ModelFormValues) {
  return {
    key: slugifyModelKey(values.key || values.providerModelId),
    name: values.name.trim() || values.providerModelId.trim(),
    provider_model_id: values.providerModelId.trim(),
    enabled: true,
    capabilities: { thinking: values.thinking, vision: values.vision },
  };
}

export function deepSeekPresetModels() {
  return [
    buildModelPayload({
      key: "deepseek-v4-flash",
      name: "DeepSeek V4 Flash",
      providerModelId: "deepseek-v4-flash",
      thinking: true,
      vision: false,
    }),
    buildModelPayload({
      key: "deepseek-v4-pro",
      name: "DeepSeek V4 Pro",
      providerModelId: "deepseek-v4-pro",
      thinking: true,
      vision: false,
    }),
  ];
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
