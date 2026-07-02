import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Brain,
  Bot,
  Gauge,
  PlugZap,
  Settings2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SkillsContent } from "@/features/admin/SkillsPage";
import { ApprovalsContent } from "@/features/admin/ApprovalsPage";
import { MemoryContent } from "@/features/admin/MemoryPage";
import { ModelProfilesContent } from "@/features/admin/ModelProfilesPage";
import { ExternalToolsContent } from "@/features/admin/ExternalToolsPage";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { healthApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

export type ManagerKind = "skills" | "approvals" | "memory" | "settings";

interface ManagerDialogApi {
  open: (kind: ManagerKind) => void;
}

const ManagerContext = React.createContext<ManagerDialogApi | null>(null);

export function useManager(): ManagerDialogApi {
  const ctx = React.useContext(ManagerContext);
  if (!ctx) throw new Error("useManager must be used within ManagerDialogs");
  return ctx;
}

export function ManagerDialogs({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation([
    "common",
    "skills",
    "approvals",
    "memory",
    "settings",
  ]);
  const [kind, setKind] = React.useState<ManagerKind | null>(null);

  const api = React.useMemo<ManagerDialogApi>(
    () => ({ open: (k) => setKind(k) }),
    [],
  );

  const titleMap: Record<ManagerKind, string> = {
    skills: t("skills:registry"),
    approvals: t("approvals:queue"),
    memory: t("memory:title"),
    settings: t("settings:title"),
  };

  return (
    <ManagerContext.Provider value={api}>
      {children}
      <Dialog open={kind !== null} onOpenChange={(o) => !o && setKind(null)}>
        <DialogContent
          className={cn(
            "p-0",
            kind === "settings"
              ? "h-[min(760px,calc(100vh-48px))] w-[min(1180px,calc(100vw-48px))] max-w-none overflow-hidden rounded-xl border-slate-200/80 bg-background shadow-2xl shadow-slate-900/20 sm:rounded-xl [&>button]:right-6 [&>button]:top-6 [&>button]:rounded-md"
              : "flex max-h-[85vh] w-full max-w-3xl flex-col gap-3",
          )}
        >
          {kind === "settings" ? (
            <SettingsTabs />
          ) : (
            <>
              <DialogHeader className="px-5 pt-5">
                <DialogTitle>{kind ? titleMap[kind] : ""}</DialogTitle>
                <DialogDescription className="sr-only">
                  {kind ? titleMap[kind] : ""}
                </DialogDescription>
              </DialogHeader>
              <ScrollArea className="min-h-0 flex-1 px-5 pb-5">
                {kind === "skills" && <SkillsContent />}
                {kind === "approvals" && <ApprovalsContent />}
                {kind === "memory" && <MemoryContent />}
              </ScrollArea>
            </>
          )}
        </DialogContent>
      </Dialog>
    </ManagerContext.Provider>
  );
}

const settingsSections = [
  {
    value: "profiles",
    labelKey: "models",
    descriptionKey: "modelsDescription",
    icon: Bot,
    content: <ModelProfilesContent />,
  },
  {
    value: "tools",
    labelKey: "externalTools",
    descriptionKey: "externalToolsDescription",
    icon: PlugZap,
    content: <ExternalToolsContent />,
  },
  {
    value: "skills",
    labelKey: "skills",
    descriptionKey: "skillsDescription",
    icon: Sparkles,
    content: <SkillsContent />,
  },
  {
    value: "memory",
    labelKey: "memory",
    descriptionKey: "memoryDescription",
    icon: Brain,
    content: <MemoryContent />,
  },
  {
    value: "runtime",
    labelKey: "runtime",
    descriptionKey: "runtimeDescription",
    icon: Gauge,
    content: <RuntimeSettingsContent />,
  },
] as const;

export function SettingsTabs() {
  const { t } = useTranslation("settings");
  return (
    <div className="flex h-full min-h-0 flex-col bg-[radial-gradient(circle_at_top_left,hsl(var(--accent)/0.08),transparent_34%),linear-gradient(135deg,hsl(var(--muted))_0%,hsl(var(--background))_54%,hsl(var(--secondary))_100%)]">
      <DialogHeader className="shrink-0 px-7 pb-4 pt-7">
        <DialogTitle className="flex items-center gap-2 text-2xl font-semibold leading-tight tracking-normal">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border bg-background/70 text-primary shadow-sm">
            <Settings2 className="h-4 w-4" />
          </span>
          {t("title")}
        </DialogTitle>
        <DialogDescription className="max-w-2xl text-sm leading-6 text-muted-foreground">
          {t("settingsSubtitle")}
        </DialogDescription>
      </DialogHeader>
      <Tabs
        defaultValue="profiles"
        orientation="vertical"
        className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)] gap-4 px-7 pb-7 max-md:grid-cols-1 max-md:grid-rows-[auto_minmax(0,1fr)]"
      >
        <TabsList className="flex h-full min-h-0 flex-col items-stretch justify-start gap-1 rounded-lg border bg-background/65 p-2 text-muted-foreground shadow-sm shadow-slate-900/5 backdrop-blur max-md:h-auto max-md:flex-row max-md:overflow-x-auto">
          {settingsSections.map((section) => (
            <SettingsNavTrigger
              key={section.value}
              value={section.value}
              icon={section.icon}
              label={t(section.labelKey)}
            />
          ))}
        </TabsList>
        <div className="min-h-0 rounded-lg border bg-background/72 shadow-sm shadow-slate-900/5 backdrop-blur">
          {settingsSections.map((section) => (
            <TabsContent
              key={section.value}
              value={section.value}
              className="m-0 h-full min-h-0 data-[state=inactive]:hidden"
            >
              <ScrollArea className="h-full">
                <div className="space-y-5 p-5">
                  <div className="max-w-3xl">
                    <h3 className="text-2xl font-semibold leading-tight tracking-normal">
                      {t(section.labelKey)}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      {t(section.descriptionKey)}
                    </p>
                  </div>
                  {section.content}
                </div>
              </ScrollArea>
            </TabsContent>
          ))}
        </div>
      </Tabs>
    </div>
  );
}

function SettingsNavTrigger({
  value,
  icon: Icon,
  label,
}: {
  value: string;
  icon: LucideIcon;
  label: string;
}) {
  return (
    <TabsTrigger
      value={value}
      className="h-11 justify-start gap-3 rounded-md px-3 text-sm font-medium data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-md data-[state=active]:shadow-primary/20 max-md:h-10 max-md:min-w-max"
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </TabsTrigger>
  );
}

function RuntimeSettingsContent() {
  const { t } = useTranslation("settings");
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: healthApi.check,
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-4">
      <section className="rounded-md border">
        <div className="border-b bg-muted/40 px-3 py-2">
          <h3 className="text-sm font-medium">{t("runtimeDefaults")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("runtimeDefaultsDescription")}
          </p>
        </div>
        <div className="divide-y">
          <RuntimeRow
            label={t("backendHealth")}
            value={
              healthQuery.isLoading ? (
                <span className="text-muted-foreground">{t("checking")}</span>
              ) : healthQuery.isError ? (
                <span className="text-destructive">{t("unavailable")}</span>
              ) : (
                <span className="flex flex-wrap items-center gap-2">
                  <Badge variant="success">{t("liveConfig")}</Badge>
                  <span className="font-mono text-xs text-muted-foreground">
                    {healthQuery.data?.service ?? "aithru-agent-backend"}
                  </span>
                </span>
              )
            }
          />
          <RuntimeRow
            label={t("managedConfiguration")}
            value={
              <span className="flex flex-wrap gap-1.5">
                <Badge variant="accent">{t("models")}</Badge>
                <Badge variant="accent">{t("externalTools")}</Badge>
                <Badge variant="accent">{t("skills")}</Badge>
                <Badge variant="accent">{t("memory")}</Badge>
              </span>
            }
          />
          <RuntimeRow
            label={t("restartRequired")}
            value={
              <span className="flex flex-wrap gap-1.5">
                <Badge variant="secondary">{t("ports")}</Badge>
                <Badge variant="secondary">{t("persistence")}</Badge>
                <Badge variant="secondary">{t("apiBoundary")}</Badge>
              </span>
            }
          />
        </div>
      </section>
      {healthQuery.isError && (
        <>
          <Separator />
          <ErrorState
            error={healthQuery.error}
            onRetry={() => healthQuery.refetch()}
          />
        </>
      )}
      {healthQuery.isLoading && <LoadingState label={t("checking")} />}
    </div>
  );
}

function RuntimeRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="grid gap-2 px-3 py-3 text-sm sm:grid-cols-[180px_1fr]">
      <div className="font-medium text-muted-foreground">{label}</div>
      <div className="min-w-0">{value}</div>
    </div>
  );
}
