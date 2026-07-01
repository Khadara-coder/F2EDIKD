import { Download, FileText, Printer, ZoomIn, ZoomOut } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface PdfPreviewPanelProps {
  fileName: string;
  orderId?: string;
  pdfUrl?: string;
}

export function PdfPreviewPanel({ fileName, orderId, pdfUrl }: PdfPreviewPanelProps) {
  const [zoom, setZoom] = useState(100);

  const src = useMemo(() => {
    const base = pdfUrl || (orderId ? `/api/orders/${orderId}/pdf` : undefined);
    if (!base) return undefined;
    return `${base}#toolbar=1&navpanes=0&view=FitH`;
  }, [pdfUrl, orderId]);

  const height = Math.round(480 * (zoom / 100));

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
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-base font-semibold">
          Aperçu PDF / Extraction
        </CardTitle>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setZoom((z) => Math.max(50, z - 10))}
            disabled={!src}
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="w-10 text-center text-xs text-muted-foreground">{zoom}%</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setZoom((z) => Math.min(200, z + 10))}
            disabled={!src}
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handleDownload}
            disabled={!src}
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={handlePrint}
            disabled={!src}
          >
            <Printer className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div
          className="overflow-auto rounded-lg border bg-slate-200 p-2"
          style={{ minHeight: 480 }}
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
            <div className="flex min-h-[480px] flex-col items-center justify-center gap-3 rounded bg-white p-8 text-center text-sm text-muted-foreground">
              <FileText className="h-10 w-10 text-slate-400" />
              <p className="font-medium text-slate-700">{fileName}</p>
              <p>PDF non disponible pour cette commande.</p>
            </div>
          )}
        </div>
        <p className="mt-3 text-center text-xs text-muted-foreground">
          {src ? "Aperçu du document source" : "Importez un PDF via Convertir pour l’afficher ici"}
        </p>
      </CardContent>
    </Card>
  );
}
