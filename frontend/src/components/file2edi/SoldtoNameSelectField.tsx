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
import type { MasterDataCustomerRow, PartnerEditSource } from "@/types";

interface SoldtoNameSelectFieldProps {
  label: string;
  value: string;
  currentSoldtoCode?: string;
  manuallyEdited?: boolean;
  editFlag?: PartnerEditSource;
  className?: string;
  onSelect: (customer: MasterDataCustomerRow) => Promise<void> | void;
  onClear?: () => Promise<void> | void;
}

function normalizeCode(code: string | undefined): string {
  return String(code ?? "").trim();
}

function customerLabel(row: MasterDataCustomerRow): string {
  return String(row.NAME ?? "").trim() || String(row.SOLDTO ?? "").trim();
}

function customerMatchesFilter(row: MasterDataCustomerRow, filter: string): boolean {
  const q = filter.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    row.NAME,
    row.SOLDTO,
    row.ORT01,
    row.PSTLZ,
    row.STRAS,
    row.VAT_NR,
    row.LAND1,
  ]
    .map((v) => String(v ?? "").toLowerCase())
    .join(" ");
  return haystack.includes(q);
}

export function SoldtoNameSelectField({
  label,
  value,
  currentSoldtoCode,
  manuallyEdited,
  editFlag,
  className,
  onSelect,
  onClear,
}: SoldtoNameSelectFieldProps) {
  const [editing, setEditing] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);
  const filterRef = useFocusWithoutScroll<HTMLInputElement>(editing);
  const [filter, setFilter] = useState("");
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<MasterDataCustomerRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const searchQuery = filter.trim() || normalizeCode(currentSoldtoCode) || value.trim();

  const { data: options = [], isLoading } = useQuery({
    queryKey: ["md-customers-search", searchQuery],
    queryFn: async () => {
      const res = await api.searchCustomers(searchQuery, 200);
      return res.results;
    },
    enabled: editing,
    staleTime: 60_000,
  });

  const filteredOptions = useMemo(
    () =>
      options
        .filter((row) => customerMatchesFilter(row, filter))
        .sort((a, b) =>
          String(a.NAME ?? "").localeCompare(String(b.NAME ?? ""), "fr", { sensitivity: "base" }),
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
    const current = normalizeCode(currentSoldtoCode);
    if (!current) return;
    const match = options.find((row) => normalizeCode(row.SOLDTO) === current);
    if (match) setSelected(match);
  }, [editing, options, currentSoldtoCode]);

  useEffect(() => {
    if (!editing) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setEditing(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editing]);

  const applySelection = async (row: MasterDataCustomerRow) => {
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
    if (!onClear) return;
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

      <div ref={anchorRef} className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-medium">{value || "-"}</span>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setEditing(true);
          }}
          className="shrink-0 rounded p-1 opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100"
        >
          <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      <FloatingLookupPanel
        anchorRef={anchorRef}
        open={editing}
        onClose={() => setEditing(false)}
        minWidth={360}
      >
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Input
              ref={filterRef}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filtrer par nom, code sold-to, ville, TVA…"
              className="h-8 text-sm flex-1"
              disabled={saving}
            />
            {onClear && (value || currentSoldtoCode) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 text-xs text-rose-700 border-rose-300 hover:bg-rose-50 gap-1 px-2 shrink-0"
                onClick={handleClear}
                disabled={saving}
                title="Vider et réinitialiser le compte Sold-to"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Vider
              </Button>
            )}
          </div>
          <div className="max-h-52 overflow-y-auto rounded-md border bg-background">
            {isLoading ? (
              <LoadingState label="Chargement des clients…" className="py-3" />
            ) : filteredOptions.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                {options.length === 0
                  ? "Aucun client trouvé. Saisissez un filtre."
                  : "Aucun résultat pour ce filtre."}
              </p>
            ) : (
              <ul className="divide-y">
                {filteredOptions.map((row) => {
                  const code = normalizeCode(row.SOLDTO);
                  const isSelected = normalizeCode(selected?.SOLDTO) === code;
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
                        <p className="text-sm font-medium">{customerLabel(row)}</p>
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
      </FloatingLookupPanel>
    </div>
  );
}
