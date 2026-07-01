import { useNavigate } from "react-router-dom";
import {
  Calendar,
  CheckCircle,
  Copy,
  FileText,
  Sigma,
  Upload,
  UserCheck,
  XCircle,
} from "lucide-react";
import { useDashboard } from "@/hooks/useFile2Edi";
import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/file2edi/StatCard";
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
import { formatDateTime, confidenceColor } from "@/lib/utils";
import { Eye, Download, FileIcon } from "lucide-react";

export function CockpitPage() {
  const navigate = useNavigate();
  const { metrics, reviewQueue, recentConversions } = useDashboard();
  const m = metrics.data;

  const kpis = [
    { label: "Aujourd'hui", value: m?.today ?? "—", sub: "Commandes reçues", icon: Calendar },
    { label: "Générés", value: m?.generated ?? "—", sub: "EDIFACT générés", icon: FileText, iconCls: "bg-blue-500/10 [&_svg]:text-blue-600" },
    { label: "Revue requise", value: m?.reviewRequired ?? "—", sub: "En attente de validation", icon: UserCheck, iconCls: "bg-amber-500/10 [&_svg]:text-amber-600" },
    { label: "Rejetés", value: m?.rejected ?? "—", sub: "Échec de traitement", icon: XCircle, iconCls: "bg-red-500/10 [&_svg]:text-red-600" },
    { label: "Partiels", value: m?.partial ?? "—", sub: "Conversion partielle", icon: CheckCircle, iconCls: "bg-violet-500/10 [&_svg]:text-violet-600" },
    { label: "Doublons", value: m?.duplicates ?? "—", sub: "Fichiers dupliqués", icon: Copy },
    { label: "SFTP échoué", value: m?.sftpFailed ?? "—", sub: "Export en échec", icon: Upload },
    { label: "Total", value: m?.total ?? "—", sub: "Tous statuts confondus", icon: Sigma, iconCls: "bg-blue-500/10 [&_svg]:text-blue-600" },
  ];

  return (
    <>
      <Header
        title="Cockpit"
        subtitle="Vue d'ensemble des conversions du jour"
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-8">
        {kpis.map((k) => (
          <StatCard
            key={k.label}
            label={k.label}
            value={k.value}
            sublabel={k.sub}
            icon={k.icon}
            iconClassName={k.iconCls}
          />
        ))}
      </div>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">
              File d'attente — revue requise
              <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-600">
                {reviewQueue.data?.length ?? 0}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
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
                {reviewQueue.data?.map((row) => (
                  <TableRow
                    key={row.orderId}
                    className="cursor-pointer"
                    onClick={() => navigate(`/revue/${row.orderId}`)}
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileIcon className="h-4 w-4 text-red-500" />
                        <span className="max-w-[140px] truncate text-sm">{row.fileName}</span>
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
            <div className="border-t p-3">
              <Button variant="link" className="text-primary" onClick={() => navigate("/revue")}>
                Voir toutes les revues requises →
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Dernières conversions</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fichier</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentConversions.data?.map((row) => (
                  <TableRow key={row.conversionId}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileIcon className="h-4 w-4 text-red-500" />
                        <span className="max-w-[140px] truncate text-sm">{row.fileName}</span>
                      </div>
                    </TableCell>
                    <TableCell>{row.clientName}</TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell className="text-sm">{formatDateTime(row.date)}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate(`/revue/${row.orderId}`)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Download className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="border-t p-3">
              <Button variant="link" className="text-primary" onClick={() => navigate("/historique")}>
                Voir tout l'historique →
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Répartition des statuts (aujourd'hui)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {m?.statusDistribution.map((s) => (
              <div key={s.label} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span>{s.label}</span>
                  <span className="text-muted-foreground">
                    {s.count} ({s.percent}%)
                  </span>
                </div>
                <div className="h-2 rounded-full bg-slate-100">
                  <div
                    className={`h-2 rounded-full ${s.color}`}
                    style={{ width: `${s.percent}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Flux de traitement (aujourd'hui)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-slate-50 p-4">
              {[
                { label: "PDF reçus", value: m?.processingFlow.pdfReceived },
                { label: "EDIFACT générés", value: m?.processingFlow.edifactGenerated },
                { label: "Validations manuelles", value: m?.processingFlow.manualValidations },
                { label: "Exports SFTP", value: m?.processingFlow.sftpExports },
              ].map((step, i, arr) => (
                <div key={step.label} className="flex items-center gap-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold">{step.value}</p>
                    <p className="text-xs text-muted-foreground">{step.label}</p>
                  </div>
                  {i < arr.length - 1 && <span className="text-muted-foreground">→</span>}
                </div>
              ))}
            </div>
            <p className="mt-4 flex items-center gap-2 text-sm text-emerald-600">
              <CheckCircle className="h-4 w-4" />
              Aucune alerte critique. Le traitement se déroule normalement.
            </p>
            <Button variant="link" className="mt-2 text-primary p-0">
              Voir le monitoring SFTP →
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
