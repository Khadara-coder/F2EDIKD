import type {
  AccessRolesResponse,
  CurrentUser,
  AppSettings,
  ConversionHistoryItem,
  DashboardMetrics,
  ExtractionPreview,
  GenerateEdifactResult,
  HistoryFilters,
  HistoryResponse,
  MasterDataClient,
  MasterDataCustomerRow,
  MasterDataPartnerRow,
  MasterDataSummary,
  OrderReview,
  PartnerEditSource,
  PartnerFieldKey,
  ReviewQueueItem,
  SystemHealth,
  UpdateOrderHeaderPayload,
  UpdateOrderLinePayload,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const MD_API_BASE = API_BASE.replace(/\/api\/?$/, "") + "/api/masterdata";

export class ApiError extends Error {
  status: number;
  detail?: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let detail: unknown;
    try {
      const body = JSON.parse(text) as Record<string, unknown>;
      detail = body.message ?? body.detail ?? body.error;
    } catch {
      detail = text.trim().slice(0, 400) || undefined;
    }
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(", ")
          : `HTTP ${res.status}`;
    throw new ApiError(msg || `HTTP ${res.status}`, res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  getAuthModes: () => request<{ profile_login_enabled: boolean; workspace_sso_available: boolean; allowed_roles: string[] }>("/auth/modes"),

  loginWithProfile: (payload: { actor: string; role: "admin" | "adv"; password: string }) =>
    request<{ ok: boolean; actor: string; role: "admin" | "adv" }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  getCurrentUser: () => request<CurrentUser>("/me"),

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
    payload: Partial<Record<PartnerFieldKey, string>> & {
      editSource?: PartnerEditSource;
      editSources?: Partial<Record<PartnerFieldKey, PartnerEditSource>>;
    },
  ) =>
    request(`/orders/partners/${partnerId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  searchCustomers: (q: string, limit = 20) =>
    fetch(`${MD_API_BASE}/customers/search?q=${encodeURIComponent(q)}&limit=${limit}`).then(
      (res) => res.json() as Promise<{ results: MasterDataCustomerRow[] }>,
    ),

  searchPartners: (q: string, limit = 20) =>
    fetch(`${MD_API_BASE}/partners/search?q=${encodeURIComponent(q)}&limit=${limit}`).then(
      (res) => res.json() as Promise<{ results: MasterDataPartnerRow[] }>,
    ),

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

  getEdifactDownloadUrl: (orderId: string) => `${API_BASE}/orders/${orderId}/edifact`,

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

  getAccessRoles: () => request<AccessRolesResponse>("/admin/roles"),

  upsertAccessRole: (payload: { actor: string; role: "admin" | "adv" }) =>
    request<{ ok: boolean; actor: string; role: "admin" | "adv"; effective_role: "admin" | "adv" }>(
      "/admin/roles",
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),

  deleteAccessRole: (actor: string) =>
    request<{ ok: boolean; actor: string; removed: boolean; effective_role: "admin" | "adv" }>(
      `/admin/roles/${encodeURIComponent(actor)}`,
      { method: "DELETE" },
    ),
};
