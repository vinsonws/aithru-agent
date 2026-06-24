import { useEffect } from "react";
import { useHost } from "./HostProvider";
import { changeLanguage } from "@/i18n";

/**
 * Keep i18n language and document lang in sync with the host runtime context.
 * In hosted production mode the host locale is the single source of truth; we
 * do not persist an independent preference there.
 */
export function useRuntimeSync() {
  const { context, hosted } = useHost();
  const lang = context.locale.language;

  useEffect(() => {
    void changeLanguage(lang);
    document.documentElement.lang = lang;
  }, [lang]);

  // Persist locale only in dev/mock mode (non-sensitive preference).
  useEffect(() => {
    if (!hosted) {
      try {
        localStorage.setItem("aithru:locale", lang);
      } catch {
        // ignore
      }
    }
  }, [lang, hosted]);
}
