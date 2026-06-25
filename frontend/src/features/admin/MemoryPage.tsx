import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Database, Trash2 } from "lucide-react";
import { ErrorState, LoadingState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { longTermMemoryApi } from "@/lib/api";
import { useTranslation } from "react-i18next";

/** Long-term memory manager content — used inside the Settings dialog. */
export function MemoryContent() {
  const { t } = useTranslation("memory");
  const healthQuery = useQuery({
    queryKey: ["long-term-memory", "health"],
    queryFn: longTermMemoryApi.health,
    refetchInterval: 30_000,
  });

  if (healthQuery.isLoading) return <LoadingState label={t("checking")} />;
  if (healthQuery.isError) {
    return <ErrorState error={healthQuery.error} onRetry={() => healthQuery.refetch()} />;
  }

  const health = healthQuery.data;
  const provider = health?.provider ?? "unknown";
  const enabled = Boolean(health?.enabled);

  return (
    <div className="space-y-4">
      <section className="rounded-md border">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-muted/40 px-3 py-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-background text-primary">
              <Database className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h3 className="text-sm font-medium">{t("longTermTitle")}</h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {t("longTermDescription")}
              </p>
            </div>
          </div>
          <Badge variant={enabled ? "success" : "secondary"}>
            {enabled ? t("enabled") : t("disabled")}
          </Badge>
        </div>
        <div className="divide-y">
          <MemoryStatusRow label={t("provider")} value={provider} />
          <MemoryStatusRow
            label={t("storageMode")}
            value={enabled ? t("mem0Only") : t("providerDisabled")}
          />
        </div>
      </section>
      {enabled && provider === "mem0" ? (
        <ForgetLongTermMemoryForm />
      ) : (
        <section className="rounded-md border bg-muted/20 px-3 py-3">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-medium">{t("localMemoryRetired")}</h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {t("localMemoryRetiredDescription")}
              </p>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function MemoryStatusRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[150px_minmax(0,1fr)] items-center gap-3 px-3 py-2.5 text-sm max-sm:grid-cols-1 max-sm:gap-1">
      <span className="text-xs font-medium uppercase text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words">{value}</span>
    </div>
  );
}

function ForgetLongTermMemoryForm() {
  const { t } = useTranslation("memory");
  const [memoryId, setMemoryId] = React.useState("");
  const forgetMutation = useMutation({
    mutationFn: (id: string) => longTermMemoryApi.forget(id),
    onSuccess: () => setMemoryId(""),
  });
  const trimmedMemoryId = memoryId.trim();

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!trimmedMemoryId || forgetMutation.isPending) return;
    forgetMutation.mutate(trimmedMemoryId);
  }

  return (
    <section className="rounded-md border">
      <div className="border-b bg-muted/40 px-3 py-3">
        <h3 className="text-sm font-medium">{t("forgetMemory")}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {t("forgetMemoryDescription")}
        </p>
      </div>
      <form className="space-y-3 p-3" onSubmit={onSubmit}>
        <div className="space-y-1.5">
          <Label htmlFor="long-term-memory-id">{t("memoryId")}</Label>
          <Input
            id="long-term-memory-id"
            value={memoryId}
            onChange={(event) => setMemoryId(event.target.value)}
            placeholder={t("memoryIdPlaceholder")}
            autoComplete="off"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="submit"
            variant="destructive"
            disabled={!trimmedMemoryId || forgetMutation.isPending}
          >
            <Trash2 className="h-4 w-4" />
            {forgetMutation.isPending ? t("forgetting") : t("forget")}
          </Button>
          {forgetMutation.isSuccess && (
            <span className="text-xs text-success">{t("forgetSuccess")}</span>
          )}
          {forgetMutation.isError && (
            <span className="text-xs text-destructive">{t("forgetFailed")}</span>
          )}
        </div>
      </form>
    </section>
  );
}
