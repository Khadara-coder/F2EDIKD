import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { MasterDataCustomerRow, MasterDataPartnerRow, PartnerEditSource } from "@/types";

interface ShiptoNameSelectFieldProps {
  label: string;
  value: string;
  soldtoCode: string;
  currentShiptoCode?: string;
  soldtoVat?: string;
  manuallyEdited?: boolean;
  editFlag?: PartnerEditSource;
  className?: string;
  onSelect: (partner: MasterDataPartnerRow) => Promise<void> | void;
}

function normalizeVat(vat: string): string {
  return vat.replace(/\s+/g, "").toUpperCase();
}

function normalizeCode(code: string | undefined): string {
  return String(code ?? "").trim();
}

function findCustomer(rows: MasterDataCustomerRow[], code: string) {
  const normalized = code.trim();
  return rows.find((r) => String(r.SOLDTO ?? "").trim() === normalized);
}

async function resolveSoldtoCodes(soldtoCode: string, soldtoVat?: string): Promise<string[]> {
  const codes = new Set<string>();
  const trimmed = soldtoCode.trim();
  if (trimmed) codes.add(trimmed);

  const vat = normalizeVat(soldtoVat ?? "");
  if (vat) {
    const res = await api.searchCustomers(vat, 200);
    for (const row of res.results) {
      if (normalizeVat(String(row.VAT_NR ?? "")) === vat) {
        const code = String(row.SOLDTO ?? "").trim();
        if (code) codes.add(code);
      }
    }
  }

  return [...codes];
}

async function fetchPartnersForSoldtos(soldtoCodes: string[]): Promise<MasterDataPartnerRow[]> {
  if (!soldtoCodes.length) return [];

  const byShipto = new Map<string, MasterDataPartnerRow>();
  for (const soldto of soldtoCodes) {
    const res = await api.searchPartners(soldto, 200);
    for (const row of res.results) {
      if (String(row.SOLDTO ?? "").trim() !== soldto) continue;
      const shipto = String(row.SHIPTO ?? "").trim();
      if (!shipto) continue;
      byShipto.set(shipto, row);
    }
  }
  return [...byShipto.values()].sort((a, b) =>
    String(a.ORT01 ?? "").localeCompare(String(b.ORT01 ?? ""), "fr", { sensitivity: "base" }),
  );
}

function partnerLabel(row: MasterDataPartnerRow): string {
  return String(row.NAME ?? "").trim() || String(row.SHIPTO ?? "").trim();
}

function partnerMatchesFilter(row: MasterDataPartnerRow, filter: string): boolean {
  const q = filter.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    row.NAME,
    row.SHIPTO,
    row.ORT01,
    row.PSTLZ,
    row.STRAS,
    row.LAND1,
  ]
    .map((v) => String(v ?? "").toLowerCase())
    .join(" ");
  return haystack.includes(q);
}

export function ShiptoNameSelectField({
  label,
  value,
  soldtoCode,
  currentShiptoCode,
  soldtoVat,
  manuallyEdited,
  editFlag,
  className,
  onSelect,
}: ShiptoNameSelectFieldProps) {
  const [editing, setEditing] = useState(false);
  const [filter, setFilter] = useState("");
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<MasterDataPartnerRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: soldtoMd } = useQuery({
    queryKey: ["md-customer", soldtoCode],
    queryFn: () => api.searchCustomers(soldtoCode),
    enabled: !!soldtoCode.trim(),
    select: (res) => findCustomer(res.results, soldtoCode),
    staleTime: 60_000,
  });

  const vat = soldtoVat ?? soldtoMd?.VAT_NR ?? "";

  const { data: options = [], isLoading } = useQuery({
    queryKey: ["md-partners-by-soldto", soldtoCode, vat],
    queryFn: async () => {
      const soldtoCodes = await resolveSoldtoCodes(soldtoCode, vat);
      return fetchPartnersForSoldtos(soldtoCodes);
    },
    enabled: editing && (!!soldtoCode.trim() || !!normalizeVat(vat)),
    staleTime: 60_000,
  });

  const filteredOptions = useMemo(
    () =>
      options
        .filter((row) => partnerMatchesFilter(row, filter))
        .sort((a, b) =>
          String(a.ORT01 ?? "").localeCompare(String(b.ORT01 ?? ""), "fr", { sensitivity: "base" }),
        ),
    [options, filter],
  );

  useEffect(() => {
    if (!editing) {
      setFilter("");
      setSelected(null);
      setError(null);
    }
  }, [editing]);

  useEffect(() => {
    if (!editing || !options.length) return;
    const current = normalizeCode(currentShiptoCode);
    if (!current) return;
    const match = options.find((row) => normalizeCode(row.SHIPTO) === current);
    if (match) setSelected(match);
  }, [editing, options, currentShiptoCode]);

  useEffect(() => {
    if (!editing) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEditing(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editing]);

  const handleOpen = () => {
    setFilter("");
    setSelected(null);
    setError(null);
    setEditing(true);
  };

  const applySelection = async (row: MasterDataPartnerRow) => {
    setSelected(row);
    setSaving(true);
    setError(null);
    try {
      await onSelect(row);
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de l'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  const flag = editFlag ?? (manuallyEdited ? "manual" : undefined);

  return (
    <div className={cn("group space-y-1", className)}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {flag === "manual" && (
          <Badge variant="info" className="px-1.5 py-0 text-[10px]">
            Modifié manuellement
          </Badge>
        )}
        {flag === "auto" && (
          <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
            Modifié automatiquement
          </Badge>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filtrer par nom, ville, code ship-to…"
            className="h-8 text-sm"
            autoFocus
            disabled={saving}
          />
          <div className="max-h-52 overflow-y-auto rounded-md border bg-background shadow-sm">
            {isLoading ? (
              <p className="p-3 text-sm text-muted-foreground">Chargement des ship-to…</p>
            ) : filteredOptions.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                {options.length === 0
                  ? "Aucun ship-to trouvé pour ce sold-to."
                  : "Aucun résultat pour ce filtre."}
              </p>
            ) : (
              <ul className="divide-y">
                {filteredOptions.map((row) => {
                  const code = normalizeCode(row.SHIPTO);
                  const isSelected = normalizeCode(selected?.SHIPTO) === code;
                  return (
                    <li key={code}>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => applySelection(row)}
                        className={cn(
                          "w-full px-3 py-2 text-left transition-colors hover:bg-muted/60 disabled:opacity-50",
                          isSelected && "bg-violet-50",
                        )}
                      >
                        <p className="text-sm font-medium">{partnerLabel(row)}</p>
                        <p className="text-xs text-muted-foreground">
                          {code}
                          {row.ORT01 ? ` · ${row.ORT01}` : ""}
                          {row.PSTLZ ? ` (${row.PSTLZ})` : ""}
                        </p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <p className="text-xs text-muted-foreground">Cliquez sur une ligne pour appliquer · Échap pour fermer</p>
        </div>
      ) : (
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate text-sm font-medium">{value || "—"}</span>
          <button
            type="button"
            onClick={handleOpen}
            className="shrink-0 rounded p-1 opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100"
          >
            <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      )}
    </div>
  );
}
