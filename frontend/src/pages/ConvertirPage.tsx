import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Eye, ArrowRight, Loader2 } from "lucide-react";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useUploadQueue } from "@/hooks/useUploadQueue";
import { Header } from "@/components/layout/Header";
import { UploadDropzone } from "@/components/file2edi/UploadDropzone";
import { UploadQueuePanel } from "@/components/file2edi/UploadQueuePanel";
import { ProgressStepper } from "@/components/file2edi/ProgressStepper";
import { ExtractedDataTable } from "@/components/file2edi/ExtractedDataTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function ConvertirPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const meQuery = useCurrentUser();
  const isAdv = meQuery.data?.role === "adv";

  const invalidateDashboard = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["orders"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }, [queryClient]);

  const { jobs, activeCount, enqueueFiles, selectedJob, selectedJobId, setSelectedJobId } =
    useUploadQueue(invalidateDashboard);

  const preview = selectedJob?.preview ?? null;

  return (
    <>
      <Header
        title="Déposer une commande"
        subtitle="Déposez un ou plusieurs PDF — le traitement continue en arrière-plan"
      />

      <div className="space-y-6">
        <UploadDropzone onFilesSelect={enqueueFiles} />

        {activeCount > 0 && (
          <div className="flex items-center justify-center gap-2 rounded-lg border bg-primary/5 py-4 text-sm text-primary">
            <Loader2 className="h-4 w-4 animate-spin" />
            {activeCount} extraction{activeCount > 1 ? "s" : ""} en cours…
          </div>
        )}

        <UploadQueuePanel
          jobs={jobs}
          selectedJobId={selectedJobId}
          onSelectJob={setSelectedJobId}
          onNavigateToReview={(orderId) => navigate(`/revue/${orderId}`)}
        />

        {!isAdv && (
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
                  La progression apparaîtra après l&apos;extraction d&apos;un PDF.
                </p>
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Aperçu des données extraites
              {preview?.fileName ? (
                <span className="ml-2 font-normal normal-case text-foreground">
                  — {preview.fileName}
                </span>
              ) : null}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {preview ? (
              <ExtractedDataTable preview={preview} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Aucun aperçu disponible. Importez un PDF pour lancer l&apos;extraction.
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
