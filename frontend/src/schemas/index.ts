import { z } from "zod";

export const orderStatusSchema = z.enum([
  "Généré",
  "Revue requise",
  "Partiel",
  "Rejeté",
  "Doublon",
  "SFTP échoué",
  "À revoir",
  "À vérifier",
  "Bloqué",
  "Validé",
]);

export const updateOrderHeaderSchema = z.object({
  clientName: z.string().min(1, "Client requis").optional(),
  customerOrderNumber: z.string().min(1, "N° commande requis").optional(),
  documentReference: z.string().optional(),
  orderDate: z.string().nullable().optional(),
  requestedDeliveryDate: z.string().nullable().optional(),
  currency: z.string().length(3).optional(),
  incoterm: z.string().optional(),
  deliveryMode: z.string().optional(),
  globalComment: z.string().optional(),
});

export const updateOrderLineSchema = z.object({
  customerReference: z.string().optional(),
  boschArticle: z.string().min(1, "Article Bosch requis").optional(),
  designation: z.string().optional(),
  quantity: z.number().positive("Quantité positive requise").optional(),
  unit: z.string().min(1, "Unité requise").optional(),
  unitPrice: z.number().min(0).optional(),
  comment: z.string().optional(),
  status: z.enum(["OK", "À vérifier", "Corrigé manuellement", "Bloqué"]).optional(),
});

export const addOrderLineSchema = z.object({
  customerReference: z.string().default(""),
  boschArticle: z.string().min(1, "Article Bosch requis"),
  designation: z.string().default(""),
  quantity: z.number().positive(),
  unit: z.string().min(1),
  unitPrice: z.number().min(0).default(0),
  comment: z.string().optional(),
});

export const historyFiltersSchema = z.object({
  search: z.string().optional(),
  dateFrom: z.string().optional(),
  dateTo: z.string().optional(),
  client: z.string().optional(),
  status: orderStatusSchema.or(z.literal("")).optional(),
  page: z.number().int().positive().default(1),
  pageSize: z.number().int().positive().max(100).default(10),
});

export const appSettingsSchema = z.object({
  ediProfile: z.string(),
  standard: z.string(),
  version: z.string(),
  defaultIncoterm: z.string(),
  currency: z.string(),
  documentLanguage: z.string(),
  timezone: z.string(),
  connectorConfig: z.object({
    apiBaseUrl: z.string(),
    dbSyncEnabled: z.boolean(),
    csvDelimiter: z.string().min(1).max(1),
    sftpProfile: z.string(),
  }),
  validation: z.object({
    autoValidationThreshold: z.number().int().min(0).max(100),
    requireCustomerReference: z.boolean(),
    requireDeliveryDate: z.boolean(),
    blockOnAmountMismatch: z.boolean(),
    duplicateWindowDays: z.number().int().min(1).max(365),
  }),
  notifications: z.object({
    emailEnabled: z.boolean(),
    emailRecipients: z.string(),
    notifyOnSuccess: z.boolean(),
    notifyOnFailure: z.boolean(),
    webhookEnabled: z.boolean(),
    webhookUrl: z.string(),
  }),
  sftpConfig: z.object({
    enabled: z.boolean(),
    host: z.string(),
    port: z.number().int().min(1).max(65535),
    username: z.string(),
    remotePath: z.string(),
    fileNamePattern: z.string(),
  }),
  security: z.object({
    enforceAuth: z.boolean(),
    sessionTimeoutMinutes: z.number().int().min(15).max(1440),
    maxLoginAttempts: z.number().int().min(1).max(20),
    auditLogEnabled: z.boolean(),
    ipAllowlist: z.string(),
  }),
  options: z.object({
    autoValidateAbove90: z.boolean(),
    detectDuplicates: z.boolean(),
    autoSftp: z.boolean(),
    manualReviewOnAnomaly: z.boolean(),
    notifyOnDuplicate: z.boolean(),
  }),
});

export type UpdateOrderHeaderForm = z.infer<typeof updateOrderHeaderSchema>;
export type UpdateOrderLineForm = z.infer<typeof updateOrderLineSchema>;
export type AddOrderLineForm = z.infer<typeof addOrderLineSchema>;
export type HistoryFiltersForm = z.infer<typeof historyFiltersSchema>;
export type AppSettingsForm = z.infer<typeof appSettingsSchema>;
