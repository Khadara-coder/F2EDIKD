import { useEffect, useMemo, useState } from "react";
import { ClipboardPaste, Plus, TableProperties, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  bulkRowsFromParsedText,
  createEmptyBulkOrderLineGrid,
  createEmptyBulkOrderLineRow,
  evaluateBulkOrderLineGrid,
  isBulkRowEmpty,
  type BulkOrderLineDraft,
} from "@/lib/parseBulkOrderLines";
import { cn } from "@/lib/utils";

interface BulkOrderLinesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImport: (lines: Array<{ boschArticle: string; quantity: number; unitPrice: number }>) => Promise<void>;
}

export function BulkOrderLinesDialog({ open, onOpenChange, onImport }: BulkOrderLinesDialogProps) {
  const [rows, setRows] = useState<BulkOrderLineDraft[]>(() => createEmptyBulkOrderLineGrid());
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { rowStatuses, validLines, invalidCount } = useMemo(
    () => evaluateBulkOrderLineGrid(rows),
    [rows],
  );
  const filledCount = rowStatuses.filter((_, index) => !isBulkRowEmpty(rows[index]!)).length;

  useEffect(() => {
    if (open) {
      setRows(createEmptyBulkOrderLineGrid());
      setError(null);
    }
  }, [open]);

  const updateRow = (id: string, patch: Partial<BulkOrderLineDraft>) => {
    setRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const addRow = () => {
    setRows((prev) => [...prev, createEmptyBulkOrderLineRow()]);
  };

  const removeRow = (id: string) => {
    setRows((prev) => {
      const next = prev.filter((row) => row.id !== id);
      return next.length > 0 ? next : [createEmptyBulkOrderLineRow()];
    });
  };

  const applyPastedText = (text: string) => {
    const pasted = bulkRowsFromParsedText(text);
    const hasExistingData = rows.some((row) => !isBulkRowEmpty(row));
    setRows(hasExistingData ? [...rows.filter((row) => !isBulkRowEmpty(row)), ...pasted] : pasted);
    setError(null);
  };

  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      applyPastedText(text);
    } catch {
      setError("Impossible de lire le presse-papiers.");
    }
  };

  const handleGridPaste = (event: React.ClipboardEvent<HTMLDivElement>) => {
    const text = event.clipboardData.getData("text/plain");
    if (!text.trim()) return;
    event.preventDefault();
    applyPastedText(text);
  };

  const handleImport = async () => {
    if (validLines.length === 0) return;
    setImporting(true);
    setError(null);
    try {
      await onImport(
        validLines.map((row) => ({
          boschArticle: row.boschArticle,
          quantity: row.quantity,
          unitPrice: row.unitPrice,
        })),
      );
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import impossible");
    } finally {
      setImporting(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setError(null);
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TableProperties className="h-5 w-5" />
            Ajouter plusieurs lignes de commande
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <p className="text-sm text-muted-foreground">
            Saisissez ou collez vos lignes : <strong>Code article</strong>, <strong>Qté</strong>,{" "}
            <strong>P.U.</strong> (Excel : tabulations · CSV : point-virgule ou virgule).
          </p>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" className="gap-2" onClick={handlePasteFromClipboard}>
              <ClipboardPaste className="h-4 w-4" />
              Coller depuis Excel
            </Button>
            <Button type="button" variant="outline" size="sm" className="gap-2" onClick={addRow}>
              <Plus className="h-4 w-4" />
              Ajouter une ligne
            </Button>
          </div>

          <div
            className="max-h-[min(420px,50vh)] overflow-auto rounded-md border"
            onPaste={handleGridPaste}
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10 px-2">#</TableHead>
                  <TableHead>Code article</TableHead>
                  <TableHead className="w-24">Qté</TableHead>
                  <TableHead className="w-28">P.U.</TableHead>
                  <TableHead className="w-40">Statut</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, index) => {
                  const status = rowStatuses[index];
                  const isInvalid = status && !isBulkRowEmpty(row) && !status.valid;
                  return (
                    <TableRow key={row.id} className={cn(isInvalid && "bg-amber-50/80")}>
                      <TableCell className="px-2 text-xs text-muted-foreground">{index + 1}</TableCell>
                      <TableCell>
                        <Input
                          value={row.boschArticle}
                          onChange={(e) => updateRow(row.id, { boschArticle: e.target.value })}
                          placeholder="F6 925 210-249"
                          className="h-8 font-mono text-xs"
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={row.quantity}
                          onChange={(e) => updateRow(row.id, { quantity: e.target.value })}
                          inputMode="decimal"
                          placeholder="10"
                          className="h-8 text-xs"
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={row.unitPrice}
                          onChange={(e) => updateRow(row.id, { unitPrice: e.target.value })}
                          inputMode="decimal"
                          placeholder="12,50"
                          className="h-8 text-xs"
                        />
                      </TableCell>
                      <TableCell className="text-xs">
                        {isBulkRowEmpty(row) ? (
                          <span className="text-muted-foreground">—</span>
                        ) : status?.valid ? (
                          <span className="text-emerald-700">OK</span>
                        ) : (
                          <span className="text-amber-700">{status?.error ?? "Invalide"}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => removeRow(row.id)}
                          aria-label="Supprimer la ligne"
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {filledCount > 0 && (
            <p className="text-sm">
              <span className="font-medium text-emerald-700">
                {validLines.length} ligne{validLines.length > 1 ? "s" : ""} prête{validLines.length > 1 ? "s" : ""} à importer
              </span>
              {invalidCount > 0 && (
                <span className="text-amber-700">
                  {" "}
                  · {invalidCount} à corriger
                </span>
              )}
            </p>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={importing}>
            Annuler
          </Button>
          <Button
            className="gap-2"
            onClick={handleImport}
            disabled={importing || validLines.length === 0}
          >
            {importing ? "Import…" : `Importer ${validLines.length} ligne${validLines.length > 1 ? "s" : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
