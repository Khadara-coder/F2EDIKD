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
import { Fragment, useMemo } from "react";

interface AnomaliesTableProps {
  anomalies: OrderAnomaly[];
  comments?: OrderComment[];
  selectedAnomalyId: string | null;
  onSelectAnomaly: (anomalyId: string | null) => void;
  onResolve: (anomalyId: string, action: "corrected" | "ignored") => void;
  disabled?: boolean;
}

const DOMAIN_ORDER = [
  "DOCUMENT",
  "PARTNER",
  "DUPLICATE",
  "ARTICLE",
  "ORDER",
  "EDI",
  "DELIVERY",
  "TECHNICAL",
] as const;

const DOMAIN_LABELS: Record<string, string> = {
  DOCUMENT: "Document",
  PARTNER: "Partenaire",
  ARTICLE: "Article",
  ORDER: "Commande",
  EDI: "EDI",
  DELIVERY: "Livraison",
  DUPLICATE: "Doublon",
  TECHNICAL: "Technique",
};

const SEVERITY_LABELS: Record<string, string> = {
  INFO: "Info",
  WARNING: "Avertissement",
  ERROR: "Erreur",
  CRITICAL: "Critique",
};

function domainOf(a: OrderAnomaly): string {
  return (a.issueDomain || "TECHNICAL").toUpperCase();
}

function isRowBlocking(a: OrderAnomaly): boolean {
  if (typeof a.blocking === "boolean") return a.blocking;
  return a.severity === "error" || a.severity === "blocking";
}

function groupAnomalies(anomalies: OrderAnomaly[]): { domain: string; items: OrderAnomaly[] }[] {
  const buckets = new Map<string, OrderAnomaly[]>();
  for (const a of anomalies) {
    const d = domainOf(a);
    const list = buckets.get(d);
    if (list) list.push(a);
    else buckets.set(d, [a]);
  }
  const known = DOMAIN_ORDER.filter((d) => buckets.has(d)).map((d) => ({
    domain: d,
    items: buckets.get(d)!,
  }));
  const extras = [...buckets.keys()]
    .filter((d) => !(DOMAIN_ORDER as readonly string[]).includes(d))
    .sort()
    .map((d) => ({ domain: d, items: buckets.get(d)! }));
  return [...known, ...extras];
}

export function AnomaliesTable({
  anomalies,
  comments = [],
  selectedAnomalyId,
  onSelectAnomaly,
  onResolve,
  disabled,
}: AnomaliesTableProps) {
  const groups = useMemo(() => groupAnomalies(anomalies), [anomalies]);

  if (!anomalies.length) {
    return <p className="text-sm text-muted-foreground">Aucune anomalie.</p>;
  }

  return (
    <div className="w-full overflow-x-auto" id="review-anomalies" tabIndex={-1}>
      <Table aria-label="Anomalies de la commande">
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Anomalie</TableHead>
            <TableHead className="w-[220px]" scope="col">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {groups.map(({ domain, items }) => (
            <Fragment key={domain}>
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={2}
                  className="bg-muted/40 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {DOMAIN_LABELS[domain] || domain}
                </TableCell>
              </TableRow>
              {items.map((a) => {
                const pending = isAnomalyPending(a);
                const isValidated = a.status === "Corrigée";
                const isIgnored = a.status === "Ignorée";
                const acceptLabel = a.buttonAccept?.trim() || "Corrigé";
                const rejectLabel = a.buttonReject?.trim() || "Refusé";
                const selected = selectedAnomalyId === a.anomalyId;
                const shortMsg = a.message.length > 80 ? `${a.message.slice(0, 80)}…` : a.message;
                const rowId = `anomaly-row-${a.anomalyId}`;
                const blocking = isRowBlocking(a);
                const commentCount = comments.filter((c) => c.anomalyId === a.anomalyId).length;
                const severityKey = (a.issueSeverity || "").toUpperCase();
                const severityLabel = SEVERITY_LABELS[severityKey];
                const statusHint =
                  isValidated ? acceptLabel
                  : isIgnored ? rejectLabel
                  : a.status;

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
                      blocking && pending && "border-l-2 border-l-red-500",
                    )}
                    onClick={() => onSelectAnomaly(selected ? null : a.anomalyId)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectAnomaly(selected ? null : a.anomalyId);
                      }
                    }}
                    aria-label={`${a.message}. Statut ${statusHint}.${selected ? " Sélectionnée." : ""}`}
                  >
                    <TableCell className="max-w-[520px] whitespace-normal text-sm leading-snug">
                      <div className="flex flex-wrap items-start gap-2">
                        <p className="min-w-0 flex-1">{a.message}</p>
                        {severityLabel && (
                          <span
                            className={cn(
                              "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                              severityKey === "CRITICAL" && "bg-red-100 text-red-800",
                              severityKey === "ERROR" && "bg-orange-100 text-orange-800",
                              severityKey === "WARNING" && "bg-amber-100 text-amber-800",
                              severityKey === "INFO" && "bg-slate-100 text-slate-700",
                            )}
                          >
                            {severityLabel}
                          </span>
                        )}
                      </div>
                      {commentCount > 0 && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {commentCount} note{commentCount > 1 ? "s" : ""}
                        </p>
                      )}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant={isValidated ? "default" : "outline"}
                          size="sm"
                          onClick={() => onResolve(a.anomalyId, "corrected")}
                          disabled={disabled}
                          aria-pressed={isValidated}
                          aria-label={`${acceptLabel} — ${shortMsg}`}
                        >
                          {acceptLabel}
                        </Button>
                        <Button
                          variant={isIgnored ? "destructive" : "outline"}
                          size="sm"
                          onClick={() => onResolve(a.anomalyId, "ignored")}
                          disabled={disabled}
                          aria-pressed={isIgnored}
                          aria-label={`${rejectLabel} — ${shortMsg}`}
                        >
                          {rejectLabel}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
