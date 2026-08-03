import { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpDown, FileIcon, Search, SlidersHorizontal, Upload, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useDashboard, useDisplayTimeZone, useOrdersList } from "@/hooks/useFile2Edi";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { Header } from "@/components/layout/Header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { confidenceColor, formatDateTime, cn } from "@/lib/utils";
import type { OrderStatus } from "@/types";

function SourceBadge({ source }: { source?: string }) {
  const map: Record<string, { label: string; className: string }> = {
    n8n:     { label: "n8n",    className: "bg-blue-100 text-blue-800 border-blue-200" },
    ui:      { label: "UI",     className: "bg-green-100 text-green-800 border-green-200" },
    api:     { label: "API",    className: "bg-orange-100 text-orange-800 border-orange-200" },
    unknown: { label: "?",      className: "bg-gray-100 text-gray-500 border-gray-200" },
  };
  const key = (source || "unknown").toLowerCase();
  const cfg = map[key] ?? map.unknown;
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

type ReviewStatusFilter = "all" | "toProcess" | "onHold" | "processed" | "sentSap" | "transferred" | "rejected" | "deliveryFailed";
type BusinessStatusGroup = Exclude<ReviewStatusFilter, "all">;
type ReviewSortKey =
  | "fileName"
  | "clientName"
  | "confidence"
  | "issue"
  | "createdAt"
  | "processedAt"
  | "processedBy"
  | "status";
type SortDirection = "asc" | "desc";

const STATUS_FILTERS: Array<{ value: ReviewStatusFilter; label: string; className: string }> = [
  { value: "all",           label: "Tous",          className: "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100" },
  { value: "toProcess",     label: "À traiter",     className: "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100" },
  { value: "onHold",        label: "En attente",    className: "border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100" },
  { value: "processed",     label: "Traité",         className: "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100" },
  { value: "sentSap",       label: "Envoyé SAP",    className: "border-teal-200 bg-teal-50 text-teal-700 hover:bg-teal-100" },
  { value: "transferred",   label: "Transféré",      className: "border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100" },
  { value: "rejected",      label: "Rejeté",         className: "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100" },
  { value: "deliveryFailed",label: "Échec d'envoi",  className: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100" },
];

const GROUP_STATUS_BADGE: Record<BusinessStatusGroup, { label: string; variant: "warning" | "success" | "info" | "destructive" | "orange" }> = {
  toProcess:     { label: "À traiter",   variant: "warning" },
  onHold:        { label: "En attente",  variant: "orange" },
  processed:     { label: "Traité",       variant: "success" },
  sentSap:       { label: "Envoyé SAP",  variant: "success" },
  transferred:   { label: "Transféré",    variant: "info" },
  rejected:      { label: "Rejeté",       variant: "destructive" },
  deliveryFailed:{ label: "Échec d'envoi",variant: "destructive" },
};

function statusToFilterGroup(status: OrderStatus): BusinessStatusGroup {
  if (status === "Revue requise" || status === "À revoir" || status === "À vérifier" || status === "Bloqué" || status === "À traiter") {
    return "toProcess";
  }
  if (status === "En attente") return "onHold";
  if (status === "Généré" || status === "Validé") return "processed";
  if (status === "Envoyé SAP") return "sentSap";
  if (status === "Transféré") return "transferred";
  if (status === "Rejeté" || status === "Doublon") return "rejected";
  if (status === "SFTP échoué" || status === "Échec SAP") return "deliveryFailed";
  return "toProcess";
}

export function RevueListPage() {
  const navigate = useNavigate();
  const { reviewQueue } = useDashboard();
  const ordersList = useOrdersList();
  const displayTimeZone = useDisplayTimeZone();
  const { data: me } = useCurrentUser();
  const isAdmin = me?.role === "admin";

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ReviewStatusFilter>("all");
  const [managerFilter, setManagerFilter] = useState<string>("all");  // "all" | username
  const [myOrdersOnly, setMyOrdersOnly] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortKey, setSortKey] = useState<ReviewSortKey>("createdAt");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const currentUsername = me?.username ?? me?.actor?.split("@")[0] ?? null;

  // Auto-activer le filtre "Mes dossiers" pour les ADV à l'ouverture
  useEffect(() => {
    if (!isAdmin && currentUsername) {
      setMyOrdersOnly(true);
    }
  }, [isAdmin, currentUsername]);

  // Liste des gestionnaires pour le filtre (username → displayName)
  const usersQuery = useQuery<Array<{ userId: string; username: string; displayName: string }>>(
    { queryKey: ["users"], queryFn: () => fetch("/api/users").then(r => r.json()), staleTime: 60_000 }
  );
  const gestionnaires = usersQuery.data ?? [];
  // Map username → displayName pour la colonne
  const displayNameMap = useMemo(
    () => Object.fromEntries(gestionnaires.map(u => [u.username.toLowerCase(), u.displayName])),
    [gestionnaires]
  );
  const getDisplayName = (username: string | undefined) => {
    if (!username) return null;
    const lc = username.toLowerCase();
    if (lc === "operator" || lc === "system") return "Système";
    return displayNameMap[lc] || username;
  };

  const items = Array.isArray(ordersList.data) ? ordersList.data : [];
  const pendingCount = reviewQueue.data?.length ?? 0;

  const handleSort = (key: ReviewSortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("asc");
  };

  const getSortValue = (row: (typeof items)[number], key: ReviewSortKey) => {
    switch (key) {
      case "confidence":
        return row.confidence ?? 0;
      case "createdAt":
        return row.createdAt || row.date || "";
      case "processedAt":
        return row.processedAt || "";
      case "processedBy":
        return (row.processedBy || "").toLowerCase();
      case "status":
        return statusToFilterGroup(row.status);
      case "issue":
        return row.issue || "";
      case "clientName":
        return row.clientName || "";
      case "fileName":
      default:
        return row.fileName || "";
    }
  };

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = items.filter((row) => {
      const matchesSearch =
        !query ||
        [row.fileName, row.clientName, row.issue, row.status, row.processedBy, row.date, row.createdAt, row.processedAt]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query));
      const matchesStatus = statusFilter === "all" || statusToFilterGroup(row.status) === statusFilter;
      // "Mes dossiers" filter
      const rowAssignee = row.assignedTo || row.processedBy || "";
      const matchesMyOrders = !myOrdersOnly || !currentUsername ||
        rowAssignee.toLowerCase() === currentUsername.toLowerCase();
      // Filtre par gestionnaire spécifique
      const matchesManager = managerFilter === "all" ||
        row.assignedTo?.toLowerCase() === managerFilter.toLowerCase() ||
        (row.processedBy || "").toLowerCase() === managerFilter.toLowerCase();
      // Filtre par date d'import
      const rowDate = row.createdAt || row.date || "";
      const matchesDateFrom = !dateFrom || rowDate >= dateFrom;
      const matchesDateTo = !dateTo || rowDate <= (dateTo + "T23:59:59");
      return matchesSearch && matchesStatus && matchesMyOrders && matchesManager && matchesDateFrom && matchesDateTo;
    });

    return filtered.sort((left, right) => {
      const leftValue = getSortValue(left, sortKey);
      const rightValue = getSortValue(right, sortKey);

      let comparison = 0;
      if (sortKey === "confidence") {
        comparison = Number(leftValue) - Number(rightValue);
      } else if (sortKey === "createdAt" || sortKey === "processedAt") {
        comparison = Date.parse(String(leftValue)) - Date.parse(String(rightValue));
        if (Number.isNaN(comparison)) {
          comparison = String(leftValue).localeCompare(String(rightValue), "fr", { sensitivity: "base" });
        }
      } else {
        comparison = String(leftValue).localeCompare(String(rightValue), "fr", { sensitivity: "base" });
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [items, managerFilter, myOrdersOnly, currentUsername, dateFrom, dateTo, search, sortDirection, sortKey, statusFilter]);

  return (
    <>
      <Header
        title="Revue"
        subtitle="Toutes les commandes converties — ouvrez un dossier pour valider ou corriger"
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 border-b bg-muted/20">
          <div>
            <CardTitle className="text-base">
              Commandes converties
              {pendingCount > 0 && (
                <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-600">
                  {pendingCount} à revoir
                </span>
              )}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Filtrez la liste par statut, gestionnaire ou mot-clé.
            </p>
          </div>
          <Button variant="outline" className="gap-2" onClick={() => navigate("/convertir")}>
            <Upload className="h-4 w-4" />
            Convertir un PDF
          </Button>
        </CardHeader>

        <CardContent className="border-b bg-muted/30 p-4">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <SlidersHorizontal className="h-4 w-4 text-primary" />
              Filtres
            </div>
            {/* Toggle Mes dossiers / Tous les dossiers */}
            <Button
              variant={myOrdersOnly ? "default" : "outline"}
              size="sm"
              className="gap-1.5"
              onClick={() => setMyOrdersOnly(!myOrdersOnly)}
              title={myOrdersOnly ? "Afficher tous les dossiers" : "Filtrer sur mes dossiers"}
            >
              {myOrdersOnly ? <X className="h-3.5 w-3.5" /> : <Search className="h-3.5 w-3.5" />}
              {myOrdersOnly
                ? currentUsername ? `Mes dossiers (${currentUsername})` : "Mes dossiers"
                : "Tous les dossiers"}
            </Button>
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_190px_310px_auto] lg:items-center">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rechercher un fichier, client, commande ou statut…"
                className="pl-9"
              />
            </div>

            {/* Filtre par gestionnaire: liste réelle des utilisateurs */}
            <Select value={managerFilter} onValueChange={setManagerFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Gestionnaire" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous les gestionnaires</SelectItem>
                {gestionnaires.map((u) => (
                  <SelectItem key={u.userId} value={u.username}>
                    {u.displayName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Filtre par dates d'import */}
            <div className="flex items-center gap-1">
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-10 w-[138px] text-xs"
                title="Date d'import — début"
              />
              <span className="shrink-0 text-muted-foreground text-xs">→</span>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-10 w-[138px] text-xs"
                title="Date d'import — fin"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              <Button
                variant="ghost"
                className="gap-2 text-muted-foreground"
                onClick={() => {
                  setSearch("");
                  setStatusFilter("all");
                  setManagerFilter("all");
                  setDateFrom("");
                  setDateTo("");
                  setMyOrdersOnly(false);   // tout effacer, y compris le filtre "Mes dossiers"
                  setSortKey("createdAt");
                  setSortDirection("desc");
                }}
              >
                <X className="h-4 w-4" />
                Réinitialiser
              </Button>
            </div>
          </div>

          {/* Palette de statuts */}
          <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border bg-background/80 p-3">
            <span className="text-sm font-medium text-foreground">Statut</span>
            {STATUS_FILTERS.map((option) => (
              <Button
                key={option.value}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setStatusFilter(option.value)}
                className={cn(
                  "rounded-full border px-3 text-xs font-semibold shadow-sm transition-colors",
                  option.className,
                  statusFilter === option.value && "ring-2 ring-primary ring-offset-2",
                )}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </CardContent>

        <CardContent className="p-0">
          {ordersList.isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Chargement…</p>
          ) : filteredItems.length === 0 ? (
            <div className="flex flex-col items-center gap-4 p-12 text-center">
              <p className="text-muted-foreground">Aucune commande ne correspond à ces filtres.</p>
              <Button onClick={() => navigate("/convertir")}>
                Importer un bon de commande PDF
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("fileName")}>
                      Fichier
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("clientName")}>
                      Client
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  {isAdmin && (
                    <TableHead>
                      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("confidence")}>
                        Confiance
                        <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                    </TableHead>
                  )}
                  {isAdmin && (
                    <TableHead>
                      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("issue")}>
                        Problématique
                        <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                    </TableHead>
                  )}
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("createdAt")}>
                      Date import
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("processedAt")}>
                      Traité le
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("processedBy")}>
                      Gestionnaire
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map((row) => (
                  <TableRow
                    key={row.orderId}
                    className="cursor-pointer"
                    onClick={() => navigate(`/revue/${row.orderId}`)}
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileIcon className="h-4 w-4 text-red-500" />
                        <span className="max-w-[200px] truncate text-sm">{row.fileName}</span>
                      </div>
                    </TableCell>
                    <TableCell>{row.clientName}</TableCell>
                    {isAdmin && (
                      <TableCell className={confidenceColor(row.confidence)}>
                        {row.confidence}%
                      </TableCell>
                    )}
                    {isAdmin && <TableCell className="text-sm text-muted-foreground">{row.issue}</TableCell>}
                    <TableCell className="text-sm">{formatDateTime(row.createdAt || row.date, displayTimeZone)}</TableCell>
                    <TableCell className="text-sm">
                      {row.processedAt ? formatDateTime(row.processedAt, displayTimeZone) : <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <Badge variant={GROUP_STATUS_BADGE[statusToFilterGroup(row.status as OrderStatus)].variant}>
                        {GROUP_STATUS_BADGE[statusToFilterGroup(row.status as OrderStatus)].label}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {getDisplayName(row.assignedTo || row.processedBy) || <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <SourceBadge source={row.source} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
