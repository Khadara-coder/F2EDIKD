import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import { api } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSidebar } from "./SidebarContext";

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
}

function SystemBadges() {
  const { data: me } = useCurrentUser();
  const { data } = useQuery({
    queryKey: ["systemHealth"],
    queryFn: api.getSystemHealth,
    refetchInterval: 30_000,
    enabled: me?.role === "admin",
  });

  if (me?.role !== "admin") {
    return null;
  }

  const badges = [
    {
      key: "api",
      label: data?.api === "connected" ? "API OK" : "API X",
      ok: data?.api === "connected",
    },
    {
      key: "database",
      label: data?.database === "connected" ? "BDD OK" : "BDD X",
      ok: data?.database === "connected",
    },
    {
      key: "csv",
      label: data?.csv === "connected" ? "CSV OK" : "CSV X",
      ok: data?.csv === "connected",
    },
    {
      key: "sftp",
      label: data?.sftp === "connected" ? "SFTP OK" : "SFTP X",
      ok: data?.sftp === "connected",
    },
    {
      key: "ai",
      label: data?.ai === "connected" ? "IA OK" : "IA X",
      ok: data?.ai === "connected",
      title: data?.aiDetail
        ? `${data.aiProvider || "IA"} - ${data.aiDetail}`
        : "Statut de configuration IA",
    },
  ];

  return (
    <div className="flex max-w-full flex-wrap items-center gap-1.5 sm:gap-2">
      {badges.map((b) => (
        <Badge
          key={b.key}
          variant="outline"
          title={"title" in b ? b.title : undefined}
          className={cn(
            "text-[10px] font-medium sm:text-xs",
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
  const { toggle } = useSidebar();

  return (
    <header className="mb-4 sm:mb-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="mb-2 flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
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
      <div className="flex flex-col gap-3 sm:gap-4">
        <div className="flex items-start gap-3">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="mt-0.5 shrink-0 lg:hidden"
            onClick={toggle}
            aria-label="Ouvrir le menu"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">{title}</h1>
            {subtitle && (
              <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
          <SystemBadges />
        </div>
      </div>
    </header>
  );
}
