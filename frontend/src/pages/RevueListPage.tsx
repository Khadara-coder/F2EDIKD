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
import {
  businessStatusLabel,
  businessStatusVariant,
  statusToBusinessGroup,
  workflowMotif,
  type ReviewStatusFilter,
} from "@/lib/orderBusinessStatus";

function SourceBadge({ source }: { source?: string }) {
  const map: Record<string, { label: string; className: string }> = {
    n8n:     { label: "n8n",    className: "bg-blue-100 text-blue-800 border-blue-200" },
    ui:      { label: "Manuelle", className: "bg-green-100 text-green-800 border-green-200" },
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

type ReviewSortKey =
  | "fileName"
  | "clientName"
  | "confidence"
  | "issue"
  | "createdAt"
  | "processedAt"
  | "sapVbeln"
  | "processedBy"
  | "status";
type SortDirection = "asc" | "desc";

const STATUS_FILTERS: Array<{ value: ReviewStatusFilter; label: string; className: string }> = [
  { value: "all",            label: "Tous",          className: "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100" },
  { value: "toProcess",      label: "À traiter",     className: "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100" },
  { value: "inProgress",     label: "En cours",      className: "border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100" },
  { value: "sentSap",        label: "Envoyé SAP",    className: "border-teal-200 bg-teal-50 text-teal-700 hover:bg-teal-100" },
  { value: "rejected",       label: "Rejeté",         className: "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100" },
  { value: "deliveryFailed", label: "Échec d'envoi",  className: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100" },
];

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
  const getDisplayName = (username?: string | null) => {
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
        return row.processedAt || row.sapSentAt || "";
      case "sapVbeln":
        return row.sapVbeln || "";
      case "processedBy":
        return (row.processedBy || "").toLowerCase();
      case "status":
        return businessStatusLabel(statusToBusinessGroup(row.status as OrderStatus));
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
        [row.fileName, row.clientName, row.issue, row.status, row.processedBy, row.date, row.createdAt, row.processedAt, row.sapSentAt, row.sapVbeln, row.sapSentBy]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query));
      const matchesStatus = statusFilter === "all" || statusToBusinessGroup(row.status as OrderStatus) === statusFilter;
      // "Mes dossiers" filter - match if user is assignee OR processor
      const rowAssignee = row.assignedTo?.toLowerCase() || "";
      const rowProcessor = (row.processedBy || "").toLowerCase();
      const userLc = (currentUsername || "").toLowerCase();
      const matchesMyOrders = !myOrdersOnly || !currentUsername ||
        rowAssignee === userLc || rowProcessor === userLc;
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
        title="Gérer les commandes"
        subtitle="Toutes les commandes converties - ouvrez un dossier pour valider ou corriger"
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
            Déposer une commande
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
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_190px_310px_auto] lg:items-center">
            <div className="relative sm:col-span-2 lg:col-span-1">
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
            <div className="flex min-w-0 flex-wrap items-center gap-1">
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-10 min-w-0 flex-1 text-xs sm:w-[138px] sm:flex-none"
                title="Date d'import - début"
              />
              <span className="shrink-0 text-xs text-muted-foreground">→</span>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-10 min-w-0 flex-1 text-xs sm:w-[138px] sm:flex-none"
                title="Date d'import - fin"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2 sm:col-span-2 lg:col-span-1 lg:justify-end">
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
                Déposer une commande PDF
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {/* 1. Identification */}
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
                  {/* 2. État métier */}
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("status")}>
                      Statut
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead className="min-w-[220px]">Motif</TableHead>
                  {/* 3. Bloc SAP */}
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("sapVbeln")}>
                      N° commande SAP
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("processedAt")}>
                      Envoyé vers SAP le
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>Envoyé vers SAP par</TableHead>
                  {/* 4. Suivi dossier */}
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("processedBy")}>
                      Gestionnaire
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  <TableHead>
                    <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => handleSort("createdAt")}>
                      Date import
                      <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </TableHead>
                  {/* 5. Métadonnées */}
                  <TableHead>Source</TableHead>
                  <TableHead>Action</TableHead>
                  {/* 6. Diagnostic admin (fin de ligne) */}
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
                        <FileIcon className="h-4 w-4 shrink-0 text-red-500" />
                        <span className="max-w-[180px] truncate text-sm">{row.fileName}</span>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[140px] truncate">{row.clientName}</TableCell>
                    <TableCell>
                      <Badge variant={businessStatusVariant(statusToBusinessGroup(row.status as OrderStatus))}>
                        {businessStatusLabel(statusToBusinessGroup(row.status as OrderStatus))}
                      </Badge>
                    </TableCell>
                    <TableCell className="min-w-[220px] max-w-sm align-top text-xs leading-snug text-muted-foreground">
                      {(() => {
                        const motif = workflowMotif(row, getDisplayName);
                        return motif ? (
                          <span className="whitespace-normal break-words text-sky-700">{motif}</span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        );
                      })()}
                    </TableCell>
                    <TableCell>
                      {row.sapVbeln ? (
                        <span className="font-mono text-sm font-medium">{row.sapVbeln}</span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">
                      {row.processedAt || row.sapSentAt
                        ? formatDateTime(row.processedAt || row.sapSentAt, displayTimeZone)
                        : <span className="text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell className="max-w-[120px] truncate text-sm text-muted-foreground">
                      {getDisplayName(row.sapSentBy) || <span className="text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell className="max-w-[120px] truncate text-sm text-muted-foreground">
                      {getDisplayName(
                        row.status === "Transféré" ? (row.transferredTo || row.assignedTo) : row.assignedTo
                        || row.processedBy
                      ) || <span className="text-muted-foreground">-</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">{formatDateTime(row.createdAt || row.date, displayTimeZone)}</TableCell>
                    <TableCell>
                      <SourceBadge source={row.source} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {row.action || <span className="text-muted-foreground">-</span>}
                    </TableCell>
                    {isAdmin && (
                      <TableCell className={confidenceColor(row.confidence)}>
                        {row.confidence}%
                      </TableCell>
                    )}
                    {isAdmin && (
                      <TableCell className="max-w-[160px] truncate text-sm text-muted-foreground">
                        {row.issue || "-"}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
