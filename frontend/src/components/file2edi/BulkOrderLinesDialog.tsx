import { useMemo, useState } from "react";
import { ClipboardPaste, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { parseBulkOrderLinesText } from "@/lib/parseBulkOrderLines";
import { cn } from "@/lib/utils";

interface BulkOrderLinesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImport: (lines: Array<{ boschArticle: string; quantity: number; unitPrice: number }>) => Promise<void>;
}

export function BulkOrderLinesDialog({ open, onOpenChange, onImport }: BulkOrderLinesDialogProps) {
  const [rawText, setRawText] = useState("");
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = useMemo(() => parseBulkOrderLinesText(rawText), [rawText]);
  const validLines = parsed.filter((row) => row.valid);
  const invalidCount = parsed.length - validLines.length;

  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setRawText(text);
      setError(null);
    } catch {
      setError("Impossible de lire le presse-papiers.");
    }
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
      setRawText("");
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import impossible");
    } finally {
      setImporting(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setRawText("");
      setError(null);
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Ajouter plusieurs lignes de commande
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <p className="text-sm text-muted-foreground">
            Collez depuis Excel ou saisissez vos lignes : <strong>Code article</strong>,{" "}
            <strong>Qté</strong>, <strong>P.U.</strong> (séparés par tabulation ou point-virgule).
          </p>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" className="gap-2" onClick={handlePasteFromClipboard}>
              <ClipboardPaste className="h-4 w-4" />
              Coller depuis le presse-papiers
            </Button>
          </div>

          <Textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder={"F6 925 210-249\t10\t12.50\nF6 925 210-250\t5\t8.00"}
            rows={6}
            className="font-mono text-xs"
          />

          {parsed.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm">
                <span className="font-medium text-emerald-700">{validLines.length} ligne{validLines.length > 1 ? "s" : ""} valide{validLines.length > 1 ? "s" : ""}</span>
                {invalidCount > 0 && (
                  <span className="text-amber-700"> · {invalidCount} ignorée{invalidCount > 1 ? "s" : ""}</span>
                )}
              </p>
              <div className="max-h-56 overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Code article</TableHead>
                      <TableHead className="w-16">Qté</TableHead>
                      <TableHead className="w-20">P.U.</TableHead>
                      <TableHead>Statut</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {parsed.map((row) => (
                      <TableRow key={row.rowIndex} className={cn(!row.valid && "bg-amber-50/80")}>
                        <TableCell className="text-xs text-muted-foreground">{row.rowIndex}</TableCell>
                        <TableCell className="font-mono text-xs">{row.boschArticle || "—"}</TableCell>
                        <TableCell className="text-xs">{Number.isFinite(row.quantity) ? row.quantity : "—"}</TableCell>
                        <TableCell className="text-xs">{Number.isFinite(row.unitPrice) ? row.unitPrice : "—"}</TableCell>
                        <TableCell className="text-xs">
                          {row.valid ? (
                            <span className="text-emerald-700">OK</span>
                          ) : (
                            <span className="text-amber-700">{row.error}</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
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
