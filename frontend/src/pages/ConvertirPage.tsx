import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, ArrowRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ExtractionPreview } from "@/types";
import { Header } from "@/components/layout/Header";
import { UploadDropzone } from "@/components/file2edi/UploadDropzone";
import { ProgressStepper } from "@/components/file2edi/ProgressStepper";
import { ExtractedDataTable } from "@/components/file2edi/ExtractedDataTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function ConvertirPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<ExtractionPreview | null>(null);

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

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Progression
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {preview ? (
              <ProgressStepper steps={preview.steps} orientation="horizontal" />
            ) : (
              <p className="text-sm text-muted-foreground">
                La progression apparaîtra après l'extraction d'un PDF.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Aperçu des données extraites
            </CardTitle>
          </CardHeader>
          <CardContent>
            {preview ? (
              <ExtractedDataTable preview={preview} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Aucun aperçu disponible. Importez un PDF pour lancer l'extraction.
              </p>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => preview && navigate(`/revue/${preview.orderId}`)}
            disabled={!preview}
          >
            <Eye className="h-4 w-4" />
            Voir le détail des lignes
          </Button>
          <Button
            className="gap-2"
            onClick={() => preview && navigate(`/revue/${preview.orderId}`)}
            disabled={!preview}
          >
            Aller à la revue
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </>
  );
}
