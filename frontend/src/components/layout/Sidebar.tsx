import { NavLink, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useCurrentUser, hasAtLeastRole } from "@/hooks/useCurrentUser";
import type { AppRole } from "@/types";
import {
  Clock,
  Database,
  FileText,
  Home,
  LogOut,
  Settings,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUploadQueue } from "@/hooks/useUploadQueue";
import { useSidebar } from "./SidebarContext";

const navItems = [
  { to: "/", icon: Home, label: "Cockpit", minRole: "admin" as AppRole },
  { to: "/convertir", icon: Upload, label: "Déposer une commande", minRole: "adv" as AppRole },
  { to: "/revue", icon: FileText, label: "Gérer les commandes", badgeFromApi: true, minRole: "adv" as AppRole },
  { to: "/historique", icon: Clock, label: "Historique", minRole: "admin" as AppRole },
  { to: "/donnees-maitres", icon: Database, label: "Données maîtres", minRole: "admin" as AppRole },
  { to: "/parametres", icon: Settings, label: "Paramètres", minRole: "admin" as AppRole },
];

export function Sidebar() {
  const { data: me } = useCurrentUser();
  const { open, close } = useSidebar();
  if (me?.authenticated === false) {
    return null;
  }
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: queue } = useQuery({
    queryKey: ["dashboard", "review-queue"],
    queryFn: api.getReviewQueue,
    refetchInterval: 60_000,
  });
  const reviewCount = queue?.length ?? 0;
  const { activeCount } = useUploadQueue();
  const role = me?.role ?? "adv";
  const displayName = me?.displayName || me?.username || me?.actor || "Utilisateur";
  const visibleNavItems = navItems.filter((item) => hasAtLeastRole(role, item.minRole));
  const initials = displayName
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("") || "OP";
  const logoSrc = `${import.meta.env.BASE_URL}genie-commande.png`;
  const logoFallback = `${import.meta.env.BASE_URL}file.png`;

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      // ignore errors - clear state anyway
    }
    queryClient.clear();
    navigate("/login");
    window.location.assign("/login");
  }

  return (
    <>
      {/* Mobile overlay */}
      <button
        type="button"
        aria-label="Fermer le menu"
        className={cn(
          "fixed inset-0 z-40 bg-black/50 transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={close}
      />

      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-screen w-[min(260px,88vw)] flex-col bg-sidebar text-sidebar-foreground shadow-xl transition-transform duration-200 ease-out lg:w-[260px] lg:translate-x-0 lg:shadow-none",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        <div className="border-b border-sidebar-border px-6 py-5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-1 items-center justify-center lg:justify-center">
              <img
                src={logoSrc}
                alt="Genie Commande"
                className="h-12 w-auto max-w-[160px] object-contain sm:h-14 sm:max-w-[180px]"
                onError={(e) => {
                  const img = e.currentTarget;
                  if (!img.src.endsWith("file.png")) {
                    img.src = logoFallback;
                  }
                }}
              />
            </div>
            <button
              type="button"
              onClick={close}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-sidebar-border hover:text-white lg:hidden"
              aria-label="Fermer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {visibleNavItems.map(({ to, icon: Icon, label, badgeFromApi }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/" || to === "/revue"}
              onClick={close}
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
              <span className="flex-1 leading-snug">{label}</span>
              {to === "/convertir" && activeCount > 0 && (
                <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 text-xs font-bold text-white">
                  {activeCount}
                </span>
              )}
              {badgeFromApi && reviewCount > 0 && (
                <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-xs font-bold text-white">
                  {reviewCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-sidebar-border px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-white">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{displayName}</p>
            </div>
            <button
              onClick={handleLogout}
              title="Se déconnecter"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-500/20 hover:text-red-400"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
