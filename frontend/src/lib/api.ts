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
  MasterDataCustomerRow,
  MasterDataPartnerRow,
  MasterDataResponse,
  OrderReview,
  PartnerEditSource,
  PartnerFieldKey,
  ReviewQueueItem,
  SystemHealth,
  UpdateOrderHeaderPayload,
  UpdateOrderLinePayload,
} from "@/types";
import { mergeSettings } from "@/lib/defaultSettings";

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
    ...options,
    credentials: options?.credentials ?? "include",
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
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

function normalizeSettingsPayload(raw: unknown): AppSettings {
  const obj = (raw && typeof raw === "object") ? (raw as Record<string, unknown>) : {};
  const persisted = (obj.app_settings && typeof obj.app_settings === "object")
    ? (obj.app_settings as Record<string, unknown>)
    : obj;

  const profile = (obj.profile && typeof obj.profile === "object")
    ? (obj.profile as Record<string, unknown>)
    : {};
  const api = (obj.api && typeof obj.api === "object")
    ? (obj.api as Record<string, unknown>)
    : {};
  const sftp = (obj.sftp && typeof obj.sftp === "object")
    ? (obj.sftp as Record<string, unknown>)
    : {};
  const storageMode = (obj.storage_mode && typeof obj.storage_mode === "object")
    ? (obj.storage_mode as Record<string, unknown>)
    : {};
  const masterdata = (obj.masterdata && typeof obj.masterdata === "object")
    ? (obj.masterdata as Record<string, unknown>)
    : {};
  const customers = (masterdata.customers && typeof masterdata.customers === "object")
    ? (masterdata.customers as Record<string, unknown>)
    : {};

  const persistedWithDerived = {
    ...persisted,
    ediProfile:
      typeof persisted.ediProfile === "string"
        ? persisted.ediProfile
        : (typeof profile.name === "string" ? profile.name : undefined),
    connectors: {
      ...(persisted.connectors && typeof persisted.connectors === "object"
        ? (persisted.connectors as Record<string, unknown>)
        : {}),
      apiExtraction:
        (typeof api.status === "string" && api.status.toLowerCase() === "ok")
          ? "connected"
          : "disconnected",
      database:
        (typeof storageMode.persistent === "boolean" ? storageMode.persistent : true)
          ? "connected"
          : "disconnected",
      csvExport:
        (typeof customers.rows === "number" && customers.rows > 0)
          ? "connected"
          : "disconnected",
      sftp:
        (typeof sftp.configured === "boolean" && sftp.configured)
          ? "connected"
          : "disconnected",
    },
    sftpConfig: {
      ...(persisted.sftpConfig && typeof persisted.sftpConfig === "object"
        ? (persisted.sftpConfig as Record<string, unknown>)
        : {}),
      hasPassword:
        typeof (persisted.sftpConfig as Record<string, unknown> | undefined)?.hasPassword === "boolean"
          ? (persisted.sftpConfig as Record<string, unknown>).hasPassword
          : false,
    },
  };

  return mergeSettings(persistedWithDerived as Partial<AppSettings>);
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
    const res = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      body: form,
      credentials: "include",
    });
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
    fetch(`${MD_API_BASE}/customers/search?q=${encodeURIComponent(q)}&limit=${limit}`, {
      credentials: "include",
    }).then(
      (res) => res.json() as Promise<{ results: MasterDataCustomerRow[] }>,
    ),

  searchPartners: (q: string, limit = 20) =>
    fetch(`${MD_API_BASE}/partners/search?q=${encodeURIComponent(q)}&limit=${limit}`, {
      credentials: "include",
    }).then(
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

  addOrderLinesBulk: (
    orderId: string,
    lines: Array<Pick<UpdateOrderLinePayload, "boschArticle" | "quantity" | "unitPrice" | "unit">>,
  ) =>
    request(`/orders/${orderId}/lines/bulk`, {
      method: "POST",
      body: JSON.stringify({ lines }),
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

  saveOrder: (orderId: string) =>
    request<{ success: boolean; message?: string; blockers?: string[]; review?: unknown }>(
      `/orders/${orderId}/save`,
      { method: "POST" },
    ),

  sendToSap: (orderId: string, payload?: { force?: boolean; ignoreCooldown?: boolean }) =>
    request<{
      success: boolean;
      message?: string;
      alreadySent?: boolean;
      requiresConfirmation?: boolean;
      cooldownActive?: boolean;
      remainingSeconds?: number;
      cooldownSeconds?: number;
      resendAvailableAt?: string | null;
    }>(`/orders/${orderId}/send-sap`, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : undefined,
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
    const params = new URLSearchParams({ type, limit: "200" });
    if (search) params.set("search", search);
    return request<MasterDataResponse>(`/master-data?${params}`);
  },

  /** Manual masterdata sync - triggers configured n8n webhook by default. */
  syncMasterData: (opts?: { fromRepo?: boolean }) => {
    const params = new URLSearchParams({
      from_repo: opts?.fromRepo ? "true" : "false",
    });
    return request<{
      synced: number;
      failed: number;
      cache_reloaded: boolean;
      from_repo?: boolean;
      source?: string;
      commit?: string;
      async?: boolean;
      message: string;
    }>(`/masterdata/sync?${params}`, { method: "POST" });
  },

  importMasterDataCsv: async (kind: string, file: File) => {
    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    const res = await fetch(`${API_BASE}/masterdata/import`, {
      method: "POST",
      credentials: "include",
      body,
    });
    if (!res.ok) {
      const text = await res.text();
      let detail: unknown;
      try {
        const parsed = JSON.parse(text) as Record<string, unknown>;
        detail = parsed.detail ?? parsed.message ?? text;
      } catch {
        detail = text;
      }
      throw new ApiError(
        typeof detail === "string" ? detail : `HTTP ${res.status}`,
        res.status,
        detail,
      );
    }
    return res.json() as Promise<{ ok: boolean; message: string; rows?: number; kind?: string }>;
  },

  addMasterDataRow: (kind: string, fields: Record<string, string>) =>
    request<{ ok: boolean; message: string; rows?: number }>(`/masterdata/rows`, {
      method: "POST",
      body: JSON.stringify({ kind, fields }),
    }),

  getSettings: async () => {
    const raw = await request<unknown>("/settings");
    return normalizeSettingsPayload(raw);
  },

  updateSettings: (payload: Partial<AppSettings>) =>
    request<unknown>("/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }).then((raw) => normalizeSettingsPayload(raw)),

  testConnector: (connector: string, payload?: unknown) =>
    request<{ status: string; message?: string }>(`/settings/test-connector/${connector}`, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : undefined,
    }),

  updateSftpPassword: (password: string) =>
    request<{ ok: boolean; message: string }>("/settings/sftp-password", {
      method: "PUT",
      body: JSON.stringify({ password }),
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

  getApiKeys: () =>
    request<{
      ok: boolean;
      items: Array<{
        id: string;
        name: string;
        created_at: string;
        created_by: string;
        last_used_at: string | null;
        is_active: boolean;
      }>;
    }>("/admin/api-keys"),

  createApiKey: (payload: { name: string }) =>
    request<{
      ok: boolean;
      key_id: string;
      name: string;
      api_key: string;
      message: string;
    }>("/admin/api-keys", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteApiKey: (keyId: string) =>
    request<{ ok: boolean; key_id: string; removed: boolean }>(
      `/admin/api-keys/${encodeURIComponent(keyId)}`,
      { method: "DELETE" },
    ),

  testAiConnection: (payload: {
    provider: "databricks" | "openai" | "ollama" | "custom";
    token?: string;
    host?: string;
    modelEndpoint?: string;
    baseUrl?: string;
    model?: string;
    chatPath?: string;
    authHeader?: string;
    authScheme?: string;
    customHeaders?: string;
  }) =>
    request<{ ok: boolean; message: string }>("/settings/ai-test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateDatabricksToken: (token: string) =>
    request<{ ok: boolean; message: string }>("/settings/databricks-token", {
      method: "PUT",
      body: JSON.stringify({ token }),
    }),

  updateAiToken: (payload: { provider: "databricks" | "openai" | "ollama" | "custom"; token: string }) =>
    request<{ ok: boolean; message: string }>("/settings/ai-token", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  getAppLogs: (params?: {
    limit?: number;
    level?: string;
    search?: string;
    file?: string;
    kind?: "technical" | "business" | "all";
    actor?: string;
    action?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.level) qs.set("level", params.level);
    if (params?.search) qs.set("search", params.search);
    if (params?.file) qs.set("file", params.file);
    if (params?.kind) qs.set("kind", params.kind);
    if (params?.actor) qs.set("actor", params.actor);
    if (params?.action) qs.set("action", params.action);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<{
      kind?: "technical" | "business" | "all";
      items: Array<{
        id?: string;
        eventId?: string;
        timestamp?: string;
        createdAt?: string;
        level?: string;
        logger?: string;
        message?: string;
        source?: string;
        raw?: string;
        kind?: "technical" | "business";
        actor?: string;
        action?: string;
        orderId?: string;
        entityType?: string;
        entityId?: string;
        result?: string;
        durationMs?: number | null;
        details?: Record<string, unknown>;
      }>;
      count: number;
      limit: number;
      level?: string;
      search?: string;
      actor?: string;
      action?: string;
      logDir?: string;
      files?: Array<{
        name: string;
        path: string;
        sizeBytes: number;
        modifiedAt: string;
      }>;
      generatedAt: string;
    }>(`/logs${suffix}`);
  },
};
