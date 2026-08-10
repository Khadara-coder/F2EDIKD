import type { OrderStatus, ReviewQueueItem } from "@/types";

/** Statuts métier affichés dans Gérer les commandes (filtres + badges). */
export type BusinessStatusGroup =
  | "toProcess"
  | "inProgress"
  | "sentSap"
  | "rejected"
  | "deliveryFailed";

export type ReviewStatusFilter = "all" | BusinessStatusGroup;

const IN_PROGRESS_STATUSES = new Set<OrderStatus>([
  "En attente",
  "Transféré",
  "Généré",
  "Validé",
]);

export function statusToBusinessGroup(status: OrderStatus): BusinessStatusGroup {
  if (
    status === "Revue requise"
    || status === "À revoir"
    || status === "À vérifier"
    || status === "Bloqué"
    || status === "À traiter"
  ) {
    return "toProcess";
  }
  if (IN_PROGRESS_STATUSES.has(status)) {
    return "inProgress";
  }
  if (status === "Envoyé SAP") {
    return "sentSap";
  }
  if (status === "Rejeté" || status === "Doublon") {
    return "rejected";
  }
  if (status === "SFTP échoué" || status === "Échec SAP") {
    return "deliveryFailed";
  }
  return "toProcess";
}

export function businessStatusLabel(group: BusinessStatusGroup): string {
  switch (group) {
    case "toProcess":
      return "À traiter";
    case "inProgress":
      return "En cours";
    case "sentSap":
      return "Envoyé SAP";
    case "rejected":
      return "Rejeté";
    case "deliveryFailed":
      return "Échec d'envoi";
  }
}

export function businessStatusVariant(
  group: BusinessStatusGroup,
): "warning" | "success" | "info" | "destructive" | "orange" {
  switch (group) {
    case "toProcess":
      return "warning";
    case "inProgress":
      return "info";
    case "sentSap":
      return "success";
    case "rejected":
      return "destructive";
    case "deliveryFailed":
      return "destructive";
  }
}

export function displayStatusLabel(status: OrderStatus): string {
  return businessStatusLabel(statusToBusinessGroup(status));
}

const BUSINESS_GROUP_STATUSES: Record<BusinessStatusGroup, OrderStatus[]> = {
  toProcess: ["Revue requise", "À revoir", "À vérifier", "Bloqué", "À traiter"],
  inProgress: ["En attente", "Transféré", "Généré", "Validé"],
  sentSap: ["Envoyé SAP"],
  rejected: ["Rejeté", "Doublon"],
  deliveryFailed: ["SFTP échoué", "Échec SAP"],
};

export function businessGroupToTechnicalStatuses(group: BusinessStatusGroup): OrderStatus[] {
  return BUSINESS_GROUP_STATUSES[group];
}

export function workflowMotif(row: Pick<
  ReviewQueueItem,
  "status" | "holdReason" | "issue" | "transferredFrom" | "transferNote"
> & { transferredFrom?: string | null }, getDisplayName?: (username?: string | null) => string | null): string | null {
  const status = row.status as OrderStatus;
  if (status === "En attente" && row.holdReason) {
    return `En attente — ${row.holdReason}`;
  }
  if (status === "Transféré") {
    const from = getDisplayName?.(row.transferredFrom) || row.transferredFrom || "—";
    return row.transferNote ? `Transféré par ${from} — ${row.transferNote}` : `Transféré par ${from}`;
  }
  if (status === "Généré" || status === "Validé") {
    return "Traité — EDIFACT prêt, en attente envoi SAP";
  }
  if (status === "Rejeté" && row.issue) {
    return row.issue;
  }
  return null;
}
