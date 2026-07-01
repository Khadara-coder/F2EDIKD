import type {
  AppSettings,
  ConversionHistoryItem,
  DashboardMetrics,
  ExtractionPreview,
  GenerateEdifactResult,
  HistoryFilters,
  HistoryResponse,
  MasterDataClient,
  MasterDataSummary,
  OrderReview,
  ReviewQueueItem,
  SystemHealth,
  UpdateOrderHeaderPayload,
  UpdateOrderLinePayload,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message ?? body.detail ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  getSystemHealth: () => request<SystemHealth>("/health/system"),

  getDashboardMetrics: () => request<DashboardMetrics>("/dashboard/metrics"),

  getReviewQueue: () => request<ReviewQueueItem[]>("/dashboard/review-queue"),

  getOrdersList: () => request<ReviewQueueItem[]>("/orders"),

  getRecentConversions: () =>
    request<ConversionHistoryItem[]>("/dashboard/recent-conversions"),

  uploadPdf: async (file: File) => {
    const form = new FormData();
    form.append("pdf", file);
    const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const detail = body.detail ?? body.message;
      throw new Error(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(", ") || "Échec de l'upload"
            : "Échec de l'upload",
      );
    }
    return res.json() as Promise<{ uploadId: string }>;
  },

  launchExtractionJob: (uploadId: string) =>
    request<ExtractionPreview>(`/upload/${uploadId}/extract`, { method: "POST" }),

  getOrderReview: (orderId: string) =>
    request<OrderReview>(`/orders/${orderId}/review`),

  updateOrderHeader: (orderId: string, payload: UpdateOrderHeaderPayload) =>
    request<OrderReview>(`/orders/${orderId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  updateOrderPartner: (
    partnerId: string,
    payload: Partial<{ partnerCode: string; partnerName: string }>,
  ) =>
    request(`/orders/partners/${partnerId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  updateOrderLine: (lineId: string, payload: UpdateOrderLinePayload) =>
    request(`/orders/lines/${lineId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  addOrderLine: (
    orderId: string,
    payload: UpdateOrderLinePayload & { lineNumber?: number },
  ) =>
    request(`/orders/${orderId}/lines`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteOrderLine: (lineId: string) =>
    request(`/orders/lines/${lineId}`, { method: "DELETE" }),

  resolveAnomaly: (
    anomalyId: string,
    action: "corrected" | "ignored" | "blocking",
  ) =>
    request(`/orders/anomalies/${anomalyId}`, {
      method: "PATCH",
      body: JSON.stringify({ action }),
    }),

  generateEdifact: (orderId: string) =>
    request<GenerateEdifactResult>(`/orders/${orderId}/generate-edifact`, {
      method: "POST",
    }),

  getHistory: (filters: HistoryFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") params.set(k, String(v));
    });
    return request<HistoryResponse>(`/conversions/history?${params}`);
  },

  getMasterData: (type: string, search?: string) => {
    const params = new URLSearchParams({ type });
    if (search) params.set("search", search);
    return request<{ summary: MasterDataSummary; clients: MasterDataClient[] }>(
      `/master-data?${params}`,
    );
  },

  getSettings: () => request<AppSettings>("/settings"),

  updateSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>("/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  testConnector: (connector: string) =>
    request<{ status: string }>(`/settings/test-connector/${connector}`, {
      method: "POST",
    }),
};
