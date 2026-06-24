import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DataTable } from "@/components/shared/DataTable";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { skillsApi } from "@/lib/api";
import type { AgentSkillRegistryEntry } from "@/lib/api";
import { useTranslation } from "react-i18next";

/** Skills registry content — used inside the Skills manager dialog. */
export function SkillsContent() {
  const { t } = useTranslation("skills");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["skill-registry"], queryFn: skillsApi.registry });

  const enableMutation = useMutation({
    mutationFn: (key: string) => skillsApi.enable(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skill-registry"] }),
  });
  const disableMutation = useMutation({
    mutationFn: (key: string) => skillsApi.disable(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skill-registry"] }),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const rows = (q.data as AgentSkillRegistryEntry[]) ?? [];

  return (
    <DataTable
      data={rows}
      columns={[
        {
          accessorKey: "key",
          header: "Key",
          cell: ({ row }) => <span className="font-mono text-xs">{row.original.key}</span>,
        },
        { accessorKey: "name", header: t("title") },
        {
          accessorKey: "source",
          header: t("builtin"),
          cell: ({ row }) => <Badge variant="outline">{row.original.source ?? "builtin"}</Badge>,
        },
        { accessorKey: "version", header: t("version") },
        { accessorKey: "owner", header: t("owner") },
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
      empty={t("noSkills")}
    />
  );
}
