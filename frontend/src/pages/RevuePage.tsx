import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { Download, CheckCircle, Send, PauseCircle, UserCheck, XCircle } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { formatCurrency, formatDate, formatDateTime, downloadTextFile } from "@/lib/utils";
import { collectReviewBlockers, countPendingAnomalies, isAnomalyPending } from "@/lib/reviewValidation";
import type { GestionnaireUser } from "@/types";

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
  const [holdOpen, setHoldOpen] = useState(false);
  const [holdReason, setHoldReason] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferTo, setTransferTo] = useState("");
  const [transferNote, setTransferNote] = useState("");

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

  // Users list for transfer
  const usersQuery = useQuery<GestionnaireUser[]>({
    queryKey: ["users"],
    queryFn: () => fetch("/api/users").then(r => r.json()),
    staleTime: 60_000,
  });

  const holdMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/orders/${orderId}/hold`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: holdReason }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Échec mise en attente");
      return res.json();
    },
    onSuccess: () => { setHoldOpen(false); setHoldReason(""); invalidate(); },
    onError: (e) => setInfoDialog({ title: "Erreur", message: e instanceof Error ? e.message : "Erreur" }),
  });

  const rejectMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/orders/${orderId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Échec du rejet");
      return res.json();
    },
    onSuccess: () => { setRejectOpen(false); setRejectReason(""); invalidate(); },
    onError: (e) => setInfoDialog({ title: "Erreur", message: e instanceof Error ? e.message : "Erreur" }),
  });

  const transferMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/orders/${orderId}/transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to: transferTo, note: transferNote }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Échec transfert");
      return res.json();
    },
    onSuccess: () => { setTransferOpen(false); setTransferTo(""); setTransferNote(""); invalidate(); },
    onError: (e) => setInfoDialog({ title: "Erreur", message: e instanceof Error ? e.message : "Erreur" }),
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
      const result = await sendToSap.mutateAsync({});
      if (result.success) {
        setInfoDialog({
          title: "Succès",
          message: result.message || "Commande envoyée vers SAP",
        });
        invalidate();
        return;
      }

      if (result.requiresConfirmation || result.alreadySent) {
        if (isAdmin) {
          setConfirmResendOpen(true);
          return;
        }
      }

      setInfoDialog({
        title: "Erreur",
        message: `Impossible d'envoyer vers SAP :\n\n${result.message || "Erreur inconnue"}`,
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
        invalidate();
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

  const handleSendClick = () => {
    if (isSentToSap && isAdmin) {
      setConfirmResendOpen(true);
      return;
    }
    setConfirmSendOpen(true);
  };

  const edifactBusy = generateEdifact.isPending || downloadEdifact.isPending || sendToSap.isPending;
  const canValidate = pendingAnomalyCount === 0;
  const isValidated = data.edifactReady || order.status === "Généré";
  const isAdv = meQuery.data?.role === "adv";
  const isAdmin = meQuery.data?.role === "admin";
  const isRejected = order.status === "Rejeté";
  const isOnHold = order.status === "En attente";
  const isSentToSap = order.status === "Envoyé SAP" || Boolean(order.sapSentAt);
  const workflowLocked = isRejected || isSentToSap;
  const canSendToSap = !isRejected && !edifactBusy && (
    (!isSentToSap && isValidated) || (isSentToSap && isAdmin)
  );

  return (
    <>
      <Header
        title="Détail de la commande"
        breadcrumbs={[
          { label: "Cockpit", href: "/" },
          { label: "Gérer les commandes", href: "/revue" },
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
            {/* Mettre en attente */}
            <Button
              variant="outline"
              size="sm"
              className="gap-2 border-orange-300 text-orange-700 hover:bg-orange-50"
              onClick={() => setHoldOpen(true)}
              disabled={isOnHold || workflowLocked}
            >
              <PauseCircle className="h-4 w-4" /> En attente
            </Button>
            {/* Rejeter */}
            <Button
              variant="outline"
              size="sm"
              className="gap-2 border-rose-300 text-rose-700 hover:bg-rose-50"
              onClick={() => setRejectOpen(true)}
              disabled={workflowLocked}
            >
              <XCircle className="h-4 w-4" /> Rejeter
            </Button>
            {/* Transférer */}
            <Button
              variant="outline"
              size="sm"
              className="gap-2 border-sky-300 text-sky-700 hover:bg-sky-50"
              onClick={() => setTransferOpen(true)}
              disabled={workflowLocked}
            >
              <UserCheck className="h-4 w-4" /> Transférer
            </Button>
            <Button size="sm" className="gap-2" onClick={handleValidate} disabled={edifactBusy || !canValidate || workflowLocked}>
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
        {isRejected && order.rejectionMessage && (
          <Badge variant="destructive" className="max-w-xl truncate" title={order.rejectionMessage}>
            Motif : {order.rejectionMessage}
          </Badge>
        )}
        {isSentToSap && (
          <Badge variant="success" className="max-w-xl truncate">
            Envoyé vers SAP
            {order.sapSentAt ? ` le ${formatDateTime(order.sapSentAt)}` : ""}
            {order.sapSentBy ? ` par ${order.sapSentBy}` : ""}
          </Badge>
        )}
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
        onUpdateSoldto={async (payload, options) => {
          if (!soldto) throw new Error("Partenaire sold-to introuvable pour cette commande");
          await api.updateOrderPartner(soldto.partnerId, {
            ...payload,
            ...options,
          });
          invalidate();
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

      <div className={isAdv ? "space-y-6" : "grid gap-6 lg:grid-cols-2"}>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Anomalies et commentaires</CardTitle>
            {pendingAnomalyCount > 0 && (
              <p className="text-sm text-amber-700">
                {pendingAnomalyCount} anomalie{pendingAnomalyCount > 1 ? "s" : ""} à traiter — choisissez
                une action pour chacune avant de valider la commande.
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
                const acceptLabel = a.buttonAccept || "Valider";
                const rejectLabel = a.buttonReject || "Ignorer";
                return (
              <div key={a.anomalyId} className="flex items-start justify-between gap-4 rounded-lg border p-3">
                <div className="min-w-0">
                  <p className="text-sm">{a.message}</p>
                  <Badge variant={pending ? "warning" : "success"} className="mt-1">
                    {a.status}
                  </Badge>
                </div>
                <div className="flex shrink-0 flex-col gap-1 sm:max-w-[240px]">
                  <Button
                    variant={isValidated ? "secondary" : "ghost"}
                    size="sm"
                    className="h-auto whitespace-normal px-2 py-1.5 text-left text-xs leading-snug"
                    onClick={() => api.resolveAnomaly(a.anomalyId, "corrected").then(invalidate)}
                  >
                    {acceptLabel}
                  </Button>
                  <Button
                    variant={isIgnored ? "secondary" : "ghost"}
                    size="sm"
                    className="h-auto whitespace-normal px-2 py-1.5 text-left text-xs leading-snug"
                    onClick={() => api.resolveAnomaly(a.anomalyId, "ignored").then(invalidate)}
                  >
                    {rejectLabel}
                  </Button>
                </div>
              </div>
                );
              })
            )}
          </CardContent>
        </Card>

        {!isAdv && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Traçabilité</CardTitle>
            </CardHeader>
            <CardContent>
              <ProgressStepper steps={traceability} />
            </CardContent>
          </Card>
        )}
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-6">
        {/* Actions secondaires (gauche) */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="gap-2 border-orange-300 text-orange-700 hover:bg-orange-50"
            onClick={() => setHoldOpen(true)}
            disabled={isOnHold || workflowLocked}
          >
            <PauseCircle className="h-4 w-4" /> En attente
          </Button>
          <Button
            variant="outline"
            className="gap-2 border-rose-300 text-rose-700 hover:bg-rose-50"
            onClick={() => setRejectOpen(true)}
            disabled={workflowLocked}
          >
            <XCircle className="h-4 w-4" /> Rejeter
          </Button>
          <Button
            variant="outline"
            className="gap-2 border-sky-300 text-sky-700 hover:bg-sky-50"
            onClick={() => setTransferOpen(true)}
            disabled={workflowLocked}
          >
            <UserCheck className="h-4 w-4" /> Transférer
          </Button>
        </div>
        {/* Actions principales (droite) */}
        <div className="flex flex-wrap gap-2">
          {!isAdv && (
            <Button
              variant="outline"
              className="gap-2"
              onClick={handleDownloadEdifact}
              disabled={edifactBusy || workflowLocked}
            >
              <Download className="h-4 w-4" /> Télécharger EDIFACT
            </Button>
          )}
          <Button className="gap-2" onClick={handleValidate} disabled={edifactBusy || !canValidate || workflowLocked}>
            <CheckCircle className="h-4 w-4" /> Valider
          </Button>
          <Button
            variant="outline"
            className="gap-2"
            onClick={handleSendClick}
            disabled={!canSendToSap}
          >
            <Send className="h-4 w-4" /> {isSentToSap && isAdmin ? "Renvoyer vers SAP" : "Envoyer vers SAP"}
          </Button>
        </div>
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
                Cette commande a déjà été envoyée vers SAP. En tant qu&apos;administrateur, vous pouvez la renvoyer.
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

      {/* ── Modal : Mise en attente ───────────────────────────────────── */}
      <Dialog open={holdOpen} onOpenChange={setHoldOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PauseCircle className="h-5 w-5 text-orange-500" />
              Mettre en attente
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">
              Précisez le motif. Le dossier sera suspendu jusqu'à nouvel ordre.
            </p>
            <div className="space-y-1.5">
              <Label>Motif *</Label>
              <Textarea
                value={holdReason}
                onChange={(e) => setHoldReason(e.target.value)}
                placeholder="Ex: En attente de validation client, information manquante…"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHoldOpen(false)}>Annuler</Button>
            <Button
              className="gap-2 bg-orange-500 hover:bg-orange-600"
              onClick={() => holdMutation.mutate()}
              disabled={!holdReason.trim() || holdMutation.isPending}
            >
              <PauseCircle className="h-4 w-4" />
              {holdMutation.isPending ? "En cours…" : "Mettre en attente"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Modal : Rejet ─────────────────────────────────────────────── */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-rose-500" />
              Rejeter la commande
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">
              Indiquez le motif du rejet. La commande passera au statut Rejeté.
            </p>
            <div className="space-y-1.5">
              <Label>Motif *</Label>
              <Textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Ex: Document illisible, client inconnu, commande annulée par le client…"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>Annuler</Button>
            <Button
              variant="destructive"
              className="gap-2"
              onClick={() => rejectMutation.mutate()}
              disabled={!rejectReason.trim() || rejectMutation.isPending}
            >
              <XCircle className="h-4 w-4" />
              {rejectMutation.isPending ? "En cours…" : "Rejeter"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Modal : Transfert ─────────────────────────────────────────── */}
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserCheck className="h-5 w-5 text-sky-500" />
              Transférer le dossier
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">
              Le dossier sera assigné au gestionnaire sélectionné. Il apparaîtra dans sa liste "À traiter".
            </p>
            <div className="space-y-1.5">
              <Label>Gestionnaire destinataire *</Label>
              <Select value={transferTo} onValueChange={setTransferTo}>
                <SelectTrigger>
                  <SelectValue placeholder="Choisir un gestionnaire…" />
                </SelectTrigger>
                <SelectContent>
                  {(usersQuery.data || []).map((u: GestionnaireUser) => (
                    <SelectItem key={u.userId} value={u.username}>
                      {u.displayName} ({u.username})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Note (optionnel)</Label>
              <Textarea
                value={transferNote}
                onChange={(e) => setTransferNote(e.target.value)}
                placeholder="Instructions ou contexte pour le destinataire…"
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTransferOpen(false)}>Annuler</Button>
            <Button
              className="gap-2 bg-sky-500 hover:bg-sky-600"
              onClick={() => transferMutation.mutate()}
              disabled={!transferTo.trim() || transferMutation.isPending}
            >
              <UserCheck className="h-4 w-4" />
              {transferMutation.isPending ? "En cours…" : "Transférer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  );
}
