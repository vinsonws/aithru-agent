import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DataTable } from "@/components/shared/DataTable";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { skillsApi } from "@/lib/api";
import type { AgentSkillRegistryEntry } from "@/lib/api";
import { useTranslation } from "react-i18next";

function SourceBadge({ source }: { source: string }) {
  const { t } = useTranslation("skills");
  if (source === "user") {
    return <Badge variant="secondary">{t("user")}</Badge>;
  }
  return <Badge variant="outline">{t("builtin")}</Badge>;
}

function CreateUserSkillDialog({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation("skills");
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [body, setBody] = useState("");

  const createMutation = useMutation({
    mutationFn: () =>
      skillsApi.createUser({
        key,
        name,
        description,
        body,
        allowed_tools: [],
        denied_tools: [],
        allowed_subagents: [],
        enabled: true,
      }),
    onSuccess: () => {
      setOpen(false);
      setKey("");
      setName("");
      setDescription("");
      setBody("");
      onCreated();
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="default" size="sm">{t("createUserSkill")}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("createUserSkill")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div>
            <Label>Key</Label>
            <Input value={key} onChange={(e) => setKey(e.target.value)} placeholder="my-skill" />
          </div>
          <div>
            <Label>{t("title")}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Skill" />
          </div>
          <div>
            <Label>{t("description")}</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
          </div>
          <div>
            <Label>{t("body")}</Label>
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} placeholder="# Instructions" />
          </div>
          <Button onClick={() => createMutation.mutate()}>{t("createUserSkill")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("registry")}</h2>
        <CreateUserSkillDialog onCreated={() => qc.invalidateQueries({ queryKey: ["skill-registry"] })} />
      </div>
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
            header: t("source"),
            cell: ({ row }) => (
              <SourceBadge source={row.original.source ?? "builtin"} />
            ),
          },
          { accessorKey: "version", header: t("version") },
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
          {
            id: "readOnly",
            header: t("readOnly"),
            cell: ({ row }) => (
              <span className="text-xs text-muted-foreground">
                {row.original.read_only ? t("readOnly") : ""}
              </span>
            ),
          },
        ]}
        empty={t("noSkills")}
      />
    </div>
  );
}
