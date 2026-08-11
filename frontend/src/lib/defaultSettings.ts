import type { AppSettings } from "@/types";
import { resolveDisplayTimeZone } from "@/lib/utils";

export const DEFAULT_APP_SETTINGS: AppSettings = {
  ediProfile: "ELM_STANDARD",
  standard: "UN/EDIFACT",
  version: "D.96A",
  defaultIncoterm: "DAP - Delivered At Place",
  currency: "EUR - Euro",
  documentLanguage: "Français (FR)",
  timezone: "Europe/Paris",
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
  masterdataN8nConfig: {
    enabled: true,
    webhookUrl: "http://localhost:5678/webhook/masterdata-sync",
    authHeader: "x-api-key",
    timeoutSeconds: 120,
  },
  aiProvider: "databricks",
  databricksConfig: {
    host: "https://adb-5555213114570927.7.azuredatabricks.net",
    apiBaseUrl: "https://file2edi-5555213114570927.7.azure.databricksapps.com",
    modelEndpoint: "databricks-gpt-oss-120b",
    sqlWarehouseEnabled: false,
    warehouseId: "",
    catalog: "hive_metastore",
    schema: "edifact_generator",
    configProfile: "",
    llmEnabled: true,
  },
  openaiConfig: {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
  },
  ollamaConfig: {
    baseUrl: "http://localhost:11434",
    model: "llama3.1",
  },
  customAiConfig: {
    baseUrl: "",
    model: "",
    chatPath: "/v1/chat/completions",
    authHeader: "Authorization",
    authScheme: "Bearer",
    customHeaders: "",
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
    remotePath: "/",
    fileNamePattern: "ORDERS_{orderId}.edi",
    hasPassword: false,
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
  const timezone = resolveDisplayTimeZone(partial.timezone) ?? partial.timezone ?? DEFAULT_APP_SETTINGS.timezone;
  return {
    ...DEFAULT_APP_SETTINGS,
    ...partial,
    connectors: { ...DEFAULT_APP_SETTINGS.connectors, ...partial.connectors },
    connectorConfig: { ...DEFAULT_APP_SETTINGS.connectorConfig, ...partial.connectorConfig },
    masterdataN8nConfig: {
      ...DEFAULT_APP_SETTINGS.masterdataN8nConfig,
      ...partial.masterdataN8nConfig,
    },
    aiProvider: partial.aiProvider ?? DEFAULT_APP_SETTINGS.aiProvider,
    databricksConfig: { ...DEFAULT_APP_SETTINGS.databricksConfig, ...partial.databricksConfig },
    openaiConfig: { ...DEFAULT_APP_SETTINGS.openaiConfig, ...partial.openaiConfig },
    ollamaConfig: { ...DEFAULT_APP_SETTINGS.ollamaConfig, ...partial.ollamaConfig },
    customAiConfig: { ...DEFAULT_APP_SETTINGS.customAiConfig, ...partial.customAiConfig },
    validation: { ...DEFAULT_APP_SETTINGS.validation, ...partial.validation },
    notifications: { ...DEFAULT_APP_SETTINGS.notifications, ...partial.notifications },
    sftpConfig: { ...DEFAULT_APP_SETTINGS.sftpConfig, ...partial.sftpConfig },
    security: { ...DEFAULT_APP_SETTINGS.security, ...partial.security },
    options: { ...DEFAULT_APP_SETTINGS.options, ...partial.options },
    timezone,
  };
}
