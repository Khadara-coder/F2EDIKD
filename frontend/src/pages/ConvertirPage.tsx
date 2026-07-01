import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Calendar,
  Euro,
  MapPin,
  Package,
  ShoppingCart,
  Eye,
  ArrowRight,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { mockExtractionPreview } from "@/lib/mockData";
import type { ExtractionPreview } from "@/types";
import { Header } from "@/components/layout/Header";
import { UploadDropzone } from "@/components/file2edi/UploadDropzone";
import { ProgressStepper } from "@/components/file2edi/ProgressStepper";
import { OrderPreviewCard } from "@/components/file2edi/OrderPreviewCard";
import { ExtractedDataTable } from "@/components/file2edi/ExtractedDataTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatCurrency, formatDate, formatDateTime, formatFileSize } from "@/lib/utils";

export function ConvertirPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<ExtractionPreview>(mockExtractionPreview);

  const extractMutation = useMutation({
    mutationFn: async (file: File) => {
      const { uploadId } = await api.uploadPdf(file);
      return api.launchExtractionJob(uploadId);
    },
    onSuccess: (data) => {
      setPreview(data);
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const isProcessing = extractMutation.isPending;

  return (
    <>
      <Header
        title="Convertir"
        subtitle="Convertir un PDF commande en fichier EDIFACT .tst"
      />

      <div className="space-y-6">
        <UploadDropzone
          onFileSelect={(file) => extractMutation.mutate(file)}
          disabled={isProcessing}
        />

        {isProcessing && (
          <div className="flex items-center justify-center gap-2 rounded-lg border bg-primary/5 py-4 text-sm text-primary">
            <Loader2 className="h-4 w-4 animate-spin" />
            Extraction en cours…
          </div>
        )}

        {extractMutation.isError && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {(extractMutation.error as Error).message || "Échec de l'extraction"}
          </p>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Résumé du fichier
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <SummaryRow label="Nom du fichier" value={preview.fileName} />
              <SummaryRow label="Taille" value={formatFileSize(preview.fileSize)} />
              <SummaryRow label="Pages" value={String(preview.pageCount)} />
              <SummaryRow label="Détecté le" value={formatDateTime(preview.detectedAt)} />
            </CardContent>
          </Card>

          <OrderPreviewCard
            title="Aperçu des extractions"
            items={[
              {
                icon: Building2,
                label: "Client",
                value: preview.clientName ? "1" : "0",
                iconColor: "text-blue-600",
              },
              {
                icon: MapPin,
                label: "Adresse de livraison",
                value: preview.deliveryAddress ? "1" : "0",
                iconColor: "text-emerald-600",
              },
              {
                icon: ShoppingCart,
                label: "Commande client",
                value: preview.customerOrderNumber ? "1" : "0",
                iconColor: "text-amber-600",
              },
              {
                icon: Package,
                label: "Lignes d'article",
                value: String(preview.lineCount),
                iconColor: "text-violet-600",
              },
              {
                icon: Calendar,
                label: "Date de commande",
                value: formatDate(preview.orderDate),
                iconColor: "text-red-500",
              },
              {
                icon: Euro,
                label: "Montant total (HT)",
                value: formatCurrency(preview.totalAmount, preview.currency),
                iconColor: "text-blue-600",
              },
            ]}
          />

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Progression
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ProgressStepper steps={preview.steps} />
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Aperçu des données extraites
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ExtractedDataTable preview={preview} />
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => navigate(`/revue/${preview.orderId}`)}
          >
            <Eye className="h-4 w-4" />
            Voir le détail des lignes
          </Button>
          <Button
            className="gap-2"
            onClick={() => navigate(`/revue/${preview.orderId}`)}
          >
            Aller à la revue
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-dashed border-slate-100 py-1.5 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="max-w-[60%] truncate text-right font-medium">{value}</span>
    </div>
  );
}
