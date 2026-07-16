export type OrderStatus =
  | "Généré"
  | "Revue requise"
  | "Partiel"
  | "Rejeté"
  | "Doublon"
  | "SFTP échoué"
  | "À revoir"
  | "À vérifier"
  | "Bloqué"
  | "Validé";

export type LineStatus = "OK" | "À vérifier" | "Corrigé manuellement" | "Bloqué";

export type AnomalySeverity = "info" | "warning" | "error" | "blocking";

export type AnomalyStatus = "Ouverte" | "Corrigée" | "Ignorée" | "Bloquante";

export type PartnerFunction = "soldto" | "shipto" | "billto" | "payer";

export type ConnectorStatus = "connected" | "disconnected";

export type AppRole = "admin" | "adv";

export interface CurrentUser {
  actor: string;
  role: AppRole;
  authenticated: boolean;
}

export interface AccessRoleItem {
  actor: string;
  role: AppRole;
  source: "env" | "db";
  is_active: boolean;
  updated_at: string | null;
  updated_by: string;
  effective_role: AppRole;
}

export interface AccessRolesResponse {
  items: AccessRoleItem[];
  env_admin_count: number;
  db_assignment_count: number;
}

export interface SystemHealth {
  api: ConnectorStatus;
  database: ConnectorStatus;
  csv: ConnectorStatus;
}

export interface DashboardMetrics {
  today: number;
  generated: number;
  reviewRequired: number;
  rejected: number;
  partial: number;
  duplicates: number;
  sftpFailed: number;
  total: number;
  statusDistribution: { label: string; count: number; percent: number; color: string }[];
  processingFlow: {
    pdfReceived: number;
    edifactGenerated: number;
    manualValidations: number;
    sftpExports: number;
  };
}

export interface ReviewQueueItem {
  orderId: string;
  fileName: string;
  clientName: string;
  confidence: number;
  issue: string;
  date: string;
  status: OrderStatus;
}

export interface ConversionHistoryItem {
  conversionId: string;
  orderId: string;
  fileName: string;
  clientName: string;
  status: OrderStatus;
  date: string;
  hasEdifact: boolean;
  hasPdf: boolean;
}

export interface PdfUpload {
  uploadId: string;
  fileName: string;
  fileSize: number;
  filePath: string;
  uploadedAt: string;
  uploadedBy: string;
  status: string;
  pageCount?: number;
}

export type PartnerEditSource = "manual" | "auto";

export type PartnerFieldKey =
  | "partnerCode"
  | "partnerName"
  | "addressLine1"
  | "postalCode"
  | "city"
  | "country";

export interface OrderPartner {
  partnerId: string;
  orderId: string;
  partnerFunction: PartnerFunction;
  partnerCode: string;
  partnerName: string;
  addressLine1: string;
  addressLine2?: string;
  postalCode: string;
  city: string;
  country: string;
  confidence: number;
  manuallyEdited?: boolean;
  editedFields?: Partial<Record<PartnerFieldKey, PartnerEditSource>>;
  previousValue?: string;
}

export interface OrderLine {
  lineId: string;
  orderId: string;
  lineNumber: number;
  customerReference: string;
  boschArticle: string;
  designation: string;
  quantity: number;
  unit: string;
  unitPrice: number;
  amount: number;
  confidence: number;
  status: LineStatus;
  comment?: string;
  manuallyEdited?: boolean;
}

export interface OrderAnomaly {
  anomalyId: string;
  orderId: string;
  lineId?: string;
  severity: AnomalySeverity;
  fieldName?: string;
  message: string;
  status: AnomalyStatus;
  createdAt: string;
}

export interface TraceabilityStep {
  id: string;
  label: string;
  status: "completed" | "current" | "pending";
  timestamp?: string;
}

export interface Order {
  orderId: string;
  uploadId: string;
  fileName: string;
  clientName: string;
  customerOrderNumber: string;
  documentReference: string;
  orderDate: string | null;
  requestedDeliveryDate: string | null;
  currency: string;
  incoterm: string;
  deliveryMode: string;
  messageType: string;
  vendor: string;
  totalAmount: number;
  globalConfidence: number;
  status: OrderStatus;
  reviewRequired: boolean;
  lineCount: number;
  createdAt: string;
  updatedAt: string;
  manuallyEditedFields?: string[];
}

export interface OrderReview {
  order: Order;
  partners: OrderPartner[];
  lines: OrderLine[];
  anomalies: OrderAnomaly[];
  traceability: TraceabilityStep[];
  pdfUrl?: string;
  edifactReady: boolean;
}

export interface ExtractionPreview {
  uploadId: string;
  orderId: string;
  fileName: string;
  fileSize: number;
  pageCount: number;
  detectedAt: string;
  clientName: string;
  clientCode: string;
  deliveryAddress: string;
  customerOrderNumber: string;
  orderDate: string | null;
  lineCount: number;
  uniqueArticles: number;
  totalAmount: number;
  currency: string;
  steps: { id: string; label: string; status: "completed" | "current" | "pending" }[];
}

export interface HistoryFilters {
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  client?: string;
  status?: OrderStatus | "";
  page?: number;
  pageSize?: number;
}

export interface HistoryKpis {
  totalProcessed: number;
  autoValidationRate: number;
  autoValidatedCount: number;
  averageTimeSeconds: number;
  errors: number;
  errorRate: number;
}

export interface HistoryRow {
  conversionId: string;
  orderId: string;
  fileName: string;
  clientName: string;
  customerOrderNumber: string;
  documentReference: string;
  processedAt: string;
  status: OrderStatus;
  confidence: number;
}

export interface HistoryResponse {
  kpis: HistoryKpis;
  rows: HistoryRow[];
  total: number;
  page: number;
  pageSize: number;
}

export interface MasterDataSummary {
  activeClients: number;
  shiptoCount: number;
  articlesCount: number;
  rulesCount: number;
  lastSync: string;
  monthlyGrowth: { clients: number; shipto: number; articles: number; rules: number };
}

export interface MasterDataClient {
  clientId: string;
  name: string;
  soldto: string;
  vat: string;
  channel: string;
  division: string;
  status: "Actif" | "Inactif";
  updatedAt: string;
  currency?: string;
  country?: string;
  language?: string;
  gln?: string;
  ediMappings?: {
    unb?: string;
    nadBy?: string;
    nadDp?: string;
    duns?: string;
    gln?: string;
  };
}

export interface AppSettings {
  ediProfile: string;
  standard: string;
  version: string;
  defaultIncoterm: string;
  currency: string;
  documentLanguage: string;
  timezone: string;
  connectors: {
    apiExtraction: ConnectorStatus;
    database: ConnectorStatus;
    csvExport: ConnectorStatus;
    sftp: ConnectorStatus;
  };
  connectorConfig: {
    apiBaseUrl: string;
    dbSyncEnabled: boolean;
    csvDelimiter: string;
    sftpProfile: string;
  };
  validation: {
    autoValidationThreshold: number;
    requireCustomerReference: boolean;
    requireDeliveryDate: boolean;
    blockOnAmountMismatch: boolean;
    duplicateWindowDays: number;
  };
  notifications: {
    emailEnabled: boolean;
    emailRecipients: string;
    notifyOnSuccess: boolean;
    notifyOnFailure: boolean;
    webhookEnabled: boolean;
    webhookUrl: string;
  };
  sftpConfig: {
    enabled: boolean;
    host: string;
    port: number;
    username: string;
    remotePath: string;
    fileNamePattern: string;
  };
  security: {
    enforceAuth: boolean;
    sessionTimeoutMinutes: number;
    maxLoginAttempts: number;
    auditLogEnabled: boolean;
    ipAllowlist: string;
  };
  options: {
    autoValidateAbove90: boolean;
    detectDuplicates: boolean;
    autoSftp: boolean;
    manualReviewOnAnomaly: boolean;
    notifyOnDuplicate: boolean;
  };
}

export interface UpdateOrderHeaderPayload {
  clientName?: string;
  customerOrderNumber?: string;
  documentReference?: string;
  orderDate?: string | null;
  requestedDeliveryDate?: string | null;
  currency?: string;
  incoterm?: string;
  deliveryMode?: string;
  globalComment?: string;
}

export interface UpdateOrderLinePayload {
  customerReference?: string;
  boschArticle?: string;
  designation?: string;
  quantity?: number;
  unit?: string;
  unitPrice?: number;
  comment?: string;
  status?: LineStatus;
}

export interface GenerateEdifactResult {
  success: boolean;
  fileName?: string;
  content?: string;
  message?: string;
  errors?: string[];
}

export interface MasterDataCustomerRow {
  SOLDTO?: string;
  NAME?: string;
  STRAS?: string;
  ORT01?: string;
  PSTLZ?: string;
  LAND1?: string;
  VAT_NR?: string;
}

export interface MasterDataPartnerRow {
  SOLDTO?: string;
  SHIPTO?: string;
  NAME?: string;
  STRAS?: string;
  ORT01?: string;
  PSTLZ?: string;
  LAND1?: string;
}
