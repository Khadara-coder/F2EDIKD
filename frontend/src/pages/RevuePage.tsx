import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { Download, CheckCircle, Send } from "lucide-react";
import { api } from "@/lib/api";
import { useOrderReview } from "@/hooks/useFile2Edi";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/file2edi/StatCard";
import { StatusBadge } from "@/components/file2edi/StatusBadge";
import { PdfPreviewPanel } from "@/components/file2edi/PdfPreviewPanel";
import { OrderGeneralInfoPanel } from "@/components/file2edi/OrderGeneralInfoPanel";
import { OrderLinesEditPanel } from "@/components/file2edi/OrderLinesEditPanel";
import { OrderLinesSummaryTable } from "@/components/file2edi/OrderLinesSummaryTable";
import { ProgressStepper } from "@/components/file2edi/ProgressStepper";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatDate, downloadTextFile } from "@/lib/utils";
import { collectReviewBlockers, countPendingAnomalies, isAnomalyPending } from "@/lib/reviewValidation";

export function RevuePage() {
  const { orderId } = useParams();
  if (!orderId) {
    return <Navigate to="/revue" replace />;
  }
  const queryClient = useQueryClient();
  const meQuery = useCurrentUser();
  const { data, isLoading, isError, error, refetch } = useOrderReview(orderId);
  const [infoDialog, setInfoDialog] = useState<{ title: string; message: string } | null>(null);
  const [confirmSendOpen, setConfirmSendOpen] = useState(false);
  const [confirmResendOpen, setConfirmResendOpen] = useState(false);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["order", orderId, "review"] });

  const updateHeader = useMutation({
    mutationFn: (payload: Parameters<typeof api.updateOrderHeader>[1]) =>
      api.updateOrderHeader(orderId, payload),
    onSuccess: invalidate,
  });

  const updateLine = useMutation({
    mutationFn: ({ lineId, payload }: { lineId: string; payload: Parameters<typeof api.updateOrderLine>[1] }) =>
      api.updateOrderLine(lineId, payload),
    onSuccess: invalidate,
  });

  const deleteLine = useMutation({
    mutationFn: api.deleteOrderLine,
    onSuccess: invalidate,
  });

  const generateEdifact = useMutation({
    mutationFn: () => api.generateEdifact(orderId),
    onSuccess: (result) => {
      if (result.success) {
        setInfoDialog({
          title: "Succès",
          message: `EDIFACT généré : ${result.fileName}`,
        });
        invalidate();
      } else {
        const detail = result.errors?.length
          ? result.errors.join("\n")
          : result.message ?? "Génération échouée";
        setInfoDialog({
          title: "Erreur",
          message: `Impossible de générer l'EDIFACT :\n\n${detail}`,
        });
      }
    },
  });

  const downloadEdifact = useMutation({
    mutationFn: async () => {
      const result = await api.generateEdifact(orderId);
      if (!result.success) {
        const detail = result.errors?.length
          ? result.errors.join("\n")
          : result.message ?? "Génération échouée";
        throw new Error(detail);
      }
      if (!result.content || !result.fileName) {
        throw new Error("Contenu EDIFACT indisponible après génération");
      }
      return result;
    },
    onSuccess: (result) => {
      downloadTextFile(result.content!, result.fileName!);
      invalidate();
    },
    onError: (err) => {
      setInfoDialog({
        title: "Erreur",
        message: `Impossible de télécharger l'EDIFACT :\n\n${err instanceof Error ? err.message : "Erreur inconnue"}`,
      });
    },
  });

  const sendToSap = useMutation({
    mutationFn: (payload?: { force?: boolean }) => api.sendToSap(orderId, payload),
  });

  if (isLoading) {
    return <p className="text-muted-foreground">Chargement de la revue…</p>;
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <p className="text-destructive">
          Commande introuvable ({orderId}).
          {error instanceof Error ? ` ${error.message}` : ""}
        </p>
        <Button onClick={() => refetch()}>Réessayer</Button>
      </div>
    );
  }

  const { order, partners, lines, anomalies, traceability } = data;
  const soldto = partners.find((p) => p.partnerFunction === "soldto");
  const shipto = partners.find((p) => p.partnerFunction === "shipto");
  const invalidDate = !order.orderDate;
  const pendingAnomalyCount = countPendingAnomalies(anomalies);

  const handleValidate = () => {
    const errors = collectReviewBlockers(order, partners, lines, anomalies);
    if (errors.length) {
      setInfoDialog({
        title: "Erreur",
        message: "Impossible de générer l'EDIFACT :\n\n" + errors.join("\n"),
      });
      return;
    }
    generateEdifact.mutate();
  };

  const handleDownloadEdifact = () => {
    const errors = collectReviewBlockers(order, partners, lines, anomalies);
    if (errors.length) {
      setInfoDialog({
        title: "Erreur",
        message: "Impossible de télécharger l'EDIFACT :\n\n" + errors.join("\n"),
      });
      return;
    }
    downloadEdifact.mutate();
  };

  const handleSendToSap = async () => {
    try {
      const first = await sendToSap.mutateAsync({});
      if (first.success) {
        setInfoDialog({
          title: "Succès",
          message: first.message || "Commande envoyée vers SAP",
        });
        return;
      }

      if (first.requiresConfirmation || first.alreadySent) {
        setConfirmResendOpen(true);
        return;
      }

      setInfoDialog({
        title: "Erreur",
        message: `Impossible d'envoyer vers SAP :\n\n${first.message || "Erreur inconnue"}`,
      });
    } catch (err) {
      setInfoDialog({
        title: "Erreur",
        message: `Impossible d'envoyer vers SAP :\n\n${err instanceof Error ? err.message : "Erreur inconnue"}`,
      });
    }
  };

  const handleForceResendToSap = async () => {
    try {
      const forced = await sendToSap.mutateAsync({ force: true });
      if (forced.success) {
        setInfoDialog({
          title: "Succès",
          message: forced.message || "Commande renvoyée vers SAP",
        });
        return;
      }
      setInfoDialog({
        title: "Erreur",
        message: `Impossible d'envoyer vers SAP :\n\n${forced.message || "Erreur inconnue"}`,
      });
    } catch (err) {
      setInfoDialog({
        title: "Erreur",
        message: `Impossible d'envoyer vers SAP :\n\n${err instanceof Error ? err.message : "Erreur inconnue"}`,
      });
    }
  };

  const edifactBusy = generateEdifact.isPending || downloadEdifact.isPending || sendToSap.isPending;
  const canValidate = pendingAnomalyCount === 0;
  const isValidated = data.edifactReady || order.status === "Généré";
  const isAdv = meQuery.data?.role === "adv";

  return (
    <>
      <Header
        title="Revue de commande"
        breadcrumbs={[
          { label: "Cockpit", href: "/" },
          { label: "Revue", href: "/revue" },
          { label: order.fileName },
        ]}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => window.open(data.pdfUrl, "_blank", "noopener,noreferrer")}
            >
              <Download className="h-4 w-4" /> PDF
            </Button>
            {!isAdv && (
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={handleDownloadEdifact}
                disabled={edifactBusy}
              >
                <Download className="h-4 w-4" /> EDIFACT
              </Button>
            )}
            <Button size="sm" className="gap-2" onClick={handleValidate} disabled={edifactBusy || !canValidate}>
              <CheckCircle className="h-4 w-4" /> Valider
            </Button>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <StatusBadge status={order.status} />
        {invalidDate && <Badge variant="destructive">Date invalide</Badge>}
        <Badge variant="outline">PDF reçu</Badge>
        {data.edifactReady && <Badge variant="success">EDIFACT prêt</Badge>}
        <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
          Confiance globale {order.globalConfidence}%
        </Badge>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
        <StatCard compact label="Client" value={order.clientName} />
        <StatCard compact label="N° commande client" value={order.customerOrderNumber} />
        <StatCard
          compact
          label="Date commande"
          value={formatDate(order.orderDate)}
          valueClassName={invalidDate ? "text-red-600" : undefined}
        />
        <StatCard compact label="Livraison demandée" value={formatDate(order.requestedDeliveryDate)} />
        <StatCard compact label="Nb lignes" value={order.lineCount} />
        <StatCard compact label="Montant estimé" value={formatCurrency(order.totalAmount, order.currency)} />
        <StatCard compact label="Statut traitement" value={order.status} valueClassName="text-violet-600" />
      </div>

      <OrderGeneralInfoPanel
        order={order}
        soldto={soldto}
        shipto={shipto}
        onUpdateHeader={async (payload) => {
          await updateHeader.mutateAsync(payload);
        }}
        onUpdateShipto={async (payload, options) => {
          if (!shipto) throw new Error("Partenaire ship-to introuvable pour cette commande");
          await api.updateOrderPartner(shipto.partnerId, {
            ...payload,
            ...options,
          });
          invalidate();
        }}
      />

      <div className="mb-6 grid items-stretch gap-6 lg:grid-cols-[13fr_7fr]">
        <PdfPreviewPanel fileName={order.fileName} orderId={order.orderId} pdfUrl={data.pdfUrl} />

        <Card className="flex h-full flex-col">
          <CardHeader>
            <CardTitle className="text-base">Lignes de commande</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col pt-0">
            <OrderLinesEditPanel
              lines={lines}
              onUpdateLine={async (lineId, payload) => {
                await updateLine.mutateAsync({ lineId, payload });
              }}
              onDeleteLine={async (lineId) => {
                await deleteLine.mutateAsync(lineId);
              }}
              onAddLine={() => {
                api.addOrderLine(orderId, {
                  boschArticle: "",
                  quantity: 1,
                  unit: "PCE",
                  unitPrice: 0,
                }).then(invalidate);
              }}
            />
          </CardContent>
        </Card>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Lignes de commande</CardTitle>
        </CardHeader>
        <CardContent>
          <OrderLinesSummaryTable lines={lines} currency={order.currency} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Anomalies et commentaires</CardTitle>
            {pendingAnomalyCount > 0 && (
              <p className="text-sm text-amber-700">
                {pendingAnomalyCount} anomalie{pendingAnomalyCount > 1 ? "s" : ""} à traiter — choisissez
                Valider ou Ignorer pour chacune avant de valider la commande.
              </p>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {anomalies.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucune anomalie signalée.</p>
            ) : (
              anomalies.map((a) => {
                const pending = isAnomalyPending(a);
                const isValidated = a.status === "Corrigée";
                const isIgnored = a.status === "Ignorée";
                return (
              <div key={a.anomalyId} className="flex items-start justify-between gap-4 rounded-lg border p-3">
                <div>
                  <p className="text-sm">{a.message}</p>
                  <Badge variant={pending ? "warning" : "success"} className="mt-1">
                    {a.status}
                  </Badge>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    variant={isValidated ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => api.resolveAnomaly(a.anomalyId, "corrected").then(invalidate)}
                  >
                    Valider
                  </Button>
                  <Button
                    variant={isIgnored ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => api.resolveAnomaly(a.anomalyId, "ignored").then(invalidate)}
                  >
                    Ignorer
                  </Button>
                </div>
              </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Traçabilité</CardTitle>
          </CardHeader>
          <CardContent>
            <ProgressStepper steps={traceability} />
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-end gap-3 border-t pt-6">
        {!isAdv && (
          <Button
            variant="outline"
            className="gap-2"
            onClick={handleDownloadEdifact}
            disabled={edifactBusy}
          >
            <Download className="h-4 w-4" /> Télécharger EDIFACT
          </Button>
        )}
        <Button className="gap-2" onClick={handleValidate} disabled={edifactBusy || !canValidate}>
          <CheckCircle className="h-4 w-4" /> Valider
        </Button>
        <Button
          variant="outline"
          className="gap-2"
          onClick={() => setConfirmSendOpen(true)}
          disabled={edifactBusy || !isValidated}
        >
          <Send className="h-4 w-4" /> Envoyer vers SAP
        </Button>
      </div>

      {confirmSendOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="text-base">Confirmation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm">Confirmer l&apos;envoi de ce fichier vers SAP ?</p>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setConfirmSendOpen(false)}>
                  Annuler
                </Button>
                <Button
                  onClick={async () => {
                    setConfirmSendOpen(false);
                    await handleSendToSap();
                  }}
                >
                  Confirmer
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {confirmResendOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="text-base">Commande déjà envoyée</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm">
                Cette commande avait déjà été envoyée vers SAP. Voulez-vous vraiment la renvoyer ?
              </p>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setConfirmResendOpen(false)}>
                  Annuler
                </Button>
                <Button
                  onClick={async () => {
                    setConfirmResendOpen(false);
                    await handleForceResendToSap();
                  }}
                >
                  Renvoyer
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {infoDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="text-base">{infoDialog.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="whitespace-pre-line text-sm">{infoDialog.message}</p>
              <div className="flex justify-end">
                <Button onClick={() => setInfoDialog(null)}>Fermer</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
