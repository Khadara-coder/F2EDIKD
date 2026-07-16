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
  connectorConfig: {
    apiBaseUrl: "",
    dbSyncEnabled: true,
    csvDelimiter: ";",
    sftpProfile: "default",
  },
  validation: {
    autoValidationThreshold: 90,
    requireCustomerReference: true,
    requireDeliveryDate: false,
    blockOnAmountMismatch: true,
    duplicateWindowDays: 30,
  },
  notifications: {
    emailEnabled: false,
    emailRecipients: "",
    notifyOnSuccess: false,
    notifyOnFailure: true,
    webhookEnabled: false,
    webhookUrl: "",
  },
  sftpConfig: {
    enabled: false,
    host: "",
    port: 22,
    username: "",
    remotePath: "/inbox",
    fileNamePattern: "ORDERS_{orderId}.edi",
  },
  security: {
    enforceAuth: true,
    sessionTimeoutMinutes: 480,
    maxLoginAttempts: 5,
    auditLogEnabled: true,
    ipAllowlist: "",
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
    connectorConfig: { ...DEFAULT_APP_SETTINGS.connectorConfig, ...partial.connectorConfig },
    validation: { ...DEFAULT_APP_SETTINGS.validation, ...partial.validation },
    notifications: { ...DEFAULT_APP_SETTINGS.notifications, ...partial.notifications },
    sftpConfig: { ...DEFAULT_APP_SETTINGS.sftpConfig, ...partial.sftpConfig },
    security: { ...DEFAULT_APP_SETTINGS.security, ...partial.security },
    options: { ...DEFAULT_APP_SETTINGS.options, ...partial.options },
  };
}
