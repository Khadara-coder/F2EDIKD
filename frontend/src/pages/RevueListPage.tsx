import { useNavigate } from "react-router-dom";
import { FileIcon, Upload } from "lucide-react";
import { useDashboard, useOrdersList } from "@/hooks/useFile2Edi";
import { Header } from "@/components/layout/Header";
import { StatusBadge } from "@/components/file2edi/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { confidenceColor, formatDateTime } from "@/lib/utils";

export function RevueListPage() {
  const navigate = useNavigate();
  const { reviewQueue } = useDashboard();
  const ordersList = useOrdersList();
  const items = ordersList.data ?? [];
  const pendingCount = reviewQueue.data?.length ?? 0;

  return (
    <>
      <Header
        title="Revue"
        subtitle="Toutes les commandes converties — ouvrez un dossier pour valider ou corriger"
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            Commandes converties
            {pendingCount > 0 && (
              <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-600">
                {pendingCount} à revoir
              </span>
            )}
          </CardTitle>
          <Button variant="outline" className="gap-2" onClick={() => navigate("/convertir")}>
            <Upload className="h-4 w-4" />
            Convertir un PDF
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {ordersList.isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Chargement…</p>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center gap-4 p-12 text-center">
              <p className="text-muted-foreground">Aucune commande en attente de revue.</p>
              <Button onClick={() => navigate("/convertir")}>
                Importer un bon de commande PDF
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fichier</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Confiance</TableHead>
                  <TableHead>Problématique</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((row) => (
                  <TableRow
                    key={row.orderId}
                    className="cursor-pointer"
                    onClick={() => navigate(`/revue/${row.orderId}`)}
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileIcon className="h-4 w-4 text-red-500" />
                        <span className="max-w-[200px] truncate text-sm">{row.fileName}</span>
                      </div>
                    </TableCell>
                    <TableCell>{row.clientName}</TableCell>
                    <TableCell className={confidenceColor(row.confidence)}>
                      {row.confidence}%
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{row.issue}</TableCell>
                    <TableCell className="text-sm">{formatDateTime(row.date)}</TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/revue/${row.orderId}`);
                        }}
                      >
                        Ouvrir
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
