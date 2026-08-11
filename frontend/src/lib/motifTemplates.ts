/** Motifs prédéfinis pour les actions workflow (mise en attente, rejet, transfert). */

export const HOLD_MOTIF_TEMPLATES = [
  "En attente de validation client",
  "Information manquante sur le PDF",
  "En attente retour commercial",
  "Ship-to ou sold-to à confirmer",
  "Doublon à vérifier",
] as const;

export const REJECT_MOTIF_TEMPLATES = [
  "Document illisible ou incomplet",
  "Client inconnu ou non référencé",
  "Commande annulée par le client",
  "Montant ou quantité incohérent",
  "Doublon confirmé",
  "Références article invalides",
] as const;

export const TRANSFER_MOTIF_TEMPLATES = [
  "À traiter en priorité",
  "Vérifier le ship-to",
  "Contacter le client",
  "Compléter les lignes manquantes",
  "Valider les corrections demandées",
] as const;

export type MotifTemplateContext = "hold" | "reject" | "transfer";

export function motifTemplatesFor(context: MotifTemplateContext): readonly string[] {
  switch (context) {
    case "hold":
      return HOLD_MOTIF_TEMPLATES;
    case "reject":
      return REJECT_MOTIF_TEMPLATES;
    case "transfer":
      return TRANSFER_MOTIF_TEMPLATES;
  }
}
