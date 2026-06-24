import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Loader2, Pencil, Plus } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { RedactedCell } from "@/components/shared/RedactedValue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { modelProfilesApi } from "@/lib/api";
import type { AgentModelProfileEntry } from "@/lib/api";
import { useTranslation } from "react-i18next";
import {
  buildModelProfileCreatePayload,
  buildModelProfileUpdatePayload,
  emptyModelProfileFormValues,
  inferProfileKey,
  inferProfileName,
  modelProfileFormValuesFromProfile,
  type ModelProfileFormValues,
  type ModelProfileProvider,
} from "./modelProfileForm";

type ProfileFormMode = "create" | "edit";

/** Model profiles content - used inside the Settings dialog. */
export function ModelProfilesContent() {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = React.useState(false);
  const [showAdvancedCreate, setShowAdvancedCreate] = React.useState(false);
  const [formValues, setFormValues] = React.useState<ModelProfileFormValues>(
    () => emptyModelProfileFormValues(),
  );
  const [editingProfileKey, setEditingProfileKey] = React.useState<string | null>(null);
  const [showAdvancedEdit, setShowAdvancedEdit] = React.useState(false);
  const [editFormValues, setEditFormValues] =
    React.useState<ModelProfileFormValues>(() => emptyModelProfileFormValues());
  const q = useQuery({ queryKey: ["model-profiles"], queryFn: modelProfilesApi.list });

  const enableMutation = useMutation({
    mutationFn: (key: string) => modelProfilesApi.enable(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-profiles"] }),
  });
  const disableMutation = useMutation({
    mutationFn: (key: string) => modelProfilesApi.disable(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-profiles"] }),
  });
  const createMutation = useMutation({
    mutationFn: (values: ModelProfileFormValues) =>
      modelProfilesApi.create(buildModelProfileCreatePayload(values)),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["model-profiles"] });
      setFormValues(emptyModelProfileFormValues());
      setShowAdvancedCreate(false);
      setShowCreate(false);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({
      profile,
      values,
    }: {
      profile: AgentModelProfileEntry;
      values: ModelProfileFormValues;
    }) => modelProfilesApi.patch(profile.key, buildModelProfileUpdatePayload(values, profile)),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["model-profiles"] });
      setEditFormValues(emptyModelProfileFormValues());
      setShowAdvancedEdit(false);
      setEditingProfileKey(null);
    },
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const rows = (q.data as AgentModelProfileEntry[]) ?? [];
  const editingProfile =
    rows.find((profile) => profile.key === editingProfileKey) ?? null;

  const startEditing = (profile: AgentModelProfileEntry) => {
    setEditFormValues(modelProfileFormValuesFromProfile(profile));
    setEditingProfileKey(profile.key);
    setShowAdvancedEdit(false);
    setShowCreate(false);
  };

  const cancelEditing = () => {
    setEditFormValues(emptyModelProfileFormValues());
    setShowAdvancedEdit(false);
    setEditingProfileKey(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          onClick={() => {
            setShowCreate((value) => !value);
            setShowAdvancedCreate(false);
            cancelEditing();
          }}
        >
          <Plus className="h-4 w-4" />
          {t("createProfile")}
        </Button>
      </div>
      {showCreate && (
        <ModelProfileForm
          mode="create"
          values={formValues}
          onValuesChange={setFormValues}
          showAdvanced={showAdvancedCreate}
          onShowAdvancedChange={setShowAdvancedCreate}
          onSubmit={() => createMutation.mutate(formValues)}
          onCancel={() => {
            setFormValues(emptyModelProfileFormValues());
            setShowAdvancedCreate(false);
            setShowCreate(false);
          }}
          isPending={createMutation.isPending}
          error={createMutation.error}
        />
      )}
      {editingProfile && (
        <ModelProfileForm
          mode="edit"
          values={editFormValues}
          onValuesChange={setEditFormValues}
          showAdvanced={showAdvancedEdit}
          onShowAdvancedChange={setShowAdvancedEdit}
          onSubmit={() =>
            updateMutation.mutate({ profile: editingProfile, values: editFormValues })
          }
          onCancel={cancelEditing}
          isPending={updateMutation.isPending}
          error={updateMutation.error}
        />
      )}
      <DataTable
        data={rows}
        columns={[
          {
            accessorKey: "key",
            header: "Key",
            cell: ({ row }) => (
              <span className="font-mono text-xs">{row.original.key}</span>
            ),
          },
          { accessorKey: "name", header: t("profileName") },
          { accessorKey: "provider", header: t("provider") },
          {
            accessorKey: "model",
            header: t("model"),
            cell: ({ row }) => (
              <span className="font-mono text-xs">{row.original.model}</span>
            ),
          },
          {
            id: "secret",
            header: t("apiKey"),
            cell: ({ row }) => (
              <RedactedCell present={!!row.original.auth_secret?.has_secret} />
            ),
          },
          {
            id: "capabilities",
            header: t("capabilities"),
            cell: ({ row }) => (
              <div className="flex gap-1">
                {row.original.capabilities?.vision && (
                  <Badge variant="accent">{t("vision")}</Badge>
                )}
                {row.original.capabilities?.thinking && (
                  <Badge variant="secondary">{t("thinking")}</Badge>
                )}
              </div>
            ),
          },
          {
            id: "enabled",
            header: t("enabled"),
            cell: ({ row }) => (
              <Switch
                checked={row.original.enabled ?? false}
                disabled={enableMutation.isPending || disableMutation.isPending}
                onCheckedChange={(checked) =>
                  (checked ? enableMutation : disableMutation).mutateAsync(
                    row.original.key,
                  )
                }
              />
            ),
          },
          {
            id: "actions",
            header: t("actions"),
            cell: ({ row }) => (
              <Button
                type="button"
                size="sm"
                variant={editingProfileKey === row.original.key ? "secondary" : "ghost"}
                aria-label={`${t("editProfile")} ${row.original.name}`}
                onClick={() => startEditing(row.original)}
              >
                <Pencil className="h-4 w-4" />
                <span className="hidden sm:inline">{t("editProfile")}</span>
              </Button>
            ),
          },
        ]}
        empty={t("noProfiles")}
      />
    </div>
  );
}

function ModelProfileForm({
  mode,
  values,
  onValuesChange,
  showAdvanced,
  onShowAdvancedChange,
  onSubmit,
  onCancel,
  isPending,
  error,
}: {
  mode: ProfileFormMode;
  values: ModelProfileFormValues;
  onValuesChange: React.Dispatch<React.SetStateAction<ModelProfileFormValues>>;
  showAdvanced: boolean;
  onShowAdvancedChange: React.Dispatch<React.SetStateAction<boolean>>;
  onSubmit: () => void;
  onCancel: () => void;
  isPending: boolean;
  error: unknown;
}) {
  const { t } = useTranslation("settings");
  const isEdit = mode === "edit";
  const setValue = <K extends keyof ModelProfileFormValues>(
    key: K,
    value: ModelProfileFormValues[K],
  ) => onValuesChange((current) => ({ ...current, [key]: value }));
  const errorMessage =
    error instanceof Error
      ? error.message
      : error
        ? isEdit
          ? t("updateProfileFailed")
          : t("createProfileFailed")
        : "";

  return (
    <form
      className="space-y-4 rounded-md border bg-background/80 p-4 shadow-sm shadow-slate-900/5"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("provider")}>
          <Select
            value={values.provider}
            onValueChange={(provider) =>
              setValue("provider", provider as ModelProfileProvider)
            }
          >
            <SelectTrigger aria-label={t("provider")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">OpenAI</SelectItem>
              <SelectItem value="anthropic">Anthropic</SelectItem>
              <SelectItem value="custom">Custom</SelectItem>
              <SelectItem value="test">Test</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label={t("model")}>
          <Input
            required
            value={values.model}
            onChange={(event) => setValue("model", event.target.value)}
            placeholder="gpt-4o-mini"
          />
        </Field>
        <Field label={t("apiKey")}>
          <Input
            type="password"
            value={values.apiKey}
            onChange={(event) => setValue("apiKey", event.target.value)}
            placeholder={isEdit ? t("apiKeyEditPlaceholder") : "sk-..."}
          />
        </Field>
        <Field label={t("profileName")}>
          <Input
            value={values.name}
            onChange={(event) => setValue("name", event.target.value)}
            placeholder={inferProfileName(values.model)}
          />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-4 rounded-md bg-muted/40 px-3 py-2">
        <ToggleField
          label={t("vision")}
          checked={values.vision}
          onCheckedChange={(checked) => setValue("vision", checked)}
        />
        <ToggleField
          label={t("thinking")}
          checked={values.thinking}
          onCheckedChange={(checked) => setValue("thinking", checked)}
        />
      </div>
      <div className="rounded-md border bg-muted/10">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm font-medium"
          aria-expanded={showAdvanced}
          onClick={() => onShowAdvancedChange((value) => !value)}
        >
          <span>{t("advancedConfiguration")}</span>
          <ChevronDown
            className={`h-4 w-4 text-muted-foreground transition-transform ${
              showAdvanced ? "rotate-180" : ""
            }`}
          />
        </button>
        {showAdvanced && (
          <div className="grid gap-3 border-t p-3 sm:grid-cols-2">
            <Field label={t("profileKey")}>
              <Input
                readOnly={isEdit}
                value={values.key}
                onChange={(event) => setValue("key", event.target.value)}
                placeholder={inferProfileKey(values.provider, values.model)}
                className={isEdit ? "font-mono text-xs" : undefined}
              />
            </Field>
            <Field label={t("baseUrl")}>
              <Input
                value={values.baseUrl}
                onChange={(event) => setValue("baseUrl", event.target.value)}
                placeholder="https://api.openai.com/v1"
              />
            </Field>
            <Field label={t("tokenCeiling")}>
              <Input
                inputMode="numeric"
                value={values.maxTotalTokens}
                onChange={(event) => setValue("maxTotalTokens", event.target.value)}
                placeholder={t("unlimited")}
              />
            </Field>
            <Field label={t("maxRunCost")}>
              <Input
                inputMode="decimal"
                value={values.maxRunCostUsd}
                onChange={(event) => setValue("maxRunCostUsd", event.target.value)}
                placeholder={t("unlimited")}
              />
            </Field>
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {isEdit ? t("modelProfileEditHint") : t("modelProfileInferenceHint")}
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel}>
            {t("cancel")}
          </Button>
          <Button type="submit" size="sm" disabled={isPending}>
            {isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {isEdit ? t("updateProfile") : t("saveProfile")}
          </Button>
        </div>
      </div>
      {errorMessage && (
        <p className="text-xs text-destructive">
          {errorMessage}
        </p>
      )}
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Label className="space-y-1.5">
      <span>{label}</span>
      {children}
    </Label>
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
