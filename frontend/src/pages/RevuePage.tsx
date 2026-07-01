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
import { ValidationPanel } from "@/components/file2edi/ValidationPanel";
import { EditableField } from "@/components/file2edi/EditableField";
import { EditableOrderLinesTable } from "@/components/file2edi/EditableOrderLinesTable";
import { ProgressStepper } from "@/components/file2edi/ProgressStepper";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { OrderPartner } from "@/types";

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
  const billto = partners.find((p) => p.partnerFunction === "billto");
  const payer = partners.find((p) => p.partnerFunction === "payer");
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

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <PdfPreviewPanel fileName={order.fileName} orderId={order.orderId} pdfUrl={data.pdfUrl} />

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Informations générales</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              <EditableField label="Type de message" value={order.messageType} onSave={() => {}} />
              <EditableField label="Vendeur" value={order.vendor} onSave={async () => { updateHeader.mutate({}); }} />
              <EditableField label="Devise" value={order.currency} onSave={(v) => updateHeader.mutate({ currency: v })} />
              <EditableField label="Incoterm" value={order.incoterm} onSave={(v) => updateHeader.mutate({ incoterm: v })} />
              <EditableField label="Mode de livraison" value={order.deliveryMode} onSave={(v) => updateHeader.mutate({ deliveryMode: v })} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Partenaires</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <PartnerRow label="Sold-to / AG" partner={soldto} onSave={async (v) => { if (soldto) await api.updateOrderPartner(soldto.partnerId, { partnerCode: v }); }} />
              <PartnerRow label="Ship-to / WE" partner={shipto} onSave={async (v) => { if (shipto) await api.updateOrderPartner(shipto.partnerId, { partnerCode: v }); }} />
              <PartnerRow label="Bill-to / RE" partner={billto} onSave={async (v) => { if (billto) await api.updateOrderPartner(billto.partnerId, { partnerCode: v }); }} />
              <PartnerRow label="Payer / RG" partner={payer} onSave={async (v) => { if (payer) await api.updateOrderPartner(payer.partnerId, { partnerCode: v }); }} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Adresses</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Adresse de facturation</p>
                <p className="text-sm">{formatAddress(billto)}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Adresse de livraison</p>
                <p className="text-sm">{formatAddress(shipto)}</p>
              </div>
            </CardContent>
          </Card>

          <ValidationPanel
            items={[
              { label: "Date invalide", status: invalidDate ? "error" : "ok" },
              { label: "Ship-to identifié", status: shipto ? "ok" : "error", detail: shipto ? `confiance ${shipto.confidence}%` : undefined },
              { label: "Articles partiellement reconnus", status: "warning", detail: `${lines.filter((l) => l.status === "OK").length}/${lines.length}` },
              { label: "Quantités cohérentes", status: "ok" },
            ]}
          />
        </div>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Lignes de commande</CardTitle>
        </CardHeader>
        <CardContent>
          <EditableOrderLinesTable
            lines={lines}
            currency={order.currency}
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
            onValidateLine={async (lineId) => {
              await updateLine.mutateAsync({ lineId, payload: { status: "OK" } });
            }}
          />
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

function PartnerRow({
  label,
  partner,
  onSave,
}: {
  label: string;
  partner?: OrderPartner;
  onSave: (v: string) => Promise<void> | void;
}) {
  if (!partner) return null;
  return (
    <EditableField
      label={label}
      value={partner.partnerCode}
      onSave={async (v) => { await onSave(v); }}
      manuallyEdited={partner.manuallyEdited}
    />
  );
}

function formatAddress(p?: OrderPartner): string {
  if (!p) return "—";
  return [p.partnerName, p.addressLine1, `${p.postalCode} ${p.city}`, p.country]
    .filter(Boolean)
    .join(", ");
}
