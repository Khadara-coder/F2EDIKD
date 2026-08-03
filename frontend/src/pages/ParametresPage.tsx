import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, CheckCircle2, Database, FileSpreadsheet, Key, Lock, Save, Server, Shield, Trash2, UserPlus, Wifi, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useSettings } from "@/hooks/useFile2Edi";
import { appSettingsSchema, type AppSettingsForm } from "@/schemas";
import { Header } from "@/components/layout/Header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { mergeSettings, DEFAULT_APP_SETTINGS } from "@/lib/defaultSettings";
import { Input } from "@/components/ui/input";
import type { GestionnaireUser } from "@/types";

const TIMEZONE_OPTIONS = (() => {
  const supported = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  const fallback = [
    "UTC",
    "Europe/Paris",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
  ];
  return Array.from(new Set([...supported, ...fallback])).sort((a, b) => a.localeCompare(b));
})();

const SECTIONS = [
  { id: "profil", label: "Profil EDI" },
  { id: "connecteurs", label: "Connecteurs" },
  { id: "ia", label: "Intelligence artificielle" },
  { id: "validation", label: "Validation" },
  { id: "notifications", label: "Notifications" },
  { id: "utilisateurs", label: "Utilisateurs" },
  { id: "api-keys", label: "Clés API" },
  { id: "sftp", label: "SFTP" },
  { id: "securite", label: "Sécurité" },
] as const;

type SettingsSection = (typeof SECTIONS)[number]["id"];

export function ParametresPage() {
  const queryClient = useQueryClient();
  const { data: settingsRaw, isLoading } = useSettings();
  const settings = mergeSettings(settingsRaw);
  const [activeSection, setActiveSection] = useState<SettingsSection>("profil");
  const [sftpPassword, setSftpPassword] = useState("");
  const [sftpPasswordMsg, setSftpPasswordMsg] = useState("");
  const [testingConnector, setTestingConnector] = useState<string | null>(null);
  const [connectorMessages, setConnectorMessages] = useState<Record<string, string>>({});
  const [databricksToken, setDatabricksToken] = useState("");
  const [databricksTokenMsg, setDatabricksTokenMsg] = useState("");
  const [aiTestResult, setAiTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // ── User management state ───────────────────────────────────────────────────
  const [newUsername, setNewUsername] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newSapId, setNewSapId] = useState("");
  const [newUserRole, setNewUserRole] = useState<"adv" | "admin">("adv");
  const [newPassword, setNewPassword] = useState("");
  const [newUserError, setNewUserError] = useState("");
  const [newUserSuccess, setNewUserSuccess] = useState("");
  const [resetUserId, setResetUserId] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetMsg, setResetMsg] = useState("");
  // Edit modal state
  const [editUser, setEditUser] = useState<GestionnaireUser | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editSapId, setEditSapId] = useState("");
  const [editRole, setEditRole] = useState<"adv" | "admin">("adv");
  const [editError, setEditError] = useState("");
  const [editSuccess, setEditSuccess] = useState("");

  const rolesQuery = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: api.getAccessRoles,
    retry: 1,
  });

  // ── User management queries/mutations ──────────────────────────────────────
  const usersQuery = useQuery<GestionnaireUser[]>({
    queryKey: ["users"],
    queryFn: () => fetch("/api/users").then(r => r.json()),
    staleTime: 30_000,
  });

  const createUserMutation = useMutation({
    mutationFn: () => fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: newUsername.trim(),
        displayName: newDisplayName.trim() || newUsername.trim(),
        email: newEmail.trim(),
        sapId: newSapId.trim(),
        role: newUserRole,
        password: newPassword,
      }),
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || "Erreur"); return r.json(); }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setNewUsername(""); setNewDisplayName(""); setNewEmail(""); setNewSapId("");
      setNewUserRole("adv"); setNewPassword("");
      setNewUserError(""); setNewUserSuccess("Utilisateur créé avec succès");
      setTimeout(() => setNewUserSuccess(""), 3000);
    },
    onError: (e) => setNewUserError(e instanceof Error ? e.message : "Erreur"),
  });

  const deleteUserMutation = useMutation({
    mutationFn: (userId: string) => fetch(`/api/users/${userId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: Partial<GestionnaireUser> }) =>
      fetch(`/api/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || "Erreur"); return r.json(); }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditSuccess("Modifications enregistrées");
      setTimeout(() => { setEditUser(null); setEditSuccess(""); }, 1500);
    },
    onError: (e) => setEditError(e instanceof Error ? e.message : "Erreur"),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ userId, password }: { userId: string; password: string }) =>
      fetch(`/api/users/${userId}/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || "Erreur"); return r.json(); }),
    onSuccess: () => {
      setResetUserId(null); setResetPassword(""); setResetMsg("Mot de passe mis à jour");
      setTimeout(() => setResetMsg(""), 3000);
    },
    onError: (e) => setResetMsg(e instanceof Error ? e.message : "Erreur"),
  });

  const form = useForm<AppSettingsForm>({
    resolver: zodResolver(appSettingsSchema),
    defaultValues: {
      ediProfile: DEFAULT_APP_SETTINGS.ediProfile,
      standard: DEFAULT_APP_SETTINGS.standard,
      version: DEFAULT_APP_SETTINGS.version,
      defaultIncoterm: DEFAULT_APP_SETTINGS.defaultIncoterm,
      currency: DEFAULT_APP_SETTINGS.currency,
      documentLanguage: DEFAULT_APP_SETTINGS.documentLanguage,
      timezone: DEFAULT_APP_SETTINGS.timezone,
      connectorConfig: DEFAULT_APP_SETTINGS.connectorConfig,
      aiProvider: DEFAULT_APP_SETTINGS.aiProvider,
      databricksConfig: DEFAULT_APP_SETTINGS.databricksConfig,
      openaiConfig: DEFAULT_APP_SETTINGS.openaiConfig,
      ollamaConfig: DEFAULT_APP_SETTINGS.ollamaConfig,
      customAiConfig: DEFAULT_APP_SETTINGS.customAiConfig,
      validation: DEFAULT_APP_SETTINGS.validation,
      notifications: DEFAULT_APP_SETTINGS.notifications,
      sftpConfig: DEFAULT_APP_SETTINGS.sftpConfig,
      security: DEFAULT_APP_SETTINGS.security,
      options: DEFAULT_APP_SETTINGS.options,
    },
  });

  useEffect(() => {
    if (settingsRaw) {
      const s = mergeSettings(settingsRaw);
      form.reset({
        ediProfile: s.ediProfile,
        standard: s.standard,
        version: s.version,
        defaultIncoterm: s.defaultIncoterm,
        currency: s.currency,
        documentLanguage: s.documentLanguage,
        timezone: s.timezone,
        connectorConfig: s.connectorConfig,
        aiProvider: s.aiProvider,
        databricksConfig: s.databricksConfig,
        openaiConfig: s.openaiConfig,
        ollamaConfig: s.ollamaConfig,
        customAiConfig: s.customAiConfig,
        validation: s.validation,
        notifications: s.notifications,
        sftpConfig: s.sftpConfig,
        security: s.security,
        options: s.options,
      });
    }
  }, [settingsRaw, form]);

  const saveMutation = useMutation({
    mutationFn: (payload: AppSettingsForm) => api.updateSettings(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const sftpPasswordMutation = useMutation({
    mutationFn: (password: string) => api.updateSftpPassword(password),
    onSuccess: (res) => {
      setSftpPassword("");
      setSftpPasswordMsg(res.message || "Mot de passe SFTP enregistré");
      form.setValue("sftpConfig.hasPassword", true);
    },
    onError: (err) => {
      setSftpPasswordMsg(err instanceof Error ? err.message : "Échec mise à jour mot de passe SFTP");
    },
  });

  const testConnectorMutation = useMutation({
    mutationFn: ({ connector, payload }: { connector: string; payload?: unknown }) =>
      api.testConnector(connector, payload),
    onMutate: ({ connector }) => {
      setTestingConnector(connector);
      setConnectorMessages((prev) => ({ ...prev, [connector]: "" }));
    },
    onSuccess: (res, vars) => {
      const connector = vars.connector;
      const label = res.status === "connected" ? "Connecté" : "Déconnecté";
      const msg = res.message ? `${label} — ${res.message}` : label;
      setConnectorMessages((prev) => ({ ...prev, [connector]: msg }));
      queryClient.setQueryData(["settings"], (current: unknown) => {
        const settings = current && typeof current === "object" ? (current as Record<string, unknown>) : {};
        const connectors =
          settings.connectors && typeof settings.connectors === "object"
            ? (settings.connectors as Record<string, unknown>)
            : {};
        return {
          ...settings,
          connectors: {
            ...connectors,
            [connector]: res.status,
          },
        };
      });
    },
    onError: (err, vars) => {
      const connector = vars.connector;
      const msg = err instanceof Error ? err.message : "Échec du test de connexion";
      setConnectorMessages((prev) => ({ ...prev, [connector]: msg }));
    },
    onSettled: () => {
      setTestingConnector(null);
    },
  });

  const databricksTokenMutation = useMutation({
    mutationFn: (token: string) => api.updateAiToken({ provider: form.getValues("aiProvider"), token }),
    onSuccess: (res) => {
      setDatabricksToken("");
      setDatabricksTokenMsg(res.message || "Token Databricks enregistré");
    },
    onError: (err) => {
      setDatabricksTokenMsg(err instanceof Error ? err.message : "Échec mise à jour token");
    },
  });

  const aiTestMutation = useMutation({
    mutationFn: (payload: {
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
      api.testAiConnection(payload),
    onSuccess: (res) => setAiTestResult(res),
    onError: (err) => setAiTestResult({ ok: false, message: err instanceof Error ? err.message : "Erreur inconnue" }),
  });

  const [newKeyName, setNewKeyName] = useState("");
  const [generatedKey, setGeneratedKey] = useState<{ key_id: string; api_key: string; message: string } | null>(null);

  const apiKeysQuery = useQuery({
    queryKey: ["admin", "api-keys"],
    queryFn: () => api.getApiKeys(),
    retry: 1,
  });

  const createKeyMutation = useMutation({
    mutationFn: (name: string) => api.createApiKey({ name }),
    onSuccess: (res) => {
      setGeneratedKey(res);
      setNewKeyName("");
      queryClient.invalidateQueries({ queryKey: ["admin", "api-keys"] });
    },
  });

  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: string) => api.deleteApiKey(keyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "api-keys"] });
    },
  });

  // roleItems still needed for securite section display
  const _roleItems = useMemo(() => rolesQuery.data?.items ?? [], [rolesQuery.data]); void _roleItems;
  const apiKeyItems = useMemo(() => apiKeysQuery.data?.items ?? [], [apiKeysQuery.data]);
  const aiProvider = form.watch("aiProvider");
  const showDatabricksSql = aiProvider === "databricks" && form.watch("databricksConfig.sqlWarehouseEnabled");

  const connectors = [
    { key: "apiExtraction", label: "API extraction", icon: Wifi, status: settings.connectors.apiExtraction },
    { key: "database", label: "Base de données", icon: Database, status: settings.connectors.database },
    { key: "csvExport", label: "Export CSV", icon: FileSpreadsheet, status: settings.connectors.csvExport },
    { key: "sftp", label: "SFTP", icon: Server, status: settings.connectors.sftp },
  ];

  if (isLoading) {
    return <p className="text-muted-foreground p-8">Chargement des paramètres…</p>;
  }

  return (
    <>
      <Header
        title="Paramètres"
        subtitle="Configuration de l'application et des intégrations"
      />

      <div className="grid gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-2 h-fit">
          <CardContent className="p-2">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setActiveSection(s.id)}
                className={cn(
                  "w-full rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  activeSection === s.id
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                {s.label}
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="lg:col-span-10 space-y-6">
          {activeSection === "profil" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Profil EDI</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <EditableField
                  label="Profil"
                  value={form.watch("ediProfile")}
                  onChange={(v) => form.setValue("ediProfile", v)}
                />
                <EditableField
                  label="Standard"
                  value={form.watch("standard")}
                  onChange={(v) => form.setValue("standard", v)}
                />
                <EditableField
                  label="Version UN/EDIFACT"
                  value={form.watch("version")}
                  onChange={(v) => form.setValue("version", v)}
                />
                <EditableField
                  label="Incoterm par défaut"
                  value={form.watch("defaultIncoterm")}
                  onChange={(v) => form.setValue("defaultIncoterm", v)}
                />
                <EditableField
                  label="Devise"
                  value={form.watch("currency")}
                  onChange={(v) => form.setValue("currency", v)}
                />
                <EditableField
                  label="Langue des documents"
                  value={form.watch("documentLanguage")}
                  onChange={(v) => form.setValue("documentLanguage", v)}
                />
                <TimezoneField
                  label="Fuseau horaire"
                  value={form.watch("timezone")}
                  onChange={(v) => form.setValue("timezone", v)}
                />
              </CardContent>
            </Card>
          )}

          {activeSection === "connecteurs" && (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">État des connecteurs</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {connectors.map((c) => (
                    <div key={c.key}>
                      <div className="flex items-center justify-between rounded-lg border p-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                            <c.icon className="h-5 w-5 text-primary" />
                          </div>
                          <div>
                            <p className="font-medium">{c.label}</p>
                            <Badge
                              variant={c.status === "connected" ? "success" : "destructive"}
                              className="mt-1"
                            >
                              {c.status === "connected" ? "Connecté" : "Déconnecté"}
                            </Badge>
                          </div>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => testConnectorMutation.mutate({
                            connector: c.key,
                            payload: c.key === "apiExtraction"
                              ? { connectorConfig: { apiBaseUrl: form.getValues("connectorConfig.apiBaseUrl") } }
                              : undefined,
                          })}
                          disabled={testConnectorMutation.isPending}
                        >
                          {testingConnector === c.key ? "Test..." : "Tester"}
                        </Button>
                      </div>
                      {connectorMessages[c.key] && (
                        <p className="mt-2 text-xs text-muted-foreground">{connectorMessages[c.key]}</p>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Configuration connecteurs</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <EditableField
                    label="URL API extraction"
                    value={form.watch("connectorConfig.apiBaseUrl")}
                    onChange={(v) => form.setValue("connectorConfig.apiBaseUrl", v)}
                  />

                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <Label className="text-sm font-medium">Synchronisation DB active</Label>
                      <p className="text-xs text-muted-foreground">Active le flux base de données interne</p>
                    </div>
                    <Switch
                      checked={form.watch("connectorConfig.dbSyncEnabled")}
                      onCheckedChange={(v) => form.setValue("connectorConfig.dbSyncEnabled", v)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Délimiteur CSV</Label>
                    <Select
                      value={form.watch("connectorConfig.csvDelimiter")}
                      onValueChange={(v) => form.setValue("connectorConfig.csvDelimiter", v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value=";">Point-virgule (;)</SelectItem>
                        <SelectItem value=",">Virgule (,)</SelectItem>
                        <SelectItem value="|">Pipe (|)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Profil SFTP</Label>
                    <Input
                      value={form.watch("connectorConfig.sftpProfile")}
                      onChange={(e) => form.setValue("connectorConfig.sftpProfile", e.target.value)}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {activeSection === "ia" && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Brain className="h-4 w-4" />
                    Configuration IA
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-2">
                    <Label>Provider LLM</Label>
                    <Select
                      value={form.watch("aiProvider")}
                      onValueChange={(v: "databricks" | "openai" | "ollama" | "custom") => form.setValue("aiProvider", v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="databricks">Databricks Model Serving</SelectItem>
                        <SelectItem value="openai">OpenAI-compatible</SelectItem>
                        <SelectItem value="ollama">Ollama (local)</SelectItem>
                        <SelectItem value="custom">Custom provider</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    {aiProvider === "databricks" && (
                      <>
                        <EditableField
                          label="Host Databricks"
                          value={form.watch("databricksConfig.host")}
                          onChange={(v) => form.setValue("databricksConfig.host", v)}
                        />
                        <EditableField
                          label="Endpoint du modèle"
                          value={form.watch("databricksConfig.modelEndpoint")}
                          onChange={(v) => form.setValue("databricksConfig.modelEndpoint", v)}
                        />
                        <div className="flex items-center justify-between gap-4 rounded-lg border p-4 sm:col-span-2">
                          <div>
                            <p className="font-medium text-sm">Activer Databricks SQL (Unity Catalog)</p>
                            <p className="text-xs text-muted-foreground">
                              Active uniquement si tu utilises Warehouse + Catalog + Schema pour des usages SQL.
                            </p>
                          </div>
                          <Switch
                            checked={form.watch("databricksConfig.sqlWarehouseEnabled")}
                            onCheckedChange={(v) => form.setValue("databricksConfig.sqlWarehouseEnabled", v)}
                          />
                        </div>
                        {showDatabricksSql && (
                          <>
                            <EditableField
                              label="Catalog Unity"
                              value={form.watch("databricksConfig.catalog")}
                              onChange={(v) => form.setValue("databricksConfig.catalog", v)}
                            />
                            <EditableField
                              label="Schema Unity"
                              value={form.watch("databricksConfig.schema")}
                              onChange={(v) => form.setValue("databricksConfig.schema", v)}
                            />
                            <EditableField
                              label="Warehouse ID"
                              value={form.watch("databricksConfig.warehouseId")}
                              onChange={(v) => form.setValue("databricksConfig.warehouseId", v)}
                            />
                          </>
                        )}
                      </>
                    )}
                    {aiProvider === "openai" && (
                      <>
                        <EditableField
                          label="Base URL OpenAI"
                          value={form.watch("openaiConfig.baseUrl")}
                          onChange={(v) => form.setValue("openaiConfig.baseUrl", v)}
                        />
                        <EditableField
                          label="Model"
                          value={form.watch("openaiConfig.model")}
                          onChange={(v) => form.setValue("openaiConfig.model", v)}
                        />
                      </>
                    )}
                    {aiProvider === "ollama" && (
                      <>
                        <EditableField
                          label="Base URL Ollama"
                          value={form.watch("ollamaConfig.baseUrl")}
                          onChange={(v) => form.setValue("ollamaConfig.baseUrl", v)}
                        />
                        <EditableField
                          label="Model"
                          value={form.watch("ollamaConfig.model")}
                          onChange={(v) => form.setValue("ollamaConfig.model", v)}
                        />
                      </>
                    )}
                    {aiProvider === "custom" && (
                      <>
                        <EditableField
                          label="Base URL custom"
                          value={form.watch("customAiConfig.baseUrl")}
                          onChange={(v) => form.setValue("customAiConfig.baseUrl", v)}
                        />
                        <EditableField
                          label="Model"
                          value={form.watch("customAiConfig.model")}
                          onChange={(v) => form.setValue("customAiConfig.model", v)}
                        />
                        <EditableField
                          label="Chat path"
                          value={form.watch("customAiConfig.chatPath")}
                          onChange={(v) => form.setValue("customAiConfig.chatPath", v)}
                        />
                        <EditableField
                          label="Auth header"
                          value={form.watch("customAiConfig.authHeader")}
                          onChange={(v) => form.setValue("customAiConfig.authHeader", v)}
                        />
                        <EditableField
                          label="Auth scheme"
                          value={form.watch("customAiConfig.authScheme")}
                          onChange={(v) => form.setValue("customAiConfig.authScheme", v)}
                        />
                        <EditableField
                          label="Headers custom (k:v, séparés par virgule)"
                          value={form.watch("customAiConfig.customHeaders")}
                          onChange={(v) => form.setValue("customAiConfig.customHeaders", v)}
                        />
                      </>
                    )}
                  </div>

                  <div className="rounded-lg border p-4 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                          <p className="font-medium text-sm">Token d&apos;accès provider IA</p>
                        <p className="text-xs text-muted-foreground">
                            Jeton runtime (non persisté). Pour persistance, utiliser les variables d&apos;environnement du serveur.
                        </p>
                      </div>
                      <Badge variant="secondary">
                        {databricksTokenMsg && !databricksToken ? "Défini" : "Runtime"}
                      </Badge>
                    </div>
                    <Input
                      type="password"
                      placeholder="Token provider..."
                      value={databricksToken}
                      onChange={(e) => {
                        setDatabricksToken(e.target.value);
                        if (databricksTokenMsg) setDatabricksTokenMsg("");
                      }}
                    />
                    <div className="flex items-center gap-3">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                          if (!databricksToken.trim()) {
                            setDatabricksTokenMsg("Token requis");
                            return;
                          }
                          databricksTokenMutation.mutate(databricksToken);
                        }}
                        disabled={databricksTokenMutation.isPending}
                      >
                        Appliquer le token
                      </Button>
                      {databricksTokenMsg && (
                        <p className="text-xs text-muted-foreground">{databricksTokenMsg}</p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Moteur IA (LLM)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
                    <div>
                      <p className="font-medium text-sm">Activer le LLM</p>
                      <p className="text-xs text-muted-foreground">
                        Active ou désactive l&apos;appel au LLM pour l&apos;extraction,
                        quel que soit l&apos;environnement. Désactivé, l&apos;application n&apos;utilise
                        que les moteurs déterministes (règles + regex).
                      </p>
                    </div>
                    <Switch
                      checked={form.watch("databricksConfig.llmEnabled")}
                      onCheckedChange={(v) => form.setValue("databricksConfig.llmEnabled", v)}
                    />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Test de connexion IA</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Vérifie que l&apos;endpoint de modèle est accessible avec la configuration actuelle.
                  </p>
                  <div className="flex items-center gap-3">
                    <Button
                      type="button"
                      onClick={() => {
                        setAiTestResult(null);
                        aiTestMutation.mutate({
                          provider: form.getValues("aiProvider"),
                          token: databricksToken,
                          host: form.getValues("databricksConfig.host"),
                          modelEndpoint: form.getValues("databricksConfig.modelEndpoint"),
                          baseUrl:
                            form.getValues("aiProvider") === "openai"
                              ? form.getValues("openaiConfig.baseUrl")
                              : form.getValues("aiProvider") === "ollama"
                                ? form.getValues("ollamaConfig.baseUrl")
                                : form.getValues("customAiConfig.baseUrl"),
                          model:
                            form.getValues("aiProvider") === "openai"
                              ? form.getValues("openaiConfig.model")
                              : form.getValues("aiProvider") === "ollama"
                                ? form.getValues("ollamaConfig.model")
                                : form.getValues("customAiConfig.model"),
                          chatPath: form.getValues("customAiConfig.chatPath"),
                          authHeader: form.getValues("customAiConfig.authHeader"),
                          authScheme: form.getValues("customAiConfig.authScheme"),
                          customHeaders: form.getValues("customAiConfig.customHeaders"),
                        });
                      }}
                      disabled={aiTestMutation.isPending}
                      className="gap-2"
                    >
                      <Brain className="h-4 w-4" />
                      {aiTestMutation.isPending ? "Test en cours…" : "Tester la connexion IA"}
                    </Button>
                  </div>
                  {aiTestResult && (
                    <div className={cn(
                      "flex items-start gap-2 rounded-lg border p-3 text-sm",
                      aiTestResult.ok ? "border-green-200 bg-green-50 text-green-800" : "border-red-200 bg-red-50 text-red-800"
                    )}>
                      {aiTestResult.ok
                        ? <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
                        : <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
                      }
                      <span>{aiTestResult.message}</span>
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Variables conseillées: <code className="font-mono">DATABRICKS_TOKEN</code>, <code className="font-mono">OPENAI_API_KEY</code>, <code className="font-mono">CUSTOM_LLM_API_KEY</code> selon le provider.
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {activeSection === "validation" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Règles de validation</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2">
                  <NumberField
                    label="Seuil auto-validation (%)"
                    value={form.watch("validation.autoValidationThreshold")}
                    min={0}
                    max={100}
                    onChange={(v) => form.setValue("validation.autoValidationThreshold", v)}
                  />
                  <NumberField
                    label="Fenêtre doublon (jours)"
                    value={form.watch("validation.duplicateWindowDays")}
                    min={1}
                    max={365}
                    onChange={(v) => form.setValue("validation.duplicateWindowDays", v)}
                  />
                </div>

                {[
                  {
                    key: "requireCustomerReference" as const,
                    label: "Référence client obligatoire",
                    desc: "Force la référence client dans le document.",
                  },
                  {
                    key: "requireDeliveryDate" as const,
                    label: "Date de livraison obligatoire",
                    desc: "Bloque si aucune date de livraison n'est détectée.",
                  },
                  {
                    key: "blockOnAmountMismatch" as const,
                    label: "Bloquer en cas d'écart de montant",
                    desc: "Arrête la génération si les montants sont incohérents.",
                  },
                ].map((opt) => (
                  <div key={opt.key} className="flex items-center justify-between gap-4">
                    <div>
                      <Label className="text-sm font-medium">{opt.label}</Label>
                      <p className="text-xs text-muted-foreground">{opt.desc}</p>
                    </div>
                    <Switch
                      checked={form.watch(`validation.${opt.key}`)}
                      onCheckedChange={(v) => form.setValue(`validation.${opt.key}`, v)}
                    />
                  </div>
                ))}

                <div className="border-t pt-4">
                  <p className="mb-3 text-sm font-medium">Comportement pipeline</p>
                  <div className="space-y-4">
                    {[
                      { key: "autoValidateAbove90" as const, label: "Auto-validation si confiance > 90%" },
                      { key: "detectDuplicates" as const, label: "Détecter les doublons" },
                      { key: "manualReviewOnAnomaly" as const, label: "Créer une revue manuelle en cas d'anomalie" },
                    ].map((opt) => (
                      <div key={opt.key} className="flex items-center justify-between gap-4">
                        <Label className="text-sm font-medium">{opt.label}</Label>
                        <Switch
                          checked={form.watch(`options.${opt.key}`)}
                          onCheckedChange={(v) => form.setValue(`options.${opt.key}`, v)}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {activeSection === "notifications" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Notifications</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-4">
                  {[
                    { key: "emailEnabled" as const, label: "Activer les e-mails" },
                    { key: "notifyOnSuccess" as const, label: "Notifier les succès" },
                    { key: "notifyOnFailure" as const, label: "Notifier les échecs" },
                    { key: "webhookEnabled" as const, label: "Activer les webhooks" },
                    { key: "notifyOnDuplicate" as const, label: "Notifier en cas de doublon détecté", fromOptions: true },
                  ].map((opt) => (
                    <div key={opt.key} className="flex items-center justify-between gap-4">
                      <Label className="text-sm font-medium">{opt.label}</Label>
                      <Switch
                        checked={opt.fromOptions ? form.watch("options.notifyOnDuplicate") : form.watch(`notifications.${opt.key as "emailEnabled" | "notifyOnSuccess" | "notifyOnFailure" | "webhookEnabled"}`)}
                        onCheckedChange={(v) => {
                          if (opt.fromOptions) {
                            form.setValue("options.notifyOnDuplicate", v);
                          } else {
                            form.setValue(`notifications.${opt.key as "emailEnabled" | "notifyOnSuccess" | "notifyOnFailure" | "webhookEnabled"}`, v);
                          }
                        }}
                      />
                    </div>
                  ))}
                </div>

                <EditableField
                  label="Destinataires e-mail (séparés par ; )"
                  value={form.watch("notifications.emailRecipients")}
                  onChange={(v) => form.setValue("notifications.emailRecipients", v)}
                />

                <EditableField
                  label="URL Webhook"
                  value={form.watch("notifications.webhookUrl")}
                  onChange={(v) => form.setValue("notifications.webhookUrl", v)}
                />
              </CardContent>
            </Card>
          )}

          {activeSection === "sftp" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">SFTP</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
                  <div>
                    <p className="font-medium">Export automatique SFTP</p>
                    <p className="text-xs text-muted-foreground">Envoi automatique après génération EDIFACT</p>
                  </div>
                  <Switch
                    checked={form.watch("options.autoSftp")}
                    onCheckedChange={(v) => form.setValue("options.autoSftp", v)}
                  />
                </div>

                <div className="flex items-center justify-between gap-4">
                  <Label className="text-sm font-medium">Connecteur SFTP activé</Label>
                  <Switch
                    checked={form.watch("sftpConfig.enabled")}
                    onCheckedChange={(v) => form.setValue("sftpConfig.enabled", v)}
                  />
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <EditableField
                    label="Hôte"
                    value={form.watch("sftpConfig.host")}
                    onChange={(v) => form.setValue("sftpConfig.host", v)}
                  />
                  <NumberField
                    label="Port"
                    value={form.watch("sftpConfig.port")}
                    min={1}
                    max={65535}
                    onChange={(v) => form.setValue("sftpConfig.port", v)}
                  />
                  <EditableField
                    label="Utilisateur"
                    value={form.watch("sftpConfig.username")}
                    onChange={(v) => form.setValue("sftpConfig.username", v)}
                  />
                  <EditableField
                    label="Répertoire distant"
                    value={form.watch("sftpConfig.remotePath")}
                    onChange={(v) => form.setValue("sftpConfig.remotePath", v)}
                  />
                </div>

                <EditableField
                  label="Pattern nom de fichier"
                  value={form.watch("sftpConfig.fileNamePattern")}
                  onChange={(v) => form.setValue("sftpConfig.fileNamePattern", v)}
                />

                <div className="space-y-2 rounded-lg border p-4">
                  <div className="flex items-center justify-between gap-3">
                    <Label>Mot de passe SFTP</Label>
                    <Badge variant={form.watch("sftpConfig.hasPassword") ? "default" : "secondary"}>
                      {form.watch("sftpConfig.hasPassword") ? "Défini" : "Non défini"}
                    </Badge>
                  </div>
                  <Input
                    type="password"
                    placeholder="Entrer le mot de passe SFTP"
                    value={sftpPassword}
                    onChange={(e) => {
                      setSftpPassword(e.target.value);
                      if (sftpPasswordMsg) setSftpPasswordMsg("");
                    }}
                  />
                  <div className="flex items-center gap-3">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        if (!sftpPassword.trim()) {
                          setSftpPasswordMsg("Mot de passe SFTP requis");
                          return;
                        }
                        sftpPasswordMutation.mutate(sftpPassword);
                      }}
                      disabled={sftpPasswordMutation.isPending}
                    >
                      Enregistrer le mot de passe
                    </Button>
                    {sftpPasswordMsg && (
                      <p className="text-xs text-muted-foreground">{sftpPasswordMsg}</p>
                    )}
                  </div>
                </div>

                <div className="space-y-2 rounded-lg border p-4">
                  <div className="flex items-center justify-between gap-3">
                    <Label>Test connexion SFTP</Label>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() =>
                        testConnectorMutation.mutate({
                          connector: "sftp",
                          payload: {
                            sftpConfig: {
                              host: form.getValues("sftpConfig.host"),
                              port: form.getValues("sftpConfig.port"),
                              username: form.getValues("sftpConfig.username"),
                              remotePath: form.getValues("sftpConfig.remotePath"),
                            },
                          },
                        })
                      }
                      disabled={testConnectorMutation.isPending}
                    >
                      {testingConnector === "sftp" ? "Test..." : "Tester la connexion"}
                    </Button>
                  </div>
                  {connectorMessages.sftp && (
                    <p className="text-xs text-muted-foreground">{connectorMessages.sftp}</p>
                  )}
                </div>

                <p className="text-xs text-muted-foreground">
                  Le mot de passe n&apos;est jamais renvoyé en clair. Il est appliqué au runtime pour les tests et exports SFTP.
                </p>
              </CardContent>
            </Card>
          )}

          {activeSection === "utilisateurs" && (
            <>
              {/* ── Créer un utilisateur ─────────────────────────────────── */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <UserPlus className="h-5 w-5" />
                    Créer un utilisateur
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2">
                    {/* Ligne 1 : identifiant + nom complet */}
                    <div className="space-y-1.5">
                      <Label>Identifiant *</Label>
                      <Input
                        placeholder="prenom.nom"
                        value={newUsername}
                        onChange={(e) => { setNewUsername(e.target.value); setNewUserError(""); }}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Nom complet</Label>
                      <Input
                        placeholder="Prénom Nom"
                        value={newDisplayName}
                        onChange={(e) => setNewDisplayName(e.target.value)}
                      />
                    </div>
                    {/* Ligne 2 : email + SAP ID */}
                    <div className="space-y-1.5">
                      <Label>Adresse e-mail *</Label>
                      <Input
                        type="email"
                        placeholder="prenom.nom@bosch.com"
                        value={newEmail}
                        onChange={(e) => { setNewEmail(e.target.value); setNewUserError(""); }}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label>
                        Identifiant SAP
                        {newUserRole === "adv" && <span className="text-destructive ml-0.5">*</span>}
                      </Label>
                      <Input
                        placeholder="8 chiffres — ex: 15016007"
                        value={newSapId}
                        maxLength={8}
                        onChange={(e) => setNewSapId(e.target.value.replace(/\D/g, "").slice(0, 8))}
                      />
                      {newUserRole === "adv" && (
                        <p className="text-xs text-muted-foreground">Requis pour les Gestionnaires (ADV)</p>
                      )}
                    </div>
                    {/* Ligne 3 : type + mot de passe */}
                    <div className="space-y-1.5">
                      <Label>Type d'utilisateur *</Label>
                      <Select value={newUserRole} onValueChange={(v) => setNewUserRole(v as "adv" | "admin")}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="adv">
                            <div className="flex items-center gap-2">
                              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
                              Gestionnaire (ADV)
                            </div>
                          </SelectItem>
                          <SelectItem value="admin">
                            <div className="flex items-center gap-2">
                              <span className="inline-block h-2 w-2 rounded-full bg-violet-500" />
                              Administrateur
                            </div>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Mot de passe initial *</Label>
                      <Input
                        type="password"
                        placeholder="6 caractères minimum"
                        value={newPassword}
                        onChange={(e) => { setNewPassword(e.target.value); setNewUserError(""); }}
                      />
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      {newUserError && <p className="text-sm text-destructive">{newUserError}</p>}
                      {newUserSuccess && <p className="text-sm text-emerald-600">{newUserSuccess}</p>}
                    </div>
                    <Button
                      className="gap-2"
                      onClick={() => {
                        if (!newUsername.trim()) { setNewUserError("Identifiant requis"); return; }
                        if (!newEmail.trim()) { setNewUserError("Adresse e-mail requise"); return; }
                        if (newUserRole === "adv") {
                          if (!newSapId.trim()) { setNewUserError("L'identifiant SAP est requis pour un Gestionnaire (ADV)"); return; }
                          if (!/^\d{8}$/.test(newSapId.trim())) { setNewUserError("L'identifiant SAP doit être composé de 8 chiffres (ex: 15016007)"); return; }
                        }
                        if (!newPassword || newPassword.length < 6) { setNewUserError("Mot de passe: 6 caractères minimum"); return; }
                        createUserMutation.mutate();
                      }}
                      disabled={createUserMutation.isPending}
                    >
                      <UserPlus className="h-4 w-4" />
                      {createUserMutation.isPending ? "En cours…" : "Créer l'utilisateur"}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Les Gestionnaires (ADV) traitent les commandes. Les Administrateurs ont accès aux paramètres.
                  </p>
                </CardContent>
              </Card>

              {/* ── Liste des gestionnaires ───────────────────────────────── */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="h-5 w-5" />
                    Gestionnaires ({usersQuery.data?.length ?? 0})
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {resetMsg && (
                    <p className={`text-sm ${resetMsg.includes("Erreur") || resetMsg.includes("impossible") ? "text-destructive" : "text-emerald-600"}`}>
                      {resetMsg}
                    </p>
                  )}
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="px-4 py-3 text-left font-medium">Identifiant</th>
                          <th className="px-4 py-3 text-left font-medium">Nom complet</th>
                          <th className="px-4 py-3 text-left font-medium">E-mail</th>
                          <th className="px-4 py-3 text-left font-medium">SAP ID</th>
                          <th className="px-4 py-3 text-left font-medium">Type</th>
                          <th className="px-4 py-3 text-left font-medium">Créé le</th>
                          <th className="px-4 py-3 text-left font-medium">Mot de passe</th>
                          <th className="px-4 py-3 text-right font-medium">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usersQuery.isLoading && (
                          <tr><td className="px-4 py-4 text-center text-muted-foreground" colSpan={8}>Chargement…</td></tr>
                        )}
                        {!usersQuery.isLoading && (usersQuery.data?.length ?? 0) === 0 && (
                          <tr><td className="px-4 py-4 text-center text-muted-foreground" colSpan={8}>Aucun utilisateur créé.</td></tr>
                        )}
                        {(usersQuery.data ?? []).map((user) => (
                          <tr key={user.userId} className="border-t hover:bg-muted/30">
                            <td className="px-4 py-3 font-mono text-xs font-semibold">{user.username}</td>
                            <td className="px-4 py-3">{user.displayName}</td>
                            <td className="px-4 py-3 text-xs text-muted-foreground">{(user as GestionnaireUser).email || "—"}</td>
                            <td className="px-4 py-3 text-xs font-mono">{(user as GestionnaireUser).sapId || "—"}</td>
                            <td className="px-4 py-3">
                              <Badge
                                variant={(user as GestionnaireUser).role === "admin" ? "default" : "secondary"}
                                className="gap-1 text-xs"
                              >
                                <Shield className="h-3 w-3" />
                                {(user as GestionnaireUser).role === "admin" ? "Admin" : "Gestionnaire"}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 text-xs text-muted-foreground">
                              {user.createdAt ? user.createdAt.slice(0, 10) : "—"}
                            </td>
                            <td className="px-4 py-3">
                              {resetUserId === user.userId ? (
                                <div className="flex items-center gap-2">
                                  <Input
                                    type="password"
                                    placeholder="Nouveau mot de passe"
                                    className="h-7 w-40 text-xs"
                                    value={resetPassword}
                                    onChange={(e) => setResetPassword(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter" && resetPassword.length >= 6)
                                        resetPasswordMutation.mutate({ userId: user.userId, password: resetPassword });
                                    }}
                                  />
                                  <Button
                                    size="sm"
                                    className="h-7 gap-1 text-xs"
                                    onClick={() => {
                                      if (resetPassword.length < 6) { setResetMsg("6 caractères minimum"); return; }
                                      resetPasswordMutation.mutate({ userId: user.userId, password: resetPassword });
                                    }}
                                    disabled={resetPasswordMutation.isPending}
                                  >
                                    <Key className="h-3 w-3" /> OK
                                  </Button>
                                  <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { setResetUserId(null); setResetPassword(""); }}>
                                    Annuler
                                  </Button>
                                </div>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 gap-1 text-xs"
                                  onClick={() => { setResetUserId(user.userId); setResetPassword(""); setResetMsg(""); }}
                                >
                                  <Lock className="h-3 w-3" /> Réinitialiser
                                </Button>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="gap-1"
                                  onClick={() => {
                                    setEditUser(user as GestionnaireUser);
                                    setEditDisplayName((user as GestionnaireUser).displayName || "");
                                    setEditEmail((user as GestionnaireUser).email || "");
                                    setEditSapId((user as GestionnaireUser).sapId || "");
                                    setEditRole(((user as GestionnaireUser).role || "adv") as "adv" | "admin");
                                    setEditError(""); setEditSuccess("");
                                  }}
                                >
                                  Modifier
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="gap-1 text-destructive hover:text-destructive"
                                  onClick={() => {
                                    if (confirm(`Supprimer le compte "${user.username}" ?`))
                                      deleteUserMutation.mutate(user.userId);
                                  }}
                                  disabled={deleteUserMutation.isPending}
                                >
                                  <Trash2 className="h-4 w-4" /> Supprimer
                                </Button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    La suppression désactive le compte sans effacer l'historique des dossiers traités.
                  </p>
                </CardContent>
              </Card>

              {/* ── Modal : Modifier un utilisateur ──────────────────────── */}
              {editUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
                  <div className="bg-background rounded-lg border shadow-xl w-full max-w-lg p-6 space-y-4">
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                      <Shield className="h-5 w-5 text-primary" />
                      Modifier — {editUser.username}
                    </h2>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label>Nom complet</Label>
                        <Input
                          value={editDisplayName}
                          onChange={(e) => setEditDisplayName(e.target.value)}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Adresse e-mail *</Label>
                        <Input
                          type="email"
                          value={editEmail}
                          onChange={(e) => { setEditEmail(e.target.value); setEditError(""); }}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>
                          Identifiant SAP
                          {editRole === "adv" && <span className="text-destructive ml-0.5">*</span>}
                        </Label>
                        <Input
                          placeholder="8 chiffres — ex: 15016007"
                          value={editSapId}
                          maxLength={8}
                          onChange={(e) => { setEditSapId(e.target.value.replace(/\D/g, "").slice(0, 8)); setEditError(""); }}
                        />
                        {editRole === "adv" && (
                          <p className="text-xs text-muted-foreground">Requis pour les Gestionnaires (ADV)</p>
                        )}
                      </div>
                      <div className="space-y-1.5">
                        <Label>Type d'utilisateur</Label>
                        <Select value={editRole} onValueChange={(v) => setEditRole(v as "adv" | "admin")}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="adv">
                              <div className="flex items-center gap-2">
                                <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
                                Gestionnaire (ADV)
                              </div>
                            </SelectItem>
                            <SelectItem value="admin">
                              <div className="flex items-center gap-2">
                                <span className="inline-block h-2 w-2 rounded-full bg-violet-500" />
                                Administrateur
                              </div>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    {editError && <p className="text-sm text-destructive">{editError}</p>}
                    {editSuccess && <p className="text-sm text-emerald-600">{editSuccess}</p>}
                    <div className="flex justify-end gap-2 pt-2">
                      <Button variant="outline" onClick={() => setEditUser(null)}>Annuler</Button>
                      <Button
                        className="gap-2"
                        onClick={() => {
                          if (!editEmail.trim()) { setEditError("Adresse e-mail requise"); return; }
                          if (editRole === "adv") {
                            if (!editSapId.trim()) { setEditError("L'identifiant SAP est requis pour un Gestionnaire (ADV)"); return; }
                            if (!/^\d{8}$/.test(editSapId.trim())) { setEditError("L'identifiant SAP doit être composé de 8 chiffres (ex: 15016007)"); return; }
                          }
                          updateUserMutation.mutate({
                            userId: editUser.userId,
                            data: {
                              displayName: editDisplayName,
                              email: editEmail,
                              sapId: editSapId,
                              role: editRole,
                            },
                          });
                        }}
                        disabled={updateUserMutation.isPending}
                      >
                        {updateUserMutation.isPending ? "En cours…" : "Enregistrer"}
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {activeSection === "api-keys" && (
            <>
              <Card>
                <CardHeader className="pb-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-bold">Clés API</h2>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        Générez et gérez les clés API pour accéder à l&apos;API File2EDI de manière programmatique.
                      </p>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  {generatedKey && (
                    <div className="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-lg p-4 space-y-3">
                      <p className="text-sm font-medium text-green-900 dark:text-green-100">
                        {generatedKey.message}
                      </p>
                      <div className="bg-white dark:bg-gray-900 p-3 rounded font-mono text-sm break-all border border-green-200 dark:border-green-800">
                        {generatedKey.api_key}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(generatedKey.api_key);
                          }}
                          className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                        >
                          📋 Copier
                        </button>
                        <button
                          onClick={() => setGeneratedKey(null)}
                          className="px-3 py-1 bg-gray-300 dark:bg-gray-600 text-sm rounded hover:bg-gray-400"
                        >
                          Masquer
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="space-y-3">
                    <h3 className="font-semibold text-sm">Générer une nouvelle clé</h3>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Nom de la clé (ex: n8n-production, mobile-app)"
                        value={newKeyName}
                        onChange={(e) => setNewKeyName(e.target.value)}
                        className="flex-1 px-3 py-2 border rounded bg-white dark:bg-gray-900 dark:border-gray-700"
                      />
                      <button
                        onClick={() => createKeyMutation.mutate(newKeyName)}
                        disabled={!newKeyName.trim() || createKeyMutation.isPending}
                        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                      >
                        {createKeyMutation.isPending ? "⏳ Création..." : "🔑 Créer"}
                      </button>
                    </div>
                    {createKeyMutation.isError && (
                      <p className="text-xs text-red-600 dark:text-red-400">
                        Erreur: {(createKeyMutation.error as Error)?.message}
                      </p>
                    )}
                  </div>

                  <div className="space-y-3">
                    <h3 className="font-semibold text-sm">Clés API actives</h3>
                    {apiKeysQuery.isLoading ? (
                      <p className="text-sm text-gray-600">Chargement des clés...</p>
                    ) : apiKeyItems.length === 0 ? (
                      <p className="text-sm text-gray-600">Aucune clé API créée</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b dark:border-gray-700">
                              <th className="text-left py-2 px-2">Nom</th>
                              <th className="text-left py-2 px-2">Créée par</th>
                              <th className="text-left py-2 px-2">Créée le</th>
                              <th className="text-left py-2 px-2">Dernière utilisation</th>
                              <th className="text-left py-2 px-2">Actif</th>
                              <th className="text-left py-2 px-2">Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {apiKeyItems.map((key) => (
                              <tr key={key.id} className="border-b dark:border-gray-700">
                                <td className="py-2 px-2">{key.name}</td>
                                <td className="py-2 px-2">{key.created_by || "—"}</td>
                                <td className="py-2 px-2">
                                  {new Date(key.created_at).toLocaleDateString("fr-FR")}
                                </td>
                                <td className="py-2 px-2">
                                  {key.last_used_at
                                    ? new Date(key.last_used_at).toLocaleDateString("fr-FR")
                                    : "Jamais"}
                                </td>
                                <td className="py-2 px-2">
                                  <span className="px-2 py-1 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 text-xs rounded">
                                    ✓ Actif
                                  </span>
                                </td>
                                <td className="py-2 px-2">
                                  <button
                                    onClick={() => deleteKeyMutation.mutate(key.id)}
                                    disabled={deleteKeyMutation.isPending}
                                    className="text-red-600 dark:text-red-400 hover:text-red-700 text-sm"
                                  >
                                    🗑️ Révoquer
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                    <p className="text-sm text-yellow-900 dark:text-yellow-100">
                      <strong>⚠️ Sécurité:</strong> Les clés API accordent un accès complet à l&apos;API. Conservez-les en sécurité et ne les
                      partagez pas. Utilisez l&apos;en-tête &quot;X-API-Key&quot; pour l&apos;authentification.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {activeSection === "securite" && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Sécurité applicative</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-4">
                      <Label className="text-sm font-medium">Authentification obligatoire</Label>
                      <Switch
                        checked={form.watch("security.enforceAuth")}
                        onCheckedChange={(v) => form.setValue("security.enforceAuth", v)}
                      />
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <Label className="text-sm font-medium">Journal d'audit actif</Label>
                      <Switch
                        checked={form.watch("security.auditLogEnabled")}
                        onCheckedChange={(v) => form.setValue("security.auditLogEnabled", v)}
                      />
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <NumberField
                      label="Durée session (minutes)"
                      value={form.watch("security.sessionTimeoutMinutes")}
                      min={15}
                      max={1440}
                      onChange={(v) => form.setValue("security.sessionTimeoutMinutes", v)}
                    />
                    <NumberField
                      label="Tentatives max de login"
                      value={form.watch("security.maxLoginAttempts")}
                      min={1}
                      max={20}
                      onChange={(v) => form.setValue("security.maxLoginAttempts", v)}
                    />
                  </div>

                  <EditableField
                    label="Liste IP autorisées (séparées par ; )"
                    value={form.watch("security.ipAllowlist")}
                    onChange={(v) => form.setValue("security.ipAllowlist", v)}
                  />
                </CardContent>
              </Card>
            </>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => form.reset()}>
              Réinitialiser
            </Button>
            <Button
              className="gap-2"
              onClick={form.handleSubmit((data) => saveMutation.mutate(data))}
              disabled={saveMutation.isPending}
            >
              <Save className="h-4 w-4" />
              Enregistrer
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}

function EditableField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-muted-foreground">{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-muted-foreground">{label}</Label>
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => {
          const raw = Number(e.target.value);
          if (Number.isNaN(raw)) {
            return;
          }
          onChange(Math.min(max, Math.max(min, raw)));
        }}
      />
    </div>
  );
}

function TimezoneField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label className="text-muted-foreground">{label}</Label>
      <Input
        list="timezone-options"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Europe/Paris"
      />
      <datalist id="timezone-options">
        {TIMEZONE_OPTIONS.map((timezone) => (
          <option key={timezone} value={timezone} />
        ))}
      </datalist>
      <p className="text-xs text-muted-foreground">
        Tapez une partie du fuseau pour filtrer, puis sélectionnez dans la liste.
      </p>
    </div>
  );
}
