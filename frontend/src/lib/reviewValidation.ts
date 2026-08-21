import type { Order, OrderAnomaly, OrderLine, OrderPartner } from "@/types";

const PENDING_ANOMALY_STATUSES = new Set(["Ouverte", "Bloquante"]);

export type ReviewFieldKey =
  | "customerOrderNumber"
  | "orderDate"
  | "soldto"
  | "shipto"
  | "lines"
  | "anomalies";

export interface ReviewBlocker {
  field: ReviewFieldKey;
  message: string;
  /** DOM id of the control to focus (when known). */
  focusId?: string;
}

export function isAnomalyPending(anomaly: OrderAnomaly): boolean {
  return PENDING_ANOMALY_STATUSES.has(anomaly.status);
}

export function countPendingAnomalies(anomalies: OrderAnomaly[]): number {
  return anomalies.filter(isAnomalyPending).length;
}

export function collectReviewBlockersDetailed(
  order: Order,
  partners: OrderPartner[],
  lines: OrderLine[],
  anomalies: OrderAnomaly[] = [],
): ReviewBlocker[] {
  const errors: ReviewBlocker[] = [];
  const soldto = partners.find((p) => p.partnerFunction === "soldto");
  const shipto = partners.find((p) => p.partnerFunction === "shipto");

  const pendingAnomalies = anomalies.filter(isAnomalyPending);
  if (pendingAnomalies.length > 0) {
    errors.push({
      field: "anomalies",
      message: `${pendingAnomalies.length} anomalie${pendingAnomalies.length > 1 ? "s" : ""} en attente - validez ou ignorez chacune avant de valider la commande`,
      focusId: "review-anomalies",
    });
    for (const anomaly of pendingAnomalies) {
      errors.push({
        field: "anomalies",
        message: `Anomalie : ${anomaly.message}`,
        focusId: `anomaly-row-${anomaly.anomalyId}`,
      });
    }
  }

  if (!order.customerOrderNumber?.trim()) {
    errors.push({
      field: "customerOrderNumber",
      message: "N° de commande client manquant",
      focusId: "field-customerOrderNumber",
    });
  }
  if (!order.orderDate) {
    errors.push({
      field: "orderDate",
      message: "Date de commande manquante",
      focusId: "field-orderDate",
    });
  }
  if (!soldto?.partnerCode?.trim()) {
    errors.push({
      field: "soldto",
      message: "Code sold-to SAP manquant (section Sold-to / AG)",
      focusId: "field-soldto",
    });
  }
  if (!shipto?.partnerCode?.trim()) {
    errors.push({
      field: "shipto",
      message: "Code ship-to SAP manquant",
      focusId: "field-shipto",
    });
  }
  if (lines.length === 0) {
    errors.push({
      field: "lines",
      message: "Aucune ligne de commande - ajoutez au moins une ligne",
      focusId: "review-order-lines",
    });
  } else {
    for (const line of lines) {
      if (!line.boschArticle?.trim()) {
        errors.push({
          field: "lines",
          message: `Ligne ${line.lineNumber} : article Bosch manquant`,
          focusId: "review-order-lines",
        });
      } else if (!line.quantity) {
        errors.push({
          field: "lines",
          message: `Ligne ${line.lineNumber} : quantité manquante`,
          focusId: "review-order-lines",
        });
      }
    }
  }

  return errors;
}

/** Backward-compatible string list used by dialogs and existing callers. */
export function collectReviewBlockers(
  order: Order,
  partners: OrderPartner[],
  lines: OrderLine[],
  anomalies: OrderAnomaly[] = [],
): string[] {
  return collectReviewBlockersDetailed(order, partners, lines, anomalies).map((e) => e.message);
}

export function fieldErrorMap(blockers: ReviewBlocker[]): Partial<Record<ReviewFieldKey, string>> {
  const map: Partial<Record<ReviewFieldKey, string>> = {};
  for (const b of blockers) {
    if (!map[b.field]) map[b.field] = b.message;
  }
  return map;
}

export function focusFirstBlocker(blockers: ReviewBlocker[]): void {
  for (const b of blockers) {
    if (!b.focusId) continue;
    const el = document.getElementById(b.focusId);
    if (!el) continue;
    el.focus({ preventScroll: false });
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
}
