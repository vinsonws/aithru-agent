import { Activity, Eye, FolderOpen, GitBranch, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const PANELS = [
  { id: "preview", icon: Eye, label: "Preview" },
  { id: "files", icon: FolderOpen, label: "Files" },
  { id: null, icon: null, label: null }, // separator
  { id: "activity", icon: Activity, label: "Activity" },
  { id: "approvals", icon: ShieldCheck, label: "Approvals" },
  { id: "trace", icon: GitBranch, label: "Trace" },
] as const;

interface RightRailProps {
  activePanel: string | null;
  onPanelChange: (panel: string | null) => void;
  badges: { approvals: number };
}

export function RightRail({ activePanel, onPanelChange, badges }: RightRailProps) {
  return (
    <aside className="hidden w-12 shrink-0 flex-col items-center gap-1 border-l border-border/70 bg-background py-3 lg:flex">
      {PANELS.map((item) => {
        if (item.id === null) {
          return <div key="sep" className="my-2 w-6 border-t border-border/50" />;
        }
        const isActive = activePanel === item.id;
        const hasBadge = item.id === "approvals" && badges.approvals > 0;
        const Icon = item.icon!;

        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onPanelChange(isActive ? null : item.id)}
            title={item.label}
            className={cn(
              "relative flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
              isActive && "bg-secondary text-foreground ring-1 ring-primary/25",
            )}
          >
            <Icon className="h-4 w-4" />
            {hasBadge && (
              <Badge
                variant="destructive"
                className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px]"
              >
                {badges.approvals > 9 ? "9+" : badges.approvals}
              </Badge>
            )}
          </button>
        );
      })}
    </aside>
  );
}
