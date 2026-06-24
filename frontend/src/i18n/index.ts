import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enCommon from "./resources/en/common.json";
import enErrors from "./resources/en/errors.json";
import enChat from "./resources/en/chat.json";
import enInspection from "./resources/en/inspection.json";
import enSkills from "./resources/en/skills.json";
import enMemory from "./resources/en/memory.json";
import enApprovals from "./resources/en/approvals.json";
import enSettings from "./resources/en/settings.json";
import zhCommon from "./resources/zh/common.json";
import zhErrors from "./resources/zh/errors.json";
import zhChat from "./resources/zh/chat.json";
import zhInspection from "./resources/zh/inspection.json";
import zhSkills from "./resources/zh/skills.json";
import zhMemory from "./resources/zh/memory.json";
import zhApprovals from "./resources/zh/approvals.json";
import zhSettings from "./resources/zh/settings.json";

export const SUPPORTED_LOCALES = ["en-US", "zh-CN"] as const;
export const FALLBACK_LOCALE = "en-US";

export function initI18n(locale: string) {
  if (!i18n.isInitialized) {
    i18n.use(initReactI18next).init({
      resources: {
        "en-US": {
          common: enCommon,
          errors: enErrors,
          chat: enChat,
          inspection: enInspection,
          skills: enSkills,
          memory: enMemory,
          approvals: enApprovals,
          settings: enSettings,
        },
        "zh-CN": {
          common: zhCommon,
          errors: zhErrors,
          chat: zhChat,
          inspection: zhInspection,
          skills: zhSkills,
          memory: zhMemory,
          approvals: zhApprovals,
          settings: zhSettings,
        },
      },
      lng: locale,
      fallbackLng: FALLBACK_LOCALE,
      defaultNS: "common",
      interpolation: { escapeValue: false },
      returnNull: false,
    });
  } else {
    void i18n.changeLanguage(locale);
  }
  return i18n;
}

export function changeLanguage(locale: string) {
  return i18n.changeLanguage(locale);
}

export default i18n;
