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

export interface OrderReview {
  order: {
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
  };
  partners: Array<{
    partnerId: string;
    orderId: string;
    partnerFunction: string;
    partnerCode: string;
    partnerName: string;
    addressLine1: string;
    postalCode: string;
    city: string;
    country: string;
    confidence: number;
    manuallyEdited?: boolean;
  }>;
  lines: Array<{
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
  }>;
  anomalies: Array<{
    anomalyId: string;
    orderId: string;
    lineId?: string;
    severity: string;
    fieldName?: string;
    message: string;
    status: string;
    createdAt: string;
  }>;
  traceability: Array<{
    id: string;
    label: string;
    status: string;
    timestamp?: string;
  }>;
  edifactReady: boolean;
  pdfUrl?: string;
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
  steps: Array<{ id: string; label: string; status: string }>;
}

export interface HistoryFilters {
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  client?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export interface HistoryResponse {
  kpis: {
    totalProcessed: number;
    autoValidationRate: number;
    autoValidatedCount: number;
    averageTimeSeconds: number;
    errors: number;
    errorRate: number;
  };
  rows: Array<{
    conversionId: string;
    orderId: string;
    fileName: string;
    clientName: string;
    customerOrderNumber: string;
    documentReference: string;
    processedAt: string;
    status: OrderStatus;
    confidence: number;
  }>;
  total: number;
  page: number;
  pageSize: number;
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
  message?: string;
  errors?: string[];
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
    apiExtraction: "connected" | "disconnected";
    database: "connected" | "disconnected";
    csvExport: "connected" | "disconnected";
    sftp: "connected" | "disconnected";
  };
  options: {
    autoValidateAbove90: boolean;
    detectDuplicates: boolean;
    autoSftp: boolean;
    manualReviewOnAnomaly: boolean;
    notifyOnDuplicate: boolean;
  };
}
