import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface EdifactPreviewPanelProps {
  content?: string;
  ready?: boolean;
}

export function EdifactPreviewPanel({ content, ready }: EdifactPreviewPanelProps) {
  const sample = content ?? `UNB+UNOC:3+4399901876613+3015981600108+250630:1042+CTRL001'
UNH+1+ORDERS:D:96A:UN'
BGM+220+026545008+9'
DTM+137:20260630:102'
NAD+BY+REXEL FRANCE::91'
NAD+DP+CHANTIER LYON PART-DIEU::91'
LIN+1++7736501437:IN'
QTY+21:2:PCE'
LIN+2++7736501444:IN'
QTY+21:1:PCE'
LIN+3++BGL25-550:IN'
QTY+21:3:PCE'
UNS+S'
CNT+2:5'
UNT+12+1'
UNZ+1+CTRL001'`;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Aperçu EDIFACT
          {ready && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
              Prêt
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <pre className="max-h-48 overflow-auto rounded-lg border bg-slate-950 p-4 font-mono text-xs text-emerald-400">
          {sample}
        </pre>
      </CardContent>
    </Card>
  );
}
