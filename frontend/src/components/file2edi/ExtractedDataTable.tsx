import type { ExtractionPreview } from "@/types";
import { formatCurrency, formatDate } from "@/lib/utils";

interface ExtractedDataTableProps {
  preview: ExtractionPreview;
}

export function ExtractedDataTable({ preview }: ExtractedDataTableProps) {
  const cellLabel = "px-4 py-3 text-sm text-muted-foreground whitespace-nowrap align-top";
  const cellValue = "px-4 py-3 text-sm font-medium align-top";

  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full border-collapse">
        <tbody>
          <tr className="border-b bg-white">
            <td className={cellLabel}>Client</td>
            <td className={cellValue}>{preview.clientName}</td>
            <td className={cellLabel}>Code client</td>
            <td className={cellValue}>{preview.clientCode}</td>
          </tr>
          <tr className="border-b bg-white">
            <td className={cellLabel}>Adresse de livraison</td>
            <td className={`${cellValue} col-span-3`} colSpan={3}>
              {preview.deliveryAddress || "—"}
            </td>
          </tr>
          <tr className="border-b bg-white">
            <td className={cellLabel}>Commande client</td>
            <td className={cellValue}>{preview.customerOrderNumber}</td>
            <td className={cellLabel}>Date</td>
            <td className={cellValue}>{formatDate(preview.orderDate)}</td>
          </tr>
          <tr className="border-b bg-white">
            <td className={cellLabel}>Lignes d&apos;article</td>
            <td className={cellValue}>{preview.lineCount}</td>
            <td className={cellLabel}>Articles uniques</td>
            <td className={cellValue}>{preview.uniqueArticles}</td>
          </tr>
          <tr className="bg-white">
            <td className={cellLabel}>Montant total (HT)</td>
            <td className={cellValue}>
              {formatCurrency(preview.totalAmount, preview.currency)}
            </td>
            <td className={cellLabel}>Devise</td>
            <td className={cellValue}>{preview.currency}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
