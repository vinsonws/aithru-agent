import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DataTable } from "@/components/shared/DataTable";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { RedactedCell } from "@/components/shared/RedactedValue";
import { externalToolsApi } from "@/lib/api";
import type { AgentExternalToolConfigEntry } from "@/lib/api";
import { useTranslation } from "react-i18next";

/** External tools content — used inside the Settings dialog. */
export function ExternalToolsContent() {
  const { t } = useTranslation("settings");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["external-tools"], queryFn: externalToolsApi.list });

  const enableMutation = useMutation({
    mutationFn: (key: string) => externalToolsApi.enable(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["external-tools"] }),
  });
  const disableMutation = useMutation({
    mutationFn: (key: string) => externalToolsApi.disable(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["external-tools"] }),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const rows = (q.data as AgentExternalToolConfigEntry[]) ?? [];

  return (
    <DataTable
      data={rows}
      columns={[
        { accessorKey: "key", header: "Key", cell: ({ row }) => <span className="font-mono text-xs">{row.original.key}</span> },
        {
          accessorKey: "provider_kind",
          header: t("kind"),
          cell: ({ row }) => <Badge variant="outline">{row.original.provider_kind}</Badge>,
        },
        {
          id: "secret",
          header: "Secret",
          cell: ({ row }) => {
            const endpoint =
              row.original.mcp?.endpoint ??
              row.original.http?.endpoint ??
              row.original.web;
            const hasSecret = !!(endpoint && (endpoint as { auth_secret?: { has_secret?: boolean } }).auth_secret?.has_secret);
            return <RedactedCell present={hasSecret} />;
          },
        },
        {
          id: "oauth",
          header: "OAuth",
          cell: ({ row }) => (
            <Badge variant={row.original.oauth_status?.connected ? "success" : "secondary"}>
              {row.original.oauth_status?.status ?? t("oauthNotConfigured")}
            </Badge>
          ),
        },
        {
          id: "cache",
          header: t("cacheState"),
          cell: ({ row }) => (
            <span className="text-xs text-muted-foreground">
              {row.original.cache_status?.status ?? "—"}
            </span>
          ),
        },
        {
          id: "enabled",
          header: t("enabled"),
          cell: ({ row }) => (
            <Switch
              checked={row.original.enabled ?? false}
              onCheckedChange={(checked) =>
                (checked ? enableMutation : disableMutation).mutateAsync(row.original.key)
              }
            />
          ),
        },
      ]}
      empty={t("noTools")}
    />
  );
}
