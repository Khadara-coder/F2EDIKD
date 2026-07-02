import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EditableField } from "@/components/file2edi/EditableField";
import { ShiptoNameSelectField } from "@/components/file2edi/ShiptoNameSelectField";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MasterDataCustomerRow, MasterDataPartnerRow, Order, OrderPartner, PartnerEditSource, PartnerFieldKey, UpdateOrderHeaderPayload } from "@/types";

interface OrderGeneralInfoPanelProps {
  order: Order;
  soldto?: OrderPartner;
  shipto?: OrderPartner;
  onUpdateHeader: (payload: UpdateOrderHeaderPayload) => Promise<void> | void;
  onUpdateShipto: (
    payload: Partial<Record<PartnerFieldKey, string>>,
    options?: {
      editSource?: PartnerEditSource;
      editSources?: Partial<Record<PartnerFieldKey, PartnerEditSource>>;
    },
  ) => Promise<void> | void;
}

function findCustomer(rows: MasterDataCustomerRow[], code: string) {
  const normalized = code.trim();
  return rows.find((r) => String(r.SOLDTO ?? "").trim() === normalized);
}

function findPartner(rows: MasterDataPartnerRow[], code: string) {
  const normalized = code.trim();
  return rows.find((r) => String(r.SHIPTO ?? "").trim() === normalized);
}

function toDateInput(value: string | null | undefined): string {
  if (!value) return "";
  const d = value.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : "";
}

function cleanDisplay(value: string | null | undefined): string {
  if (!value) return "";
  const cleaned = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && line !== "0")
    .join(" ");
  return cleaned === "0" ? "" : cleaned;
}

function shiptoFieldFlag(
  shipto: OrderPartner | undefined,
  field: PartnerFieldKey,
): PartnerEditSource | undefined {
  return shipto?.editedFields?.[field];
}

const ADDRESS_FIELDS: PartnerFieldKey[] = [
  "addressLine1",
  "postalCode",
  "city",
  "country",
];

function autoSources(fields: PartnerFieldKey[]): Partial<Record<PartnerFieldKey, PartnerEditSource>> {
  return Object.fromEntries(fields.map((field) => [field, "auto" as const]));
}

export function OrderGeneralInfoPanel({
  order,
  soldto,
  shipto,
  onUpdateHeader,
  onUpdateShipto,
}: OrderGeneralInfoPanelProps) {
  const soldtoCode = soldto?.partnerCode ?? "";
  const shiptoCode = shipto?.partnerCode ?? "";

  const { data: soldtoMd } = useQuery({
    queryKey: ["md-customer", soldtoCode],
    queryFn: () => api.searchCustomers(soldtoCode),
    enabled: !!soldtoCode,
    select: (res) => findCustomer(res.results, soldtoCode),
    staleTime: 60_000,
  });

  const { data: shiptoMd } = useQuery({
    queryKey: ["md-partner", shiptoCode],
    queryFn: () => api.searchPartners(shiptoCode),
    enabled: !!shiptoCode,
    select: (res) => findPartner(res.results, shiptoCode),
    staleTime: 60_000,
  });

  const soldtoSapId = cleanDisplay(soldtoMd?.SOLDTO ?? soldtoCode);
  const soldtoName = cleanDisplay(soldtoMd?.NAME ?? soldto?.partnerName ?? "—");
  const clientName = cleanDisplay(
    shipto?.partnerName || shiptoMd?.NAME || order.clientName || "—",
  );

  const handleShiptoSelect = async (md: MasterDataPartnerRow) => {
    const payload = {
      partnerCode: cleanDisplay(md.SHIPTO),
      partnerName: cleanDisplay(md.NAME),
      addressLine1: cleanDisplay(md.STRAS),
      postalCode: cleanDisplay(md.PSTLZ),
      city: cleanDisplay(md.ORT01),
      country: cleanDisplay(md.LAND1),
    };
    await onUpdateShipto(payload, {
      editSources: {
        partnerName: "manual",
        partnerCode: "auto",
        ...autoSources(ADDRESS_FIELDS),
      },
    });
  };

  const handleShiptoCodeSave = async (code: string) => {
    const res = await api.searchPartners(code);
    const md = findPartner(res.results, code);
    const payload = {
      partnerCode: cleanDisplay(md?.SHIPTO ?? code),
      partnerName: cleanDisplay(md?.NAME ?? shipto?.partnerName),
      addressLine1: cleanDisplay(md?.STRAS ?? shipto?.addressLine1),
      postalCode: cleanDisplay(md?.PSTLZ ?? shipto?.postalCode),
      city: cleanDisplay(md?.ORT01 ?? shipto?.city),
      country: cleanDisplay(md?.LAND1 ?? shipto?.country),
    };
    await onUpdateShipto(payload, {
      editSources: {
        partnerCode: "manual",
        partnerName: "auto",
        ...autoSources(ADDRESS_FIELDS),
      },
    });
  };

  return (
    <Card className="mb-6">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">Informations générales</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <section>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Sold-to / AG
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <EditableField label="Compte SAP sold-to" value={soldtoSapId} readOnly />
            <EditableField label="Nom client sold-to" value={soldtoName} readOnly />
          </div>
        </section>

        <section className="border-t pt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
            <EditableField
              label="N° commande client"
              value={cleanDisplay(order.customerOrderNumber)}
              manuallyEdited={order.manuallyEditedFields?.includes("customerOrderNumber")}
              onSave={(v) =>
                onUpdateHeader({ customerOrderNumber: cleanDisplay(v) })
              }
            />
            <EditableField
              label="Compte client ship-to SAP"
              value={cleanDisplay(shiptoCode)}
              editFlag={shiptoFieldFlag(shipto, "partnerCode")}
              onSave={handleShiptoCodeSave}
            />
            <ShiptoNameSelectField
              label="Nom du client"
              value={clientName}
              soldtoCode={soldtoCode || soldtoSapId}
              currentShiptoCode={shiptoCode}
              soldtoVat={soldtoMd?.VAT_NR}
              editFlag={shiptoFieldFlag(shipto, "partnerName")}
              className="sm:col-span-2 lg:col-span-2"
              onSelect={handleShiptoSelect}
            />
            <EditableField
              label="Date de la commande"
              type="date"
              value={toDateInput(order.orderDate)}
              manuallyEdited={order.manuallyEditedFields?.includes("orderDate")}
              onSave={(v) => onUpdateHeader({ orderDate: v || null })}
            />
            <EditableField
              label="Date de livraison"
              type="date"
              value={toDateInput(order.requestedDeliveryDate)}
              manuallyEdited={order.manuallyEditedFields?.includes("requestedDeliveryDate")}
              onSave={(v) => onUpdateHeader({ requestedDeliveryDate: v || null })}
            />
          </div>
        </section>

        <section className="border-t pt-6">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Adresse de livraison
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <EditableField
              label="Rue"
              value={cleanDisplay(shipto?.addressLine1)}
              className="sm:col-span-2"
              editFlag={shiptoFieldFlag(shipto, "addressLine1")}
              onSave={(v) =>
                onUpdateShipto({ addressLine1: cleanDisplay(v) }, { editSource: "manual" })
              }
            />
            <EditableField
              label="Code postal"
              value={cleanDisplay(shipto?.postalCode)}
              editFlag={shiptoFieldFlag(shipto, "postalCode")}
              onSave={(v) =>
                onUpdateShipto({ postalCode: cleanDisplay(v) }, { editSource: "manual" })
              }
            />
            <EditableField
              label="Ville"
              value={cleanDisplay(shipto?.city)}
              editFlag={shiptoFieldFlag(shipto, "city")}
              onSave={(v) => onUpdateShipto({ city: cleanDisplay(v) }, { editSource: "manual" })}
            />
            <EditableField
              label="Pays"
              value={cleanDisplay(shipto?.country)}
              editFlag={shiptoFieldFlag(shipto, "country")}
              onSave={(v) =>
                onUpdateShipto({ country: cleanDisplay(v) }, { editSource: "manual" })
              }
            />
          </div>
        </section>
      </CardContent>
    </Card>
  );
}
