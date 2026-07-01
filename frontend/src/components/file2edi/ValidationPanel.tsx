import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ValidationItem {
  label: string;
  status: "ok" | "warning" | "error";
  detail?: string;
}

interface ValidationPanelProps {
  items: ValidationItem[];
  className?: string;
}

const icons = {
  ok: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const colors = {
  ok: "text-emerald-600",
  warning: "text-amber-600",
  error: "text-red-600",
};

export function ValidationPanel({ items, className }: ValidationPanelProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">Validation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((item, i) => {
          const Icon = icons[item.status];
          return (
            <div key={i} className="flex items-start gap-2">
              <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", colors[item.status])} />
              <div>
                <p className="text-sm">{item.label}</p>
                {item.detail && (
                  <p className="text-xs text-muted-foreground">{item.detail}</p>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
