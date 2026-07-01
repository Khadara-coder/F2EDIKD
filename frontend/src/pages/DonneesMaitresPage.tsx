import { useState } from "react";
import { Building2, Database, Package, RefreshCw, Shield, Plus, Upload } from "lucide-react";
import { useMasterData } from "@/hooks/useFile2Edi";
import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/file2edi/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/utils";
import type { MasterDataClient } from "@/types";
import { X, ExternalLink } from "lucide-react";

export function DonneesMaitresPage() {
  const [tab, setTab] = useState("clients");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<MasterDataClient | null>(null);
  const { data } = useMasterData(tab, search);

  const summary = data?.summary;
  const clients = data?.clients ?? [];

  return (
    <>
      <Header
        title="Données maîtres"
        subtitle="Référentiels clients, partenaires et articles"
      />

      <Tabs value={tab} onValueChange={setTab}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <TabsList>
            <TabsTrigger value="clients" className="gap-2">
              <Building2 className="h-4 w-4" /> Clients
            </TabsTrigger>
            <TabsTrigger value="shipto">Ship-to</TabsTrigger>
            <TabsTrigger value="articles">Articles Bosch</TabsTrigger>
            <TabsTrigger value="rules">Règles de validation</TabsTrigger>
          </TabsList>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="gap-2">
              <Upload className="h-4 w-4" /> Importer CSV
            </Button>
            <Button size="sm" className="gap-2">
              <Plus className="h-4 w-4" /> Ajouter
            </Button>
            <Button variant="outline" size="sm" className="gap-2">
              <RefreshCw className="h-4 w-4" /> Synchroniser
            </Button>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-2 space-y-3">
            <StatCard label="Clients actifs" value={summary?.activeClients ?? "—"} sublabel={`+${summary?.monthlyGrowth.clients ?? 0} ce mois`} icon={Building2} />
            <StatCard label="Ship-to" value={summary?.shiptoCount.toLocaleString("fr-FR") ?? "—"} sublabel={`+${summary?.monthlyGrowth.shipto ?? 0} ce mois`} icon={Database} />
            <StatCard label="Articles" value={summary?.articlesCount.toLocaleString("fr-FR") ?? "—"} sublabel={`+${summary?.monthlyGrowth.articles ?? 0} ce mois`} icon={Package} />
            <StatCard label="Règles" value={summary?.rulesCount ?? "—"} sublabel={`+${summary?.monthlyGrowth.rules ?? 0} ce mois`} icon={Shield} />
            <p className="text-xs text-muted-foreground px-1">
              Dernière synchronisation
              <br />
              {formatDateTime(summary?.lastSync)}
            </p>
          </div>

          <div className="lg:col-span-7">
            <TabsContent value="clients" className="mt-0">
              <Card>
                <CardHeader className="flex flex-row items-center gap-4 space-y-0 pb-4">
                  <Input
                    placeholder="Rechercher un client…"
                    className="max-w-sm"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                  <Button variant="outline" size="sm">Filtres</Button>
                </CardHeader>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-8" />
                        <TableHead>ID client</TableHead>
                        <TableHead>Nom</TableHead>
                        <TableHead>Sold-to</TableHead>
                        <TableHead>TVA</TableHead>
                        <TableHead>Canal</TableHead>
                        <TableHead>Division</TableHead>
                        <TableHead>Statut</TableHead>
                        <TableHead>Dernière mise à jour</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {clients.map((c) => (
                        <TableRow
                          key={c.clientId}
                          className="cursor-pointer"
                          data-state={selected?.clientId === c.clientId ? "selected" : undefined}
                          onClick={() => setSelected(c)}
                        >
                          <TableCell>
                            <div className={`h-4 w-4 rounded-full border-2 ${selected?.clientId === c.clientId ? "border-primary bg-primary" : "border-muted"}`} />
                          </TableCell>
                          <TableCell className="font-mono text-xs">{c.clientId}</TableCell>
                          <TableCell className="font-medium">{c.name}</TableCell>
                          <TableCell>{c.soldto}</TableCell>
                          <TableCell className="text-xs">{c.vat}</TableCell>
                          <TableCell>{c.channel}</TableCell>
                          <TableCell>{c.division}</TableCell>
                          <TableCell>
                            <Badge variant={c.status === "Actif" ? "success" : "secondary"}>
                              {c.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm">{formatDateTime(c.updatedAt)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
          </div>

          <div className="lg:col-span-3">
            {selected ? (
              <Card>
                <CardHeader className="flex flex-row items-start justify-between space-y-0">
                  <div>
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Détail du client</p>
                    <CardTitle className="text-lg mt-1">{selected.name}</CardTitle>
                    <Badge variant="success" className="mt-2">{selected.status}</Badge>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => setSelected(null)}>
                    <X className="h-4 w-4" />
                  </Button>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {[
                    ["ID client", selected.clientId],
                    ["Sold-to", selected.soldto],
                    ["TVA", selected.vat],
                    ["Canal", selected.channel],
                    ["Division", selected.division],
                    ["Devise", selected.currency ?? "EUR"],
                    ["Pays", selected.country ?? "FR"],
                    ["GLN", selected.gln ?? "—"],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 border-b pb-2">
                      <span className="text-muted-foreground">{k}</span>
                      <span className="font-medium text-right">{v}</span>
                    </div>
                  ))}
                  <SeparatorLabel>Mappings EDI</SeparatorLabel>
                  {selected.ediMappings && Object.entries(selected.ediMappings).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 text-xs">
                      <span className="text-muted-foreground uppercase">{k}</span>
                      <span>{v}</span>
                    </div>
                  ))}
                  <Button variant="outline" className="w-full gap-2 mt-4">
                    Voir toutes les informations
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="flex h-64 items-center justify-center text-sm text-muted-foreground">
                  Sélectionnez un client
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </Tabs>
    </>
  );
}

function SeparatorLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="pt-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
      {children}
    </p>
  );
}
