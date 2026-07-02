import { useEffect, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import type { OrderLine } from "@/types";
import { REVIEW_LINES_PAGE_SIZE, REVIEW_PANEL_BODY_MIN_HEIGHT } from "@/lib/reviewLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface OrderLinesEditPanelProps {
  lines: OrderLine[];
  onUpdateLine: (lineId: string, payload: Partial<OrderLine>) => Promise<void>;
  onDeleteLine: (lineId: string) => Promise<void>;
  onAddLine: () => void;
}

type LineDraft = {
  boschArticle: string;
  quantity: number;
  unitPrice: number;
};

export function OrderLinesEditPanel({
  lines,
  onUpdateLine,
  onDeleteLine,
  onAddLine,
}: OrderLinesEditPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, LineDraft>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const totalPages = Math.max(1, Math.ceil(lines.length / REVIEW_LINES_PAGE_SIZE));
  const pageStart = page * REVIEW_LINES_PAGE_SIZE;
  const pageLines = lines.slice(pageStart, pageStart + REVIEW_LINES_PAGE_SIZE);

  useEffect(() => {
    if (page > totalPages - 1) {
      setPage(Math.max(0, totalPages - 1));
    }
  }, [page, totalPages]);

  const getDraft = (line: OrderLine): LineDraft =>
    drafts[line.lineId] ?? {
      boschArticle: line.boschArticle,
      quantity: line.quantity,
      unitPrice: line.unitPrice,
    };

  const setDraftField = (line: OrderLine, patch: Partial<LineDraft>) => {
    setDrafts((prev) => ({
      ...prev,
      [line.lineId]: { ...getDraft(line), ...patch },
    }));
  };

  const saveLine = async (line: OrderLine) => {
    const draft = getDraft(line);
    setSavingId(line.lineId);
    try {
      await onUpdateLine(line.lineId, {
        boschArticle: draft.boschArticle,
        quantity: draft.quantity,
        unitPrice: draft.unitPrice,
        amount: draft.quantity * draft.unitPrice,
        status: "Corrigé manuellement",
        manuallyEdited: true,
      });
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[line.lineId];
        return next;
      });
    } finally {
      setSavingId(null);
    }
  };

  const isDirty = (line: OrderLine) => {
    const draft = getDraft(line);
    return (
      draft.boschArticle !== line.boschArticle ||
      draft.quantity !== line.quantity ||
      draft.unitPrice !== line.unitPrice
    );
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border"
        style={{ minHeight: REVIEW_PANEL_BODY_MIN_HEIGHT }}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-9 px-2">Ligne</TableHead>
              <TableHead>Code article</TableHead>
              <TableHead className="w-20">Qté</TableHead>
              <TableHead className="w-24">P.U.</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageLines.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center text-sm text-muted-foreground">
                  Aucune ligne sur cette page.
                </TableCell>
              </TableRow>
            ) : (
              pageLines.map((line) => {
                const draft = getDraft(line);
                const dirty = isDirty(line);
                return (
                  <TableRow key={line.lineId}>
                    <TableCell className="w-9 px-2">
                      <span className="font-mono text-xs">{line.lineNumber}</span>
                    </TableCell>
                    <TableCell>
                      <Input
                        value={draft.boschArticle}
                        onChange={(e) => setDraftField(line, { boschArticle: e.target.value })}
                        className="h-8 text-xs"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={0}
                        value={draft.quantity}
                        onChange={(e) =>
                          setDraftField(line, { quantity: Number(e.target.value) })
                        }
                        className="h-8 w-16 text-xs"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={0}
                        step={0.01}
                        value={draft.unitPrice}
                        onChange={(e) =>
                          setDraftField(line, { unitPrice: Number(e.target.value) })
                        }
                        className="h-8 w-20 text-xs"
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          disabled={!dirty || savingId === line.lineId}
                          onClick={() => saveLine(line)}
                        >
                          <Check className="h-4 w-4 text-emerald-600" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => onDeleteLine(line.lineId)}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {lines.length > REVIEW_LINES_PAGE_SIZE && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
            Précédent
          </Button>
          <span className="text-muted-foreground">
            Page {page + 1} / {totalPages}
            <span className="hidden sm:inline">
              {" "}
              · lignes {pageStart + 1}–{Math.min(pageStart + REVIEW_LINES_PAGE_SIZE, lines.length)} sur{" "}
              {lines.length}
            </span>
          </span>
          <Button
            variant="outline"
            size="sm"
            className="gap-1"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Suivant
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}

      <Button variant="outline" size="sm" onClick={onAddLine} className="gap-2 self-start">
        <Plus className="h-4 w-4" />
        Ajouter une ligne de commande
      </Button>
    </div>
  );
}
