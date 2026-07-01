/**
 * In-memory mock store for local development.
 * Replace with Databricks queries when MOCK_MODE=false.
 */
import { v4 as uuidv4 } from "uuid";
import type {
  AppSettings,
  ExtractionPreview,
  GenerateEdifactResult,
  HistoryFilters,
  HistoryResponse,
  OrderReview,
  UpdateOrderHeaderPayload,
  UpdateOrderLinePayload,
} from "../types.js";

// Rexel sample data (matches frontend mockData)
const MOCK_ORDER_ID = "ord-rexel-026545008";

let orderReview: OrderReview = structuredClone(getInitialOrderReview());
let settings: AppSettings = structuredClone(getInitialSettings());

function getInitialOrderReview(): OrderReview {
  return {
    order: {
      orderId: MOCK_ORDER_ID,
      uploadId: "upl-rexel-001",
      fileName: "Rexel_BOT_CM1_4513_CDE_026545008.PDF",
      clientName: "Rexel",
      customerOrderNumber: "026545008",
      documentReference: "15021368",
      orderDate: null,
      requestedDeliveryDate: "2026-07-05",
      currency: "EUR",
      incoterm: "DAP",
      deliveryMode: "Messagerie",
      messageType: "ORDERS",
      vendor: "CM1",
      totalAmount: 2340,
      globalConfidence: 89,
      status: "Revue requise",
      reviewRequired: true,
      lineCount: 5,
      createdAt: "2025-06-30T10:42:00Z",
      updatedAt: "2025-06-30T10:42:00Z",
    },
    partners: [
      { partnerId: "p-soldto-1", orderId: MOCK_ORDER_ID, partnerFunction: "soldto", partnerCode: "REXEL FRANCE", partnerName: "REXEL FRANCE", addressLine1: "5 Rue des Entrepreneurs", postalCode: "69120", city: "Vaulx-en-Velin", country: "FR", confidence: 96 },
      { partnerId: "p-shipto-1", orderId: MOCK_ORDER_ID, partnerFunction: "shipto", partnerCode: "CHANTIER LYON PART-DIEU", partnerName: "CHANTIER LYON PART-DIEU", addressLine1: "12 Rue de la République", postalCode: "69003", city: "Lyon", country: "FR", confidence: 96 },
      { partnerId: "p-billto-1", orderId: MOCK_ORDER_ID, partnerFunction: "billto", partnerCode: "REXEL FRANCE", partnerName: "REXEL FRANCE", addressLine1: "5 Rue des Entrepreneurs", postalCode: "69120", city: "Vaulx-en-Velin", country: "FR", confidence: 95 },
      { partnerId: "p-payer-1", orderId: MOCK_ORDER_ID, partnerFunction: "payer", partnerCode: "REXEL FRANCE", partnerName: "REXEL FRANCE", addressLine1: "5 Rue des Entrepreneurs", postalCode: "69120", city: "Vaulx-en-Velin", country: "FR", confidence: 95 },
    ],
    lines: [
      { lineId: "ln-1", orderId: MOCK_ORDER_ID, lineNumber: 1, customerReference: "8716142345678", boschArticle: "7736501437", designation: "Junkers Cerapur Comfort ZWB 24-1 DE 23", quantity: 2, unit: "PCE", unitPrice: 450, amount: 900, confidence: 95, status: "OK" },
      { lineId: "ln-2", orderId: MOCK_ORDER_ID, lineNumber: 2, customerReference: "8716142345685", boschArticle: "7736501444", designation: "Junkers Cerapur Comfort ZWB 28-1 DE 23", quantity: 1, unit: "PCE", unitPrice: 520, amount: 520, confidence: 92, status: "OK" },
      { lineId: "ln-3", orderId: MOCK_ORDER_ID, lineNumber: 3, customerReference: "BGL 25-550", boschArticle: "BGL 25-550 ?", designation: "Kit de raccordement", quantity: 3, unit: "PCE", unitPrice: 180, amount: 540, confidence: 72, status: "À vérifier", comment: "Article partiellement reconnu" },
      { lineId: "ln-4", orderId: MOCK_ORDER_ID, lineNumber: 4, customerReference: "8716142345701", boschArticle: "7736501451", designation: "Thermostat d'ambiance CR10", quantity: 5, unit: "PCE", unitPrice: 76, amount: 380, confidence: 94, status: "OK" },
      { lineId: "ln-5", orderId: MOCK_ORDER_ID, lineNumber: 5, customerReference: "PORT", boschArticle: "PORTSFAB", designation: "Frais de port fournisseur", quantity: 1, unit: "PCE", unitPrice: 0, amount: 0, confidence: 100, status: "OK" },
    ],
    anomalies: [
      { anomalyId: "an-1", orderId: MOCK_ORDER_ID, severity: "error", fieldName: "orderDate", message: "La date de commande extraite n'est pas valide", status: "Ouverte", createdAt: "2025-06-30T10:42:05Z" },
      { anomalyId: "an-2", orderId: MOCK_ORDER_ID, lineId: "ln-3", severity: "warning", fieldName: "boschArticle", message: "Ligne 3 : article Bosch à confirmer (BGL 25-550 ?)", status: "Ouverte", createdAt: "2025-06-30T10:42:06Z" },
      { anomalyId: "an-3", orderId: MOCK_ORDER_ID, severity: "info", fieldName: "deliveryAddress", message: "Adresse de livraison détectée avec forte confiance (96 %)", status: "Corrigée", createdAt: "2025-06-30T10:42:07Z" },
    ],
    traceability: [
      { id: "1", label: "PDF reçu", status: "completed", timestamp: "2025-06-30T10:42:00Z" },
      { id: "2", label: "Extraction OCR", status: "completed", timestamp: "2025-06-30T10:42:02Z" },
      { id: "3", label: "Mapping client", status: "completed", timestamp: "2025-06-30T10:42:04Z" },
      { id: "4", label: "Contrôles métier", status: "completed", timestamp: "2025-06-30T10:42:05Z" },
      { id: "5", label: "Revue manuelle", status: "current" },
      { id: "6", label: "Génération EDIFACT", status: "pending" },
      { id: "7", label: "Export SFTP", status: "pending" },
    ],
    edifactReady: true,
  };
}

function getInitialSettings(): AppSettings {
  return {
    ediProfile: "ELM_STANDARD",
    standard: "UN/EDIFACT",
    version: "D.96A",
    defaultIncoterm: "DAP - Delivered At Place",
    currency: "EUR - Euro",
    documentLanguage: "Français (FR)",
    timezone: "(UTC+01:00) Europe/Paris",
    connectors: {
      apiExtraction: "disconnected",
      database: "connected",
      csvExport: "connected",
      sftp: "connected",
    },
    options: {
      autoValidateAbove90: true,
      detectDuplicates: true,
      autoSftp: true,
      manualReviewOnAnomaly: true,
      notifyOnDuplicate: false,
    },
  };
}

function recalcTotal(orderId: string) {
  const review = orderReview.order.orderId === orderId ? orderReview : null;
  if (!review) return;
  review.order.totalAmount = review.lines.reduce((s, l) => s + l.amount, 0);
  review.order.lineCount = review.lines.length;
}

export const mockStore = {
  getSystemHealth: () => ({
    api: "disconnected" as const,
    database: "connected" as const,
    csv: "connected" as const,
  }),

  getDashboardMetrics: () => ({
    today: 14,
    generated: 9,
    reviewRequired: 3,
    rejected: 1,
    partial: 1,
    duplicates: 0,
    sftpFailed: 0,
    total: 14,
    statusDistribution: [
      { label: "Générés", count: 9, percent: 64, color: "bg-emerald-500" },
      { label: "Revue requise", count: 3, percent: 21, color: "bg-amber-500" },
      { label: "Partiels", count: 1, percent: 7, color: "bg-violet-500" },
      { label: "Rejetés", count: 1, percent: 7, color: "bg-red-500" },
    ],
    processingFlow: {
      pdfReceived: 14,
      edifactGenerated: 9,
      manualValidations: 3,
      sftpExports: 9,
    },
  }),

  getReviewQueue: () => [
    { orderId: MOCK_ORDER_ID, fileName: "Rexel_BOT_CM1_4513_CDE_026545008.PDF", clientName: "Rexel", confidence: 86, issue: "Date invalide", date: "2025-06-30T10:42:00Z", status: "À revoir" as const },
    { orderId: "ord-leroy-002", fileName: "LeroyMerlin_CDE_884521.PDF", clientName: "Leroy Merlin", confidence: 78, issue: "Ship-to ambigu", date: "2025-06-30T09:15:00Z", status: "À vérifier" as const },
    { orderId: "ord-cedeo-003", fileName: "Cedeo_Commande_77234.PDF", clientName: "Cedeo", confidence: 65, issue: "Article inconnu", date: "2025-06-30T08:30:00Z", status: "Bloqué" as const },
  ],

  getRecentConversions: () => [
    { conversionId: "conv-001", orderId: MOCK_ORDER_ID, fileName: "Rexel_BOT_CM1_4513_CDE_026545008.PDF", clientName: "Rexel", status: "Généré" as const, date: "2025-06-30T10:42:00Z", hasEdifact: true, hasPdf: true },
    { conversionId: "conv-002", orderId: "ord-sonepar-002", fileName: "Sonepar_CDE_445821.PDF", clientName: "Sonepar", status: "Partiel" as const, date: "2025-06-30T09:30:00Z", hasEdifact: true, hasPdf: true },
  ],

  saveUpload: (fileName: string, fileSize: number) => {
    const uploadId = uuidv4();
    return { uploadId, fileName, fileSize };
  },

  launchExtraction: (uploadId: string, fileName: string, fileSize: number): ExtractionPreview => ({
    uploadId,
    orderId: MOCK_ORDER_ID,
    fileName,
    fileSize,
    pageCount: 3,
    detectedAt: new Date().toISOString(),
    clientName: "Rexel France",
    clientCode: "026545008",
    deliveryAddress: "REXEL FRANCE - AGENCE DE LYON, 5 RUE DES ENTREPRENEURS, 69120 VAULX-EN-VELIN, FRANCE",
    customerOrderNumber: "CDE_026545008",
    orderDate: "2025-06-30",
    lineCount: 12,
    uniqueArticles: 7,
    totalAmount: 5842.35,
    currency: "EUR",
    steps: [
      { id: "1", label: "PDF reçu", status: "completed" },
      { id: "2", label: "Texte extrait", status: "completed" },
      { id: "3", label: "Données détectées", status: "completed" },
      { id: "4", label: "Sold-to résolu", status: "completed" },
      { id: "5", label: "Ship-to résolu", status: "completed" },
      { id: "6", label: "Articles validés", status: "completed" },
      { id: "7", label: "Doublon contrôlé", status: "completed" },
      { id: "8", label: "EDIFACT préparé", status: "completed" },
      { id: "9", label: "Aperçu du résultat", status: "current" },
      { id: "10", label: "Revue manuelle", status: "pending" },
      { id: "11", label: "Fichier .tst", status: "pending" },
    ],
  }),

  getOrderReview: (orderId: string): OrderReview | null => {
    if (orderId === orderReview.order.orderId) return structuredClone(orderReview);
    return null;
  },

  updateOrderHeader: (orderId: string, payload: UpdateOrderHeaderPayload) => {
    if (orderReview.order.orderId !== orderId) return null;
    Object.assign(orderReview.order, payload, { updatedAt: new Date().toISOString() });
    if (payload.orderDate) {
      orderReview.anomalies = orderReview.anomalies.map((a) =>
        a.fieldName === "orderDate" ? { ...a, status: "Corrigée" as const } : a,
      );
    }
    return structuredClone(orderReview);
  },

  updateOrderPartner: (partnerId: string, payload: { partnerCode?: string; partnerName?: string }) => {
    const p = orderReview.partners.find((x) => x.partnerId === partnerId);
    if (!p) return null;
    Object.assign(p, payload, { manuallyEdited: true });
    return structuredClone(orderReview);
  },

  updateOrderLine: (lineId: string, payload: UpdateOrderLinePayload) => {
    const line = orderReview.lines.find((l) => l.lineId === lineId);
    if (!line) return null;
    Object.assign(line, payload, { manuallyEdited: true });
    if (payload.quantity !== undefined || payload.unitPrice !== undefined) {
      line.amount = (line.quantity ?? 0) * (line.unitPrice ?? 0);
    }
    recalcTotal(orderReview.order.orderId);
    return structuredClone(orderReview);
  },

  addOrderLine: (orderId: string, payload: UpdateOrderLinePayload) => {
    if (orderReview.order.orderId !== orderId) return null;
    const lineNumber = orderReview.lines.length + 1;
    const qty = payload.quantity ?? 1;
    const price = payload.unitPrice ?? 0;
    orderReview.lines.push({
      lineId: uuidv4(),
      orderId,
      lineNumber,
      customerReference: payload.customerReference ?? "",
      boschArticle: payload.boschArticle ?? "",
      designation: payload.designation ?? "",
      quantity: qty,
      unit: payload.unit ?? "PCE",
      unitPrice: price,
      amount: qty * price,
      confidence: 100,
      status: "Corrigé manuellement",
      comment: payload.comment,
      manuallyEdited: true,
    });
    recalcTotal(orderId);
    return structuredClone(orderReview);
  },

  deleteOrderLine: (lineId: string) => {
    orderReview.lines = orderReview.lines.filter((l) => l.lineId !== lineId);
    orderReview.lines.forEach((l, i) => { l.lineNumber = i + 1; });
    recalcTotal(orderReview.order.orderId);
    return structuredClone(orderReview);
  },

  resolveAnomaly: (anomalyId: string, action: "corrected" | "ignored" | "blocking") => {
    const statusMap = { corrected: "Corrigée", ignored: "Ignorée", blocking: "Bloquante" } as const;
    const a = orderReview.anomalies.find((x) => x.anomalyId === anomalyId);
    if (!a) return null;
    a.status = statusMap[action];
    return structuredClone(orderReview);
  },

  generateEdifact: (orderId: string): GenerateEdifactResult => {
    if (orderReview.order.orderId !== orderId) {
      return { success: false, message: "Commande introuvable" };
    }
    const blocking = orderReview.anomalies.filter(
      (a) => a.status === "Ouverte" && (a.severity === "blocking" || a.severity === "error"),
    );
    if (blocking.length) {
      return { success: false, errors: blocking.map((a) => a.message) };
    }
    if (!orderReview.order.orderDate) {
      return { success: false, errors: ["Date commande invalide"] };
    }
    const fileName = `ORDERS_${orderReview.order.customerOrderNumber}_${Date.now()}.tst`;
    orderReview.order.status = "Généré";
    orderReview.traceability = orderReview.traceability.map((s) =>
      s.label === "Génération EDIFACT" ? { ...s, status: "completed" as const } : s,
    );
    return { success: true, fileName };
  },

  getHistory: (filters: HistoryFilters): HistoryResponse => ({
    kpis: {
      totalProcessed: 1248,
      autoValidationRate: 87.6,
      autoValidatedCount: 1093,
      averageTimeSeconds: 154,
      errors: 32,
      errorRate: 2.6,
    },
    rows: [
      { conversionId: "conv-h-1", orderId: MOCK_ORDER_ID, fileName: "Rexel_BOT_CM1_4513_CDE_026545008.PDF", clientName: "Rexel", customerOrderNumber: "026545008", documentReference: "15021368", processedAt: "2025-06-30T10:42:00Z", status: "Généré", confidence: 96 },
      { conversionId: "conv-h-2", orderId: "ord-leroy-002", fileName: "LeroyMerlin_CDE_884521.PDF", clientName: "Leroy Merlin", customerOrderNumber: "884521", documentReference: "LM-2025-4421", processedAt: "2025-06-30T09:30:00Z", status: "Revue requise", confidence: 78 },
    ],
    total: 1248,
    page: filters.page ?? 1,
    pageSize: filters.pageSize ?? 10,
  }),

  getMasterData: () => ({
    summary: {
      activeClients: 248,
      shiptoCount: 1923,
      articlesCount: 12480,
      rulesCount: 18,
      lastSync: "2025-06-30T10:42:00Z",
      monthlyGrowth: { clients: 8, shipto: 37, articles: 215, rules: 1 },
    },
    clients: [
      { clientId: "cli-rexel", name: "REXEL FRANCE", soldto: "1056400123", vat: "FR12345678901", channel: "Distribution", division: "Thermique", status: "Actif" as const, updatedAt: "2025-06-28T14:00:00Z", currency: "EUR", country: "FR", gln: "3015981600108", ediMappings: { unb: "0004 (Party)", nadBy: "NAD+BY (Buyer)", nadDp: "NAD+DP (Ship-to par défaut)", gln: "3015981600108" } },
      { clientId: "cli-leroy", name: "LEROY MERLIN", soldto: "1056400456", vat: "FR98765432109", channel: "Grande distribution", division: "Thermique", status: "Actif" as const, updatedAt: "2025-06-27T10:00:00Z" },
    ],
  }),

  getSettings: () => structuredClone(settings),

  updateSettings: (payload: Partial<AppSettings>) => {
    settings = { ...settings, ...payload, options: { ...settings.options, ...payload.options } };
    return structuredClone(settings);
  },

  testConnector: (connector: string) => ({
    status: connector === "apiExtraction" ? "disconnected" : "connected",
  }),
};
