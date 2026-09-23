import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { OrderAnomaly, OrderComment } from "@/types";
import { Fragment, useMemo } from "react";

interface AnomaliesTableProps {
  anomalies: OrderAnomaly[];
  comments?: OrderComment[];
  selectedAnomalyId: string | null;
  onSelectAnomaly: (anomalyId: string | null) => void;
  onChoose: (anomalyId: string, outcome: string) => void;
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
  onChoose,
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
                const selected = selectedAnomalyId === a.anomalyId;
                const rowId = `anomaly-row-${a.anomalyId}`;
                const commentCount = comments.filter((c) => c.anomalyId === a.anomalyId).length;
                const severityKey = (a.issueSeverity || "").toUpperCase();
                const severityLabel = SEVERITY_LABELS[severityKey];
                // Dual-display: rejection_catalog.format_rejection_message produces
                // per-line dynamic text ("Ligne 3 : la référence X remplacée par Y…",
                // "Quantité manquante sur la/les ligne(s) : 3, 5", "PO-42 existe
                // déjà dans l'historique SAP") stored in `a.message`; the catalog's
                // uxMessage is the general framing. The primary line is the
                // specific text, the secondary line is the framing when it adds
                // something distinct. Handles: message empty → fall back to
                // uxMessage; uxMessage empty (UX-08) → only primary; identical →
                // no duplicate.
                const rawMessage = a.message?.trim() ?? "";
                const rawUxMessage = a.uxMessage?.trim() ?? "";
                const displayMessage = rawMessage || rawUxMessage;
                const secondaryMessage =
                  rawUxMessage &&
                  rawUxMessage.toLowerCase() !== rawMessage.toLowerCase() &&
                  rawUxMessage !== displayMessage
                    ? rawUxMessage
                    : null;
                const statusHint = a.status;

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
                      // Only handle keys targeting the row itself — do not
                      // swallow Enter/Space when they were dispatched to a
                      // focused inner button (choice buttons must remain
                      // keyboard-activatable for a11y).
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectAnomaly(selected ? null : a.anomalyId);
                      }
                    }}
                    aria-label={`${displayMessage}. Statut ${statusHint}.${selected ? " Sélectionnée." : ""}`}
                  >
                    <TableCell className="max-w-[520px] whitespace-normal text-sm leading-snug">
                      <div className="flex flex-wrap items-start gap-2">
                        <p className="min-w-0 flex-1">{displayMessage}</p>
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
                      {secondaryMessage && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {secondaryMessage}
                        </p>
                      )}
                      {commentCount > 0 && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {commentCount} note{commentCount > 1 ? "s" : ""}
                        </p>
                      )}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex flex-wrap gap-2">
                        {a.uxChoices?.map((choice) => (
                          <Button
                            key={`${a.anomalyId}-${choice.outcome}`}
                            type="button"
                                variant={a.uxChoice === choice.outcome ? "default" : "outline"}
                            size="sm"
                                className={cn(
                                  "border-blue-300",
                                  a.uxChoice === choice.outcome
                                    ? "bg-blue-600 text-white hover:bg-blue-700"
                                    : "text-blue-700 hover:bg-blue-50 hover:text-blue-800",
                                )}
                            onClick={() => onChoose(a.anomalyId, choice.outcome)}
                            disabled={disabled}
                          >
                            {choice.label}
                          </Button>
                        ))}
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
