import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Database,
  Package,
  RefreshCw,
  Shield,
  Plus,
  Upload,
  X,
  ExternalLink,
} from "lucide-react";
import { useDisplayTimeZone, useMasterData } from "@/hooks/useFile2Edi";
import { api } from "@/lib/api";
import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/file2edi/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatDateTime } from "@/lib/utils";
import type {
  MasterDataArticleRow,
  MasterDataClient,
  MasterDataRuleRow,
  MasterDataShipToRow,
} from "@/types";

type TabKey = "clients" | "shipto" | "articles" | "rules";

const ADD_FIELDS: Record<Exclude<TabKey, "rules">, { key: string; label: string; required?: boolean }[]> = {
  clients: [
    { key: "SOLDTO", label: "Sold-to", required: true },
    { key: "NAME", label: "Nom", required: true },
    { key: "STRAS", label: "Adresse", required: true },
    { key: "ORT01", label: "Ville", required: true },
    { key: "PSTLZ", label: "Code postal", required: true },
    { key: "LAND1", label: "Pays", required: true },
    { key: "VAT_NR", label: "TVA", required: true },
  ],
  shipto: [
    { key: "SOLDTO", label: "Sold-to", required: true },
    { key: "SHIPTO", label: "Ship-to", required: true },
    { key: "NAME", label: "Nom", required: true },
    { key: "STRAS", label: "Adresse", required: true },
    { key: "ORT01", label: "Ville", required: true },
    { key: "PSTLZ", label: "Code postal", required: true },
    { key: "LAND1", label: "Pays", required: true },
    { key: "PARVW", label: "Fonction partenaire", required: true },
  ],
  articles: [
    { key: "MATNR", label: "Code article", required: true },
    { key: "MAKTX", label: "Désignation", required: true },
  ],
};

function growthLabel(n: number | undefined): string | undefined {
  if (n == null || n === 0) return undefined;
  return `${n > 0 ? "+" : ""}${n} ce mois`;
}

export function DonneesMaitresPage() {
  const [tab, setTab] = useState<TabKey>("clients");
  const [search, setSearch] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [selectedClient, setSelectedClient] = useState<MasterDataClient | null>(null);
  const [selectedShipTo, setSelectedShipTo] = useState<MasterDataShipToRow | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<MasterDataArticleRow | null>(null);
  const [selectedRule, setSelectedRule] = useState<MasterDataRuleRow | null>(null);
  const [detailFields, setDetailFields] = useState<Record<string, string> | null>(null);
  const [page, setPage] = useState(1);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addFields, setAddFields] = useState<Record<string, string>>({});
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const displayTimeZone = useDisplayTimeZone();
  const pageSize = 8;
  const { data, refetch, isFetching } = useMasterData(tab, search);

  const summary = data?.summary;
  const clients = (data?.clients ?? []) as MasterDataClient[];
  const shipTos = (tab === "shipto" ? (data?.rows ?? []) : []) as MasterDataShipToRow[];
  const articles = (tab === "articles" ? (data?.rows ?? []) : []) as MasterDataArticleRow[];
  const rules = (tab === "rules" ? (data?.rows ?? []) : []) as MasterDataRuleRow[];

  const filteredClients = useMemo(() => {
    if (!countryFilter.trim()) return clients;
    const c = countryFilter.trim().toLowerCase();
    return clients.filter((row) => (row.country || "").toLowerCase().includes(c));
  }, [clients, countryFilter]);

  const filteredShipTos = useMemo(() => {
    if (!countryFilter.trim()) return shipTos;
    const c = countryFilter.trim().toLowerCase();
    return shipTos.filter((row) => (row.country || "").toLowerCase().includes(c));
  }, [shipTos, countryFilter]);

  const currentRows =
    tab === "clients"
      ? filteredClients
      : tab === "shipto"
        ? filteredShipTos
        : tab === "articles"
          ? articles
          : rules;

  const totalPages = Math.max(1, Math.ceil(currentRows.length / pageSize));
  const paginated = useMemo(
    () => currentRows.slice((page - 1) * pageSize, page * pageSize),
    [currentRows, page],
  );

  useEffect(() => {
    setPage(1);
    setSelectedClient(null);
    setSelectedShipTo(null);
    setSelectedArticle(null);
    setSelectedRule(null);
  }, [tab, search, countryFilter]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const invalidateMasterData = () => {
    void queryClient.invalidateQueries({ queryKey: ["master-data"] });
    void refetch();
  };

  const syncMutation = useMutation({
    mutationFn: () => api.syncMasterData(),
    onMutate: () => setSyncMessage(null),
    onSuccess: (res) => {
      setSyncMessage(res.message || "Synchronisation terminée");
      invalidateMasterData();
    },
    onError: (err) => {
      setSyncMessage(err instanceof Error ? err.message : "Échec de la synchronisation");
    },
  });

  const importMutation = useMutation({
    mutationFn: ({ kind, file }: { kind: string; file: File }) =>
      api.importMasterDataCsv(kind, file),
    onSuccess: (res) => {
      setActionMessage(res.message || "Import terminé");
      setImportOpen(false);
      invalidateMasterData();
    },
    onError: (err) => {
      setActionMessage(err instanceof Error ? err.message : "Échec de l'import");
    },
  });

  const addMutation = useMutation({
    mutationFn: () => api.addMasterDataRow(tab === "shipto" ? "shipto" : tab, addFields),
    onSuccess: (res) => {
      setActionMessage(res.message || "Ligne ajoutée");
      setAddOpen(false);
      setAddFields({});
      invalidateMasterData();
    },
    onError: (err) => {
      setActionMessage(err instanceof Error ? err.message : "Échec de l'ajout");
    },
  });

  const canMutateTab = tab === "clients" || tab === "shipto" || tab === "articles";

  const openAdd = () => {
    if (!canMutateTab) {
      setActionMessage("Les règles de validation sont issues du catalogue applicatif (lecture seule).");
      return;
    }
    const defaults: Record<string, string> = {};
    for (const f of ADD_FIELDS[tab]) defaults[f.key] = f.key === "LAND1" ? "FR" : f.key === "PARVW" ? "SH" : "";
    setAddFields(defaults);
    setAddOpen(true);
  };

  const openImport = () => {
    if (!canMutateTab) {
      setActionMessage("Import CSV indisponible pour les règles (catalogue applicatif).");
      return;
    }
    setImportOpen(true);
  };

  const searchPlaceholder =
    tab === "clients"
      ? "Rechercher un client…"
      : tab === "shipto"
        ? "Rechercher un ship-to…"
        : tab === "articles"
          ? "Rechercher un article…"
          : "Rechercher une règle…";

  return (
    <>
      <Header
        title="Données maîtres"
        subtitle="Référentiels clients, partenaires et articles"
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <TabsList>
            <TabsTrigger value="clients" className="gap-2">
              <Building2 className="h-4 w-4" /> Clients
            </TabsTrigger>
            <TabsTrigger value="shipto">Ship-to</TabsTrigger>
            <TabsTrigger value="articles">Articles Bosch</TabsTrigger>
            <TabsTrigger value="rules">Règles de validation</TabsTrigger>
          </TabsList>
          <div className="flex flex-col items-end gap-1">
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="gap-2" onClick={openImport}>
                <Upload className="h-4 w-4" /> Importer CSV
              </Button>
              <Button size="sm" className="gap-2" onClick={openAdd}>
                <Plus className="h-4 w-4" /> Ajouter
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                disabled={syncMutation.isPending}
                onClick={() => syncMutation.mutate()}
                title="Déclencher le workflow n8n (GitHub → masterdata → reload-cache)"
              >
                <RefreshCw className={`h-4 w-4 ${syncMutation.isPending ? "animate-spin" : ""}`} />
                {syncMutation.isPending ? "Synchronisation…" : "Synchroniser"}
              </Button>
            </div>
            {(syncMessage || actionMessage) && (
              <p
                className={`max-w-lg text-right text-xs ${
                  syncMutation.isError || addMutation.isError || importMutation.isError
                    ? "text-red-600"
                    : "text-muted-foreground"
                }`}
              >
                {actionMessage || syncMessage}
              </p>
            )}
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-2 space-y-3">
            <StatCard
              label="Clients actifs"
              value={summary?.activeClients?.toLocaleString("fr-FR") ?? "—"}
              sublabel={growthLabel(summary?.monthlyGrowth.clients)}
              icon={Building2}
            />
            <StatCard
              label="Ship-to"
              value={summary?.shiptoCount?.toLocaleString("fr-FR") ?? "—"}
              sublabel={growthLabel(summary?.monthlyGrowth.shipto)}
              icon={Database}
            />
            <StatCard
              label="Articles"
              value={summary?.articlesCount?.toLocaleString("fr-FR") ?? "—"}
              sublabel={growthLabel(summary?.monthlyGrowth.articles)}
              icon={Package}
            />
            <StatCard
              label="Règles"
              value={summary?.rulesCount?.toLocaleString("fr-FR") ?? "—"}
              sublabel={growthLabel(summary?.monthlyGrowth.rules)}
              icon={Shield}
            />
            <p className="text-xs text-muted-foreground px-1">
              Dernière synchronisation
              <br />
              {summary?.lastSync ? formatDateTime(summary.lastSync, displayTimeZone) : "—"}
              {summary?.syncStatus ? (
                <>
                  <br />
                  <span className="uppercase tracking-wide">{summary.syncStatus}</span>
                  {summary.syncCommit ? ` · ${String(summary.syncCommit).slice(0, 8)}` : ""}
                </>
              ) : null}
            </p>
          </div>

          <div className="lg:col-span-7">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-center gap-4 space-y-0 pb-4">
                <Input
                  placeholder={searchPlaceholder}
                  className="max-w-sm"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <Button
                  variant={showFilters ? "default" : "outline"}
                  size="sm"
                  onClick={() => setShowFilters((v) => !v)}
                >
                  Filtres
                </Button>
                {isFetching && (
                  <span className="text-xs text-muted-foreground">Chargement…</span>
                )}
                {showFilters && (tab === "clients" || tab === "shipto") && (
                  <div className="flex w-full items-center gap-2">
                    <Label className="text-xs text-muted-foreground whitespace-nowrap">Pays</Label>
                    <Input
                      placeholder="FR, DE…"
                      className="max-w-[140px]"
                      value={countryFilter}
                      onChange={(e) => setCountryFilter(e.target.value)}
                    />
                    {countryFilter && (
                      <Button variant="ghost" size="sm" onClick={() => setCountryFilter("")}>
                        Réinitialiser
                      </Button>
                    )}
                  </div>
                )}
              </CardHeader>
              <CardContent className="p-0">
                <TabsContent value="clients" className="mt-0">
                  <DataTable
                    empty={paginated.length === 0}
                    headers={[
                      "",
                      "ID client",
                      "Nom",
                      "Sold-to",
                      "TVA",
                      "Pays",
                      "Ville",
                      "Statut",
                      "Dernière mise à jour",
                    ]}
                  >
                    {(paginated as MasterDataClient[]).map((c) => (
                      <TableRow
                        key={c.clientId}
                        className="cursor-pointer"
                        data-state={selectedClient?.clientId === c.clientId ? "selected" : undefined}
                        onClick={() => setSelectedClient(c)}
                      >
                        <TableCell>
                          <div
                            className={`h-4 w-4 rounded-full border-2 ${
                              selectedClient?.clientId === c.clientId
                                ? "border-primary bg-primary"
                                : "border-muted"
                            }`}
                          />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{c.clientId}</TableCell>
                        <TableCell className="font-medium">{c.name}</TableCell>
                        <TableCell>{c.soldto}</TableCell>
                        <TableCell className="text-xs">{c.vat || "—"}</TableCell>
                        <TableCell>{c.country || "—"}</TableCell>
                        <TableCell>{c.city || "—"}</TableCell>
                        <TableCell>
                          <Badge variant={c.status === "Actif" ? "success" : "secondary"}>
                            {c.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">
                          {c.updatedAt ? formatDateTime(c.updatedAt, displayTimeZone) : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </DataTable>
                </TabsContent>

                <TabsContent value="shipto" className="mt-0">
                  <DataTable
                    empty={paginated.length === 0}
                    headers={[
                      "",
                      "Ship-to",
                      "Sold-to",
                      "Nom",
                      "Pays",
                      "Ville",
                      "Fonction",
                      "ADV",
                    ]}
                  >
                    {(paginated as MasterDataShipToRow[]).map((row) => (
                      <TableRow
                        key={`${row.soldto}-${row.shipto}-${row.id}`}
                        className="cursor-pointer"
                        data-state={selectedShipTo?.id === row.id ? "selected" : undefined}
                        onClick={() => setSelectedShipTo(row)}
                      >
                        <TableCell>
                          <div
                            className={`h-4 w-4 rounded-full border-2 ${
                              selectedShipTo?.id === row.id
                                ? "border-primary bg-primary"
                                : "border-muted"
                            }`}
                          />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{row.shipto}</TableCell>
                        <TableCell className="font-mono text-xs">{row.soldto}</TableCell>
                        <TableCell className="font-medium">{row.name}</TableCell>
                        <TableCell>{row.country || "—"}</TableCell>
                        <TableCell>{row.city || "—"}</TableCell>
                        <TableCell>{row.partnerFunction || "—"}</TableCell>
                        <TableCell className="text-xs">{row.advManager || "—"}</TableCell>
                      </TableRow>
                    ))}
                  </DataTable>
                </TabsContent>

                <TabsContent value="articles" className="mt-0">
                  <DataTable empty={paginated.length === 0} headers={["", "Code article", "Désignation"]}>
                    {(paginated as MasterDataArticleRow[]).map((row) => (
                      <TableRow
                        key={row.id}
                        className="cursor-pointer"
                        data-state={selectedArticle?.id === row.id ? "selected" : undefined}
                        onClick={() => setSelectedArticle(row)}
                      >
                        <TableCell>
                          <div
                            className={`h-4 w-4 rounded-full border-2 ${
                              selectedArticle?.id === row.id
                                ? "border-primary bg-primary"
                                : "border-muted"
                            }`}
                          />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{row.materialId}</TableCell>
                        <TableCell className="font-medium">{row.description}</TableCell>
                      </TableRow>
                    ))}
                  </DataTable>
                </TabsContent>

                <TabsContent value="rules" className="mt-0">
                  <DataTable empty={paginated.length === 0} headers={["", "Code", "Sévérité", "Statut", "Message"]}>
                    {(paginated as MasterDataRuleRow[]).map((row) => (
                      <TableRow
                        key={row.id}
                        className="cursor-pointer"
                        data-state={selectedRule?.id === row.id ? "selected" : undefined}
                        onClick={() => setSelectedRule(row)}
                      >
                        <TableCell>
                          <div
                            className={`h-4 w-4 rounded-full border-2 ${
                              selectedRule?.id === row.id
                                ? "border-primary bg-primary"
                                : "border-muted"
                            }`}
                          />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{row.code}</TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              row.severity === "BLOCKER"
                                ? "destructive"
                                : row.severity === "BUSINESS_REJECT"
                                  ? "secondary"
                                  : "outline"
                            }
                          >
                            {row.severity}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">{row.businessStatus}</TableCell>
                        <TableCell className="text-sm max-w-xs truncate">{row.message}</TableCell>
                      </TableRow>
                    ))}
                  </DataTable>
                </TabsContent>

                <PaginationBar
                  total={currentRows.length}
                  page={page}
                  pageSize={pageSize}
                  totalPages={totalPages}
                  onPrev={() => setPage((p) => Math.max(1, p - 1))}
                  onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
                />
              </CardContent>
            </Card>
          </div>

          <div className="lg:col-span-3">
            {selectedClient && tab === "clients" && (
              <DetailCard
                title={selectedClient.name}
                badge={selectedClient.status}
                onClose={() => setSelectedClient(null)}
                rows={[
                  ["ID client", selectedClient.clientId],
                  ["Sold-to", selectedClient.soldto],
                  ["TVA", selectedClient.vat || "—"],
                  ["Adresse", selectedClient.address || "—"],
                  ["Ville", selectedClient.city || "—"],
                  ["Code postal", selectedClient.postalCode || "—"],
                  ["Pays", selectedClient.country || "—"],
                  ["Devise", selectedClient.currency ?? "EUR"],
                ]}
                onShowAll={() => setDetailFields(selectedClient.fields || {})}
              />
            )}
            {selectedShipTo && tab === "shipto" && (
              <DetailCard
                title={selectedShipTo.name}
                badge={selectedShipTo.partnerFunction || "Ship-to"}
                onClose={() => setSelectedShipTo(null)}
                rows={[
                  ["Ship-to", selectedShipTo.shipto],
                  ["Sold-to", selectedShipTo.soldto],
                  ["Adresse", selectedShipTo.address || "—"],
                  ["Ville", selectedShipTo.city || "—"],
                  ["Code postal", selectedShipTo.postalCode || "—"],
                  ["Pays", selectedShipTo.country || "—"],
                  ["ADV", selectedShipTo.advManager || "—"],
                ]}
                onShowAll={() => setDetailFields(selectedShipTo.fields || {})}
              />
            )}
            {selectedArticle && tab === "articles" && (
              <DetailCard
                title={selectedArticle.description}
                badge="Article"
                onClose={() => setSelectedArticle(null)}
                rows={[
                  ["Code article", selectedArticle.materialId],
                  ["Désignation", selectedArticle.description],
                ]}
                onShowAll={() => setDetailFields(selectedArticle.fields || {})}
              />
            )}
            {selectedRule && tab === "rules" && (
              <DetailCard
                title={selectedRule.code}
                badge={selectedRule.severity}
                onClose={() => setSelectedRule(null)}
                rows={[
                  ["Code", selectedRule.code],
                  ["Sévérité", selectedRule.severity],
                  ["Statut métier", selectedRule.businessStatus],
                  ["Message", selectedRule.message],
                  ["Retry", selectedRule.retryAllowed ? "Oui" : "Non"],
                  ["Revue manuelle", selectedRule.manualReview ? "Oui" : "Non"],
                ]}
                onShowAll={() => setDetailFields(selectedRule.fields || {})}
              />
            )}
          </div>
        </div>
      </Tabs>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Importer un CSV</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground mb-4">
            Remplace le fichier runtime pour l’onglet courant (
            {tab === "clients" ? "Clients" : tab === "shipto" ? "Ship-to" : "Articles"}
            ). Séparateur <code>;</code>, colonnes attendues selon le schéma masterdata.
            Une synchronisation Git ultérieure pourra écraser cet import.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              importMutation.mutate({ kind: tab, file });
              e.target.value = "";
            }}
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setImportOpen(false)}>
              Annuler
            </Button>
            <Button
              disabled={importMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              {importMutation.isPending ? "Import…" : "Choisir un fichier"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              Ajouter —{" "}
              {tab === "clients" ? "client" : tab === "shipto" ? "ship-to" : "article"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {canMutateTab &&
              ADD_FIELDS[tab].map((field) => (
                <div key={field.key} className="space-y-1">
                  <Label className="text-xs">
                    {field.label}
                    {field.required ? " *" : ""}
                  </Label>
                  <Input
                    value={addFields[field.key] ?? ""}
                    onChange={(e) =>
                      setAddFields((prev) => ({ ...prev, [field.key]: e.target.value }))
                    }
                  />
                </div>
              ))}
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Annuler
            </Button>
            <Button
              disabled={addMutation.isPending}
              onClick={() => addMutation.mutate()}
            >
              {addMutation.isPending ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detailFields} onOpenChange={(open) => !open && setDetailFields(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Toutes les informations</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            {detailFields &&
              Object.entries(detailFields).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b pb-2">
                  <span className="text-muted-foreground font-mono text-xs">{k}</span>
                  <span className="text-right break-all">{v || "—"}</span>
                </div>
              ))}
          </div>
          <div className="mt-4 flex justify-end">
            <Button variant="outline" onClick={() => setDetailFields(null)}>
              Fermer
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DataTable({
  headers,
  children,
  empty,
}: {
  headers: string[];
  children: React.ReactNode;
  empty?: boolean;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {headers.map((h) => (
            <TableHead key={h || "sel"} className={h === "" ? "w-8" : undefined}>
              {h}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {empty ? (
          <TableRow>
            <TableCell colSpan={headers.length} className="py-10 text-center text-sm text-muted-foreground">
              Aucun résultat pour cet onglet.
            </TableCell>
          </TableRow>
        ) : (
          children
        )}
      </TableBody>
    </Table>
  );
}

function PaginationBar({
  total,
  page,
  pageSize,
  totalPages,
  onPrev,
  onNext,
}: {
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
      <span className="text-muted-foreground">
        {total === 0
          ? "0 résultat"
          : `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} sur ${total}`}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onPrev} disabled={page <= 1}>
          Précédent
        </Button>
        <span className="w-20 text-center text-muted-foreground">
          Page {page}/{totalPages}
        </span>
        <Button variant="outline" size="sm" onClick={onNext} disabled={page >= totalPages}>
          Suivant
        </Button>
      </div>
    </div>
  );
}

function DetailCard({
  title,
  badge,
  rows,
  onClose,
  onShowAll,
}: {
  title: string;
  badge?: string;
  rows: [string, string][];
  onClose: () => void;
  onShowAll: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Détail</p>
          <CardTitle className="text-lg mt-1">{title || "—"}</CardTitle>
          {badge ? (
            <Badge variant="success" className="mt-2">
              {badge}
            </Badge>
          ) : null}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 border-b pb-2">
            <span className="text-muted-foreground">{k}</span>
            <span className="font-medium text-right break-all">{v}</span>
          </div>
        ))}
        <Button variant="outline" className="w-full gap-2 mt-4" onClick={onShowAll}>
          Voir toutes les informations
          <ExternalLink className="h-4 w-4" />
        </Button>
      </CardContent>
    </Card>
  );
}
