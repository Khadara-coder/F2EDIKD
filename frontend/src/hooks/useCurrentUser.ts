import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AppRole } from "@/types";

export const ROLE_RANK: Record<AppRole, number> = {
  readonly: 0,
  reviewer: 1,
  operator: 2,
  admin: 3,
};

export function useCurrentUser() {
  return useQuery({
    queryKey: ["currentUser"],
    queryFn: api.getCurrentUser,
    staleTime: 60_000,
    retry: 1,
  });
}

export function hasAtLeastRole(role: AppRole | undefined, minRole: AppRole): boolean {
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}
