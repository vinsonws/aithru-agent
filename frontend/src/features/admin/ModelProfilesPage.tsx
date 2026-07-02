import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { modelProvidersApi } from "@/lib/api";
import type { AgentModelProviderWithModels } from "@/lib/api";
import { modelRef } from "@/features/chat/composerState";
import { useTranslation } from "react-i18next";
import {
  buildCustomProviderPayload,
  buildModelPayload,
  deepSeekPresetModels,
  deepSeekPresetProvider,
  slugifyModelKey,
  type CustomProviderFormValues,
  type ModelFormValues,
} from "./modelProfileForm";

type CreateMode = "deepseek" | "custom" | null;

function emptyCustomProvider(): CustomProviderFormValues {
  return { key: "", name: "", baseUrl: "", apiKey: "" };
}

function emptyModel(): ModelFormValues {
  return {
    key: "",
    name: "",
    providerModelId: "",
    thinking: true,
    vision: false,
  };
}

function enabledModelCount(provider: AgentModelProviderWithModels): number {
  return (provider.models ?? []).filter((model) => model.enabled !== false)
    .length;
}

/** Kept for import stability while the settings tab stays provider-first. */
export function ModelProfilesContent() {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();
  const [createMode, setCreateMode] = React.useState<CreateMode>(null);
  const [deepSeekApiKey, setDeepSeekApiKey] = React.useState("");
  const [customProvider, setCustomProvider] =
    React.useState<CustomProviderFormValues>(emptyCustomProvider());
  const [customModels, setCustomModels] = React.useState<ModelFormValues[]>([
    emptyModel(),
  ]);
  const [selectedProviderKey, setSelectedProviderKey] =
    React.useState<string>("");

  const providersQuery = useQuery({
    queryKey: ["model-providers"],
    queryFn: modelProvidersApi.list,
  });

  React.useEffect(() => {
    const providers = providersQuery.data ?? [];
    if (!providers.length) {
      setSelectedProviderKey("");
      return;
    }
    if (
      selectedProviderKey &&
      providers.some((provider) => provider.key === selectedProviderKey)
    ) {
      return;
    }
    setSelectedProviderKey(providers[0]?.key ?? "");
  }, [providersQuery.data, selectedProviderKey]);

  const resetCreateForms = React.useCallback(() => {
    setCreateMode(null);
    setDeepSeekApiKey("");
    setCustomProvider(emptyCustomProvider());
    setCustomModels([emptyModel()]);
  }, []);

  const invalidateProviders = React.useCallback(
    async (preferredProviderKey?: string) => {
      await qc.invalidateQueries({ queryKey: ["model-providers"] });
      if (preferredProviderKey) setSelectedProviderKey(preferredProviderKey);
    },
    [qc],
  );

  const createDeepSeekMutation = useMutation({
    mutationFn: async (apiKey: string) => {
      const provider = deepSeekPresetProvider(apiKey);
      await modelProvidersApi.create(provider);
      for (const model of deepSeekPresetModels()) {
        await modelProvidersApi.createModel(provider.key, model);
      }
      return provider.key;
    },
    onSuccess: async (providerKey) => {
      resetCreateForms();
      await invalidateProviders(providerKey);
    },
  });

  const createCustomMutation = useMutation({
    mutationFn: async ({
      provider,
      models,
    }: {
      provider: CustomProviderFormValues;
      models: ModelFormValues[];
    }) => {
      const providerPayload = buildCustomProviderPayload(provider);
      await modelProvidersApi.create(providerPayload);
      for (const model of models) {
        await modelProvidersApi.createModel(
          providerPayload.key,
          buildModelPayload(model),
        );
      }
      return providerPayload.key;
    },
    onSuccess: async (providerKey) => {
      resetCreateForms();
      await invalidateProviders(providerKey);
    },
  });

  const patchProviderMutation = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      modelProvidersApi.patch(key, { enabled }),
    onSuccess: async () => {
      await invalidateProviders();
    },
  });

  const patchModelMutation = useMutation({
    mutationFn: ({
      providerKey,
      modelKey,
      enabled,
    }: {
      providerKey: string;
      modelKey: string;
      enabled: boolean;
    }) => modelProvidersApi.patchModel(providerKey, modelKey, { enabled }),
    onSuccess: async () => {
      await invalidateProviders();
    },
  });

  const defaultMutation = useMutation({
    mutationFn: (nextModelRef: string) =>
      modelProvidersApi.setDefault({ model_ref: nextModelRef }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["model-default"] });
      await invalidateProviders();
    },
  });

  if (providersQuery.isLoading) return <LoadingState />;
  if (providersQuery.isError) {
    return (
      <ErrorState
        error={providersQuery.error}
        onRetry={() => providersQuery.refetch()}
      />
    );
  }

  const providers = providersQuery.data ?? [];
  const selectedProvider =
    providers.find((provider) => provider.key === selectedProviderKey) ??
    providers[0] ??
    null;
  const defaultModelRef =
    providers.find((provider) => provider.default_model_ref)
      ?.default_model_ref ?? "";
  const createError =
    createDeepSeekMutation.error ??
    createCustomMutation.error ??
    patchProviderMutation.error;

  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-background/80 p-4 shadow-sm shadow-slate-900/5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">{t("models")}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("modelsDescription")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={createMode === "deepseek" ? "secondary" : "outline"}
              onClick={() =>
                setCreateMode((value) =>
                  value === "deepseek" ? null : "deepseek",
                )
              }
            >
              DeepSeek
            </Button>
            <Button
              type="button"
              size="sm"
              variant={createMode === "custom" ? "secondary" : "outline"}
              onClick={() =>
                setCreateMode((value) => (value === "custom" ? null : "custom"))
              }
            >
              OpenAI-compatible
            </Button>
          </div>
        </div>
        {providers.length === 0 && (
          <p className="mt-3 text-sm text-muted-foreground">
            {t("noProviders")}
          </p>
        )}
        {createMode === "deepseek" && (
          <form
            className="mt-4 grid gap-3 rounded-md border bg-muted/15 p-3 sm:grid-cols-[minmax(0,1fr)_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              createDeepSeekMutation.mutate(deepSeekApiKey);
            }}
          >
            <Field label={t("apiKey")}>
              <Input
                type="password"
                value={deepSeekApiKey}
                onChange={(event) => setDeepSeekApiKey(event.target.value)}
                placeholder="sk-..."
              />
            </Field>
            <div className="flex items-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={resetCreateForms}
              >
                {t("cancel")}
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={createDeepSeekMutation.isPending}
              >
                {createDeepSeekMutation.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                {t("addProvider")}
              </Button>
            </div>
          </form>
        )}
        {createMode === "custom" && (
          <form
            className="mt-4 space-y-4 rounded-md border bg-muted/15 p-3"
            onSubmit={(event) => {
              event.preventDefault();
              createCustomMutation.mutate({
                provider: customProvider,
                models: customModels,
              });
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("providerKey")}>
                <Input
                  value={customProvider.key}
                  onChange={(event) =>
                    setCustomProvider((current) => ({
                      ...current,
                      key: event.target.value,
                    }))
                  }
                  placeholder="my-gateway"
                />
              </Field>
              <Field label={t("providerName")}>
                <Input
                  value={customProvider.name}
                  onChange={(event) =>
                    setCustomProvider((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                  placeholder="My Gateway"
                />
              </Field>
              <Field label={t("baseUrl")}>
                <Input
                  required
                  value={customProvider.baseUrl}
                  onChange={(event) =>
                    setCustomProvider((current) => ({
                      ...current,
                      baseUrl: event.target.value,
                    }))
                  }
                  placeholder="https://gateway.example/v1"
                />
              </Field>
              <Field label={t("apiKey")}>
                <Input
                  type="password"
                  value={customProvider.apiKey}
                  onChange={(event) =>
                    setCustomProvider((current) => ({
                      ...current,
                      apiKey: event.target.value,
                    }))
                  }
                  placeholder="sk-..."
                />
              </Field>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h4 className="text-sm font-semibold">{t("models")}</h4>
                  <p className="text-xs text-muted-foreground">
                    {t("modelsHelp")}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setCustomModels((current) => [...current, emptyModel()])
                  }
                >
                  <Plus className="h-4 w-4" />
                  {t("addModel")}
                </Button>
              </div>
              {customModels.map((model, index) => (
                <div
                  key={index}
                  className="rounded-md border bg-background p-3"
                >
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label={t("modelId")}>
                      <Input
                        required
                        value={model.providerModelId}
                        onChange={(event) =>
                          setCustomModels((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index
                                ? {
                                    ...entry,
                                    providerModelId: event.target.value,
                                    key:
                                      entry.key ||
                                      slugifyModelKey(event.target.value),
                                  }
                                : entry,
                            ),
                          )
                        }
                        placeholder="qwen3-coder"
                      />
                    </Field>
                    <Field label={t("modelKey")}>
                      <Input
                        value={model.key}
                        onChange={(event) =>
                          setCustomModels((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index
                                ? { ...entry, key: event.target.value }
                                : entry,
                            ),
                          )
                        }
                        placeholder={slugifyModelKey(model.providerModelId)}
                      />
                    </Field>
                    <Field label={t("modelName")}>
                      <Input
                        value={model.name}
                        onChange={(event) =>
                          setCustomModels((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index
                                ? { ...entry, name: event.target.value }
                                : entry,
                            ),
                          )
                        }
                        placeholder="Qwen3 Coder"
                      />
                    </Field>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap gap-4">
                      <ToggleField
                        label={t("thinking")}
                        checked={model.thinking}
                        onCheckedChange={(checked) =>
                          setCustomModels((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index
                                ? { ...entry, thinking: checked }
                                : entry,
                            ),
                          )
                        }
                      />
                      <ToggleField
                        label={t("vision")}
                        checked={model.vision}
                        onCheckedChange={(checked) =>
                          setCustomModels((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index
                                ? { ...entry, vision: checked }
                                : entry,
                            ),
                          )
                        }
                      />
                    </div>
                    {customModels.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setCustomModels((current) =>
                            current.filter(
                              (_, entryIndex) => entryIndex !== index,
                            ),
                          )
                        }
                      >
                        {t("removeModel")}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={resetCreateForms}
              >
                {t("cancel")}
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={createCustomMutation.isPending}
              >
                {createCustomMutation.isPending && (
                  <Loader2 className="h-4 w-4 animate-spin" />
                )}
                {t("addProvider")}
              </Button>
            </div>
          </form>
        )}
        {createError instanceof Error && (
          <p className="mt-3 text-xs text-destructive">{createError.message}</p>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <section className="rounded-lg border bg-background/80 shadow-sm shadow-slate-900/5">
          <div className="border-b px-4 py-3">
            <h3 className="text-sm font-semibold">
              {t("configuredProviders")}
            </h3>
          </div>
          <div className="divide-y">
            {providers.length === 0 ? (
              <div className="px-4 py-6 text-sm text-muted-foreground">
                {t("noProviders")}
              </div>
            ) : (
              providers.map((provider) => {
                const isSelected = provider.key === selectedProvider?.key;
                const count = enabledModelCount(provider);
                return (
                  <button
                    key={provider.key}
                    type="button"
                    onClick={() => setSelectedProviderKey(provider.key)}
                    className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm ${
                      isSelected ? "bg-secondary/70" : "hover:bg-muted/40"
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium">
                        {provider.name}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {provider.key}
                      </span>
                    </span>
                    <div className="flex items-center gap-2">
                      {provider.enabled !== false ? (
                        <Badge variant="success">{t("enabled")}</Badge>
                      ) : (
                        <Badge variant="outline">{t("disabled")}</Badge>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {t("enabledModelCount", { count })}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="rounded-lg border bg-background/80 shadow-sm shadow-slate-900/5">
          {selectedProvider ? (
            <div className="space-y-4 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold">
                    {selectedProvider.name}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {selectedProvider.key}
                  </p>
                </div>
                <ToggleField
                  label={t("enabled")}
                  checked={selectedProvider.enabled !== false}
                  onCheckedChange={(checked) =>
                    patchProviderMutation.mutate({
                      key: selectedProvider.key,
                      enabled: checked,
                    })
                  }
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <ReadOnlyField
                  label={t("providerName")}
                  value={selectedProvider.name}
                />
                <ReadOnlyField
                  label={t("providerKey")}
                  value={selectedProvider.key}
                  mono
                />
                <ReadOnlyField
                  label={t("kind")}
                  value={selectedProvider.kind}
                  mono
                />
                <ReadOnlyField
                  label={t("baseUrl")}
                  value={selectedProvider.base_url || t("notSet")}
                  mono
                />
              </div>
              <div className="flex flex-wrap gap-2">
                {selectedProvider.compat && (
                  <Badge variant="secondary">{selectedProvider.compat}</Badge>
                )}
                {selectedProvider.auth_secret?.has_secret ? (
                  <Badge variant="accent">{t("apiKeyConfigured")}</Badge>
                ) : (
                  <Badge variant="outline">{t("apiKeyMissing")}</Badge>
                )}
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold">{t("models")}</h4>
                  <span className="text-xs text-muted-foreground">
                    {t("enabledModelCount", {
                      count: enabledModelCount(selectedProvider),
                    })}
                  </span>
                </div>
                <div className="space-y-2">
                  {selectedProvider.models.length === 0 ? (
                    <div className="rounded-md border border-dashed px-3 py-4 text-sm text-muted-foreground">
                      {t("noModels")}
                    </div>
                  ) : (
                    selectedProvider.models.map((model) => {
                      const ref = modelRef(selectedProvider.key, model.key);
                      const isDefault = defaultModelRef === ref;
                      return (
                        <div
                          key={model.key}
                          className="flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium">{model.name}</span>
                              {isDefault && (
                                <Badge variant="accent">
                                  {t("defaultModel")}
                                </Badge>
                              )}
                              {model.capabilities?.thinking && (
                                <Badge variant="secondary">
                                  {t("thinking")}
                                </Badge>
                              )}
                              {model.capabilities?.vision && (
                                <Badge variant="secondary">{t("vision")}</Badge>
                              )}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              <span className="font-mono">
                                {model.provider_model_id}
                              </span>
                              <span className="mx-2">•</span>
                              <span className="font-mono">{ref}</span>
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <ToggleField
                              label={t("enabled")}
                              checked={model.enabled !== false}
                              onCheckedChange={(checked) =>
                                patchModelMutation.mutate({
                                  providerKey: selectedProvider.key,
                                  modelKey: model.key,
                                  enabled: checked,
                                })
                              }
                            />
                            <Button
                              type="button"
                              size="sm"
                              variant={isDefault ? "secondary" : "outline"}
                              disabled={isDefault || defaultMutation.isPending}
                              onClick={() => defaultMutation.mutate(ref)}
                            >
                              {defaultMutation.isPending &&
                                defaultMutation.variables === ref && (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                )}
                              {t("setDefault")}
                            </Button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="px-4 py-10 text-sm text-muted-foreground">
              {t("noProviders")}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Label className="space-y-1.5">
      <span>{label}</span>
      {children}
    </Label>
  );
}

function ReadOnlyField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-md border bg-muted/15 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={`mt-1 text-sm ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}

function ToggleField({
  label,
  checked,
  onCheckedChange,
}: {
  label: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
      <span>{label}</span>
    </label>
  );
}
