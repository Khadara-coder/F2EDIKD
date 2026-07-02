import type { OrderLine } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn, confidenceColor, formatCurrency } from "@/lib/utils";

interface OrderLinesSummaryTableProps {
  lines: OrderLine[];
  currency?: string;
}

export function OrderLinesSummaryTable({
  lines,
  currency = "EUR",
}: OrderLinesSummaryTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Ligne</TableHead>
          <TableHead>Code article</TableHead>
          <TableHead>Désignation</TableHead>
          <TableHead>Qté</TableHead>
          <TableHead>P.U.</TableHead>
          <TableHead>Confiance</TableHead>
          <TableHead>Statut</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => {
          const variant =
            line.status === "OK"
              ? "success"
              : line.status === "À vérifier"
                ? "warning"
                : line.status === "Corrigé manuellement"
                  ? "info"
                  : "destructive";
          return (
            <TableRow key={line.lineId}>
              <TableCell>
                <span className="font-mono text-xs">{line.lineNumber}</span>
              </TableCell>
              <TableCell>
                <span
                  className={cn(
                    "text-sm font-medium",
                    line.status === "À vérifier" && "text-amber-600",
                  )}
                >
                  {line.boschArticle || "—"}
                </span>
              </TableCell>
              <TableCell>
                <span className="block max-w-[280px] truncate text-sm text-muted-foreground">
                  {line.designation || "—"}
                </span>
              </TableCell>
              <TableCell>{line.quantity}</TableCell>
              <TableCell>{formatCurrency(line.unitPrice, currency)}</TableCell>
              <TableCell>
                <div className="flex min-w-[80px] items-center gap-2">
                  <span className={cn("text-xs font-medium", confidenceColor(line.confidence))}>
                    {line.confidence}%
                  </span>
                  <Progress value={line.confidence} className="h-1.5 w-12" />
                </div>
              </TableCell>
              <TableCell>
                <Badge variant={variant}>{line.status}</Badge>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
