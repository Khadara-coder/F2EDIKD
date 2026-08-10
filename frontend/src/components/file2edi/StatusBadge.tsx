import type { OrderStatus } from "@/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  businessStatusVariant,
  displayStatusLabel,
  statusToBusinessGroup,
} from "@/lib/orderBusinessStatus";

const statusConfig: Record<
  OrderStatus,
  { variant: "success" | "warning" | "destructive" | "purple" | "info" | "secondary" | "orange"; label: string }
> = {
  Généré:          { variant: "success",     label: "Généré" },
  "Revue requise": { variant: "purple",      label: "Revue requise" },
  Rejeté:          { variant: "destructive", label: "Rejeté" },
  Doublon:         { variant: "secondary",   label: "Doublon" },
  "SFTP échoué":   { variant: "destructive", label: "SFTP échoué" },
  "À revoir":      { variant: "warning",     label: "À revoir" },
  "À vérifier":    { variant: "warning",     label: "À vérifier" },
  Bloqué:          { variant: "destructive", label: "Bloqué" },
  Validé:          { variant: "success",     label: "Validé" },
  "À traiter":     { variant: "warning",     label: "À traiter" },
  "En attente":    { variant: "orange",      label: "En attente" },
  "Envoyé SAP":    { variant: "success",     label: "Envoyé SAP" },
  "Confirmé SAP":  { variant: "success",     label: "Confirmé SAP" },
  Transféré:       { variant: "info",        label: "Transféré" },
  "Échec SAP":     { variant: "destructive", label: "Échec SAP" },
};

interface StatusBadgeProps {
  status: OrderStatus | string;
  className?: string;
  /** Affiche le statut métier (En cours) au lieu du statut technique. */
  business?: boolean;
}

export function StatusBadge({ status, className, business = true }: StatusBadgeProps) {
  if (business && status in statusConfig) {
    const group = statusToBusinessGroup(status as OrderStatus);
    return (
      <Badge variant={businessStatusVariant(group)} className={cn("font-medium", className)}>
        {displayStatusLabel(status as OrderStatus)}
      </Badge>
    );
  }
  const config = statusConfig[status as OrderStatus] ?? {
    variant: "secondary" as const,
    label: status,
  };
  return (
    <Badge variant={config.variant} className={cn("font-medium", className)}>
      {config.label}
    </Badge>
  );
}
