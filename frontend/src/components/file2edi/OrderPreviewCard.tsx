import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface PreviewItem {
  icon: LucideIcon;
  label: string;
  value: string;
  iconColor?: string;
}

interface OrderPreviewCardProps {
  title: string;
  items: PreviewItem[];
  className?: string;
}

export function OrderPreviewCard({ title, items, className }: OrderPreviewCardProps) {
  return (
    <Card className={className}>
      <CardContent className="p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {items.map((item, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-lg border bg-slate-50/50 p-3"
            >
              <item.icon className={cn("h-4 w-4 mt-0.5 shrink-0", item.iconColor ?? "text-primary")} />
              <div className="min-w-0">
                <p className="text-[10px] text-muted-foreground">{item.label}</p>
                <p className="text-sm font-medium truncate">{item.value}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
