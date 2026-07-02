import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  sublabel?: string;
  icon?: LucideIcon;
  iconClassName?: string;
  valueClassName?: string;
  className?: string;
  compact?: boolean;
}

export function StatCard({
  label,
  value,
  sublabel,
  icon: Icon,
  iconClassName,
  valueClassName,
  className,
  compact = false,
}: StatCardProps) {
  return (
    <Card className={cn("border shadow-sm", className)}>
      <CardContent className={cn("flex items-start justify-between", compact ? "p-3" : "p-4")}>
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p
            className={cn(
              compact
                ? "truncate text-sm font-semibold leading-tight"
                : "text-2xl font-bold tracking-tight",
              valueClassName,
            )}
          >
            {value}
          </p>
          {sublabel && (
            <p className="text-xs text-muted-foreground">{sublabel}</p>
          )}
        </div>
        {Icon && (
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10",
              iconClassName,
            )}
          >
            <Icon className="h-5 w-5 text-primary" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
