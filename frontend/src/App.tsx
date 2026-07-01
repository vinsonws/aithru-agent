import * as React from "react";
import { BrowserRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import { TooltipProvider } from "@/components/ui/tooltip";
import { HostProvider, useHost } from "@/lib/host/HostProvider";
import { useRuntimeSync } from "@/lib/host/useRuntimeSync";
import { QueryProvider } from "@/lib/query";
import { changeLanguage, initI18n } from "@/i18n";
import { AppShell } from "./AppShell";

const appI18n = initI18n("en-US");

function routerBaseName(basePath?: string): string | undefined {
  if (!basePath || basePath === "/") return undefined;
  return basePath.replace(/\/+$/, "");
}

function BootstrappedApp() {
  const { context, ready } = useHost();
  useRuntimeSync();

  React.useEffect(() => {
    void changeLanguage(context.locale.language);
  }, [context.locale.language]);

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Connecting to host…
      </div>
    );
  }

  return (
    <TooltipProvider>
      <BrowserRouter basename={routerBaseName(context.route?.basePath)}>
        <AppShell />
      </BrowserRouter>
    </TooltipProvider>
  );
}

export default function App() {
  return (
    <QueryProvider>
      <HostProvider>
        <I18nextProvider i18n={appI18n}>
          <BootstrappedApp />
        </I18nextProvider>
      </HostProvider>
    </QueryProvider>
  );
}
