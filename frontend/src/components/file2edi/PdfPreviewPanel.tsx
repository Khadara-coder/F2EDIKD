import { Download, FileText, Printer, ZoomIn, ZoomOut } from "lucide-react";
import { useMemo, useState } from "react";
import { REVIEW_PANEL_BODY_MIN_HEIGHT } from "@/lib/reviewLayout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface PdfPreviewPanelProps {
  fileName: string;
  orderId?: string;
  pdfUrl?: string;
  /** When false on small screens, hide heavy preview to keep page scroll simple. */
  expanded?: boolean;
  onToggleExpanded?: () => void;
}

export function PdfPreviewPanel({
  fileName,
  orderId,
  pdfUrl,
  expanded = true,
  onToggleExpanded,
}: PdfPreviewPanelProps) {
  const [zoom, setZoom] = useState(100);

  const src = useMemo(() => {
    const base = pdfUrl || (orderId ? `/api/orders/${orderId}/pdf` : undefined);
    if (!base) return undefined;
    return `${base}#toolbar=1&navpanes=0&view=FitH`;
  }, [pdfUrl, orderId]);

  const height = Math.round(REVIEW_PANEL_BODY_MIN_HEIGHT * (zoom / 100));

  const handleDownload = () => {
    if (!src) return;
    const link = document.createElement("a");
    link.href = src.split("#")[0];
    link.download = fileName || "document.pdf";
    link.click();
  };

  const handlePrint = () => {
    if (!src) return;
    const w = window.open(src.split("#")[0], "_blank");
    w?.print();
  };

  return (
    <Card className="flex h-full min-w-0 flex-col">
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <CardTitle className="truncate text-base font-semibold">
            Aperçu PDF
          </CardTitle>
          {onToggleExpanded && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0 lg:hidden"
              onClick={onToggleExpanded}
            >
              {expanded ? "Masquer" : "Afficher"}
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setZoom((z) => Math.max(50, z - 10))}
            disabled={!src || !expanded}
            aria-label="Zoom arrière"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="w-10 text-center text-xs text-muted-foreground">{zoom}%</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setZoom((z) => Math.min(200, z + 10))}
            disabled={!src || !expanded}
            aria-label="Zoom avant"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handleDownload}
            disabled={!src}
            aria-label="Télécharger le PDF"
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handlePrint}
            disabled={!src}
            aria-label="Imprimer le PDF"
          >
            <Printer className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      {expanded ? (
        <CardContent className="flex flex-1 flex-col pt-0">
          <div
            className="max-h-[min(70vh,720px)] min-h-[280px] flex-1 overflow-auto rounded-lg border bg-slate-200 p-2 lg:min-h-[520px]"
          >
            {src ? (
              <object
                data={src}
                type="application/pdf"
                title={fileName}
                className="w-full rounded bg-white"
                style={{ height }}
              >
                <iframe
                  src={src}
                  title={fileName}
                  className="w-full rounded border-0 bg-white"
                  style={{ height }}
                />
              </object>
            ) : (
              <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded bg-white p-8 text-center text-sm text-muted-foreground lg:min-h-[520px]">
                <FileText className="h-10 w-10 text-slate-400" />
                <p className="font-medium text-slate-700">{fileName}</p>
                <p>PDF non disponible pour cette commande.</p>
              </div>
            )}
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            {src ? "Document source" : "Importez un PDF via Déposer une commande"}
          </p>
        </CardContent>
      ) : (
        <CardContent className="pt-0 lg:hidden">
          <p className="rounded-lg border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            Aperçu masqué pour faciliter le défilement. Touchez « Afficher » pour le rouvrir.
          </p>
        </CardContent>
      )}
    </Card>
  );
}
