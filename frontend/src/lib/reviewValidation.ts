import type { Order, OrderAnomaly, OrderLine, OrderPartner } from "@/types";

const PENDING_ANOMALY_STATUSES = new Set(["Ouverte", "Bloquante"]);

export function isAnomalyPending(anomaly: OrderAnomaly): boolean {
  return PENDING_ANOMALY_STATUSES.has(anomaly.status);
}

export function countPendingAnomalies(anomalies: OrderAnomaly[]): number {
  return anomalies.filter(isAnomalyPending).length;
}

export function collectReviewBlockers(
  order: Order,
  partners: OrderPartner[],
  lines: OrderLine[],
  anomalies: OrderAnomaly[] = [],
): string[] {
  const errors: string[] = [];
  const soldto = partners.find((p) => p.partnerFunction === "soldto");
  const shipto = partners.find((p) => p.partnerFunction === "shipto");

  const pendingAnomalies = anomalies.filter(isAnomalyPending);
  if (pendingAnomalies.length > 0) {
    errors.push(
      `${pendingAnomalies.length} anomalie${pendingAnomalies.length > 1 ? "s" : ""} en attente — validez ou ignorez chacune avant de valider la commande`,
    );
    for (const anomaly of pendingAnomalies) {
      errors.push(`Anomalie : ${anomaly.message}`);
    }
  }

  if (!order.customerOrderNumber?.trim()) {
    errors.push("N° de commande client manquant");
  }
  if (!order.orderDate) {
    errors.push("Date de commande manquante");
  }
  if (!soldto?.partnerCode?.trim()) {
    errors.push("Code sold-to SAP manquant (section Sold-to / AG)");
  }
  if (!shipto?.partnerCode?.trim()) {
    errors.push("Code ship-to SAP manquant");
  }
  if (lines.length === 0) {
    errors.push("Aucune ligne de commande — ajoutez au moins une ligne");
  } else {
    for (const line of lines) {
      if (!line.boschArticle?.trim()) {
        errors.push(`Ligne ${line.lineNumber} : article Bosch manquant`);
      } else if (!line.quantity) {
        errors.push(`Ligne ${line.lineNumber} : quantité manquante`);
      }
    }
  }

  return errors;
}
