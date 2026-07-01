import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Database, FileSpreadsheet, Save, Server, Wifi } from "lucide-react";
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

const SECTIONS = [
  { id: "profil", label: "Profil EDI" },
  { id: "connecteurs", label: "Connecteurs" },
  { id: "validation", label: "Validation" },
  { id: "notifications", label: "Notifications" },
  { id: "sftp", label: "SFTP" },
  { id: "securite", label: "Sécurité" },
];

export function ParametresPage() {
  const { data: settingsRaw, isLoading } = useSettings();
  const settings = mergeSettings(settingsRaw);
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
        options: s.options,
      });
    }
  }, [settingsRaw, form]);

  const saveMutation = useMutation({
    mutationFn: (payload: AppSettingsForm) => api.updateSettings(payload),
  });

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
            {SECTIONS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                className={cn(
                  "w-full rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  i === 0 ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted",
                )}
              >
                {s.label}
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="lg:col-span-10 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Profil EDI</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Profil" value={settings.ediProfile} />
              <Field label="Standard" value={settings.standard} />
              <Field label="Version UN/EDIFACT" value={settings.version} />
              <Field label="Incoterm par défaut" value={settings.defaultIncoterm} />
              <Field label="Devise" value={settings.currency} />
              <Field label="Langue des documents" value={settings.documentLanguage} />
              <Field label="Fuseau horaire" value={settings.timezone} />
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Connecteurs</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {connectors.map((c) => (
                  <div key={c.key} className="flex items-center justify-between rounded-lg border p-4">
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
                      onClick={() => api.testConnector(c.key)}
                    >
                      Tester la connexion
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Options</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {[
                  { key: "autoValidateAbove90" as const, label: "Auto-validation si confiance > 90%", desc: "Valider automatiquement les commandes à haute confiance" },
                  { key: "detectDuplicates" as const, label: "Détecter les doublons", desc: "Bloquer les fichiers déjà traités" },
                  { key: "autoSftp" as const, label: "Envoyer le fichier par SFTP automatiquement", desc: "Export SFTP après génération EDIFACT" },
                  { key: "manualReviewOnAnomaly" as const, label: "Créer une revue manuelle en cas d'anomalie", desc: "Forcer la revue si anomalie détectée" },
                  { key: "notifyOnDuplicate" as const, label: "Notifier en cas de doublon détecté", desc: "Envoyer une alerte ADV" },
                ].map((opt) => (
                  <div key={opt.key} className="flex items-center justify-between gap-4">
                    <div>
                      <Label className="text-sm font-medium">{opt.label}</Label>
                      <p className="text-xs text-muted-foreground">{opt.desc}</p>
                    </div>
                    <Switch
                      checked={form.watch(`options.${opt.key}`)}
                      onCheckedChange={(v) => form.setValue(`options.${opt.key}`, v)}
                    />
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

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

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-2">
      <Label className="text-muted-foreground">{label}</Label>
      <Select defaultValue={value}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={value}>{value}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
