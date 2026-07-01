import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Check, Pencil, Plus, Trash2 } from "lucide-react";
import type { OrderLine } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn, confidenceColor, formatCurrency } from "@/lib/utils";

interface EditableOrderLinesTableProps {
  lines: OrderLine[];
  currency?: string;
  onUpdateLine: (lineId: string, payload: Partial<OrderLine>) => Promise<void>;
  onDeleteLine: (lineId: string) => Promise<void>;
  onAddLine: () => void;
  onValidateLine: (lineId: string) => Promise<void>;
}

export function EditableOrderLinesTable({
  lines,
  currency = "EUR",
  onUpdateLine,
  onDeleteLine,
  onAddLine,
  onValidateLine,
}: EditableOrderLinesTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<OrderLine>>({});

  const startEdit = (line: OrderLine) => {
    setEditingId(line.lineId);
    setDraft({ ...line });
  };

  const saveEdit = async () => {
    if (!editingId) return;
    const qty = draft.quantity ?? 0;
    const price = draft.unitPrice ?? 0;
    await onUpdateLine(editingId, {
      ...draft,
      amount: qty * price,
      status: "Corrigé manuellement",
      manuallyEdited: true,
    });
    setEditingId(null);
  };

  const columns = useMemo<ColumnDef<OrderLine>[]>(
    () => [
      {
        accessorKey: "lineNumber",
        header: "Ligne",
        cell: ({ row }) => (
          <span className="font-mono text-xs">{row.original.lineNumber}</span>
        ),
      },
      {
        accessorKey: "customerReference",
        header: "Réf. client",
        cell: ({ row }) =>
          editingId === row.original.lineId ? (
            <Input
              value={draft.customerReference ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, customerReference: e.target.value }))
              }
              className="h-8 text-xs"
            />
          ) : (
            <span className="text-sm">{row.original.customerReference}</span>
          ),
      },
      {
        accessorKey: "boschArticle",
        header: "Article Bosch",
        cell: ({ row }) =>
          editingId === row.original.lineId ? (
            <Input
              value={draft.boschArticle ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, boschArticle: e.target.value }))
              }
              className="h-8 text-xs"
            />
          ) : (
            <span
              className={cn(
                "text-sm font-medium",
                row.original.status === "À vérifier" && "text-amber-600",
              )}
            >
              {row.original.boschArticle}
            </span>
          ),
      },
      {
        accessorKey: "designation",
        header: "Désignation",
        cell: ({ row }) =>
          editingId === row.original.lineId ? (
            <Input
              value={draft.designation ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, designation: e.target.value }))
              }
              className="h-8 text-xs"
            />
          ) : (
            <span className="text-sm text-muted-foreground max-w-[200px] truncate block">
              {row.original.designation}
            </span>
          ),
      },
      {
        accessorKey: "quantity",
        header: "Qté",
        cell: ({ row }) =>
          editingId === row.original.lineId ? (
            <Input
              type="number"
              value={draft.quantity ?? 0}
              onChange={(e) =>
                setDraft((d) => ({ ...d, quantity: Number(e.target.value) }))
              }
              className="h-8 w-16 text-xs"
            />
          ) : (
            <span>{row.original.quantity}</span>
          ),
      },
      {
        accessorKey: "unit",
        header: "UVC",
        cell: ({ row }) =>
          editingId === row.original.lineId ? (
            <Input
              value={draft.unit ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, unit: e.target.value }))}
              className="h-8 w-16 text-xs"
            />
          ) : (
            <span>{row.original.unit}</span>
          ),
      },
      {
        accessorKey: "unitPrice",
        header: "Prix",
        cell: ({ row }) =>
          editingId === row.original.lineId ? (
            <Input
              type="number"
              value={draft.unitPrice ?? 0}
              onChange={(e) =>
                setDraft((d) => ({ ...d, unitPrice: Number(e.target.value) }))
              }
              className="h-8 w-20 text-xs"
            />
          ) : (
            <span>{formatCurrency(row.original.unitPrice, currency)}</span>
          ),
      },
      {
        accessorKey: "amount",
        header: "Montant",
        cell: ({ row }) => (
          <span className="font-medium">
            {formatCurrency(row.original.amount, currency)}
          </span>
        ),
      },
      {
        accessorKey: "confidence",
        header: "Confiance",
        cell: ({ row }) => (
          <div className="flex items-center gap-2 min-w-[80px]">
            <span className={cn("text-xs font-medium", confidenceColor(row.original.confidence))}>
              {row.original.confidence}%
            </span>
            <Progress value={row.original.confidence} className="h-1.5 w-12" />
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Statut",
        cell: ({ row }) => {
          const s = row.original.status;
          const variant =
            s === "OK"
              ? "success"
              : s === "À vérifier"
                ? "warning"
                : s === "Corrigé manuellement"
                  ? "info"
                  : "destructive";
          return <Badge variant={variant}>{s}</Badge>;
        },
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            {editingId === row.original.lineId ? (
              <Button size="icon" variant="ghost" className="h-8 w-8" onClick={saveEdit}>
                <Check className="h-4 w-4 text-emerald-600" />
              </Button>
            ) : (
              <>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  onClick={() => startEdit(row.original)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  onClick={() => onValidateLine(row.original.lineId)}
                >
                  <Check className="h-4 w-4 text-emerald-600" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  onClick={() => onDeleteLine(row.original.lineId)}
                >
                  <Trash2 className="h-4 w-4 text-red-500" />
                </Button>
              </>
            )}
          </div>
        ),
      },
    ],
    [editingId, draft, currency, onDeleteLine, onValidateLine],
  );

  const table = useReactTable({
    data: lines,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((h) => (
                <TableHead key={h.id}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <TableCell key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Button variant="outline" size="sm" onClick={onAddLine} className="gap-2">
        <Plus className="h-4 w-4" />
        Ajouter une ligne de commande
      </Button>
    </div>
  );
}
