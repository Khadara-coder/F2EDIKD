import type { AppSettings } from "@/types";

export const DEFAULT_APP_SETTINGS: AppSettings = {
  ediProfile: "ELM_STANDARD",
  standard: "UN/EDIFACT",
  version: "D.96A",
  defaultIncoterm: "DAP - Delivered At Place",
  currency: "EUR - Euro",
  documentLanguage: "Français (FR)",
  timezone: "(UTC+01:00) Europe/Paris",
  connectors: {
    apiExtraction: "connected",
    database: "connected",
    csvExport: "connected",
    sftp: "disconnected",
  },
  options: {
    autoValidateAbove90: true,
    detectDuplicates: true,
    autoSftp: false,
    manualReviewOnAnomaly: true,
    notifyOnDuplicate: false,
  },
};

export function mergeSettings(partial?: Partial<AppSettings> | null): AppSettings {
  if (!partial) return DEFAULT_APP_SETTINGS;
  return {
    ...DEFAULT_APP_SETTINGS,
    ...partial,
    connectors: { ...DEFAULT_APP_SETTINGS.connectors, ...partial.connectors },
    options: { ...DEFAULT_APP_SETTINGS.options, ...partial.options },
  };
}
