import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Download, Pencil, XCircle, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useOrderReview } from "@/hooks/useFile2Edi";
import { MOCK_ORDER_ID } from "@/lib/mockData";
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
import { formatCurrency, formatDate } from "@/lib/utils";

export function RevuePage() {
  const { orderId = MOCK_ORDER_ID } = useParams();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useOrderReview(orderId);

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
        alert(`EDIFACT généré : ${result.fileName}`);
        invalidate();
      } else {
        alert(result.errors?.join("\n") ?? result.message);
      }
    },
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

  const handleValidate = () => {
    const errors: string[] = [];
    const blocking = anomalies.filter((a) => a.status === "Bloquante" || a.status === "Ouverte" && a.severity === "blocking");
    if (blocking.length) errors.push("Anomalies bloquantes ouvertes");
    if (!soldto) errors.push("Sold-to manquant");
    if (!shipto) errors.push("Ship-to manquant");
    if (invalidDate) errors.push("Date commande invalide");
    const badLines = lines.filter((l) => !l.boschArticle || !l.quantity || !l.unit);
    if (badLines.length) errors.push(`${badLines.length} ligne(s) incomplète(s)`);
    if (errors.length) {
      alert("Validation impossible :\n" + errors.join("\n"));
      return;
    }
    generateEdifact.mutate();
  };

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
            <Button variant="outline" size="sm" className="gap-2">
              <Download className="h-4 w-4" /> PDF
            </Button>
            <Button variant="outline" size="sm" className="gap-2">
              <Download className="h-4 w-4" /> EDIFACT
            </Button>
            <Button variant="outline" size="sm" className="gap-2">
              <Pencil className="h-4 w-4" /> Corriger
            </Button>
            <Button variant="outline" size="sm" className="gap-2 text-red-600 border-red-200">
              <XCircle className="h-4 w-4" /> Rejeter
            </Button>
            <Button size="sm" className="gap-2" onClick={handleValidate} disabled={generateEdifact.isPending}>
              <CheckCircle className="h-4 w-4" /> Valider et générer
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

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-8">
        <StatCard label="Client" value={order.clientName} />
        <StatCard label="N° commande client" value={order.customerOrderNumber} />
        <StatCard label="Référence document" value={order.documentReference} />
        <StatCard label="Date commande" value={formatDate(order.orderDate)} valueClassName={invalidDate ? "text-red-600" : undefined} />
        <StatCard label="Livraison demandée" value={formatDate(order.requestedDeliveryDate)} />
        <StatCard label="Nb lignes" value={order.lineCount} />
        <StatCard label="Montant estimé" value={formatCurrency(order.totalAmount, order.currency)} />
        <StatCard label="Statut traitement" value={order.status} valueClassName="text-violet-600 text-lg" />
      </div>

      <OrderGeneralInfoPanel
        order={order}
        soldto={soldto}
        shipto={shipto}
        onUpdateHeader={async (payload) => {
          await updateHeader.mutateAsync(payload);
        }}
        onUpdateShipto={async (payload) => {
          if (!shipto) return;
          await api.updateOrderPartner(shipto.partnerId, payload);
          invalidate();
        }}
      />

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <PdfPreviewPanel fileName={order.fileName} orderId={order.orderId} pdfUrl={data.pdfUrl} />

        <Card className="h-full">
          <CardHeader>
            <CardTitle className="text-base">Lignes de commande</CardTitle>
          </CardHeader>
          <CardContent>
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
          </CardHeader>
          <CardContent className="space-y-3">
            {anomalies.map((a) => (
              <div key={a.anomalyId} className="flex items-start justify-between gap-4 rounded-lg border p-3">
                <div>
                  <p className="text-sm">{a.message}</p>
                  <Badge variant={a.status === "Ouverte" ? "warning" : "success"} className="mt-1">
                    {a.status}
                  </Badge>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => api.resolveAnomaly(a.anomalyId, "corrected").then(invalidate)}>
                    Corrigée
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => api.resolveAnomaly(a.anomalyId, "ignored").then(invalidate)}>
                    Ignorer
                  </Button>
                </div>
              </div>
            ))}
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
    </>
  );
}
