import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Download,
  Eye,
  FileText,
  Search,
} from "lucide-react";
import { useHistory } from "@/hooks/useFile2Edi";
import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/file2edi/StatCard";
import { StatusBadge } from "@/components/file2edi/StatusBadge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { confidenceColor, formatDateTime } from "@/lib/utils";
import type { HistoryFilters, OrderStatus } from "@/types";

const STATUS_OPTIONS: (OrderStatus | "all")[] = [
  "all",
  "Généré",
  "Revue requise",
  "Partiel",
  "Rejeté",
];

export function HistoriquePage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<HistoryFilters>({
    page: 1,
    pageSize: 10,
    search: "",
    status: "",
  });
  const { data, isLoading } = useHistory(filters);

  return (
    <>
      <Header
        title="Historique"
        subtitle="Consultez toutes les commandes traitées et leur statut"
      />

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <StatCard
          label="Total traités"
          value={data?.kpis.totalProcessed.toLocaleString("fr-FR") ?? "—"}
          sublabel="Sur les 30 derniers jours"
          icon={FileText}
        />
        <StatCard
          label="Taux auto-validation"
          value={data ? `${data.kpis.autoValidationRate}%` : "—"}
          sublabel={data ? `${data.kpis.autoValidatedCount} / ${data.kpis.totalProcessed}` : undefined}
          icon={CheckCircle}
          iconClassName="bg-emerald-500/10 [&_svg]:text-emerald-600"
        />
        <StatCard
          label="Temps moyen"
          value={data ? `${Math.floor(data.kpis.averageTimeSeconds / 60)}m ${data.kpis.averageTimeSeconds % 60}s` : "—"}
          sublabel="Par document"
          icon={Clock}
          iconClassName="bg-blue-500/10 [&_svg]:text-blue-600"
        />
        <StatCard
          label="Erreurs"
          value={data?.kpis.errors ?? "—"}
          sublabel={data ? `Soit ${data.kpis.errorRate}%` : undefined}
          icon={AlertTriangle}
          iconClassName="bg-red-500/10 [&_svg]:text-red-600"
        />
      </div>

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-3 p-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Rechercher un fichier, client, commande…"
              className="pl-9"
              value={filters.search ?? ""}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value, page: 1 }))}
            />
          </div>
          <Input type="date" className="w-40" />
          <Input type="date" className="w-40" />
          <Select
            value={filters.status || "all"}
            onValueChange={(v) =>
              setFilters((f) => ({
                ...f,
                status: v === "all" ? "" : (v as OrderStatus),
                page: 1,
              }))
            }
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Tous les statuts" />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s} value={s}>
                  {s === "all" ? "Tous les statuts" : s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" className="gap-2">
            <Download className="h-4 w-4" />
            Exporter CSV
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <p className="p-6 text-muted-foreground">Chargement…</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fichier</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Commande client</TableHead>
                  <TableHead>Réf. document</TableHead>
                  <TableHead>Date traitement</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>Confiance</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.rows.map((row) => (
                  <TableRow key={row.conversionId}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-red-500" />
                        <span className="max-w-[160px] truncate text-sm">{row.fileName}</span>
                      </div>
                    </TableCell>
                    <TableCell>{row.clientName}</TableCell>
                    <TableCell>{row.customerOrderNumber}</TableCell>
                    <TableCell>{row.documentReference}</TableCell>
                    <TableCell className="text-sm">{formatDateTime(row.processedAt)}</TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell className={confidenceColor(row.confidence)}>
                      {row.confidence}%
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate(`/revue/${row.orderId}`)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Download className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <div className="flex items-center justify-between border-t px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Affichage {(filters.page! - 1) * filters.pageSize! + 1} à{" "}
              {Math.min(filters.page! * filters.pageSize!, data?.total ?? 0)} sur{" "}
              {data?.total.toLocaleString("fr-FR")} résultats
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={filters.page === 1}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
              >
                Préc.
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(filters.page ?? 1) * (filters.pageSize ?? 10) >= (data?.total ?? 0)}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
              >
                Suiv.
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
