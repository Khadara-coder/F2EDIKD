export type OrderStatus =
  | "Généré"
  | "Revue requise"
  | "Rejeté"
  | "Doublon"
  | "SFTP échoué"
  | "À revoir"
  | "À vérifier"
  | "Bloqué"
  | "Validé"
  // Nouveaux statuts workflow
  | "À traiter"
  | "En attente"
  | "Envoyé SAP"
  | "Transféré"
  | "Échec SAP";

export type GestionnaireUser = {
  userId: string;
  username: string;
  displayName: string;
  email?: string;
  sapId?: string;
  role?: "adv" | "admin";
  createdAt?: string;
};

export type LineStatus = "OK" | "À vérifier" | "Corrigé manuellement" | "Bloqué";

export type AnomalySeverity = "info" | "warning" | "error" | "blocking";

export type AnomalyStatus = "Ouverte" | "Corrigée" | "Ignorée" | "Bloquante";

export type PartnerFunction = "soldto" | "shipto" | "billto" | "payer";

export type ConnectorStatus = "connected" | "disconnected";

export type AppRole = "admin" | "adv";

export interface CurrentUser {
  actor: string;
  username?: string;     // identifiant DB (login)
  displayName?: string;  // Prénom Nom
  role: AppRole;
  authenticated: boolean;
}

export interface AccessRoleItem {
  actor: string;
  display_name?: string;
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
  sftp: ConnectorStatus;
  ai?: ConnectorStatus;
  aiProvider?: string;
  aiDetail?: string;
}

export interface DashboardMetrics {
  today: number;
  generated: number;
  reviewRequired: number;
  rejected: number;
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
  createdAt?: string;
  updatedAt?: string;
  status: OrderStatus;
  processedAt?: string;
  sapSentAt?: string;
  sapSentBy?: string;
  processedBy?: string;
  assignedTo?: string;       // username du gestionnaire assigné
  holdReason?: string;       // motif mise en attente
  transferredFrom?: string;  // username de celui qui a transféré
  transferredTo?: string;    // username du destinataire
  transferNote?: string;     // note de transfert
  source?: "ui" | "n8n" | "api" | "unknown";
  action?: string | null;
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
  rejectionCode?: string;
  buttonAccept?: string;
  buttonReject?: string;
  autoActionAccept?: string;
  autoActionReject?: string;
  actionMode?: string;
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
  syncStatus?: string;
  syncCommit?: string;
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
  city?: string;
  postalCode?: string;
  address?: string;
  language?: string;
  gln?: string;
  fields?: Record<string, string>;
  ediMappings?: {
    unb?: string;
    nadBy?: string;
    nadDp?: string;
    duns?: string;
    gln?: string;
  };
}

export interface MasterDataShipToRow {
  id: string;
  shipto: string;
  soldto: string;
  name: string;
  country?: string;
  city?: string;
  postalCode?: string;
  address?: string;
  partnerFunction?: string;
  advManager?: string;
  updatedAt?: string;
  fields?: Record<string, string>;
}

export interface MasterDataArticleRow {
  id: string;
  materialId: string;
  description: string;
  updatedAt?: string;
  fields?: Record<string, string>;
}

export interface MasterDataRuleRow {
  id: string;
  code: string;
  severity: string;
  businessStatus: string;
  message: string;
  retryAllowed: boolean;
  manualReview: boolean;
  buttonAccept?: string;
  buttonReject?: string;
  autoActionAccept?: string;
  autoActionReject?: string;
  mode?: string;
  fields?: Record<string, string>;
}

export interface MasterDataResponse {
  summary: MasterDataSummary;
  type: string;
  clients: MasterDataClient[];
  rows: Array<MasterDataClient | MasterDataShipToRow | MasterDataArticleRow | MasterDataRuleRow>;
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
  masterdataN8nConfig: {
    enabled: boolean;
    webhookUrl: string;
    authHeader: string;
    timeoutSeconds: number;
  };
  aiProvider: "databricks" | "openai" | "ollama" | "custom";
  databricksConfig: {
    host: string;
    apiBaseUrl: string;
    modelEndpoint: string;
    sqlWarehouseEnabled: boolean;
    warehouseId: string;
    catalog: string;
    schema: string;
    configProfile: string;
    llmEnabled: boolean;
  };
  openaiConfig: {
    baseUrl: string;
    model: string;
  };
  ollamaConfig: {
    baseUrl: string;
    model: string;
  };
  customAiConfig: {
    baseUrl: string;
    model: string;
    chatPath: string;
    authHeader: string;
    authScheme: string;
    customHeaders: string;
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
    hasPassword: boolean;
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
