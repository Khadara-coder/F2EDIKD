import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isAnomalyPending } from "@/lib/reviewValidation";
import { cn } from "@/lib/utils";
import type { OrderAnomaly, OrderComment } from "@/types";

interface AnomaliesTableProps {
  anomalies: OrderAnomaly[];
  comments?: OrderComment[];
  selectedAnomalyId: string | null;
  onSelectAnomaly: (anomalyId: string | null) => void;
  onResolve: (anomalyId: string, action: "corrected" | "ignored") => void;
  disabled?: boolean;
}

function severityMeta(severity: string): { label: string; variant: "destructive" | "warning" | "info" | "secondary" } {
  if (severity === "error" || severity === "blocking") {
    return { label: "Erreur", variant: "destructive" };
  }
  if (severity === "warning") {
    return { label: "Alerte", variant: "warning" };
  }
  if (severity === "info") {
    return { label: "Info", variant: "info" };
  }
  return { label: severity || "Alerte", variant: "secondary" };
}

function latestCommentFor(anomalyId: string, comments: OrderComment[]): string {
  const linked = comments.filter((c) => c.anomalyId === anomalyId);
  if (!linked.length) return "";
  return linked[linked.length - 1]?.body?.trim() || "";
}

export function AnomaliesTable({
  anomalies,
  comments = [],
  selectedAnomalyId,
  onSelectAnomaly,
  onResolve,
  disabled,
}: AnomaliesTableProps) {
  if (!anomalies.length) {
    return <p className="text-sm text-muted-foreground">Aucune anomalie signalée.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[88px]">Gravité</TableHead>
          <TableHead>Anomalie</TableHead>
          <TableHead className="w-[140px]">Statut</TableHead>
          <TableHead className="min-w-[140px]">Commentaire</TableHead>
          <TableHead className="w-[200px]">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {anomalies.map((a) => {
          const pending = isAnomalyPending(a);
          const isValidated = a.status === "Corrigée";
          const isIgnored = a.status === "Ignorée";
          const acceptLabel = a.buttonAccept?.trim() || "Corrigé";
          const rejectLabel = a.buttonReject?.trim() || "Refusé";
          const statusLabel =
            a.status === "Corrigée" ? acceptLabel
            : a.status === "Ignorée" ? rejectLabel
            : a.status;
          const selected = selectedAnomalyId === a.anomalyId;
          const preview = latestCommentFor(a.anomalyId, comments);
          const sev = severityMeta(a.severity);

          return (
            <TableRow
              key={a.anomalyId}
              data-state={selected ? "selected" : undefined}
              className={cn("cursor-pointer", selected && "bg-primary/5")}
              onClick={() => onSelectAnomaly(selected ? null : a.anomalyId)}
            >
              <TableCell>
                <Badge variant={sev.variant}>{sev.label}</Badge>
              </TableCell>
              <TableCell className="max-w-[360px] whitespace-normal text-sm leading-snug">
                {a.message}
              </TableCell>
              <TableCell>
                <Badge variant={pending ? "warning" : "success"}>{statusLabel}</Badge>
              </TableCell>
              <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground" title={preview}>
                {preview || "—"}
              </TableCell>
              <TableCell onClick={(e) => e.stopPropagation()}>
                <div className="flex flex-col gap-1">
                  <Button
                    variant={isValidated ? "secondary" : "ghost"}
                    size="sm"
                    className="h-auto whitespace-normal px-2 py-1.5 text-left text-xs leading-snug"
                    onClick={() => onResolve(a.anomalyId, "corrected")}
                    disabled={disabled}
                  >
                    {acceptLabel}
                  </Button>
                  <Button
                    variant={isIgnored ? "secondary" : "ghost"}
                    size="sm"
                    className="h-auto whitespace-normal px-2 py-1.5 text-left text-xs leading-snug"
                    onClick={() => onResolve(a.anomalyId, "ignored")}
                    disabled={disabled}
                  >
                    {rejectLabel}
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
