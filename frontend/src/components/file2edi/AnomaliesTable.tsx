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
    <div className="w-full overflow-x-auto" id="review-anomalies" tabIndex={-1}>
      <Table aria-label="Anomalies de la commande">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[88px]" scope="col">Gravité</TableHead>
            <TableHead scope="col">Anomalie</TableHead>
            <TableHead className="w-[140px]" scope="col">Statut</TableHead>
            <TableHead className="min-w-[140px]" scope="col">Commentaire</TableHead>
            <TableHead className="w-[200px]" scope="col">Actions</TableHead>
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
            const shortMsg = a.message.length > 80 ? `${a.message.slice(0, 80)}…` : a.message;
            const rowId = `anomaly-row-${a.anomalyId}`;

            return (
              <TableRow
                key={a.anomalyId}
                id={rowId}
                tabIndex={0}
                aria-selected={selected}
                data-state={selected ? "selected" : undefined}
                className={cn(
                  "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  selected && "bg-primary/5",
                )}
                onClick={() => onSelectAnomaly(selected ? null : a.anomalyId)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectAnomaly(selected ? null : a.anomalyId);
                  }
                }}
                aria-label={`${sev.label}. ${a.message}. Statut ${statusLabel}.${selected ? " Sélectionnée pour commentaire." : " Appuyez sur Entrée pour sélectionner."}`}
              >
                <TableCell>
                  <Badge variant={sev.variant} aria-label={`Gravité ${sev.label}`}>
                    {sev.label}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-[360px] whitespace-normal text-sm leading-snug">
                  {a.message}
                </TableCell>
                <TableCell>
                  <Badge
                    variant={pending ? "warning" : "success"}
                    aria-label={`Statut ${statusLabel}`}
                  >
                    {statusLabel}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground" title={preview}>
                  {preview || "—"}
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <div className="flex flex-col gap-1">
                    <Button
                      variant={isValidated ? "secondary" : "ghost"}
                      size="sm"
                      className="h-auto min-h-9 whitespace-normal px-2 py-1.5 text-left text-xs leading-snug"
                      onClick={() => onResolve(a.anomalyId, "corrected")}
                      disabled={disabled}
                      aria-label={`${acceptLabel} — ${shortMsg}`}
                    >
                      {acceptLabel}
                    </Button>
                    <Button
                      variant={isIgnored ? "secondary" : "ghost"}
                      size="sm"
                      className="h-auto min-h-9 whitespace-normal px-2 py-1.5 text-left text-xs leading-snug"
                      onClick={() => onResolve(a.anomalyId, "ignored")}
                      disabled={disabled}
                      aria-label={`${rejectLabel} — ${shortMsg}`}
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
    </div>
  );
}
