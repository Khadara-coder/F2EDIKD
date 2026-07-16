import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FileSpreadsheet, Save, Server, Shield, Trash2, UserPlus, Wifi } from "lucide-react";
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

const SECTIONS = [
  { id: "profil", label: "Profil EDI" },
  { id: "connecteurs", label: "Connecteurs" },
  { id: "validation", label: "Validation" },
  { id: "notifications", label: "Notifications" },
  { id: "sftp", label: "SFTP" },
  { id: "securite", label: "Sécurité" },
] as const;

type SettingsSection = (typeof SECTIONS)[number]["id"];

export function ParametresPage() {
  const queryClient = useQueryClient();
  const { data: settingsRaw, isLoading } = useSettings();
  const settings = mergeSettings(settingsRaw);
  const [activeSection, setActiveSection] = useState<SettingsSection>("profil");
  const [newActor, setNewActor] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "adv">("adv");
  const [roleError, setRoleError] = useState("");
  const [sftpPassword, setSftpPassword] = useState("");
  const [sftpPasswordMsg, setSftpPasswordMsg] = useState("");
  const [testingConnector, setTestingConnector] = useState<string | null>(null);
  const [connectorMessages, setConnectorMessages] = useState<Record<string, string>>({});

  const rolesQuery = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: api.getAccessRoles,
    retry: 1,
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
      databricksConfig: DEFAULT_APP_SETTINGS.databricksConfig,
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
        databricksConfig: s.databricksConfig,
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

  const roleUpsertMutation = useMutation({
    mutationFn: (payload: { actor: string; role: "admin" | "adv" }) => api.upsertAccessRole(payload),
    onSuccess: async () => {
      setNewActor("");
      setRoleError("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
    },
    onError: (err) => {
      setRoleError(err instanceof Error ? err.message : "Échec de l'attribution du rôle");
    },
  });

  const roleDeleteMutation = useMutation({
    mutationFn: (actor: string) => api.deleteAccessRole(actor),
    onSuccess: async () => {
      setRoleError("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
    },
    onError: (err) => {
      setRoleError(err instanceof Error ? err.message : "Échec de la révocation du rôle");
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

  const roleItems = useMemo(() => rolesQuery.data?.items ?? [], [rolesQuery.data]);

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
                <EditableField
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
                          onClick={() => testConnectorMutation.mutate({ connector: c.key })}
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

                  <div className="border-t pt-4">
                    <p className="mb-3 text-sm font-medium">API Databricks</p>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <EditableField
                        label="Host Databricks"
                        value={form.watch("databricksConfig.host")}
                        onChange={(v) => form.setValue("databricksConfig.host", v)}
                      />
                      <EditableField
                        label="Base URL File2EDI"
                        value={form.watch("databricksConfig.apiBaseUrl")}
                        onChange={(v) => form.setValue("databricksConfig.apiBaseUrl", v)}
                      />
                      <EditableField
                        label="Serving endpoint modèle"
                        value={form.watch("databricksConfig.modelEndpoint")}
                        onChange={(v) => form.setValue("databricksConfig.modelEndpoint", v)}
                      />
                      <EditableField
                        label="Warehouse ID"
                        value={form.watch("databricksConfig.warehouseId")}
                        onChange={(v) => form.setValue("databricksConfig.warehouseId", v)}
                      />
                      <EditableField
                        label="Catalog"
                        value={form.watch("databricksConfig.catalog")}
                        onChange={(v) => form.setValue("databricksConfig.catalog", v)}
                      />
                      <EditableField
                        label="Schema"
                        value={form.watch("databricksConfig.schema")}
                        onChange={(v) => form.setValue("databricksConfig.schema", v)}
                      />
                      <EditableField
                        label="Profil Databricks local"
                        value={form.watch("databricksConfig.configProfile")}
                        onChange={(v) => form.setValue("databricksConfig.configProfile", v)}
                      />
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">
                      Le token Databricks reste géré hors application via variables d&apos;environnement ou profil CLI.
                    </p>
                  </div>
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

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Gestion des profils et droits d&apos;accès</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
              <div className="grid gap-3 rounded-lg border p-4 md:grid-cols-[1fr_180px_auto]">
                <div className="space-y-1.5">
                  <Label>Identifiant utilisateur</Label>
                  <Input
                    placeholder="prenom.nom@bosch.com"
                    value={newActor}
                    onChange={(e) => setNewActor(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Rôle</Label>
                  <Select value={newRole} onValueChange={(v: "admin" | "adv") => setNewRole(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="adv">ADV</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-end">
                  <Button
                    className="w-full gap-2"
                    onClick={() => {
                      const actor = newActor.trim();
                      if (!actor) {
                        setRoleError("Identifiant utilisateur requis");
                        return;
                      }
                      roleUpsertMutation.mutate({ actor, role: newRole });
                    }}
                    disabled={roleUpsertMutation.isPending}
                  >
                    <UserPlus className="h-4 w-4" />
                    Attribuer
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">Admins env: {rolesQuery.data?.env_admin_count ?? 0}</Badge>
                <Badge variant="outline">Affectations DB: {rolesQuery.data?.db_assignment_count ?? 0}</Badge>
              </div>

              {roleError && <p className="text-sm text-destructive">{roleError}</p>}

              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">Utilisateur</th>
                      <th className="px-3 py-2 text-left font-medium">Rôle</th>
                      <th className="px-3 py-2 text-left font-medium">Source</th>
                      <th className="px-3 py-2 text-left font-medium">Maj par</th>
                      <th className="px-3 py-2 text-right font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rolesQuery.isLoading && (
                      <tr>
                        <td className="px-3 py-4 text-muted-foreground" colSpan={5}>Chargement des profils...</td>
                      </tr>
                    )}
                    {!rolesQuery.isLoading && roleItems.length === 0 && (
                      <tr>
                        <td className="px-3 py-4 text-muted-foreground" colSpan={5}>Aucun profil configuré.</td>
                      </tr>
                    )}
                    {!rolesQuery.isLoading && roleItems.map((item) => (
                      <tr key={`${item.actor}-${item.source}`} className="border-t">
                        <td className="px-3 py-2">{item.actor}</td>
                        <td className="px-3 py-2">
                          <Badge variant={item.effective_role === "admin" ? "default" : "secondary"} className="gap-1">
                            <Shield className="h-3 w-3" />
                            {item.effective_role.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-3 py-2">{item.source === "env" ? "ENV" : "DB"}</td>
                        <td className="px-3 py-2">{item.updated_by || "system"}</td>
                        <td className="px-3 py-2 text-right">
                          {item.source === "db" ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="gap-1 text-destructive"
                              onClick={() => roleDeleteMutation.mutate(item.actor)}
                              disabled={roleDeleteMutation.isPending}
                            >
                              <Trash2 className="h-4 w-4" />
                              Révoquer
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">Géré par app.yaml</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
