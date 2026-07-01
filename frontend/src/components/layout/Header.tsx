import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
}

function SystemBadges() {
  const { data } = useQuery({
    queryKey: ["systemHealth"],
    queryFn: api.getSystemHealth,
    refetchInterval: 30_000,
  });

  const badges = [
    {
      label: data?.api === "connected" ? "API OK" : "API X",
      ok: data?.api === "connected",
    },
    {
      label: "BDD OK",
      ok: data?.database === "connected",
    },
    {
      label: "CSV OK",
      ok: data?.csv === "connected",
    },
  ];

  return (
    <div className="flex items-center gap-2">
      {badges.map((b) => (
        <Badge
          key={b.label}
          variant="outline"
          className={cn(
            "text-xs font-medium",
            b.ok
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-red-200 bg-red-50 text-red-700",
          )}
        >
          {b.label}
        </Badge>
      ))}
    </div>
  );
}

export function Header({ title, subtitle, actions, breadcrumbs }: HeaderProps) {
  return (
    <header className="mb-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="mb-2 flex items-center gap-1.5 text-sm text-muted-foreground">
          {breadcrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <span>/</span>}
              {crumb.href ? (
                <a href={crumb.href} className="hover:text-foreground">
                  {crumb.label}
                </a>
              ) : (
                <span className="text-foreground">{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {actions}
          <SystemBadges />
        </div>
      </div>
    </header>
  );
}
