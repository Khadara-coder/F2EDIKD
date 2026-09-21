import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FloatingLookupPanel } from "@/components/file2edi/FloatingLookupPanel";
import { LoadingState } from "@/components/ui/loading-state";
import { useFocusWithoutScroll } from "@/hooks/useFocusWithoutScroll";
import { cn } from "@/lib/utils";
import type { MasterDataCustomerRow, MasterDataPartnerRow, PartnerEditSource } from "@/types";

interface ShiptoCodeSelectFieldProps {
  label: string;
  value: string;
  soldtoCode: string;
  currentShiptoName?: string;
  soldtoVat?: string;
  fieldId?: string;
  invalid?: boolean;
  errorMessage?: string;
  manuallyEdited?: boolean;
  editFlag?: PartnerEditSource;
  className?: string;
  onSelect: (partner: MasterDataPartnerRow) => Promise<void> | void;
  onClear: () => Promise<void> | void;
}

function normalizeCode(code: string | undefined): string {
  return String(code ?? "").trim();
}

function findCustomer(rows: MasterDataCustomerRow[], code: string) {
  const normalized = code.trim();
  return rows.find((r) => String(r.SOLDTO ?? "").trim() === normalized);
}

function resolveSoldtoCodes(soldtoCode: string): string[] {
  const trimmed = soldtoCode.trim();
  return trimmed ? [trimmed] : [];
}

async function fetchPartnersForSoldtos(soldtoCodes: string[]): Promise<MasterDataPartnerRow[]> {
  if (!soldtoCodes.length) return [];

  const byShipto = new Map<string, MasterDataPartnerRow>();
  for (const soldto of soldtoCodes) {
    const res = await api.searchPartners(soldto, 200, "review");
    for (const row of res.results) {
      if (String(row.SOLDTO ?? "").trim() !== soldto) continue;
      if (String(row.PARVW ?? "").trim().toUpperCase() !== "SH") continue;
      const shipto = String(row.SHIPTO ?? "").trim();
      if (!shipto) continue;
      byShipto.set(shipto, row);
    }
  }
  return [...byShipto.values()].sort((a, b) =>
    String(a.SHIPTO ?? "").localeCompare(String(b.SHIPTO ?? ""), "fr", { sensitivity: "base" }),
  );
}

function partnerLabel(row: MasterDataPartnerRow): string {
  return String(row.NAME ?? "").trim() || String(row.SHIPTO ?? "").trim();
}

function partnerMatchesFilter(row: MasterDataPartnerRow, filter: string): boolean {
  const q = filter.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    row.SHIPTO,
    row.NAME,
    row.ORT01,
    row.PSTLZ,
    row.STRAS,
    row.LAND1,
  ]
    .map((v) => String(v ?? "").toLowerCase())
    .join(" ");
  return haystack.includes(q);
}

export function ShiptoCodeSelectField({
  label,
  value,
  soldtoCode,
  currentShiptoName,
  soldtoVat,
  fieldId,
  invalid,
  errorMessage,
  manuallyEdited,
  editFlag,
  className,
  onSelect,
  onClear,
}: ShiptoCodeSelectFieldProps) {
  const [editing, setEditing] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);
  const filterRef = useFocusWithoutScroll<HTMLInputElement>(editing);
  const [filter, setFilter] = useState("");
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<MasterDataPartnerRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: soldtoMd } = useQuery({
    queryKey: ["md-customer", soldtoCode],
    queryFn: () => api.searchCustomers(soldtoCode, 20, "review"),
    enabled: !!soldtoCode.trim(),
    select: (res) => findCustomer(res.results, soldtoCode),
    staleTime: 60_000,
  });

  const vat = soldtoVat ?? soldtoMd?.VAT_NR ?? "";

  const { data: options = [], isLoading } = useQuery({
    queryKey: ["md-partners-by-soldto-code", soldtoCode, vat, filter],
    queryFn: async () => {
      if (soldtoCode.trim()) {
        const soldtoCodes = resolveSoldtoCodes(soldtoCode);
        return fetchPartnersForSoldtos(soldtoCodes);
      }
      const q = filter.trim() || normalizeCode(value) || (currentShiptoName ?? "").trim();
      const res = await api.searchPartners(q, 200, "review");
      return res.results.filter((row) => String(row.PARVW ?? "").trim().toUpperCase() === "SH");
    },
    enabled: editing,
    staleTime: 60_000,
  });

  const filteredOptions = useMemo(
    () =>
      options
        .filter((row) => partnerMatchesFilter(row, filter))
        .sort((a, b) =>
          String(a.SHIPTO ?? "").localeCompare(String(b.SHIPTO ?? ""), "fr", { sensitivity: "base" }),
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
    const current = normalizeCode(value);
    if (!current) return;
    const match = options.find((row) => normalizeCode(row.SHIPTO) === current);
    if (match) setSelected(match);
  }, [editing, options, value]);

  useEffect(() => {
    if (!editing) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEditing(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editing]);

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

  const handleClear = async () => {
    setSaving(true);
    setError(null);
    try {
      await onClear();
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la suppression");
    } finally {
      setSaving(false);
    }
  };

  const flag = editFlag ?? (manuallyEdited ? "manual" : undefined);

  return (
    <div className={cn("group space-y-1", className)} id={fieldId}>
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

      <div
        ref={anchorRef}
        className={cn(
          "flex min-w-0 items-center gap-2 rounded px-1 -mx-1",
          invalid && "border border-red-500 bg-red-50/50",
        )}
      >
        <span className={cn("truncate font-mono text-sm font-semibold", !value && "text-muted-foreground font-normal")}>
          {value || "-"}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setEditing(true);
          }}
          className="shrink-0 rounded p-1 opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100"
          title="Modifier le compte client ship-to SAP"
        >
          <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>
      {invalid && errorMessage && (
        <p className="text-xs text-red-600 font-medium">{errorMessage}</p>
      )}

      <FloatingLookupPanel
        anchorRef={anchorRef}
        open={editing}
        onClose={() => setEditing(false)}
        minWidth={380}
      >
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Input
              ref={filterRef}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Rechercher par code ship-to, nom, ville…"
              className="h-8 text-sm flex-1"
              disabled={saving}
            />
            {value && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 text-xs text-rose-700 border-rose-300 hover:bg-rose-50 gap-1 px-2 shrink-0"
                onClick={handleClear}
                disabled={saving}
                title="Vider et réinitialiser le compte Ship-to et l'adresse"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Vider
              </Button>
            )}
          </div>

          <div className="max-h-52 overflow-y-auto rounded-md border bg-background">
            {isLoading ? (
              <LoadingState label="Chargement des ship-to…" className="py-3" />
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
                        <p className="text-sm font-mono font-bold text-violet-700">{code}</p>
                        <p className="text-sm font-medium">{partnerLabel(row)}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.STRAS ? `${row.STRAS} · ` : ""}
                          {row.ORT01 ? `${row.ORT01}` : ""}
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
          <p className="text-xs text-muted-foreground">Cliquez sur un lieu de livraison pour l'appliquer · Échap pour fermer</p>
        </div>
      </FloatingLookupPanel>
    </div>
  );
}
