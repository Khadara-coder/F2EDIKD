import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useCurrentUser, hasAtLeastRole } from "@/hooks/useCurrentUser";
import type { AppRole } from "@/types";
import {
  Clock,
  Database,
  FileText,
  Home,
  Settings,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const navItems = [
  { to: "/", icon: Home, label: "Cockpit", minRole: "admin" as AppRole },
  { to: "/convertir", icon: Upload, label: "Convertir", minRole: "adv" as AppRole },
  { to: "/revue", icon: FileText, label: "Revue", badgeFromApi: true, minRole: "adv" as AppRole },
  { to: "/historique", icon: Clock, label: "Historique", minRole: "adv" as AppRole },
  { to: "/donnees-maitres", icon: Database, label: "Données maîtres", minRole: "admin" as AppRole },
  { to: "/parametres", icon: Settings, label: "Paramètres", minRole: "admin" as AppRole },
];

export function Sidebar() {
  const { data: me } = useCurrentUser();
  const { data: queue } = useQuery({
    queryKey: ["dashboard", "review-queue"],
    queryFn: api.getReviewQueue,
    refetchInterval: 60_000,
  });
  const reviewCount = queue?.length ?? 0;
  const role = me?.role ?? "adv";
  const visibleNavItems = navItems.filter((item) => hasAtLeastRole(role, item.minRole));
  const initials = (me?.actor || "OP")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("") || "OP";

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-[260px] flex-col bg-sidebar text-sidebar-foreground">
      <div className="border-b border-sidebar-border px-6 py-5">
        <h1 className="text-lg font-bold tracking-tight text-white">File2EDI</h1>
        <p className="mt-0.5 text-xs text-slate-400">EDIFACT GENERATOR</p>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {visibleNavItems.map(({ to, icon: Icon, label, badgeFromApi }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/" || to === "/revue"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-white"
                  : "text-slate-300 hover:bg-sidebar-border hover:text-white",
              )
            }
          >
            <Icon className="h-5 w-5 shrink-0" />
            <span className="flex-1">{label}</span>
            {badgeFromApi && reviewCount > 0 && (
              <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-xs font-bold text-white">
                {reviewCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-sidebar-border px-4 py-4">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Profil EDI
        </p>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 text-amber-400 text-[10px]">
            ELM_STANDARD
          </Badge>
          <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 text-amber-400 text-[10px]">
            UNOC : 3
          </Badge>
          <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 text-amber-400 text-[10px]">
            D. 96A
          </Badge>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-white">
            {initials}
          </div>
          <div>
            <p className="text-sm font-medium text-white">{me?.actor || "adv"}</p>
            <p className="text-xs text-slate-400">{role.toUpperCase()} · File2EDI V2</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
