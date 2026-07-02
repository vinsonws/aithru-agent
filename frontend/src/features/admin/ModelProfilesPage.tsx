import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { modelProvidersApi } from "@/lib/api";
import type { AgentModelProviderWithModels } from "@/lib/api";
import { modelRef } from "@/features/chat/composerState";
import { useTranslation } from "react-i18next";
import {
  buildCustomProviderPayload,
  buildModelPayload,
  deepSeekPresetModelValues,
  deepSeekPresetProvider,
  slugifyModelKey,
  type CustomProviderFormValues,
  type ModelFormValues,
} from "./modelProfileForm";

type ProviderTemplateId = "deepseek" | "custom";
type WizardStep = "provider" | "models";

function emptyCustomProvider(): CustomProviderFormValues {
  return { key: "", name: "", baseUrl: "", apiKey: "" };
}

function emptyModel(): ModelFormValues {
  return {
    key: "",
    name: "",
    providerModelId: "",
    contextWindowTokens: "",
    requestJson: "",
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
  const [wizardOpen, setWizardOpen] = React.useState(false);
  const [wizardStep, setWizardStep] = React.useState<WizardStep>("provider");
  const [selectedTemplate, setSelectedTemplate] =
    React.useState<ProviderTemplateId | null>(null);
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
    setWizardOpen(false);
    setWizardStep("provider");
    setSelectedTemplate(null);
    setCustomProvider(emptyCustomProvider());
    setCustomModels([emptyModel()]);
  }, []);

  const openCreateWizard = React.useCallback(() => {
    setWizardOpen(true);
    setWizardStep("provider");
    setSelectedTemplate(null);
    setCustomProvider(emptyCustomProvider());
    setCustomModels([emptyModel()]);
  }, []);

  const selectProviderTemplate = React.useCallback((template: ProviderTemplateId) => {
    setSelectedTemplate(template);
    setWizardStep("provider");
    if (template === "deepseek") {
      setCustomProvider({
        key: "deepseek",
        name: "DeepSeek",
        baseUrl: "https://api.deepseek.com",
        apiKey: "",
      });
      setCustomModels(deepSeekPresetModelValues());
      return;
    }
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

  const createProviderMutation = useMutation({
    mutationFn: async ({
      template,
      provider,
      models,
    }: {
      template: ProviderTemplateId;
      provider: CustomProviderFormValues;
      models: ModelFormValues[];
    }) => {
      const providerPayload =
        template === "deepseek"
          ? {
              ...deepSeekPresetProvider(provider.apiKey),
              key: slugifyModelKey(provider.key),
              name: provider.name.trim() || provider.key.trim(),
              base_url: provider.baseUrl.trim(),
            }
          : buildCustomProviderPayload(provider);
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
    createProviderMutation.error ??
    patchProviderMutation.error;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <section className="rounded-lg border bg-background/80 shadow-sm shadow-slate-900/5">
          <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
            <h3 className="text-sm font-semibold">
              {t("configuredProviders")}
            </h3>
            <Button
              type="button"
              size="icon"
              variant={wizardOpen ? "secondary" : "ghost"}
              aria-label={t("addProvider")}
              onClick={openCreateWizard}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
          <div className="divide-y">
            {providers.length === 0 ? (
              <div className="px-4 py-6 text-sm text-muted-foreground">
                {t("noProviders")}
              </div>
            ) : (
              providers.map((provider) => {
                const isSelected =
                  !wizardOpen && provider.key === selectedProvider?.key;
                const count = enabledModelCount(provider);
                return (
                  <button
                    key={provider.key}
                    type="button"
                    onClick={() => {
                      setWizardOpen(false);
                      setSelectedProviderKey(provider.key);
                    }}
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
          {wizardOpen ? (
            <AddProviderWizard
              step={wizardStep}
              selectedTemplate={selectedTemplate}
              provider={customProvider}
              models={customModels}
              error={createError}
              pending={createProviderMutation.isPending}
              onSelectTemplate={selectProviderTemplate}
              onProviderChange={setCustomProvider}
              onModelsChange={setCustomModels}
              onStepChange={setWizardStep}
              onCancel={resetCreateForms}
              onSubmit={() => {
                if (!selectedTemplate) return;
                createProviderMutation.mutate({
                  template: selectedTemplate,
                  provider: customProvider,
                  models: customModels,
                });
              }}
            />
          ) : selectedProvider ? (
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
                            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                              <span
                                className="min-w-0 max-w-full truncate font-mono"
                                title={model.provider_model_id}
                              >
                                {model.provider_model_id}
                              </span>
                              <span>•</span>
                              <span
                                className="min-w-0 max-w-full truncate font-mono"
                                title={ref}
                              >
                                {ref}
                              </span>
                            </div>
                            {model.context_window_tokens && (
                              <div className="mt-1 text-xs text-muted-foreground">
                                {t("maxContextValue", {
                                  count: model.context_window_tokens,
                                })}
                              </div>
                            )}
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

function AddProviderWizard({
  step,
  selectedTemplate,
  provider,
  models,
  error,
  pending,
  onSelectTemplate,
  onProviderChange,
  onModelsChange,
  onStepChange,
  onCancel,
  onSubmit,
}: {
  step: WizardStep;
  selectedTemplate: ProviderTemplateId | null;
  provider: CustomProviderFormValues;
  models: ModelFormValues[];
  error: unknown;
  pending: boolean;
  onSelectTemplate: (template: ProviderTemplateId) => void;
  onProviderChange: React.Dispatch<React.SetStateAction<CustomProviderFormValues>>;
  onModelsChange: React.Dispatch<React.SetStateAction<ModelFormValues[]>>;
  onStepChange: (step: WizardStep) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const { t } = useTranslation("settings");
  const providerReady =
    Boolean(selectedTemplate) &&
    provider.key.trim().length > 0 &&
    provider.baseUrl.trim().length > 0;
  const modelsReady = models.length > 0 && models.every((model) => model.providerModelId.trim());

  function updateModel(index: number, patch: Partial<ModelFormValues>) {
    onModelsChange((current) =>
      current.map((entry, entryIndex) =>
        entryIndex === index ? { ...entry, ...patch } : entry,
      ),
    );
  }

  return (
    <form
      className="grid min-h-[560px] lg:grid-cols-[260px_minmax(0,1fr)]"
      onSubmit={(event) => {
        event.preventDefault();
        if (step === "provider") {
          if (providerReady) onStepChange("models");
          return;
        }
        if (providerReady && modelsReady) onSubmit();
      }}
    >
      <aside className="border-b p-4 lg:border-b-0 lg:border-r">
        <h3 className="text-sm font-semibold">{t("providerTemplate")}</h3>
        <div className="mt-3 space-y-2">
          <TemplateButton
            title="DeepSeek"
            description={t("officialProvider")}
            selected={selectedTemplate === "deepseek"}
            onClick={() => onSelectTemplate("deepseek")}
          />
          <TemplateButton
            title="OpenAI-compatible"
            description={t("customEndpoint")}
            selected={selectedTemplate === "custom"}
            onClick={() => onSelectTemplate("custom")}
          />
        </div>
      </aside>

      <div className="min-w-0 p-4">
        {!selectedTemplate ? (
          <div className="flex h-full min-h-[360px] items-center justify-center rounded-md border border-dashed px-6 text-center text-sm text-muted-foreground">
            {t("chooseProviderTemplate")}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold">{t("addProvider")}</h3>
                <p className="text-sm text-muted-foreground">
                  {step === "provider" ? t("providerStep") : t("modelStep")}
                </p>
              </div>
              <div className="flex gap-2">
                <Badge variant={step === "provider" ? "accent" : "secondary"}>
                  {t("provider")}
                </Badge>
                <Badge variant={step === "models" ? "accent" : "secondary"}>
                  {t("models")}
                </Badge>
              </div>
            </div>

            {step === "provider" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={t("providerKey")}>
                  <Input
                    required
                    value={provider.key}
                    onChange={(event) =>
                      onProviderChange((current) => ({
                        ...current,
                        key: event.target.value,
                      }))
                    }
                    placeholder="my-gateway"
                  />
                </Field>
                <Field label={t("providerName")}>
                  <Input
                    value={provider.name}
                    onChange={(event) =>
                      onProviderChange((current) => ({
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
                    value={provider.baseUrl}
                    onChange={(event) =>
                      onProviderChange((current) => ({
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
                    value={provider.apiKey}
                    onChange={(event) =>
                      onProviderChange((current) => ({
                        ...current,
                        apiKey: event.target.value,
                      }))
                    }
                    placeholder="sk-..."
                  />
                </Field>
              </div>
            ) : (
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
                      onModelsChange((current) => [...current, emptyModel()])
                    }
                  >
                    <Plus className="h-4 w-4" />
                    {t("addModel")}
                  </Button>
                </div>

                {models.map((model, index) => (
                  <div key={index} className="rounded-md border bg-background p-3">
                    <div className="grid gap-3 sm:grid-cols-3">
                      <Field label={t("modelId")}>
                        <Input
                          required
                          value={model.providerModelId}
                          onChange={(event) =>
                            updateModel(index, {
                              providerModelId: event.target.value,
                              key:
                                model.key ||
                                slugifyModelKey(event.target.value),
                            })
                          }
                          placeholder="qwen3-coder"
                        />
                      </Field>
                      <Field label={t("modelKey")}>
                        <Input
                          value={model.key}
                          onChange={(event) =>
                            updateModel(index, { key: event.target.value })
                          }
                          placeholder={slugifyModelKey(model.providerModelId)}
                        />
                      </Field>
                      <Field label={t("modelName")}>
                        <Input
                          value={model.name}
                          onChange={(event) =>
                            updateModel(index, { name: event.target.value })
                          }
                          placeholder="Qwen3 Coder"
                        />
                      </Field>
                      <Field label={t("maxContext")}>
                        <Input
                          type="number"
                          min={1}
                          value={model.contextWindowTokens}
                          onChange={(event) =>
                            updateModel(index, {
                              contextWindowTokens: event.target.value,
                            })
                          }
                          placeholder="128000"
                        />
                      </Field>
                      <div className="flex items-end gap-4 pb-1 sm:col-span-2">
                        <ToggleField
                          label={t("thinking")}
                          checked={model.thinking}
                          onCheckedChange={(checked) =>
                            updateModel(index, { thinking: checked })
                          }
                        />
                        <ToggleField
                          label={t("vision")}
                          checked={model.vision}
                          onCheckedChange={(checked) =>
                            updateModel(index, { vision: checked })
                          }
                        />
                        {models.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              onModelsChange((current) =>
                                current.filter((_, entryIndex) => entryIndex !== index),
                              )
                            }
                          >
                            {t("removeModel")}
                          </Button>
                        )}
                      </div>
                      <div className="sm:col-span-3">
                        <Field label={t("requestParameters")}>
                          <Textarea
                            className="min-h-[96px] font-mono"
                            value={model.requestJson}
                            onChange={(event) =>
                              updateModel(index, {
                                requestJson: event.target.value,
                              })
                            }
                            placeholder='{"max_tokens":8192,"temperature":0.7}'
                          />
                        </Field>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {error instanceof Error && (
              <p className="text-xs text-destructive">{error.message}</p>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={
                  step === "models" ? () => onStepChange("provider") : onCancel
                }
              >
                {step === "models" ? t("back") : t("cancel")}
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={
                  pending ||
                  !providerReady ||
                  (step === "models" && !modelsReady)
                }
              >
                {pending && <Loader2 className="h-4 w-4 animate-spin" />}
                {step === "models" ? t("confirm") : t("next")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </form>
  );
}

function TemplateButton({
  title,
  description,
  selected,
  onClick,
}: {
  title: string;
  description: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
        selected ? "border-primary bg-primary/10" : "hover:bg-muted/40"
      }`}
    >
      <span className="block font-medium">{title}</span>
      <span className="mt-1 block text-xs text-muted-foreground">
        {description}
      </span>
    </button>
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
    <div className="min-w-0 rounded-md border bg-muted/15 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div
        className={`mt-1 truncate text-sm ${mono ? "font-mono" : ""}`}
        title={value}
      >
        {value}
      </div>
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
